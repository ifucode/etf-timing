@echo off
cd /d "%~dp0"

set "PY="
where python >nul 2>&1 && set "PY=python"
if not defined PY ( where py >nul 2>&1 && set "PY=py" )
if not defined PY ( if exist "D:/ProgramData/anaconda3/python.exe" set "PY=D:/ProgramData/anaconda3/python.exe" )
if not defined PY ( if exist "C:/Users/iszho/.workbuddy/binaries/python/versions/3.13.12/python.exe" set "PY=C:/Users/iszho/.workbuddy/binaries/python/versions/3.13.12/python.exe" )
if not defined PY ( if exist "C:/Users/iszho/.workbuddy/binaries/python/versions/3.11.7/python.exe" set "PY=C:/Users/iszho/.workbuddy/binaries/python/versions/3.11.7/python.exe" )
if not defined PY (
  echo [ERROR] Python not found. Install Python 3 or add it to PATH.
  pause
  exit /b 1
)

echo ============================================
echo   ETF timing dashboard - one-click update
echo   Re-fetch quotes and regenerate index.html / data.json
echo ============================================

if exist fuyao_key.txt (
  set /p FUYAO_API_KEY=<fuyao_key.txt
)

echo.
echo [1/2] Fetching quotes + building matrix ...
%PY% fetch_data.py

echo.
echo [2/2] Fill small-cap ETF today bar (520830) ...
%PY% fill_today.py 520830

echo.
echo Done. index.html / data.json updated.
echo Press any key to close ...
pause >nul
