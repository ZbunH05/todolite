@echo off
rem Nhap dup de cai dat TodoLite. Chay lai sau khi nang cap Python hoac chuyen thu muc.
chcp 65001 >nul
cd /d "%~dp0"
set "PY=python"
where py >nul 2>nul && set "PY=py -3"
%PY% tools\setup.py %*
if errorlevel 1 (
    echo.
    echo Cai dat that bai. Xem thong bao loi o tren.
    pause
    exit /b 1
)
timeout /t 3 >nul 2>nul
exit /b 0
