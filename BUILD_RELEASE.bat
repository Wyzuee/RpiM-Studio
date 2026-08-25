@echo off
setlocal
cd /d "%~dp0"
title RpiM Studio - Release Builder
where py >nul 2>&1
if not errorlevel 1 (
  py -3 BUILD_RELEASE.py
) else (
  python BUILD_RELEASE.py
)
if errorlevel 1 (
  echo.
  echo Build basarisiz. Yukaridaki hata mesajini kontrol edin.
  pause
  exit /b 1
)
pause
