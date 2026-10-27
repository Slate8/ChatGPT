# Backend

Python 3.10+ using only the standard library at runtime.

```bash
python -m venv .venv
# Windows PowerShell: .venv\Scripts\Activate.ps1
# Linux: source .venv/bin/activate
python -m pip install -e ".[dev]"
python -m pytest
python -m ruff check src tests
```

Run it:

```bash
python -m logsanitizer --workspace ../workspace serve        # web UI on 127.0.0.1:8765
python -m logsanitizer selftest                              # synthetic end-to-end test
python -m logsanitizer samples /tmp/samples --big-mb 500     # synthetic data
python -m logsanitizer --workspace ../workspace sanitize --project demo -r /tmp/samples
```

The UI is served from `../frontend/dist` (override with `LOGSANITIZER_STATIC`). Set `LOGSANITIZER_WORKERS` to force a number of worker processes.
