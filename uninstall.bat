@echo off
rem Go TodoLite khoi Windows. Du lieu task duoc giu nguyen.
chcp 65001 >nul
cd /d "%~dp0"
set "PY=python"
where py >nul 2>nul && set "PY=py -3"
%PY% tools\setup.py --uninstall
pause
