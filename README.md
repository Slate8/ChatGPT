# LogSanitizer

A portable, offline application for sanitizing application logs on Windows and Linux. Internal host names, IP addresses, accounts and secrets are replaced by consistent placeholders such as `[Server_1].[Domain_1]` or `[IP_3]`; the structure of text and JSON files is preserved.

> **Project status:** pre-release (0.1.0-dev). The core workflow is implemented and tested with synthetic data. It has not had an independent security review. Check outputs by sample before sharing them. A passed residual scan does not prove that every sensitive value was detected.

## What it does

- **Consistent placeholders per project**: the same original value gets the same placeholder in every file and in later runs (`srv01` → `[Server_1]` everywhere). The numbering is independent of file order.
- **Structure preserved**: text files keep line endings, encoding (UTF-8, UTF-8 BOM, UTF-16, Windows-1252) and layout. In JSON and JSON Lines only string contents change; whitespace, numbers and structure stay byte-identical.
- **Detection**: IPv4/IPv6, MAC, e-mail, FQDNs, `DOMAIN\user`, UNC paths, domain SIDs, URL hosts, passwords/tokens in assignments and JSON fields, plus project name lists for short internal names (`dc01`, `svc_backup`). Values learned once are also replaced wherever they appear standalone.
- **Fail-closed**: every run re-scans its output for rule matches and all known original values. Only runs that pass every check get an `output` folder; failed or cancelled runs leave nothing, and blocked runs are clearly marked.
- **Large files**: blockwise streaming with flat memory use (~70 MB), spread across CPU cores. About 20 s per 200 MB on 10 cores; about 110 s on one core.
- **Sources are read-only**: they are never modified, moved or deleted.

## Running it (no installation, no admin rights)

The German user guide is in [docs/ANLEITUNG.md](docs/ANLEITUNG.md) (also included in every package).

Download the release ZIP from GitHub, copy it to the target system and extract it:

| Package | Contents | Start |
| --- | --- | --- |
| `LogSanitizer-<version>-windows-x64.zip` | app + embedded Python 3.12 | `start.bat` (UI), `selbsttest.bat`, `cli.bat …` |
| `LogSanitizer-<version>-portable.zip` | app only, needs Python 3.10+ | `./start.sh`, `./cli.sh selftest` |

Verify the ZIP after transfer with `SHA256SUMS.txt`. The server listens on `127.0.0.1` only and every API call requires the session token from the start link. Without a browser, the CLI offers the same functionality:

```bash
cli.sh sanitize --project "Kunde A" --names Server=server.txt --recursive /data/logs
cli.sh export-rules --project "Kunde A" regeln.json
cli.sh selftest
```

Projects live in `workspace/` next to the scripts. **This folder is confidential**: it holds the mapping from placeholders to original values. Only the `output` folder of a run marked ready may be shared.

## Technology

- Backend: Python 3.10+ **standard library only** (`http.server`, `sqlite3`, `re`, `multiprocessing`), so nothing has to be installed with pip on site.
- Frontend: React + TypeScript, built ahead of time and served by the backend (no Node.js on site).
- Metadata: SQLite mapping store and JSON project/rule files (versioned rule format).

## Development

```bash
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python -m pytest && python -m ruff check src tests

cd ../frontend
npm ci && npm test && npm run build

cd ..
python -m logsanitizer --workspace workspace serve   # with backend/src on PYTHONPATH or installed
```

`python -m logsanitizer samples DIR` generates synthetic logs in `DIR/logs` and name lists in `DIR/namenslisten` (fictitious company "Nordwerk"), and `--big-mb N` adds a large file for performance tests. Never commit real logs, name lists or mappings.

CI runs the backend tests on Linux and Windows (Python 3.10 and 3.12), builds the packages and runs the self-test from the unpacked Windows ZIP with the embedded Python. A tag `v*` publishes a GitHub release with both ZIPs and checksums.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), [docs/REQUIREMENTS.md](docs/REQUIREMENTS.md) and [docs/ROADMAP.md](docs/ROADMAP.md).

## Security principles

- Never upload log contents, secrets, name lists or mapping data to this repository.
- Source files are read-only inputs.
- Incomplete, failed or blocked runs must never be treated as releasable output.
- A successful validation scan is not proof that every sensitive value has been detected.

## License

No license has been selected yet. All rights reserved by default until a license is explicitly chosen.
