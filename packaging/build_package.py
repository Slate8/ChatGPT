"""Assemble the portable release folders and ZIP files.

Usage: python packaging/build_package.py --out dist [--python-embed python-...-embed-amd64.zip]

Produces LogSanitizer-<version>-portable.zip (uses an installed Python 3.10+) and,
with --python-embed, LogSanitizer-<version>-windows-x64.zip including Python.
Only uses the standard library.
"""
from __future__ import annotations

import argparse
import hashlib
import shutil
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ["cli.bat", "start.bat", "selbsttest.bat", "cli.sh", "start.sh", "LIESMICH.txt"]


def version() -> str:
    sys.path.insert(0, str(ROOT / "backend" / "src"))
    from logsanitizer import __version__

    return __version__


def assemble(target: Path) -> None:
    dist = ROOT / "frontend" / "dist"
    if not (dist / "index.html").is_file():
        sys.exit("frontend/dist fehlt – zuerst 'npm run build' im Ordner frontend ausführen.")
    shutil.copytree(ROOT / "backend" / "src" / "logsanitizer", target / "backend" / "src" / "logsanitizer",
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    shutil.copytree(dist, target / "frontend" / "dist")
    for name in SCRIPTS:
        shutil.copy2(ROOT / "packaging" / name, target / name)
    shutil.copy2(ROOT / "docs" / "ANLEITUNG.md", target / "ANLEITUNG.md")


def add_embedded_python(target: Path, embed_zip: Path) -> None:
    python_dir = target / "python"
    with zipfile.ZipFile(embed_zip) as archive:
        archive.extractall(python_dir)
    pth_files = list(python_dir.glob("python3*._pth"))
    if len(pth_files) != 1:
        sys.exit("Unerwarteter Inhalt im Python-Embeddable-Paket (._pth nicht gefunden).")
    # The embeddable Python ignores PYTHONPATH; its search path comes from this file.
    pth = pth_files[0]
    pth.write_text(pth.read_text(encoding="utf-8").rstrip() + "\n..\\backend\\src\n", encoding="utf-8")


def make_zip(folder: Path, zip_path: Path) -> None:
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(folder.rglob("*")):
            info = zipfile.ZipInfo.from_file(path, path.relative_to(folder.parent).as_posix())
            if path.is_file():
                if path.suffix == ".sh":
                    info.external_attr = 0o100755 << 16
                archive.writestr(info, path.read_bytes(), zipfile.ZIP_DEFLATED)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--python-embed", type=Path)
    args = parser.parse_args()

    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    name = f"LogSanitizer-{version()}"
    builds = [("portable", None)]
    if args.python_embed:
        builds.append(("windows-x64", args.python_embed))

    zips = []
    for label, embed in builds:
        staging = out / "staging" / label / name
        shutil.rmtree(staging.parent, ignore_errors=True)
        assemble(staging)
        if embed:
            add_embedded_python(staging, embed)
        zip_path = out / f"{name}-{label}.zip"
        make_zip(staging, zip_path)
        zips.append(zip_path)
        print(f"{zip_path.name}: {zip_path.stat().st_size / 1e6:.1f} MB")

    lines = [f"{hashlib.sha256(z.read_bytes()).hexdigest()}  {z.name}" for z in zips]
    (out / "SHA256SUMS.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
