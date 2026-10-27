"""Residual scan of sanitized output.

Two independent checks run on the written output:
1. the detection rules again (anything they still find was not replaced), and
2. a search for every original value known to the project (mapping + name lists).

A clean scan reduces risk but does not prove that no sensitive data is left.
"""
from __future__ import annotations

import re
from collections.abc import Iterable

from .engine import PLACEHOLDER_RE, Detector

MIN_KNOWN_LENGTH = 3
MAX_HITS_PER_FILE = 200


class ResidualScanner:
    def __init__(self, detector: Detector, known: Iterable[tuple[str, str]]):
        self.detector = detector
        self._category: dict[str, str] = {}
        for category, value in known:
            if len(value) >= MIN_KNOWN_LENGTH and not detector.is_allowed(category, value):
                self._category.setdefault(value.casefold(), category)
        values = sorted(self._category, key=lambda v: (-len(v), v))
        self._known = (re.compile(r"(?<![A-Za-z0-9])(?:" + "|".join(map(re.escape, values))
                                  + r")(?![A-Za-z0-9])", re.IGNORECASE) if values else None)

    def scan_text(self, text: str) -> list[tuple[int, str, str, str]]:
        """Return (offset, category, value, check) for every residual finding.

        ``check`` is "rules" (a detection rule still matches) or "known-values".
        """
        found = []
        for hit in self.detector.find(text):
            if not hit.allowed:
                found.append((hit.start, hit.category, text[hit.start:hit.end], "rules"))
        if self._known is not None:
            placeholders = [m.span() for m in PLACEHOLDER_RE.finditer(text)]
            for match in self._known.finditer(text):
                if any(s <= match.start() < e for s, e in placeholders):
                    continue
                category = self._category.get(match.group().casefold(), "?")
                found.append((match.start(), category, match.group(), "known-values"))
        found.sort()
        return found
