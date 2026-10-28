@echo off
rem ============================================================
rem  Windows side: push the A100-made git bundle to GitHub
rem  Usage:  push-bundle.cmd [-DryRun] [-NoSync] [-Bundle path] [-Branch name] [-Repo path]
rem  Example: push-bundle.cmd -DryRun
rem ============================================================
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0push-bundle.ps1" %*
exit /b %ERRORLEVEL%
