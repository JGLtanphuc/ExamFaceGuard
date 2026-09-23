@echo off
chcp 65001 > nul
title Cloudflare Tunnel - He Thong Giam Sat Thi
echo ======================================================================
echo   DANG TAO DUONG HAM CLOUDFLARE TUNNEL (HTTPS MIEN PHI TOAN CAU)
echo ======================================================================
echo.
echo [*] Luu y: Hay dam bao server "python run.py" dang bat o mot cua so khac!
echo [*] Dang ket noi toi Cloudflare de tao duong link HTTPS...
echo.
.\cloudflared.exe tunnel --url http://localhost:8000
pause
