@echo off
setlocal enabledelayedexpansion
title Sabro Networks - GitHub Repository Uploader
color 0b

echo =====================================================================
echo   Sabro Networks FTTH - GitHub Repository Push Wizard
echo =====================================================================
echo.

:: Check Git availability
where git >nul 2>nul
if %errorlevel% neq 0 (
    set "GIT_PATH=%LOCALAPPDATA%\Programs\Git\cmd\git.exe"
) else (
    set "GIT_PATH=git"
)

if not exist "!GIT_PATH!" (
    where git >nul 2>nul
    if %errorlevel% neq 0 (
        echo [ERROR] Git was not found in your PATH or LocalAppData.
        pause
        exit /b 1
    )
)

echo [1/4] Checking Git repository status...
"!GIT_PATH!" status
echo.

echo [2/4] Enter your GitHub Repository URL.
echo Examples:
echo   https://github.com/your-username/sabro-networks.git
echo   git@github.com:your-username/sabro-networks.git
echo.
set /p REPO_URL="Paste GitHub Repo URL here: "

if "%REPO_URL%"=="" (
    echo [ERROR] No repository URL provided. Aborted.
    pause
    exit /b 1
)

echo.
echo [3/4] Configuring remote 'origin'...
"!GIT_PATH!" remote remove origin 2>nul
"!GIT_PATH!" remote add origin %REPO_URL%
"!GIT_PATH!" branch -M main

echo.
echo [4/4] Pushing code to GitHub (branch: main)...
"!GIT_PATH!" push -u origin main

if %errorlevel% equ 0 (
    echo.
    echo =====================================================================
    echo   [SUCCESS] Your repository has been pushed to GitHub successfully!
    echo =====================================================================
) else (
    echo.
    echo [NOTE] If GitHub asked for authentication, sign in via browser or personal access token.
)

echo.
pause
