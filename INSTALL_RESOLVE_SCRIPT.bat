@echo off
setlocal
cd /d "%~dp0"

set "TARGET_DIR=%APPDATA%\Blackmagic Design\DaVinci Resolve\Support\Fusion\Scripts\Utility"
if not exist "%TARGET_DIR%" mkdir "%TARGET_DIR%"

copy /Y "resolve_integration\run_shorts_batch_resolve.py" "%TARGET_DIR%\run_shorts_batch_resolve.py" >nul

set "CFG_FILE=%TARGET_DIR%\short_editor_resolve_config.json"
> "%CFG_FILE%" echo {
>> "%CFG_FILE%" echo   "project_root": "%CD:\=\\%"
>> "%CFG_FILE%" echo }

echo Installed Resolve script to:
echo %TARGET_DIR%\run_shorts_batch_resolve.py
echo Config written to:
echo %CFG_FILE%
echo.
echo In Resolve: Workspace - Scripts - Utility - run_shorts_batch_resolve
echo.
echo Done. Press any key to close.
pause >nul
