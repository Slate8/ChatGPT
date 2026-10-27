"""A sanitization run: scan -> assign placeholders -> write -> validate.

Phase 1 reads every source and collects all sensitive values. New values are
numbered in sorted order, so placeholders do not depend on file order. Phase 2
writes the sanitized copies into ``output.partial``. Phase 3 re-checks the output.

Fail-closed: only a run where every check passed gets an ``output`` folder.
Failed or cancelled runs leave no output; runs with residual findings keep their
output as ``output.blocked`` for inspection, marked as not releasable.
"""
from __future__ import annotations

import json
import os
import shutil
import threading
import uuid
from collections import Counter
from collections.abc import Callable, Iterator
from datetime import datetime, timezone
from pathlib import Path

from .blocks import Executor, worker_count
from .formats import (
    FileEncoding,
    FormatError,
    create_text,
    detect_encoding,
    detect_format,
    iter_blocks,
    open_text,
    parse_encoding,
)
from .project import Project, Source
from .validate import MAX_HITS_PER_FILE

STATUS_READY = "ready"  # all mandatory checks passed
STATUS_BLOCKED = "blocked"  # finished, but checks found problems
STATUS_FAILED = "failed"
STATUS_CANCELLED = "cancelled"
STATUS_RUNNING = "running"

BLOCKED_NOTICE = (
    "NICHT FREIGEGEBEN\n\n"
    "Dieser Lauf hat Pflichtprüfungen nicht bestanden. Die Dateien in diesem Ordner\n"
    "dürfen nicht weitergegeben werden. Details stehen in report.json im Laufordner.\n"
)

ProgressCallback = Callable[[dict], None]


class RunCancelled(Exception):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Run:
    def __init__(self, project: Project, cancel: threading.Event | None = None,
                 progress: ProgressCallback | None = None):
        self.project = project
        self.cancel = cancel or threading.Event()
        self.progress = progress or (lambda _info: None)
        self.run_id = datetime.now().strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:4]
        self.dir = project.runs_dir / self.run_id
        self.partial = self.dir / "output.partial"
        self.report: dict = {"run_id": self.run_id, "project": project.name,
                             "status": STATUS_RUNNING, "started": _now(), "finished": None,
                             "files": [], "checks": [], "residual_hits": [], "errors": []}
        self._bytes_total = 0
        self._bytes_done = 0

    # -- public -----------------------------------------------------------------

    def execute(self) -> dict:
        self.dir.mkdir(parents=True)
        self._save_report()
        try:
            self._execute()
        except RunCancelled:
            self.report["status"] = STATUS_CANCELLED
            shutil.rmtree(self.partial, ignore_errors=True)
        except (FormatError, OSError, KeyError, ValueError) as exc:
            self.report["status"] = STATUS_FAILED
            self.report["errors"].append(_describe(exc))
            shutil.rmtree(self.partial, ignore_errors=True)
        self.report["finished"] = _now()
        self._save_report()
        self.progress({"phase": "done", "status": self.report["status"], "percent": 100})
        return self.report

    # -- phases -----------------------------------------------------------------

    def _execute(self) -> None:
        project = self.project
        if not project.sources:
            raise ValueError("Das Projekt enthält keine Dateien.")
        rules = project.load_rules().to_dict()
        names = project.load_names()
        store = project.mapping()

        before = {s.id: _fingerprint(s) for s in project.sources}
        files = []
        for source in project.sources:
            encoding, fmt = self._resolve(source)
            files.append((source, encoding, fmt))
            self.report["files"].append({
                "source": source.path, "output": source.rel, "format": fmt,
                "encoding": encoding.label, "bytes": before[source.id][0]})
        total_bytes = sum(size for size, _ in before.values())
        self._bytes_total = total_bytes * 3
        workers = worker_count(total_bytes)
        self.report["workers"] = workers

        # Phase 1: collect all values.
        values: set[tuple[str, str]] = set()
        with Executor(workers, rules=rules, names=names, learned=store.originals()) as executor:
            for source, encoding, fmt in files:
                for found in self._map_file(executor, "scan", "scan", source,
                                            Path(source.path), encoding, fmt, {}):
                    values |= found
        new = store.assign(values, self.run_id)
        mapping = store.load()

        # Phase 2 also replaces standalone occurrences of values learned in phase 1.
        known = list(mapping) + [(c, v.casefold()) for c, vs in names.items() for v in vs]
        counts_total: Counter[str] = Counter()
        hit_total = 0
        with Executor(workers, rules=rules, names=names, learned=list(mapping),
                      mapping=mapping, known=known) as executor:
            for info, (source, encoding, fmt) in zip(self.report["files"], files):
                counts, lines_in, lines_out = self._write_file(executor, source, encoding, fmt)
                info.update(replacements=dict(sorted(counts.items())), lines=lines_in)
                counts_total.update(counts)
                self._check(f"Zeilenanzahl {source.rel}", lines_in == lines_out,
                            f"{lines_in} Eingabe- / {lines_out} Ausgabezeilen")

            # Phase 3: residual scan of the written output.
            for info, (source, encoding, _fmt) in zip(self.report["files"], files):
                hits, total = self._validate_file(executor, source, encoding)
                info["residual_hits"] = total
                hit_total += total
                self.report["residual_hits"].extend(hits)
        self._check("Restscan", hit_total == 0, f"{hit_total} Fundstellen")

        changed = [s.rel for s in project.sources if _fingerprint(s) != before[s.id]]
        self._check("Quelldateien unverändert", not changed, ", ".join(changed) or "ok")

        self.report["summary"] = {
            "files": len(files),
            "bytes": total_bytes,
            "replacements": dict(sorted(counts_total.items())),
            "new_mappings": new,
            "residual_hits": hit_total,
        }
        if all(c["passed"] for c in self.report["checks"]):
            os.replace(self.partial, self.dir / "output")
            self.report["status"] = STATUS_READY
        else:
            blocked = self.dir / "output.blocked"
            os.replace(self.partial, blocked)
            (blocked / "NICHT_FREIGEGEBEN.txt").write_text(BLOCKED_NOTICE, encoding="utf-8")
            self.report["status"] = STATUS_BLOCKED

    def _resolve(self, source: Source) -> tuple[FileEncoding, str]:
        path = Path(source.path)
        try:
            encoding = (detect_encoding(path) if source.encoding == "auto"
                        else parse_encoding(source.encoding))
            fmt = detect_format(path, encoding) if source.format == "auto" else source.format
        except (FormatError, LookupError) as exc:
            raise FormatError(f"{source.rel}: {exc}") from exc
        return encoding, fmt

    def _write_file(self, executor: Executor, source: Source, encoding: FileEncoding,
                    fmt: str) -> tuple[Counter[str], int, int]:
        counts: Counter[str] = Counter()
        stats = {"lines": 0}
        lines_out = 0
        target = self.partial / source.rel
        target.parent.mkdir(parents=True, exist_ok=True)
        with create_text(target, encoding) as out:
            for text, block_counts in self._map_file(executor, "write", "write", source,
                                                     Path(source.path), encoding, fmt, stats):
                out.write(text)
                lines_out += text.count("\n")
                counts.update(block_counts)
        return counts, stats["lines"], lines_out

    def _validate_file(self, executor: Executor, source: Source,
                       encoding: FileEncoding) -> tuple[list[dict], int]:
        hits: list[dict] = []
        total = 0
        line_base = 0
        for found, block_lines in self._map_file(executor, "validate", "validate", source,
                                                 self.partial / source.rel, encoding, "text", {}):
            total += len(found)
            for line, category, value, check in found[:MAX_HITS_PER_FILE - len(hits)]:
                hits.append({"file": source.rel, "line": line_base + line,
                             "category": category, "value": value, "check": check})
            line_base += block_lines
        return hits, total

    def _map_file(self, executor: Executor, method: str, phase: str, source: Source,
                  path: Path, encoding: FileEncoding, fmt: str, stats: dict) -> Iterator:
        """Feed a file's blocks through ``executor`` and yield the results in order."""
        self._step(phase, source)
        stats.setdefault("lines", 0)
        items = ((block, fmt) for block in self._read_blocks(path, encoding, stats))
        try:
            yield from executor.map(method, items, parallel=fmt != "json")
            if fmt == "json":
                executor.engine.finish_json()
        except FormatError as exc:
            raise FormatError(f"{source.rel}: {exc}") from exc

    def _read_blocks(self, path: Path, encoding: FileEncoding, stats: dict) -> Iterator[str]:
        with open_text(path, encoding) as stream:
            position = 0
            for block in iter_blocks(stream):
                if self.cancel.is_set():
                    raise RunCancelled()
                stats["lines"] += block.count("\n")
                yield block
                current = stream.buffer.tell()
                self._advance(current - position)
                position = current

    # -- helpers ----------------------------------------------------------------

    def _check(self, name: str, passed: bool, detail: str) -> None:
        self.report["checks"].append({"name": name, "passed": passed, "detail": detail})

    def _step(self, phase: str, source: Source) -> None:
        self._phase = phase
        self._file = source.rel
        self._emit()

    def _advance(self, nbytes: int) -> None:
        self._bytes_done += max(nbytes, 0)
        self._emit()

    def _emit(self) -> None:
        percent = 100 * self._bytes_done / self._bytes_total if self._bytes_total else 0
        self.progress({"phase": self._phase, "file": self._file,
                       "percent": round(min(percent, 99.9), 1)})

    def _save_report(self) -> None:
        tmp = self.dir / "report.json.tmp"
        tmp.write_text(json.dumps(self.report, indent=2, ensure_ascii=False) + "\n",
                       encoding="utf-8")
        os.replace(tmp, self.dir / "report.json")


def run_project(project: Project, cancel: threading.Event | None = None,
                progress: ProgressCallback | None = None) -> dict:
    return Run(project, cancel, progress).execute()


def _fingerprint(source: Source) -> tuple[int, int]:
    stat = Path(source.path).stat()
    return stat.st_size, stat.st_mtime_ns


def _describe(exc: Exception) -> str:
    if isinstance(exc, KeyError):
        return "Quelldatei hat sich während des Laufs verändert (unbekannter Wert in Phase 2)."
    return str(exc)
