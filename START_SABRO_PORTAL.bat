@echo off
title Sabro Networks Powered By Connect - FTTH Billing System
color 6f
echo ===============================================================
echo     Sabro Networks Powered By Connect (FTTH)
echo     Enterprise Billing, Recovery, Ticketing & Staff Logins
echo ===============================================================
echo.
echo Default Login Credentials:
echo   - Admin:         Username: admin       Password: admin123
echo   - Complain Boy:  Username: rashid.tech Password: tech123
echo   - Recovery Boy:  Username: shahzaib    Password: rec123
echo.
echo Starting local web server on http://localhost:5000 ...
echo Press Ctrl+C in this window anytime to stop the server.
echo.

start "" "http://localhost:5000"
python app.py

pause
