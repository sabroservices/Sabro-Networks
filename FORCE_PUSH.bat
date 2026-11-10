@echo off
title Push All Fixes to GitHub
color 0a

echo =====================================================================
echo   Pushing all 6 bug fixes to GitHub...
echo =====================================================================
echo.

set "GIT_PATH=%LOCALAPPDATA%\Programs\Git\cmd\git.exe"
if not exist "%GIT_PATH%" set "GIT_PATH=git"

"%GIT_PATH%" push -u origin main

if %errorlevel% equ 0 (
    echo.
    echo =====================================================================
    echo   [SUCCESS] All fixes uploaded to GitHub!
    echo   Render is now automatically updating your live website!
    echo =====================================================================
) else (
    echo.
    echo [ERROR] Push failed. If a browser window opened, please authorize GitHub.
)

echo.
pause
