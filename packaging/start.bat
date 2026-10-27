@echo off
rem Starts the LogSanitizer web interface (only reachable from this computer).
call "%~dp0cli.bat" serve %*
if errorlevel 1 pause
