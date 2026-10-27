"""Command line interface. Works without the web UI, e.g. if a browser is unavailable."""
from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
from pathlib import Path

from . import __version__, samples
from .pipeline import STATUS_READY, run_project
from .project import ProjectError, Workspace
from .rules import RuleError, RuleSet

DEFAULT_WORKSPACE = Path.cwd() / "workspace"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="logsanitizer", description="LogSanitizer " + __version__)
    parser.add_argument("--workspace", type=Path, default=DEFAULT_WORKSPACE,
                        help="Arbeitsbereich für Projekte (Standard: ./workspace)")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("serve", help="Weboberfläche starten (nur 127.0.0.1)")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--no-browser", action="store_true", help="Browser nicht automatisch öffnen")

    p = sub.add_parser("sanitize", help="Dateien/Ordner einem Projekt hinzufügen und bereinigen")
    p.add_argument("--project", required=True, help="Projektname (wird bei Bedarf angelegt)")
    p.add_argument("paths", nargs="*", type=Path, help="Dateien oder Ordner")
    p.add_argument("-r", "--recursive", action="store_true", help="Ordner rekursiv einlesen")
    p.add_argument("--names", action="append", default=[], metavar="KATEGORIE=DATEI",
                   help="Namensliste importieren, z. B. Server=server.txt (mehrfach möglich)")

    p = sub.add_parser("projects", help="Projekte auflisten")

    p = sub.add_parser("export-rules", help="Regeln eines Projekts exportieren (ohne Namen/Mappings)")
    p.add_argument("--project", required=True)
    p.add_argument("file", type=Path)

    p = sub.add_parser("import-rules", help="Versionierte Regeldatei in ein Projekt importieren")
    p.add_argument("--project", required=True)
    p.add_argument("file", type=Path)

    p = sub.add_parser("export-mapping", help="VERTRAULICH: Zuordnungstabelle als CSV schreiben")
    p.add_argument("--project", required=True)
    p.add_argument("file", type=Path)

    p = sub.add_parser("samples", help="Synthetische Beispiel-Logs erzeugen")
    p.add_argument("target", type=Path)
    p.add_argument("--big-mb", type=int, default=0, help="Zusätzliche große Datei (MB)")

    sub.add_parser("selftest", help="Funktionstest mit synthetischen Daten (keine echten Logs)")

    args = parser.parse_args(argv)
    try:
        return _COMMANDS[args.command](args)
    except (ProjectError, RuleError, OSError) as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        return 2


def _serve(args: argparse.Namespace) -> int:
    from .server import serve

    return serve(Workspace(args.workspace), port=args.port, open_browser=not args.no_browser)


def _sanitize(args: argparse.Namespace) -> int:
    project = Workspace(args.workspace).open_or_create(args.project)
    if args.names:
        names = project.load_names()
        for spec in args.names:
            category, _, file = spec.partition("=")
            if not file:
                raise ProjectError(f"--names erwartet KATEGORIE=DATEI, nicht {spec!r}.")
            names.setdefault(category, []).extend(_read_name_list(Path(file)))
        project.save_names(names)
    if args.paths:
        added = project.add_sources(args.paths, recursive=args.recursive)
        print(f"{len(added)} Datei(en) hinzugefügt, {len(project.sources)} im Projekt.")
    report = run_project(project, progress=_print_progress)
    print()
    _print_report(project.runs_dir / report["run_id"], report)
    return 0 if report["status"] == STATUS_READY else 1


def _projects(args: argparse.Namespace) -> int:
    for project in Workspace(args.workspace).list_projects():
        print(f"{project.slug:30} {project.name} ({len(project.sources)} Dateien)")
    return 0


def _export_rules(args: argparse.Namespace) -> int:
    project = Workspace(args.workspace).open_or_create(args.project)
    project.load_rules().save(args.file)
    print(f"Regeln exportiert nach {args.file} (enthält keine Namenslisten oder Zuordnungen).")
    return 0


def _import_rules(args: argparse.Namespace) -> int:
    project = Workspace(args.workspace).open_or_create(args.project)
    project.save_rules(RuleSet.load(args.file))
    print("Regeln importiert.")
    return 0


def _export_mapping(args: argparse.Namespace) -> int:
    import csv

    project = Workspace(args.workspace).open_or_create(args.project)
    with open(args.file, "x", encoding="utf-8-sig", newline="") as fh:
        writer = csv.writer(fh, delimiter=";")
        writer.writerow(["Platzhalter", "Kategorie", "Original", "Lauf", "Erstellt"])
        for row in project.mapping().rows():
            writer.writerow([row["placeholder"], row["category"], row["original"],
                             row["run_id"], row["created"]])
    print(f"VERTRAULICH: Zuordnung geschrieben nach {args.file}. Nicht weitergeben.")
    return 0


def _samples(args: argparse.Namespace) -> int:
    files = samples.generate(args.target, big_mb=args.big_mb)
    print(f"{len(files)} Beispiel-Logs in {args.target / 'logs'}, "
          f"Namenslisten in {args.target / 'namenslisten'}.")
    return 0


def _selftest(_args: argparse.Namespace) -> int:
    """Generate samples, sanitize them and verify nothing sensitive is left."""
    with tempfile.TemporaryDirectory(prefix="logsanitizer-selftest-") as tmp:
        root = Path(tmp)
        samples.generate(root / "samples")
        source_dir = root / "samples" / "logs"
        names = {c: _read_name_list(root / "samples" / "namenslisten" / f"{c.lower()}.txt")
                 for c in samples.NAME_LISTS}
        before = {p: p.read_bytes() for p in source_dir.rglob("*") if p.is_file()}

        project = Workspace(root / "workspace").create("Selbsttest")
        project.save_names(names)
        project.add_sources([source_dir], recursive=True)
        report = run_project(project)
        output = project.runs_dir / report["run_id"] / "output"

        problems = []
        if report["status"] != STATUS_READY:
            problems.append(f"Laufstatus {report['status']}: {report['errors'] or report['checks']}")
        if any(p.read_bytes() != data for p, data in before.items()):
            problems.append("Quelldateien wurden verändert.")
        if output.exists():
            problems += _find_sensitive(output)
            problems += _check_consistency(output)
        else:
            problems.append("Kein Ausgabeordner erzeugt.")

    if problems:
        print("SELBSTTEST FEHLGESCHLAGEN")
        for problem in problems:
            print(" -", problem)
        return 1
    summary = report["summary"]
    print(f"Selbsttest bestanden: {summary['files']} Dateien, "
          f"{sum(summary['replacements'].values())} Ersetzungen, "
          f"{summary['new_mappings']} Platzhalter, keine Restfunde.")
    return 0


def _find_sensitive(output: Path) -> list[str]:
    problems = []
    pattern = re.compile(r"(?<![A-Za-z0-9])(?:" + "|".join(
        re.escape(v) for v in sorted(samples.SENSITIVE, key=len, reverse=True))
        + r")(?![A-Za-z0-9])", re.IGNORECASE)
    for path in sorted(output.rglob("*")):
        if path.is_file():
            text = _decode(path.read_bytes())
            for match in pattern.finditer(text):
                problems.append(f"{path.relative_to(output)}: {match.group()!r} nicht ersetzt")
    return problems


def _check_consistency(output: Path) -> list[str]:
    """The same server must have the same placeholder in different files."""
    syslog = (output / "logs" / "syslog.log").read_text(encoding="utf-8")
    jsonl = (output / "logs" / "events.jsonl").read_text(encoding="utf-8")
    hosts_syslog = set(re.findall(r"resolved (\[Server_\d+\])\.\[Domain_\d+\]", syslog))
    hosts_json = {json.loads(line)["host"].split(".")[0] for line in jsonl.splitlines()}
    if not hosts_json <= hosts_syslog:
        return [f"Uneinheitliche Platzhalter: {sorted(hosts_json)} vs. {sorted(hosts_syslog)}"]
    return []


def _decode(data: bytes) -> str:
    if data.startswith(b"\xff\xfe"):
        return data[2:].decode("utf-16-le")
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("cp1252")


def _read_name_list(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8-sig")
    return [line.strip() for line in text.splitlines()
            if line.strip() and not line.lstrip().startswith("#")]


def _print_progress(info: dict) -> None:
    if info.get("phase") == "done":
        return
    phases = {"scan": "Analyse", "write": "Schreiben", "validate": "Prüfung"}
    line = f"\r{info.get('percent', 0):5.1f} %  {phases.get(info.get('phase'), '')}: {info.get('file', '')}"
    print(line[:100].ljust(100), end="", flush=True)


def _print_report(run_dir: Path, report: dict) -> None:
    labels = {"ready": "FREIGABEFÄHIG (alle Pflichtprüfungen bestanden)",
              "blocked": "GESPERRT (Prüfungen nicht bestanden)",
              "failed": "FEHLGESCHLAGEN", "cancelled": "ABGEBROCHEN"}
    print(f"Lauf {report['run_id']}: {labels.get(report['status'], report['status'])}")
    for error in report["errors"]:
        print(f"  Fehler: {error}")
    for check in report["checks"]:
        print(f"  [{'ok' if check['passed'] else 'X '}] {check['name']}: {check['detail']}")
    for hit in report["residual_hits"][:20]:
        print(f"  Restfund {hit['file']}:{hit['line']} {hit['category']} ({hit['check']})")
    if report.get("summary"):
        print(f"  Ersetzungen: {report['summary']['replacements']}")
    if report["status"] == STATUS_READY:
        print(f"  Ausgabe: {run_dir / 'output'}")
    print(f"  Bericht (vertraulich): {run_dir / 'report.json'}")


_COMMANDS = {
    "serve": _serve,
    "sanitize": _sanitize,
    "projects": _projects,
    "export-rules": _export_rules,
    "import-rules": _import_rules,
    "export-mapping": _export_mapping,
    "samples": _samples,
    "selftest": _selftest,
}
