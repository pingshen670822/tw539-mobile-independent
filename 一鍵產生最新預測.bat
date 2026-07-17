@echo off
chcp 65001 >nul
cd /d "%~dp0"
where python >nul 2>nul
if not errorlevel 1 (
  python tw539_ultra.py
) else (
  py -3 tw539_ultra.py
)
if errorlevel 1 (
  echo.
  echo 執行失敗，請確認已安裝 Python 且 data\539.csv 存在。
  pause
  exit /b 1
)
start "" "reports\最新539科學預測戰報.html"
