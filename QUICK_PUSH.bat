@echo off
title Sabro Networks - 1-Click Fast Push to GitHub & Live Website
color 0b

echo =====================================================================
echo   Sabro Networks FTTH - Instant Push to GitHub & Live Website
echo =====================================================================
echo.

set "GIT_PATH=%LOCALAPPDATA%\Programs\Git\cmd\git.exe"
if not exist "%GIT_PATH%" set "GIT_PATH=git"

echo [*] Staging all modified files...
"%GIT_PATH%" add .

set /p MSG="Enter commit message (Press Enter for auto timestamp): "
if "%MSG%"=="" (
    for /f "tokens=1-4 delims=/ " %%a in ('date /t') do set mydate=%%a-%%b-%%c
    for /f "tokens=1-2 delims=: " %%a in ('time /t') do set mytime=%%a:%%b
    set "MSG=update: portal changes on !mydate! !mytime!"
)

echo.
echo [*] Committing: "%MSG%"...
"%GIT_PATH%" commit -m "%MSG%"

echo.
echo [*] Pushing to GitHub (origin main)...
"%GIT_PATH%" push origin main

if %errorlevel% equ 0 (
    echo.
    echo =====================================================================
    echo   [SUCCESS] Code pushed to GitHub!
    echo   Your live cloud website (Vercel / Render) is updating right now!
    echo =====================================================================
) else (
    echo.
    echo [ERROR] Push failed. Please check network or GitHub credentials.
)

echo.
pause
