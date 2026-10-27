"""Block processing, optionally spread over several worker processes.

Blocks always end at a line break, so text and JSON Lines blocks can be handled
independently. Results are consumed in input order and only a bounded number of
blocks is in flight, so memory stays flat for files of any size. A single JSON
document is processed sequentially because its parser state spans blocks.
"""
from __future__ import annotations

import os
from collections import Counter, deque
from collections.abc import Callable, Iterable, Iterator
from typing import Any

from .engine import Detector, Hit, replace
from .formats import FormatError, JsonStringRewriter
from .rules import RuleSet
from .validate import ResidualScanner

PARALLEL_MIN_BYTES = 16 * 1024 * 1024
MAX_WORKERS = 8


def worker_count(total_bytes: int) -> int:
    configured = os.environ.get("LOGSANITIZER_WORKERS")
    if configured:
        return max(1, int(configured))
    if total_bytes < PARALLEL_MIN_BYTES:
        return 1
    return max(1, min((os.cpu_count() or 1) - 1, MAX_WORKERS))


class BlockEngine:
    """Everything one process needs to scan, rewrite or validate blocks."""

    def __init__(self, rules: dict, names: dict[str, list[str]],
                 learned: list[tuple[str, str]], mapping: dict[tuple[str, str], str] | None = None,
                 known: list[tuple[str, str]] | None = None):
        ruleset = RuleSet.from_dict(rules)
        self.detector = Detector(ruleset, names, learned)
        self.sanitize_keys = ruleset.sanitize_json_keys
        self.mapping = mapping or {}
        self.scanner = ResidualScanner(self.detector, known) if known is not None else None
        self._collect: set[tuple[str, str]] | None = None
        self._counts: Counter[str] = Counter()
        self._rewriter: JsonStringRewriter | None = None

    # -- per-block operations (results must be picklable) --------------------------

    def scan(self, block: str, fmt: str) -> set[tuple[str, str]]:
        self._collect = set()
        self._run(block, fmt)
        values, self._collect = self._collect, None
        return values

    def write(self, block: str, fmt: str) -> tuple[str, Counter[str]]:
        self._counts = Counter()
        return self._run(block, fmt), self._counts

    def validate(self, block: str, _fmt: str) -> tuple[list[tuple[int, str, str, str]], int]:
        """Residual findings as (line within block, category, value, check), line count."""
        assert self.scanner is not None
        found = [(block.count("\n", 0, offset) + 1, category, value, check)
                 for offset, category, value, check in self.scanner.scan_text(block)]
        return found, block.count("\n")

    # -- internals --------------------------------------------------------------

    def _run(self, block: str, fmt: str) -> str:
        if fmt == "text":
            return self._handle(block, self.detector.find(block))
        if fmt == "jsonl":
            rewriter = self._new_rewriter()
            result = rewriter.feed(block)
            try:
                rewriter.close()
            except FormatError as exc:
                raise FormatError("Keine gültigen JSON Lines (Zeichenkette über Zeilenende); "
                                  "Format 'JSON' oder 'Text' wählen.") from exc
            return result
        if self._rewriter is None:  # single JSON document, sequential
            self._rewriter = self._new_rewriter()
        return self._rewriter.feed(block)

    def finish_json(self) -> None:
        if self._rewriter is not None:
            self._rewriter.close()
            self._rewriter = None

    def _new_rewriter(self) -> JsonStringRewriter:
        return JsonStringRewriter(self._on_json_string, self.detector.json_secret_keys)

    def _on_json_string(self, value: str, is_key: bool, is_secret: bool) -> str | None:
        if is_key and not self.sanitize_keys:
            return None
        if is_secret and value:
            hits = [Hit(0, len(value), "Secret", value, False, "json-secret-key")]
        else:
            hits = self.detector.find(value)
        return self._handle(value, hits) if hits else None

    def _handle(self, text: str, hits: list[Hit]) -> str:
        if self._collect is not None:
            self._collect.update((h.category, h.value) for h in hits if not h.allowed)
            return text
        self._counts.update(h.category for h in hits if not h.allowed)
        return replace(text, hits, self._lookup)[0]

    def _lookup(self, category: str, value: str) -> str:
        return self.mapping[(category, value)]


# -- process pool plumbing --------------------------------------------------------

_ENGINE: BlockEngine | None = None


def _init_worker(kwargs: dict) -> None:
    global _ENGINE
    _ENGINE = BlockEngine(**kwargs)


def _call(method: str, args: tuple) -> Any:
    assert _ENGINE is not None
    return getattr(_ENGINE, method)(*args)


class _Inline:
    """Same interface as the pool, executed in this process."""

    def __init__(self, engine: BlockEngine):
        self.engine = engine

    def submit(self, method: str, args: tuple) -> Callable[[], Any]:
        result = getattr(self.engine, method)(*args)
        return lambda: result

    def close(self) -> None:
        pass


class _Pool:
    def __init__(self, workers: int, kwargs: dict):
        import multiprocessing

        ctx = multiprocessing.get_context("spawn")  # same behaviour on Windows and Linux
        self.pool = ctx.Pool(workers, initializer=_init_worker, initargs=(kwargs,))

    def submit(self, method: str, args: tuple) -> Callable[[], Any]:
        return self.pool.apply_async(_call, (method, args)).get

    def close(self) -> None:
        self.pool.terminate()
        self.pool.join()


class Executor:
    """Runs BlockEngine methods inline or in worker processes, preserving order."""

    def __init__(self, workers: int, **kwargs: Any):
        self.workers = workers
        self._kwargs = kwargs
        self.engine = BlockEngine(**kwargs)  # used inline and for sequential JSON
        self._backend = _Pool(workers, kwargs) if workers > 1 else _Inline(self.engine)

    def map(self, method: str, items: Iterable[tuple], parallel: bool = True) -> Iterator[Any]:
        backend = self._backend if parallel else _Inline(self.engine)
        pending: deque[Callable[[], Any]] = deque()
        limit = self.workers * 2
        for args in items:
            pending.append(backend.submit(method, args))
            if len(pending) >= limit:
                yield pending.popleft()()
        while pending:
            yield pending.popleft()()

    def close(self) -> None:
        self._backend.close()

    def __enter__(self) -> Executor:  # noqa: PYI034 - typing.Self needs 3.11
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
