"""Project workspace layout.

<workspace>/projects/<slug>/
    project.json    name, sources, settings (no log contents)
    rules.json      versioned rule set (exportable)
    names.json      CONFIDENTIAL: known internal names per category
    mapping.sqlite  CONFIDENTIAL: original value -> placeholder
    runs/<run_id>/  report.json and output/ (only when all checks passed)
"""
from __future__ import annotations

import json
import os
import re
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .mapping import MappingStore
from .rules import CATEGORY_RE, RuleSet, default_ruleset

PROJECT_FORMAT = "logsanitizer.project"
PROJECT_VERSION = 1
FORMATS = ("auto", "text", "json", "jsonl")


class ProjectError(ValueError):
    pass


@dataclass
class Source:
    id: str
    path: str
    rel: str  # relative output path
    format: str = "auto"  # auto | text | json | jsonl
    encoding: str = "auto"
    size: int = 0


@dataclass
class Project:
    dir: Path
    name: str
    created: str
    sources: list[Source] = field(default_factory=list)

    @property
    def rules_path(self) -> Path:
        return self.dir / "rules.json"

    @property
    def names_path(self) -> Path:
        return self.dir / "names.json"

    @property
    def runs_dir(self) -> Path:
        return self.dir / "runs"

    @property
    def slug(self) -> str:
        return self.dir.name

    def mapping(self) -> MappingStore:
        return MappingStore(self.dir / "mapping.sqlite")

    def save(self) -> None:
        data = {"format": PROJECT_FORMAT, "version": PROJECT_VERSION, "name": self.name,
                "created": self.created, "sources": [asdict(s) for s in self.sources]}
        _write_json(self.dir / "project.json", data)

    def load_rules(self) -> RuleSet:
        return RuleSet.load(self.rules_path)

    def save_rules(self, ruleset: RuleSet) -> None:
        ruleset.save(self.rules_path)

    def load_names(self) -> dict[str, list[str]]:
        if not self.names_path.exists():
            return {}
        return json.loads(self.names_path.read_text(encoding="utf-8"))

    def save_names(self, names: dict[str, list[str]]) -> None:
        for category in names:
            if not CATEGORY_RE.match(category):
                raise ProjectError(f"Ungültige Kategorie {category!r}.")
        cleaned = {c: sorted({v.strip() for v in values if v.strip()}, key=str.casefold)
                   for c, values in names.items()}
        _write_json(self.names_path, {c: v for c, v in sorted(cleaned.items()) if v})

    def add_sources(self, paths: list[Path], recursive: bool = False) -> list[Source]:
        """Register files (or folders) as read-only inputs; returns the added sources."""
        known = {s.path for s in self.sources}
        used = {s.rel.casefold() for s in self.sources}
        added: list[Source] = []
        for path in paths:
            path = Path(path).resolve()
            if not path.exists():
                raise ProjectError(f"Pfad nicht gefunden: {path}")
            if _is_relative_to(path, self.dir) or _is_relative_to(self.dir, path):
                raise ProjectError("Der Projektordner kann nicht als Quelle verwendet werden.")
            if path.is_dir():
                pattern = "**/*" if recursive else "*"
                files = sorted(p for p in path.glob(pattern) if p.is_file())
                pairs = [(f, Path(path.name) / f.relative_to(path)) for f in files]
            else:
                pairs = [(path, Path(path.name))]
            for file, rel in pairs:
                if str(file) in known:
                    continue
                rel_text = _unique_rel(rel.as_posix(), used)
                used.add(rel_text.casefold())
                known.add(str(file))
                source = Source(id=uuid.uuid4().hex[:12], path=str(file), rel=rel_text,
                                size=file.stat().st_size)
                self.sources.append(source)
                added.append(source)
        self.save()
        return added

    def remove_source(self, source_id: str) -> None:
        self.sources = [s for s in self.sources if s.id != source_id]
        self.save()

    def update_source(self, source_id: str, fmt: str | None = None,
                      encoding: str | None = None) -> Source:
        for source in self.sources:
            if source.id == source_id:
                if fmt is not None:
                    if fmt not in FORMATS:
                        raise ProjectError(f"Unbekanntes Format {fmt!r}.")
                    source.format = fmt
                if encoding is not None:
                    source.encoding = encoding
                self.save()
                return source
        raise ProjectError("Quelle nicht gefunden.")

    def runs(self) -> list[dict]:
        if not self.runs_dir.exists():
            return []
        reports = []
        for report in sorted(self.runs_dir.glob("*/report.json"), reverse=True):
            data = json.loads(report.read_text(encoding="utf-8"))
            reports.append({k: data.get(k) for k in
                            ("run_id", "status", "started", "finished", "summary")})
        return reports


class Workspace:
    def __init__(self, root: Path):
        self.root = Path(root).resolve()
        self.projects_dir = self.root / "projects"
        self.projects_dir.mkdir(parents=True, exist_ok=True)

    def list_projects(self) -> list[Project]:
        projects = []
        for path in sorted(self.projects_dir.iterdir()):
            if (path / "project.json").exists():
                projects.append(self.open(path.name))
        return projects

    def create(self, name: str) -> Project:
        name = name.strip()
        if not name or len(name) > 80:
            raise ProjectError("Projektname muss 1 bis 80 Zeichen lang sein.")
        slug = _slugify(name)
        directory = self.projects_dir / slug
        if directory.exists():
            raise ProjectError(f"Projekt {name!r} existiert bereits.")
        directory.mkdir(parents=True)
        project = Project(dir=directory, name=name,
                          created=datetime.now(timezone.utc).isoformat(timespec="seconds"))
        project.save()
        project.save_rules(default_ruleset())
        project.save_names({})
        project.mapping()
        return project

    def open(self, slug: str) -> Project:
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,79}", slug):
            raise ProjectError("Ungültige Projektkennung.")
        path = self.projects_dir / slug / "project.json"
        if not path.exists():
            raise ProjectError(f"Projekt {slug!r} nicht gefunden.")
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("format") != PROJECT_FORMAT:
            raise ProjectError("Keine LogSanitizer-Projektdatei.")
        return Project(dir=path.parent, name=data["name"], created=data["created"],
                       sources=[Source(**s) for s in data.get("sources", [])])

    def open_or_create(self, name: str) -> Project:
        slug = _slugify(name)
        if (self.projects_dir / slug / "project.json").exists():
            return self.open(slug)
        return self.create(name)


def _slugify(name: str) -> str:
    table = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"})
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower().translate(table)).strip("-")
    return slug[:80] or "projekt"


def _unique_rel(rel: str, used: set[str]) -> str:
    if rel.casefold() not in used:
        return rel
    stem, dot, suffix = rel.rpartition(".")
    if not dot or "/" in suffix:
        stem, suffix = rel, ""
    counter = 2
    while True:
        candidate = f"{stem}_{counter}" + (f".{suffix}" if suffix else "")
        if candidate.casefold() not in used:
            return candidate
        counter += 1


def _is_relative_to(path: Path, other: Path) -> bool:
    try:
        path.resolve().relative_to(other.resolve())
        return True
    except ValueError:
        return False


def _write_json(path: Path, data: object) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, path)
