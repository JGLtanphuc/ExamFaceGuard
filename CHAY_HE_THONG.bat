@echo off
title HE THONG GIAM SAT THI
cd /d "%~dp0"
cls
echo ======================================================================
echo    DANG KHOI DONG HE THONG VA MO LINK TRUY CAP TU DONG...
echo ======================================================================
echo.
python -u launcher.py
if errorlevel 1 (
    echo.
    echo [ERROR] Khong the khoi dong launcher.py bang Python!
    pause
)
