@echo off
setlocal enabledelayedexpansion

chcp 65001 > nul 2>&1
title SpriteFrameStudio

cd /d %~dp0

REM Disable user site-packages to avoid conflicts
set "PYTHONNOUSERSITE=1"

echo.
echo ==========================================
echo   SpriteFrameStudio - Starting
echo ==========================================
echo.

REM Check for portable environment first
set "PORTABLE_ENV=%~dp0python_env"
if exist "!PORTABLE_ENV!\python.exe" (
    echo Using portable Python environment...
    set "PATH=!PORTABLE_ENV!;!PORTABLE_ENV!\Library\bin;!PORTABLE_ENV!\Scripts;!PATH!"
    set "PYTHONHOME=!PORTABLE_ENV!"
    set "PYTHONPATH=%~dp0src"
    echo.
    echo Starting application...
    "!PORTABLE_ENV!\python.exe" src/main.py
    pause
    exit /b 0
)

REM ========== Conda Mode ==========
set "CONDA_PATH=E:\software\miniconda3"

echo Portable environment not found, checking Conda...
echo.

REM Check if Conda exists
if not exist "!CONDA_PATH!\condabin\conda.bat" (
    echo Conda not found, trying to use portable python_env...
    echo.
    
    REM Try portable environment in portable_output folder
    set "PORTABLE_ENV=%~dp0portable_output\SpriteFrameStudio\python_env"
    if exist "!PORTABLE_ENV!\python.exe" (
        echo Found portable Python environment at: !PORTABLE_ENV!
        set "PATH=!PORTABLE_ENV!;!PORTABLE_ENV!\Library\bin;!PORTABLE_ENV!\Scripts;!PATH!"
        set "PYTHONHOME=!PORTABLE_ENV!"
        set "PYTHONPATH=%~dp0src"
        echo.
        echo Starting application...
        "!PORTABLE_ENV!\python.exe" src/main.py
        pause
        exit /b 0
    ) else (
        echo Error: No Python environment found!
        echo Neither Conda nor portable python_env is available.
        pause
        exit /b 1
    )
)

echo Found Conda at: !CONDA_PATH!
echo.

echo Activating spriteframe environment...
call "!CONDA_PATH!\condabin\conda.bat" activate spriteframe
if errorlevel 1 (
    echo Failed to activate spriteframe environment, trying portable python_env...
    echo.
    
    REM Try portable environment if conda env activation fails
    set "PORTABLE_ENV=%~dp0portable_output\SpriteFrameStudio\python_env"
    if exist "!PORTABLE_ENV!\python.exe" (
        echo Found portable Python environment at: !PORTABLE_ENV!
        set "PATH=!PORTABLE_ENV!;!PORTABLE_ENV!\Library\bin;!PORTABLE_ENV!\Scripts;!PATH!"
        set "PYTHONHOME=!PORTABLE_ENV!"
        set "PYTHONPATH=%~dp0src"
        echo.
        echo Starting application...
        "!PORTABLE_ENV!\python.exe" src/main.py
        pause
        exit /b 0
    ) else (
        echo Error: No Python environment found!
        pause
        exit /b 1
    )
)

echo Environment activated successfully
echo.

echo Starting application...
echo.

python src/main.py
pause

endlocal
