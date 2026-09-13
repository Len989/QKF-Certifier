@echo off
setlocal
cd /d "%~dp0"
where lake >nul 2>nul
if errorlevel 1 (
  echo Lean is not installed or this window needs to be reopened.
  echo Follow 00_START_HERE_RU.md, then run this file again.
  pause
  exit /b 1
)
call lake env lean --version > CHECK_LOG.txt 2>&1
if errorlevel 1 goto failed
call lake build >> CHECK_LOG.txt 2>&1
if errorlevel 1 goto failed
type CHECK_LOG.txt
echo.
echo QKF CHECK PASSED. Full log: CHECK_LOG.txt
pause
exit /b 0
:failed
type CHECK_LOG.txt
echo.
echo QKF CHECK FAILED. Send CHECK_LOG.txt for diagnosis.
pause
exit /b 1
