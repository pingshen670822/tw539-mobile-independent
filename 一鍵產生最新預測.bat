@echo off
chcp 65001 >nul
cd /d "%~dp0"
where python >nul 2>nul
if not errorlevel 1 (
  python cloud_pipeline.py --strict-freshness
) else (
  py -3 cloud_pipeline.py --strict-freshness
)
if errorlevel 1 (
  echo.
  echo 執行失敗，請確認已安裝 Python 且 data\539.csv 存在。
  pause
  exit /b 1
)
start "" "reports\最新539科學預測戰報.html"
