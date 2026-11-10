@echo off
title Sabro Networks - Real-Time Git & CI/CD Auto-Sync
color 0a

echo =====================================================================
echo   Sabro Networks FTTH - Real-Time Git & Cloud Deployment Sync
echo =====================================================================
echo.
echo Whenever you save a file, this script will automatically:
echo   1. Detect changes within 3 seconds
echo   2. Commit changes
echo   3. Push to GitHub (main)
echo   4. Trigger real-time redeployment on Vercel / Render!
echo.
echo Leave this window open while working. Press Ctrl+C anytime to stop.
echo.

python auto_git_sync.py
if %errorlevel% neq 0 (
    echo.
    echo Python was not found directly, trying local path...
    "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" auto_git_sync.py
)

pause
