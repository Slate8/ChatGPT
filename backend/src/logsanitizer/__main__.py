import sys

# Intentional although pyproject requires 3.10: the portable package can be started
# with whatever Python is on the system, and older versions should fail clearly.
if sys.version_info < (3, 10):  # noqa: UP036
    sys.exit("LogSanitizer benötigt Python 3.10 oder neuer "
             f"(gefunden: {sys.version.split()[0]}).")

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
