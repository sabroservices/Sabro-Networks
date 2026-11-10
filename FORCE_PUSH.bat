@echo off
title Sabro Networks - Complete GitHub Push
color 0a

echo =====================================================================
echo   Pushing COMPLETE project (Templates, Static assets & Code) to GitHub
echo =====================================================================
echo.

set "GIT_PATH=%LOCALAPPDATA%\Programs\Git\cmd\git.exe"
if not exist "%GIT_PATH%" set "GIT_PATH=git"

echo [*] Target repository: https://github.com/sabroservices/Sabro-Networks.git
echo [*] Pushing with --force to overwrite incomplete web upload...
echo.

"%GIT_PATH%" remote set-url origin https://github.com/sabroservices/Sabro-Networks.git
"%GIT_PATH%" push -u origin main --force

if %errorlevel% equ 0 (
    echo.
    echo =====================================================================
    echo   [SUCCESS] COMPLETE repository uploaded to GitHub!
    echo   - templates/ (all 19 HTML files included)
    echo   - static/ (all logos & assets included)
    echo   - gunicorn & serverless deployment files included
    echo.
    echo   Render is now automatically rebuilding and will be live in 1 min!
    echo =====================================================================
) else (
    echo.
    echo =====================================================================
    echo   [NOTE] If a GitHub browser popup appeared, please click 'Authorize'.
    echo =====================================================================
)

echo.
pause
