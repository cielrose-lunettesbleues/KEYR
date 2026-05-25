@echo off
cd /d "%~dp0"
title Short Editor - Learn Batch
set "LOG_FILE=%~dp0learn_shorts.log"
echo [%date% %time%] Starting learn > "%LOG_FILE%"

where py >nul 2>nul
if %errorlevel%==0 (
  py -3 -m short_editor.cli learn --config config\pipeline.json --feedback feedback\latest_feedback.csv >> "%LOG_FILE%" 2>&1
) else (
  where python >nul 2>nul
  if %errorlevel%==0 (
    python -m short_editor.cli learn --config config\pipeline.json --feedback feedback\latest_feedback.csv >> "%LOG_FILE%" 2>&1
  ) else (
    echo Python launcher not found. Install Python or py launcher. >> "%LOG_FILE%"
    type "%LOG_FILE%"
    echo.
    echo Done. Press any key to close.
    pause >nul
    exit /b 1
  )
)

type "%LOG_FILE%"
echo.
echo Done.
