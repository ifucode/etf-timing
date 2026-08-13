@echo off
chcp 936 >nul
cd /d "%~dp0"

set "PY="
where python >nul 2>&1 && set "PY=python"
if not defined PY ( where py >nul 2>&1 && set "PY=py" )
if not defined PY ( if exist "D:\ProgramData\anaconda3\python.exe" set "PY=D:\ProgramData\anaconda3\python.exe" )
if not defined PY ( if exist "C:\Users\iszho\.workbuddy\binaries\python\versions\3.13.12\python.exe" set "PY=C:\Users\iszho\.workbuddy\binaries\python\versions\3.13.12\python.exe" )
if not defined PY ( if exist "C:\Users\iszho\.workbuddy\binaries\python\versions\3.11.7\python.exe" set "PY=C:\Users\iszho\.workbuddy\binaries\python\versions\3.11.7\python.exe" )
if not defined PY (
  echo [错误] 未找到 Python，请安装 Python 3 或确认已加入 PATH
  pause
  exit /b 1
)

echo ============================================
echo   ETF 择时看板 - 一键更新数据
echo   重新抓取行情并生成 index.html / data.json
echo ============================================

if exist fuyao_key.txt (
  set /p FUYAO_API_KEY=<fuyao_key.txt
)

echo.
echo [1/2] 抓取行情 + 生成矩阵 ...
%PY% fetch_data.py

echo.
echo [2/2] 兜底补齐小众标的当日(520830) ...
%PY% fill_today.py 520830

echo.
echo 完成。index.html / data.json 已更新。
echo 按任意键关闭窗口...
pause >nul
