"""Synthetic sample logs for tests, demos and the on-site self-test.

Everything here is invented ("Nordwerk" is a fictitious company). The generated
files cover typical formats and encodings; ``SENSITIVE`` lists every value that
must not survive sanitization.
"""
from __future__ import annotations

import codecs
import json
import random
from pathlib import Path

NETBIOS = "NORDWERK"
DOMAIN = "nordwerk.local"
SERVERS = ["srv-app01", "srv-app02", "dc01", "sqlprod02", "fileserver", "web-gw"]
USERS = ["jdoe", "m.mustermann", "a.schmidt", "svc_backup"]
IPS = ["10.20.1.15", "10.20.2.30", "10.20.0.5", "10.20.5.77", "10.20.9.9", "192.168.40.12"]
IPV6 = "fd12:3456:789a::5"
MACS = ["00:1a:2b:3c:4d:5e", "00-1A-2B-3C-4D-5F"]
SID = "S-1-5-21-3623811015-3361044348-30300820-1013"
SECRETS = ["Sommer2024!", "Geheim123", "eyJhbGciOiJIUzI1NiJ9.c2VjcmV0.abc123"]

SENSITIVE = [NETBIOS, "nordwerk", *SERVERS, *USERS, *IPS, IPV6, *MACS, SID, *SECRETS]

# Short host names and service accounts cannot be recognised generically; on site
# they come from name lists maintained per project.
NAME_LISTS = {
    "Server": ["dc01", "fileserver", "sqlprod02", "web-gw"],
    "User": ["svc_backup"],
}


def generate(target: Path, big_mb: int = 0, seed: int = 7) -> list[Path]:
    """Write logs to ``target/logs`` and name lists to ``target/namenslisten``.

    Optionally adds a large file of ``big_mb`` MB. Returns the written log files.
    """
    rng = random.Random(seed)
    logs = target / "logs"
    lists = target / "namenslisten"
    logs.mkdir(parents=True, exist_ok=True)
    lists.mkdir(parents=True, exist_ok=True)
    files = {
        "syslog.log": (_syslog(rng, 200), "utf-8", b"", "\n"),
        "windows_events.txt": (_windows_events(), "cp1252", b"", "\r\n"),
        "iis/u_ex261027.log": (_iis(rng, 100), "utf-8", b"", "\r\n"),
        "app_stacktrace.log": (_stacktrace(), "utf-8", codecs.BOM_UTF8, "\n"),
        "events.jsonl": (_jsonl(rng, 100), "utf-8", b"", "\n"),
        "inventory.json": (_inventory(), "utf-8", b"", "\n"),
        "export_utf16.log": (_utf16_export(), "utf-16-le", codecs.BOM_UTF16_LE, "\r\n"),
    }
    written = []
    for name, (lines, codec, bom, newline) in files.items():
        path = logs / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(bom + (newline.join(lines) + newline).encode(codec))
        written.append(path)
    if big_mb:
        written.append(_big(logs / "big_syslog.log", big_mb, rng))
    for category, values in NAME_LISTS.items():
        (lists / f"{category.lower()}.txt").write_text("\n".join(values) + "\n",
                                                             encoding="utf-8")
    return written


def _syslog(rng: random.Random, count: int) -> list[str]:
    lines = []
    for i in range(count):
        server = rng.choice(SERVERS)
        user = rng.choice(USERS[:3])
        ip = rng.choice(IPS)
        stamp = f"Oct 27 10:{i // 60:02d}:{i % 60:02d}"
        lines.append(rng.choice([
            f"{stamp} {server} sshd[{1000 + i}]: Accepted publickey for {user} from {ip} port 5{i:04d} ssh2",
            f"{stamp} {server} kernel: eth0 link up, hwaddr {MACS[0]}",
            f"{stamp} {server} CRON[{2000 + i}]: (root) CMD (/usr/bin/backup --target \\\\fileserver\\backup)",
            f"{stamp} {server} named[53]: resolved {server}.{DOMAIN} to {ip}",
        ]))
    return lines


def _windows_events() -> list[str]:
    return [
        "Ein Konto wurde erfolgreich angemeldet.",
        f"Konto: {NETBIOS}\\m.mustermann",
        "Arbeitsstation: SRV-APP02",
        f"Quellnetzwerkadresse: {IPS[1]}",
        f"Sicherheits-ID: {SID}",
        f"Anmeldung für {NETBIOS}\\a.schmidt fehlgeschlagen, Grund: Kennwort abgelaufen",
        f"Freigabe \\\\fileserver\\Abteilung geöffnet von {IPS[3]}",
    ]


def _iis(rng: random.Random, count: int) -> list[str]:
    lines = ["#Software: Microsoft Internet Information Services 10.0",
             "#Fields: date time s-ip cs-method cs-uri-stem s-port c-ip cs(Referer) sc-status"]
    for i in range(count):
        lines.append(f"2026-10-27 10:00:{i % 60:02d} {IPS[0]} GET /api/orders/{i} 443 "
                     f"{rng.choice(IPS)} http://srv-app01.{DOMAIN}:8080/health 200")
    return lines


def _stacktrace() -> list[str]:
    return [
        f"2026-10-27 10:15:00 ERROR Connection to sqlprod02.{DOMAIN}:1433 failed",
        "java.sql.SQLException: Login failed for user 'svc_backup'",
        "\tat com.example.db.Pool.open(Pool.java:42)",
        "\tat com.example.web.OrderController.list(OrderController.java:88)",
        f"Caused by: jdbc:sqlserver://sqlprod02;user=svc_backup;password={SECRETS[0]}",
        f"2026-10-27 10:15:01 WARN Retrying via http://web-gw:8443/ as {USERS[0]}@{DOMAIN}",
        f"2026-10-27 10:15:02 INFO Authorization: Bearer {SECRETS[2]}",
    ]


def _jsonl(rng: random.Random, count: int) -> list[str]:
    lines = []
    for i in range(count):
        server = rng.choice(SERVERS[:2])
        record = {
            "ts": f"2026-10-27T10:{i // 60:02d}:{i % 60:02d}Z",
            "host": f"{server}.{DOMAIN}",
            "src_ip": rng.choice(IPS),
            "user": f"{NETBIOS}\\jdoe",
            "msg": f"Login ok for jdoe@mail.{DOMAIN} (Größe {i} KB)",
            "duration_ms": i * 3,
        }
        if i % 10 == 0:
            record["password"] = SECRETS[1]
        lines.append(json.dumps(record, ensure_ascii=False))
    return lines


def _inventory() -> list[str]:
    data = {
        "generated": "2026-10-27",
        "servers": {
            "dc01": {"ip": IPS[2], "ipv6": IPV6, "mac": MACS[1], "roles": ["AD", "DNS"]},
            "fileserver": {"ip": IPS[5], "share": "\\\\fileserver\\backup", "owner": "a.schmidt"},
            f"web-gw.{DOMAIN}": {"ip": IPS[4], "upstream": f"https://srv-app01.{DOMAIN}/"},
        },
        "contacts": [f"m.mustermann@{DOMAIN}"],
        "api": {"token": SECRETS[2], "retries": 3, "enabled": True},
    }
    return json.dumps(data, indent=2, ensure_ascii=False).split("\n")


def _utf16_export() -> list[str]:
    return [
        f"Computer=WEB-GW;IP={IPS[4]};User=a.schmidt@mail.{DOMAIN}",
        f"Computer=DC01;IP={IPS[2]};User={NETBIOS}\\jdoe",
    ]


def _big(path: Path, megabytes: int, rng: random.Random) -> Path:
    target = megabytes * 1024 * 1024
    written = 0
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        while written < target:
            chunk = "\n".join(_syslog(rng, 1000)) + "\n"
            fh.write(chunk)
            written += len(chunk)
    return path
