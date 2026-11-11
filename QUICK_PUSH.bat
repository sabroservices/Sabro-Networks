@echo off
setlocal enabledelayedexpansion
title Sabro Networks - 1-Click Push to GitHub & Auto-Deploy Render
color 0b

echo =====================================================================
echo   Sabro Networks FTTH - Instant Push to GitHub ^& Render Auto-Deploy
echo =====================================================================
echo.

set "GIT_PATH=%LOCALAPPDATA%\Programs\Git\cmd\git.exe"
if not exist "%GIT_PATH%" set "GIT_PATH=git"

echo [*] Staging all modified files...
"%GIT_PATH%" add .

set /p MSG="Enter commit message (Press Enter for auto timestamp): "
if "!MSG!"=="" (
    for /f "tokens=1-3 delims=/ " %%a in ('date /t') do set mydate=%%a-%%b-%%c
    for /f "tokens=1-2 delims=: " %%a in ('time /t') do set mytime=%%a:%%b
    set "MSG=update: portal changes on !mydate! !mytime!"
)

echo.
echo [*] Committing: "!MSG!"...
"%GIT_PATH%" commit -m "!MSG!"

echo.
echo [*] Syncing and pushing to GitHub (origin main)...
"%GIT_PATH%" pull --rebase origin main
"%GIT_PATH%" push origin main

if %errorlevel% equ 0 (
    echo.
    echo =====================================================================
    echo   [SUCCESS] Code pushed to GitHub!
    echo   Render is automatically deploying these updates right now!
    echo =====================================================================
) else (
    echo.
    echo [ERROR] Push failed. Please check network or GitHub credentials.
)

echo.
pause
