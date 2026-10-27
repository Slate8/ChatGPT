"""Sanitization rules, built-in defaults and the versioned JSON rule format.

A rule is either a regular expression or a literal. Regex rules may use named
groups; each named group is a category (for example ``(?P<Server>...)``) and only
the group spans are replaced. Rules without named groups replace the whole match
with the rule's ``category``.

Patterns may contain ``{LABEL}`` (one DNS label) and ``{TLD}`` (alternation of the
configured top-level domains); both are expanded at compile time.

Rule exports never contain project name lists or mapping data.
"""
from __future__ import annotations

import json
import multiprocessing
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

RULES_FORMAT = "logsanitizer.rules"
RULES_VERSION = 1

CATEGORY_RE = re.compile(r"^[A-Za-z][A-Za-z0-9]{0,31}$")

LABEL = r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"

DEFAULT_TLDS = [
    # internal / reserved
    "local", "lan", "corp", "intern", "internal", "intranet", "home", "localdomain",
    "priv", "private", "ad", "test", "example", "invalid", "arpa",
    # common public
    "com", "net", "org", "info", "biz", "io", "co", "gov", "edu", "mil", "int", "eu",
    "de", "at", "ch", "li", "lu", "nl", "be", "fr", "it", "es", "uk", "dk", "se", "no",
    "fi", "cz", "us", "ca",
]

# After a domain: no further label characters and no further ".label".
_DOMAIN_END = r"(?![A-Za-z0-9-]|\.[A-Za-z0-9])"

DEFAULT_RULES: list[dict] = [
    {
        "id": "secret-assignment",
        "name": "Geheimnisse in Zuweisungen",
        "description": "Werte nach password=, token: usw.",
        "pattern": r"(?<![\w-])(?:password|passwd|pwd|secret|token|api[_-]?key|client[_-]?secret)"
                   r"[\"']?[ \t]*[=:][ \t]*[\"']?(?P<Secret>[^\s\"',;&]{1,256})",
        "anchors": ["pass", "pwd", "secret", "token", "api"],
        "priority": 90,
    },
    {
        "id": "authorization-header",
        "name": "Authorization-Header",
        "description": "Bearer-/Basic-/NTLM-Token in HTTP-Headern.",
        "pattern": r"(?<![\w-])authorization:[ \t]*(?:bearer|basic|negotiate|ntlm)[ \t]+"
                   r"(?P<Secret>[A-Za-z0-9._~+/=-]+)",
        "anchors": ["authorization"],
        "priority": 90,
    },
    {
        "id": "url-credentials",
        "name": "Zugangsdaten in URLs",
        "description": "scheme://benutzer:passwort@host",
        "pattern": r"://(?P<User>[^:@/\s\"']+):(?P<Secret>[^@/\s\"']+)@",
        "anchors": ["://"],
        "priority": 85,
    },
    {
        "id": "email",
        "name": "E-Mail-Adressen",
        "description": "Lokaler Teil wird als Benutzer, Domain wie bei FQDNs ersetzt.",
        "pattern": r"(?<![\w.%+-])(?P<User>[A-Za-z0-9._%+-]{1,64})@"
                   r"(?:(?P<Server>{LABEL})\.(?=(?:{LABEL}\.)+[A-Za-z]{2,24}" + _DOMAIN_END + r"))?"
                   r"(?P<Domain>(?:{LABEL}\.)+[A-Za-z]{2,24})" + _DOMAIN_END,
        "anchors": ["@"],
        "priority": 80,
    },
    {
        "id": "windows-account",
        "name": "Windows-Konten (DOMAIN\\Benutzer)",
        "description": "NetBIOS-Domain in Großbuchstaben, gefolgt von Benutzername.",
        "pattern": r"(?<![\w\\:/.-])(?P<Domain>[A-Z][A-Z0-9-]{0,14})\\{1,2}"
                   r"(?P<User>[A-Za-z0-9][\w.$-]{0,63})(?![\w\\$-])",
        "anchors": ["\\"],
        "ignore_case": False,
        "priority": 70,
    },
    {
        "id": "unc-path",
        "name": "UNC-Pfade (\\\\server\\freigabe)",
        "description": "Servername in UNC-Pfaden.",
        "pattern": r"(?<![\w\\])\\{2,4}(?P<Server>{LABEL})(?=\\)",
        "anchors": ["\\\\"],
        "priority": 70,
    },
    {
        "id": "windows-sid",
        "name": "Domänen-SIDs",
        "description": "Security Identifier, die eine Domäne identifizieren.",
        "pattern": r"(?<![\w-])S-1-5-21(?:-\d{1,10}){3,4}(?![\w-])",
        "category": "SID",
        "anchors": ["s-1-5-21"],
        "ignore_case": False,
        "priority": 60,
    },
    {
        "id": "fqdn",
        "name": "Vollqualifizierte Hostnamen",
        "description": "server.domain.tld -> [Server_n].[Domain_n]",
        "pattern": r"(?<![\w.-])(?P<Server>{LABEL})\.(?P<Domain>(?:{LABEL}\.)+(?:{TLD}))" + _DOMAIN_END,
        "priority": 50,
    },
    {
        "id": "domain",
        "name": "Domainnamen",
        "description": "domain.tld -> [Domain_n]",
        "pattern": r"(?<![\w.-])(?P<Domain>{LABEL}\.(?:{TLD}))" + _DOMAIN_END,
        "priority": 50,
    },
    {
        "id": "url-host",
        "name": "Hostnamen in URLs",
        "description": "Einteilige Hostnamen nach scheme://",
        "pattern": r"(?<=://)(?P<Server>[A-Za-z][A-Za-z0-9-]{0,62})(?=[:/?#\s\"']|$)",
        "anchors": ["://"],
        "priority": 45,
    },
    {
        "id": "ipv4",
        "name": "IPv4-Adressen",
        # Starts with a character class (fast scanning); octet ranges and
        # zero-padded forms are validated during normalization.
        "pattern": r"[0-9](?<![\w.][0-9])[0-9]{0,2}(?:\.[0-9]{1,3}){3}(?![\w]|\.[0-9])",
        "category": "IP",
        "priority": 40,
    },
    {
        "id": "ipv6",
        "name": "IPv6-Adressen",
        # Valid addresses contain "::" or exactly seven colons; the lookahead keeps
        # timestamps like 10:00:05 from becoming candidates.
        # The trailing check leaves IPv4-mapped forms (::ffff:1.2.3.4) to the IPv4 rule.
        "pattern": r"[0-9A-Fa-f:](?<![\w:][0-9A-Fa-f:])"
                   r"(?:(?<=:)(?=:)|(?=[0-9A-Fa-f:]*::)|(?=(?:[0-9A-Fa-f]{0,4}:){6}))"
                   r"[0-9A-Fa-f:]*(?:%[\w.]+)?(?![\w:]|\.[0-9])",
        "category": "IPv6",
        "priority": 40,
    },
    {
        "id": "mac",
        "name": "MAC-Adressen",
        "pattern": r"[0-9A-Fa-f](?<![\w:-][0-9A-Fa-f])[0-9A-Fa-f]([:-])[0-9A-Fa-f]{2}"
                   r"(?:\1[0-9A-Fa-f]{2}){4}(?![\w:-])",
        "category": "MAC",
        "priority": 40,
    },
    {
        "id": "hostname-pattern-example",
        "name": "Beispiel: Hostnamen-Muster",
        "description": "Vorlage für kundenspezifische Namenskonventionen; vor Aktivierung anpassen.",
        "pattern": r"(?<![\w-])(?:srv|dc|sql|app|web|fs)[\w-]*\d+(?![\w-])",
        "category": "Server",
        "enabled": False,
        "priority": 55,
    },
]

DEFAULT_ALLOWLIST: dict[str, list[str]] = {
    "IP": ["0.0.0.0", "127.0.0.1", "255.255.255.255"],
    "IPv6": ["::1", "::"],
    "Server": ["localhost"],
    "Domain": ["asp.net"],
}

DEFAULT_JSON_SECRET_KEYS = (
    r"(?i)(pass(word|wd)?|pwd|secret|token|api[_-]?key|authorization|cookie|credential)"
)


class RuleError(ValueError):
    """Raised for invalid rule sets."""


@dataclass
class Rule:
    id: str
    name: str
    pattern: str
    category: str = ""
    kind: str = "regex"  # "regex" or "literal"
    enabled: bool = True
    ignore_case: bool = True
    priority: int = 50
    description: str = ""
    # Optional speed-up: lowercase substrings every match must contain. The rule
    # then only runs on lines containing one of them. Leave empty if unsure.
    anchors: list[str] = field(default_factory=list)


@dataclass
class RuleSet:
    rules: list[Rule] = field(default_factory=list)
    tlds: list[str] = field(default_factory=lambda: list(DEFAULT_TLDS))
    allowlist: dict[str, list[str]] = field(default_factory=lambda: {
        k: list(v) for k, v in DEFAULT_ALLOWLIST.items()})
    json_secret_keys: str = DEFAULT_JSON_SECRET_KEYS
    sanitize_json_keys: bool = True

    def to_dict(self) -> dict:
        return {
            "format": RULES_FORMAT,
            "version": RULES_VERSION,
            "rules": [asdict(r) for r in self.rules],
            "tlds": self.tlds,
            "allowlist": self.allowlist,
            "json_secret_keys": self.json_secret_keys,
            "sanitize_json_keys": self.sanitize_json_keys,
        }

    @classmethod
    def from_dict(cls, data: dict) -> RuleSet:
        if data.get("format") != RULES_FORMAT:
            raise RuleError("Keine LogSanitizer-Regeldatei (Feld 'format' fehlt oder ist falsch).")
        if data.get("version") != RULES_VERSION:
            raise RuleError(f"Nicht unterstützte Regelversion: {data.get('version')!r}.")
        known = set(Rule.__dataclass_fields__)
        rules = []
        for raw in data.get("rules", []):
            unknown = set(raw) - known
            if unknown:
                raise RuleError(f"Unbekannte Felder in Regel {raw.get('id')!r}: {sorted(unknown)}")
            rules.append(Rule(**raw))
        defaults = cls()
        ruleset = cls(
            rules=rules,
            tlds=list(data.get("tlds", defaults.tlds)),
            allowlist={k: list(v) for k, v in data.get("allowlist", defaults.allowlist).items()},
            json_secret_keys=data.get("json_secret_keys", defaults.json_secret_keys),
            sanitize_json_keys=bool(data.get("sanitize_json_keys", True)),
        )
        errors = validate_ruleset(ruleset)
        if errors:
            raise RuleError("; ".join(errors))
        return ruleset

    @classmethod
    def load(cls, path: Path) -> RuleSet:
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))

    def save(self, path: Path) -> None:
        text = json.dumps(self.to_dict(), indent=2, ensure_ascii=False) + "\n"
        Path(path).write_text(text, encoding="utf-8")


def default_ruleset() -> RuleSet:
    return RuleSet(rules=[Rule(**r) for r in DEFAULT_RULES])


def expand_pattern(pattern: str, tlds: list[str]) -> str:
    tld_alt = "|".join(re.escape(t) for t in sorted(tlds, key=len, reverse=True)) or "(?!)"
    return pattern.replace("{LABEL}", LABEL).replace("{TLD}", tld_alt)


def compile_rule(rule: Rule, tlds: list[str]) -> re.Pattern[str]:
    flags = re.IGNORECASE if rule.ignore_case else 0
    if rule.kind == "literal":
        return re.compile(r"(?<![\w-])" + re.escape(rule.pattern) + r"(?![\w-])", flags)
    return re.compile(expand_pattern(rule.pattern, tlds), flags)


def validate_ruleset(ruleset: RuleSet) -> list[str]:
    errors: list[str] = []
    seen: set[str] = set()
    for rule in ruleset.rules:
        prefix = f"Regel {rule.id!r}"
        if not rule.id or rule.id in seen:
            errors.append(f"{prefix}: ID fehlt oder ist doppelt.")
        seen.add(rule.id)
        if rule.kind not in ("regex", "literal"):
            errors.append(f"{prefix}: unbekannte Art {rule.kind!r}.")
            continue
        if not rule.pattern:
            errors.append(f"{prefix}: Muster ist leer.")
            continue
        try:
            compiled = compile_rule(rule, ruleset.tlds)
        except re.error as exc:
            errors.append(f"{prefix}: ungültiger regulärer Ausdruck ({exc}).")
            continue
        groups = list(compiled.groupindex)
        for name in groups:
            if not CATEGORY_RE.match(name):
                errors.append(f"{prefix}: Gruppenname {name!r} ist keine gültige Kategorie.")
        if not groups and not CATEGORY_RE.match(rule.category or ""):
            errors.append(f"{prefix}: Kategorie fehlt oder ist ungültig.")
        if compiled.fullmatch(""):
            errors.append(f"{prefix}: Muster darf nicht auf leeren Text passen.")
        if any(not a or a != a.lower() or "\n" in a for a in rule.anchors):
            errors.append(f"{prefix}: Anker müssen nicht leer und kleingeschrieben sein.")
    for category in ruleset.allowlist:
        if not CATEGORY_RE.match(category):
            errors.append(f"Allowlist: ungültige Kategorie {category!r}.")
    try:
        re.compile(ruleset.json_secret_keys)
    except re.error as exc:
        errors.append(f"JSON-Schlüsselmuster ungültig ({exc}).")
    return errors


# Inputs that make badly written patterns backtrack catastrophically.
_STRESS_INPUTS = [
    "a" * 5000 + "!",
    "1." * 2000 + "x",
    ("ab-" * 1500) + "\\",
    " " * 5000 + "@",
    ":" * 3000 + "g",
]


def _stress(pattern: str, flags: int) -> None:
    compiled = re.compile(pattern, flags)
    for text in _STRESS_INPUTS:
        for _ in compiled.finditer(text):
            pass


def check_regex_performance(rule: Rule, tlds: list[str], timeout: float = 3.0) -> bool:
    """Run a rule against adversarial inputs in a separate process.

    Returns False if it does not finish within ``timeout`` seconds. Python's ``re``
    cannot be interrupted, so the worker process is terminated instead.
    """
    if rule.kind == "literal":
        return True
    flags = re.IGNORECASE if rule.ignore_case else 0
    ctx = multiprocessing.get_context("spawn")
    proc = ctx.Process(target=_stress, args=(expand_pattern(rule.pattern, tlds), flags), daemon=True)
    proc.start()
    proc.join(timeout)
    if proc.is_alive():
        proc.terminate()
        proc.join()
        return False
    return proc.exitcode == 0
