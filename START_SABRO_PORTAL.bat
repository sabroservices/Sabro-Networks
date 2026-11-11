@echo off
title Sabro Networks - FTTH Operations & Billing System
color 1f
echo ===============================================================
echo     Sabro Networks (FTTH)
echo     Enterprise Billing, Recovery, Ticketing & NOC Portal
echo ===============================================================
echo.
echo Authenticated Admin Login Enabled (Username: ahmedbaloch)
echo.
echo Starting local web server on http://localhost:5000 ...
echo Press Ctrl+C in this window anytime to stop the server.
echo.

start "" "http://localhost:5000"
python app.py

pause
