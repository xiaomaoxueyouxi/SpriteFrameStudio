@echo off
setlocal enabledelayedexpansion

chcp 65001 > nul 2>&1
title SpriteFrameStudio

cd /d %~dp0

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

echo Portable environment not found, using Conda...
echo.

echo Checking Conda path...
if not exist "!CONDA_PATH!\condabin\conda.bat" (
    echo Error: Conda not found at !CONDA_PATH!
    echo Please check your Miniconda installation path
    echo.
    echo How to fix:
    echo 1. Open Anaconda Prompt or Miniconda command line
    echo 2. Run: echo %%CONDA_PREFIX%%
    echo 3. Copy the path
    echo 4. Edit run.bat with the correct path
    echo.
    pause
    exit /b 1
)

echo Found Conda at: !CONDA_PATH!
echo.

echo Activating spriteframe environment...
call "!CONDA_PATH!\condabin\conda.bat" activate spriteframe
if errorlevel 1 (
    echo Error: Failed to activate environment spriteframe
    echo.
    echo Please run: "!CONDA_PATH!\condabin\conda.bat" env list
    echo to see available environments
    echo.
    pause
    exit /b 1
)

echo Environment activated successfully
echo.

echo Starting application...
echo.

python src/main.py
pause

endlocal
