@echo off
title Push Sabro Networks to GitHub
color 0a

echo =====================================================================
echo   Pushing Sabro Networks to https://github.com/sabroservices/Sabro-Networks
echo =====================================================================
echo.

set "GIT_PATH=%LOCALAPPDATA%\Programs\Git\cmd\git.exe"
if not exist "%GIT_PATH%" set "GIT_PATH=git"

"%GIT_PATH%" push -u origin main

if %errorlevel% equ 0 (
    echo.
    echo =====================================================================
    echo   [SUCCESS] Uploaded to GitHub successfully!
    echo =====================================================================
) else (
    echo.
    echo =====================================================================
    echo   [NOTE] If authentication is needed, please approve the browser prompt.
    echo =====================================================================
)

echo.
pause
