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

echo [1/3] Linked Repository:
set "REPO_URL=https://github.com/vshatkaysolutions-alt/Sabro-Networks.git"
echo %REPO_URL%
echo.

echo [2/3] Configuring remote 'origin' and main branch...
"!GIT_PATH!" remote remove origin 2>nul
"!GIT_PATH!" remote add origin %REPO_URL%
"!GIT_PATH!" branch -M main

echo.
echo [3/3] Pushing all files to GitHub...
echo (If a browser window opens, please click 'Sign in with browser' to approve)
echo.
"!GIT_PATH!" push -u origin main

if %errorlevel% equ 0 (
    echo.
    echo =====================================================================
    echo   [SUCCESS] Your repository has been pushed to GitHub successfully!
    echo   Visit: https://github.com/vshatkaysolutions-alt/Sabro-Networks
    echo =====================================================================
) else (
    echo.
    echo =====================================================================
    echo   [NOTE] If authentication failed, please verify you have write
    echo   access to vshatkaysolutions-alt/Sabro-Networks, or sign in via browser.
    echo =====================================================================
)

echo.
pause
