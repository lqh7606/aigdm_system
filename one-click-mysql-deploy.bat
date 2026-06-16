@echo off
setlocal
chcp 65001 >nul
title AIGDM Launcher
cd /d "%~dp0"
echo AIGDM MySQL visual launcher
echo Current directory: %CD%
echo.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\one_click_mysql_deploy.ps1" %*
set "AIGDM_EXIT_CODE=%ERRORLEVEL%"
echo.
echo AIGDM script exited with code: %AIGDM_EXIT_CODE%
pause
exit /b %AIGDM_EXIT_CODE%
