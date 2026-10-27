"""Local web server: JSON API under /api plus the bundled frontend.

Safety measures:
- binds to 127.0.0.1 only;
- every API call needs the random session token from the start URL
  (header ``X-Session-Token``), so other web pages or local users cannot use it;
- the Host header must name the loopback address (DNS-rebinding protection);
- no CORS headers are sent.
"""
from __future__ import annotations

import json
import os
import re
import secrets
import string
import subprocess
import sys
import threading
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from . import __version__
from .engine import Detector, replace
from .pipeline import STATUS_RUNNING, Run
from .project import FORMATS, Project, ProjectError, Workspace
from .rules import RuleError, RuleSet, check_regex_performance, default_ruleset

HOST = "127.0.0.1"
MAX_BODY = 5 * 1024 * 1024
STATIC_DIR = Path(os.environ.get("LOGSANITIZER_STATIC")
                  or Path(__file__).resolve().parents[3] / "frontend" / "dist")
CONTENT_TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
                 ".css": "text/css; charset=utf-8", ".svg": "image/svg+xml",
                 ".json": "application/json", ".png": "image/png", ".ico": "image/x-icon",
                 ".woff2": "font/woff2"}


class ApiError(Exception):
    def __init__(self, status: HTTPStatus, message: str):
        super().__init__(message)
        self.status = status


class App:
    """Request routing and run management, independent of the HTTP plumbing."""

    def __init__(self, workspace: Workspace, token: str):
        self.workspace = workspace
        self.token = token
        self._runs: dict[str, dict] = {}  # project slug -> active/last run
        self._lock = threading.Lock()
        self.routes = [
            ("GET", r"/api/health", self.health),
            ("GET", r"/api/projects", self.list_projects),
            ("POST", r"/api/projects", self.create_project),
            ("GET", r"/api/projects/(?P<slug>[^/]+)", self.get_project),
            ("POST", r"/api/projects/(?P<slug>[^/]+)/sources", self.add_sources),
            ("PATCH", r"/api/projects/(?P<slug>[^/]+)/sources/(?P<sid>[^/]+)", self.update_source),
            ("DELETE", r"/api/projects/(?P<slug>[^/]+)/sources/(?P<sid>[^/]+)", self.remove_source),
            ("GET", r"/api/projects/(?P<slug>[^/]+)/rules", self.get_rules),
            ("PUT", r"/api/projects/(?P<slug>[^/]+)/rules", self.put_rules),
            ("POST", r"/api/projects/(?P<slug>[^/]+)/rules/reset", self.reset_rules),
            ("GET", r"/api/projects/(?P<slug>[^/]+)/names", self.get_names),
            ("PUT", r"/api/projects/(?P<slug>[^/]+)/names", self.put_names),
            ("POST", r"/api/projects/(?P<slug>[^/]+)/preview", self.preview),
            ("GET", r"/api/projects/(?P<slug>[^/]+)/mapping", self.get_mapping),
            ("GET", r"/api/projects/(?P<slug>[^/]+)/runs", self.list_runs),
            ("POST", r"/api/projects/(?P<slug>[^/]+)/runs", self.start_run),
            ("GET", r"/api/projects/(?P<slug>[^/]+)/runs/(?P<rid>[^/]+)", self.get_run),
            ("POST", r"/api/projects/(?P<slug>[^/]+)/runs/(?P<rid>[^/]+)/cancel", self.cancel_run),
            ("POST", r"/api/projects/(?P<slug>[^/]+)/runs/(?P<rid>[^/]+)/open", self.open_run),
            ("GET", r"/api/fs", self.browse),
        ]

    def dispatch(self, method: str, path: str, query: dict, body: dict | None) -> object:
        for route_method, pattern, handler in self.routes:
            match = re.fullmatch(pattern, path)
            if match and route_method == method:
                return handler(query=query, body=body or {}, **match.groupdict())
        raise ApiError(HTTPStatus.NOT_FOUND, "Unbekannter API-Pfad.")

    # -- projects ---------------------------------------------------------------

    def health(self, **_: object) -> dict:
        return {"status": "ok", "application": "LogSanitizer", "version": __version__}

    def list_projects(self, **_: object) -> list[dict]:
        return [{"slug": p.slug, "name": p.name, "created": p.created,
                 "sources": len(p.sources)} for p in self.workspace.list_projects()]

    def create_project(self, body: dict, **_: object) -> dict:
        return self._project_info(self.workspace.create(str(body.get("name", ""))))

    def get_project(self, slug: str, **_: object) -> dict:
        return self._project_info(self._project(slug))

    def _project_info(self, project: Project) -> dict:
        return {"slug": project.slug, "name": project.name, "created": project.created,
                "dir": str(project.dir), "formats": FORMATS,
                "sources": [vars(s) | {"exists": Path(s.path).is_file()} for s in project.sources],
                "names": {c: len(v) for c, v in project.load_names().items()},
                "mapping": project.mapping().counts(),
                "active_run": self._active_run_id(project.slug)}

    def add_sources(self, slug: str, body: dict, **_: object) -> dict:
        project = self._project(slug)
        paths = [Path(p) for p in body.get("paths", []) if str(p).strip()]
        if not paths:
            raise ApiError(HTTPStatus.BAD_REQUEST, "Keine Pfade angegeben.")
        added = project.add_sources(paths, recursive=bool(body.get("recursive")))
        return {"added": len(added), "project": self._project_info(project)}

    def update_source(self, slug: str, sid: str, body: dict, **_: object) -> dict:
        project = self._project(slug)
        project.update_source(sid, fmt=body.get("format"), encoding=body.get("encoding"))
        return self._project_info(project)

    def remove_source(self, slug: str, sid: str, **_: object) -> dict:
        project = self._project(slug)
        project.remove_source(sid)
        return self._project_info(project)

    # -- rules and names --------------------------------------------------------

    def get_rules(self, slug: str, **_: object) -> dict:
        return self._project(slug).load_rules().to_dict()

    def put_rules(self, slug: str, body: dict, **_: object) -> dict:
        project = self._project(slug)
        ruleset = RuleSet.from_dict(body)
        previous = {(r.id, r.pattern) for r in project.load_rules().rules}
        for rule in ruleset.rules:
            if (rule.id, rule.pattern) not in previous and not check_regex_performance(
                    rule, ruleset.tlds):
                raise ApiError(HTTPStatus.BAD_REQUEST,
                               f"Regel {rule.id!r} ist zu langsam (mögliches katastrophales "
                               "Backtracking). Bitte Muster vereinfachen.")
        project.save_rules(ruleset)
        return ruleset.to_dict()

    def reset_rules(self, slug: str, **_: object) -> dict:
        project = self._project(slug)
        project.save_rules(default_ruleset())
        return project.load_rules().to_dict()

    def get_names(self, slug: str, **_: object) -> dict:
        return self._project(slug).load_names()

    def put_names(self, slug: str, body: dict, **_: object) -> dict:
        project = self._project(slug)
        names = {str(c): [str(v) for v in values] for c, values in body.items()
                 if isinstance(values, list)}
        project.save_names(names)
        return project.load_names()

    def preview(self, slug: str, body: dict, **_: object) -> dict:
        """Sanitize a text sample without changing the project mapping."""
        project = self._project(slug)
        ruleset = RuleSet.from_dict(body["rules"]) if body.get("rules") else project.load_rules()
        text = str(body.get("text", ""))[:200_000]
        mapping = project.mapping().load()
        detector = Detector(ruleset, project.load_names(), learned=list(mapping))
        hits = detector.find(text)
        output, _ = replace(text, hits,
                            lambda c, v: mapping.get((c, v), f"[{c}_neu]"))
        return {"output": output,
                "hits": [{"start": h.start, "end": h.end, "category": h.category,
                          "text": text[h.start:h.end], "rule": h.rule_id, "allowed": h.allowed,
                          "known": (h.category, h.value) in mapping} for h in hits]}

    def get_mapping(self, slug: str, **_: object) -> list[dict]:
        return self._project(slug).mapping().rows()

    # -- runs -------------------------------------------------------------------

    def list_runs(self, slug: str, **_: object) -> list[dict]:
        return self._project(slug).runs()

    def start_run(self, slug: str, **_: object) -> dict:
        project = self._project(slug)
        with self._lock:
            if self._active_run_id(slug):
                raise ApiError(HTTPStatus.CONFLICT, "Für dieses Projekt läuft bereits ein Lauf.")
            state: dict = {"progress": {"phase": "start", "percent": 0}}
            cancel = threading.Event()
            run = Run(project, cancel=cancel, progress=lambda info: state.update(progress=info))
            state.update(run=run, cancel=cancel,
                         thread=threading.Thread(target=run.execute, daemon=True))
            self._runs[slug] = state
            state["thread"].start()
        return {"run_id": run.run_id}

    def get_run(self, slug: str, rid: str, **_: object) -> dict:
        state = self._runs.get(slug)
        if state and state["run"].run_id == rid and state["run"].report["status"] == STATUS_RUNNING:
            return state["run"].report | {"progress": state["progress"]}
        path = self._run_dir(slug, rid) / "report.json"
        if not path.exists():
            raise ApiError(HTTPStatus.NOT_FOUND, "Lauf nicht gefunden.")
        return json.loads(path.read_text(encoding="utf-8"))

    def cancel_run(self, slug: str, rid: str, **_: object) -> dict:
        state = self._runs.get(slug)
        if not state or state["run"].run_id != rid:
            raise ApiError(HTTPStatus.NOT_FOUND, "Lauf ist nicht aktiv.")
        state["cancel"].set()
        return {"cancelling": True}

    def open_run(self, slug: str, rid: str, **_: object) -> dict:
        run_dir = self._run_dir(slug, rid)
        target = next((run_dir / n for n in ("output", "output.blocked")
                       if (run_dir / n).is_dir()), run_dir)
        _open_in_file_manager(target)
        return {"opened": str(target)}

    def _active_run_id(self, slug: str) -> str | None:
        state = self._runs.get(slug)
        if state and state["thread"].is_alive():
            return state["run"].run_id
        return None

    def _run_dir(self, slug: str, rid: str) -> Path:
        if not re.fullmatch(r"[0-9]{8}-[0-9]{6}-[0-9a-f]{4}", rid):
            raise ApiError(HTTPStatus.BAD_REQUEST, "Ungültige Lauf-ID.")
        return self._project(slug).runs_dir / rid

    # -- file system browser ----------------------------------------------------

    def browse(self, query: dict, **_: object) -> dict:
        raw = (query.get("path") or [""])[0]
        if not raw:
            return {"path": "", "parent": None, "entries": [
                {"name": str(p), "path": str(p), "dir": True, "size": None} for p in _roots()]}
        path = Path(raw).expanduser().resolve()
        if not path.is_dir():
            raise ApiError(HTTPStatus.BAD_REQUEST, "Ordner nicht gefunden.")
        entries = []
        try:
            children = list(path.iterdir())
        except OSError as exc:
            raise ApiError(HTTPStatus.FORBIDDEN, f"Kein Zugriff: {exc.strerror}") from exc
        for child in children:
            try:
                is_dir = child.is_dir()
                size = None if is_dir else child.stat().st_size
            except OSError:
                continue
            entries.append({"name": child.name, "path": str(child), "dir": is_dir, "size": size})
        entries.sort(key=lambda e: (not e["dir"], e["name"].casefold()))
        parent = str(path.parent) if path.parent != path else ""
        return {"path": str(path), "parent": parent, "entries": entries}

    def _project(self, slug: str) -> Project:
        try:
            return self.workspace.open(slug)
        except ProjectError as exc:
            raise ApiError(HTTPStatus.NOT_FOUND, str(exc)) from exc


def _roots() -> list[Path]:
    roots = [Path.home()]
    if sys.platform == "win32":
        roots += [Path(f"{d}:\\") for d in string.ascii_uppercase if Path(f"{d}:\\").exists()]
    else:
        roots.append(Path("/"))
    return roots


def _open_in_file_manager(path: Path) -> None:
    if sys.platform == "win32":
        os.startfile(path)
    else:
        opener = "open" if sys.platform == "darwin" else "xdg-open"
        subprocess.Popen([opener, str(path)], stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL)


class Handler(BaseHTTPRequestHandler):
    app: App
    port: int
    server_version = "LogSanitizer"
    sys_version = ""

    def do_GET(self) -> None:
        self._handle("GET")

    def do_POST(self) -> None:
        self._handle("POST")

    def do_PUT(self) -> None:
        self._handle("PUT")

    def do_PATCH(self) -> None:
        self._handle("PATCH")

    def do_DELETE(self) -> None:
        self._handle("DELETE")

    def _handle(self, method: str) -> None:
        if self.headers.get("Host") not in (f"{HOST}:{self.port}", f"localhost:{self.port}"):
            self._send_json(HTTPStatus.MISDIRECTED_REQUEST, {"error": "Ungültiger Host."})
            return
        url = urlsplit(self.path)
        if not url.path.startswith("/api/"):
            if method == "GET":
                self._send_static(url.path)
            else:
                self._send_json(HTTPStatus.METHOD_NOT_ALLOWED, {"error": "Nicht erlaubt."})
            return
        if not secrets.compare_digest(self.headers.get("X-Session-Token", ""), self.app.token):
            self._send_json(HTTPStatus.UNAUTHORIZED, {
                "error": "Sitzung ungültig. Bitte LogSanitizer über den Startlink neu öffnen."})
            return
        try:
            body = self._read_body() if method in ("POST", "PUT", "PATCH") else None
            result = self.app.dispatch(method, url.path, parse_qs(url.query), body)
            self._send_json(HTTPStatus.OK, result)
        except ApiError as exc:
            self._send_json(exc.status, {"error": str(exc)})
        except (ProjectError, RuleError, ValueError, KeyError, OSError) as exc:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})

    def _read_body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY:
            raise ApiError(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "Anfrage zu groß.")
        if not length:
            return {}
        if not (self.headers.get("Content-Type") or "").startswith("application/json"):
            raise ApiError(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, "JSON erwartet.")
        data = json.loads(self.rfile.read(length).decode("utf-8"))
        if not isinstance(data, dict):
            raise ApiError(HTTPStatus.BAD_REQUEST, "JSON-Objekt erwartet.")
        return data

    def _send_json(self, status: HTTPStatus, data: object) -> None:
        payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self._security_headers()
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _send_static(self, path: str) -> None:
        root = STATIC_DIR.resolve()
        target = (root / path.lstrip("/")).resolve()
        if not target.is_relative_to(root) or not target.is_file():
            target = root / "index.html"  # single-page app fallback
        if not target.is_file():
            self._send_json(HTTPStatus.NOT_FOUND, {
                "error": f"Oberfläche nicht gefunden ({root}). Frontend bauen oder Release-Paket nutzen."})
            return
        payload = target.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", CONTENT_TYPES.get(target.suffix, "application/octet-stream"))
        self.send_header("Cache-Control", "no-cache")
        self._security_headers()
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _security_headers(self) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy",
                         "default-src 'self'; style-src 'self' 'unsafe-inline'; "
                         "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'")

    def log_message(self, format: str, *args: object) -> None:
        pass  # no request logging: URLs may contain local paths


def make_server(workspace: Workspace, port: int, token: str | None = None
                ) -> tuple[ThreadingHTTPServer, App]:
    app = App(workspace, token or secrets.token_urlsafe(24))
    last_error: OSError | None = None
    for candidate in range(port, port + 20) if port else [0]:
        handler = type("BoundHandler", (Handler,), {"app": app, "port": candidate})
        try:
            server = ThreadingHTTPServer((HOST, candidate), handler)
        except OSError as exc:
            last_error = exc
            continue
        handler.port = server.server_address[1]  # actual port if 0 was requested
        server.daemon_threads = True
        return server, app
    raise OSError(f"Kein freier Port ab {port}: {last_error}")


def serve(workspace: Workspace, port: int = 8765, open_browser: bool = True) -> int:
    server, app = make_server(workspace, port)
    url = f"http://{HOST}:{server.server_address[1]}/#token={app.token}"
    print("LogSanitizer läuft lokal (nur dieser Rechner).")
    print(f"Arbeitsbereich: {workspace.root}")
    print(f"Im Browser öffnen: {url}")
    print("Beenden mit Strg+C oder durch Schließen dieses Fensters.", flush=True)
    if open_browser:
        threading.Timer(0.5, webbrowser.open, args=(url,)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0
