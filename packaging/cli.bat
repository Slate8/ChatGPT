@echo off
rem LogSanitizer command line. Uses the bundled Python if present.
setlocal
set "APP=%~dp0"
set "PYTHONPATH=%APP%backend\src"
if exist "%APP%python\python.exe" (
  "%APP%python\python.exe" -m logsanitizer --workspace "%APP%workspace" %*
) else (
  where py >nul 2>nul
  if not errorlevel 1 (
    py -3 -m logsanitizer --workspace "%APP%workspace" %*
  ) else (
    python -m logsanitizer --workspace "%APP%workspace" %*
  )
)
exit /b %errorlevel%
