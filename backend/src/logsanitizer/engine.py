"""Detection and replacement of sensitive values in text.

All rules are evaluated against the same text. Overlapping matches are resolved
once (higher priority, then longer match, then earlier start wins), so a value is
never replaced twice and placeholders are never re-processed.
"""
from __future__ import annotations

import ipaddress
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from functools import lru_cache

from .rules import Rule, RuleSet, compile_rule

PLACEHOLDER_RE = re.compile(r"\[[A-Za-z][A-Za-z0-9]{0,31}_\d+\]")

NAMES_PRIORITY = 60
# Values already in the project mapping are matched as literals too, but below all
# structural rules, so e.g. a full FQDN still wins over a learned host name.
LEARNED_PRIORITY = 10
LEARNED_MIN_LENGTH = 3
# Pattern-detected categories whose text form varies; they are not learned.
NOT_LEARNED = {"IP", "IPv6", "MAC"}


@dataclass(slots=True)
class Hit:
    start: int
    end: int
    category: str
    value: str  # normalized original value
    allowed: bool  # on the allowlist: detected but left unchanged
    rule_id: str


@lru_cache(maxsize=65536)
def normalize(category: str, value: str) -> str | None:
    """Return the canonical form used for mapping, or None if the value is invalid."""
    if category == "IP":
        octets = value.split(".")
        if len(octets) != 4 or not all(o.isdigit() and int(o) <= 255 for o in octets):
            return None
        return ".".join(str(int(o)) for o in octets)  # 010.001.002.003 == 10.1.2.3
    if category == "IPv6":
        address = value.split("%", 1)[0]
        if address.count(":") < 2:
            return None
        try:
            return ipaddress.IPv6Address(address).compressed
        except ValueError:
            return None
    if category == "MAC":
        return value.lower().replace("-", ":")
    return value.casefold()


@dataclass
class _Compiled:
    rule: Rule
    regex: re.Pattern[str]
    groups: tuple[str, ...]
    anchors: tuple[str, ...] = ()
    # Literal lists: case-sensitive regex over the lowercased text (much faster
    # than IGNORECASE); the left word boundary is checked in Python.
    lower_regex: re.Pattern[str] | None = None


class Detector:
    """Finds sensitive values using a rule set plus project name lists."""

    def __init__(self, ruleset: RuleSet, names: dict[str, Iterable[str]] | None = None,
                 learned: Iterable[tuple[str, str]] = ()):
        self.ruleset = ruleset
        self._compiled: list[_Compiled] = []
        for rule in ruleset.rules:
            if rule.enabled:
                regex = compile_rule(rule, ruleset.tlds)
                self._compiled.append(_Compiled(rule, regex, tuple(regex.groupindex),
                                                tuple(rule.anchors)))
        for category, values in sorted((names or {}).items()):
            self._add_literals(f"names:{category}", category, values, NAMES_PRIORITY)
        by_category: dict[str, list[str]] = {}
        for category, value in learned:
            if category not in NOT_LEARNED and len(value) >= LEARNED_MIN_LENGTH:
                by_category.setdefault(category, []).append(value)
        for category, values in sorted(by_category.items()):
            self._add_literals(f"learned:{category}", category, values, LEARNED_PRIORITY)
        self._allow = {
            (category, normalize(category, value) or value.casefold())
            for category, values in ruleset.allowlist.items() for value in values
        }
        self.json_secret_keys = re.compile(ruleset.json_secret_keys)

    def _add_literals(self, rule_id: str, category: str, values: Iterable[str],
                      priority: int) -> None:
        alternation = _literal_alternation(values)
        if alternation:
            rule = Rule(id=rule_id, name=rule_id, pattern="", category=category,
                        priority=priority)
            regex = re.compile(r"(?<![\w-])(?:" + alternation + r")(?![\w-])", re.IGNORECASE)
            lower = re.compile(r"(?:" + alternation.lower() + r")(?![\w-])")
            self._compiled.append(_Compiled(rule, regex, (), lower_regex=lower))

    def is_allowed(self, category: str, value: str) -> bool:
        return (category, value) in self._allow

    def find(self, text: str) -> list[Hit]:
        candidates: list[tuple[int, int, int, int, list[Hit]]] = []
        lowered = text.lower()
        if len(lowered) != len(text):  # rare Unicode case changes: no lowercase shortcuts
            lowered = None
        for item in self._compiled:
            rule = item.rule
            for match in self._matches(item, text, lowered):
                if match.end() == match.start():
                    continue
                if item.groups:
                    spans = [(match.start(g), match.end(g), g, match.group(g))
                             for g in item.groups if match.start(g) != -1]
                else:
                    spans = [(match.start(), match.end(), rule.category,
                              text[match.start():match.end()])]
                hits = []
                for start, end, category, raw in spans:
                    if start == end or PLACEHOLDER_RE.fullmatch(raw):
                        continue
                    value = normalize(category, raw)
                    if value is None:
                        break
                    hits.append(Hit(start, end, category, value,
                                    self.is_allowed(category, value), rule.id))
                else:
                    if hits:
                        candidates.append((-rule.priority, match.start() - match.end(),
                                           match.start(), match.end(), hits))
        candidates.sort(key=lambda c: c[:3])
        occupied = bytearray(len(text))  # 1 = character already claimed by a match
        accepted: list[Hit] = []
        for _, _, start, end, hits in candidates:
            if occupied.find(1, start, end) != -1:
                continue
            occupied[start:end] = b"\x01" * (end - start)
            accepted.extend(hits)
        accepted.sort(key=lambda h: h.start)
        return accepted

    @staticmethod
    def _matches(item: _Compiled, text: str, lowered: str | None) -> Iterable[re.Match[str]]:
        if lowered is None:
            return item.regex.finditer(text)
        if item.lower_regex is not None:
            return (m for m in item.lower_regex.finditer(lowered)
                    if m.start() == 0 or not _is_word_char(lowered[m.start() - 1]))
        if item.anchors:
            ranges = _anchor_line_ranges(text, lowered, item.anchors)
            if ranges is not None:
                return (m for start, end in ranges for m in item.regex.finditer(text, start, end))
        return item.regex.finditer(text)


def _is_word_char(char: str) -> bool:
    return char.isalnum() or char in "_-"


def _anchor_line_ranges(text: str, lowered: str, anchors: tuple[str, ...]
                        ) -> list[tuple[int, int]] | None:
    """Line ranges containing any anchor; None if they cover most of the text anyway."""
    ranges = []
    covered = 0
    limit = len(text) // 2
    for anchor in anchors:
        pos = lowered.find(anchor)
        while pos != -1:
            start = text.rfind("\n", 0, pos) + 1
            end = text.find("\n", pos)
            if end == -1:
                end = len(text)
            ranges.append((start, end))
            covered += end - start
            if covered > limit:
                return None
            pos = lowered.find(anchor, end)
    ranges.sort()
    merged: list[tuple[int, int]] = []
    for start, end in ranges:
        if merged and start <= merged[-1][1] + 1:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def _literal_alternation(values: Iterable[str]) -> str:
    cleaned = {v.strip() for v in values if v and v.strip()}
    return "|".join(re.escape(v) for v in sorted(cleaned, key=lambda v: (-len(v), v)))


Lookup = Callable[[str, str], str]


def replace(text: str, hits: list[Hit], lookup: Lookup) -> tuple[str, int]:
    """Replace all non-allowlisted hits; returns the new text and the replacement count."""
    pieces: list[str] = []
    position = 0
    count = 0
    for hit in hits:
        if hit.allowed:
            continue
        pieces.append(text[position:hit.start])
        pieces.append(lookup(hit.category, hit.value))
        position = hit.end
        count += 1
    if not count:
        return text, 0
    pieces.append(text[position:])
    return "".join(pieces), count
