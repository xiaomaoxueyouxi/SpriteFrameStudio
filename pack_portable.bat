@echo off
setlocal enabledelayedexpansion

chcp 65001 > nul 2>&1
title SpriteFrameStudio - Portable Pack Tool

echo.
echo ==========================================
echo   SpriteFrameStudio Portable Pack Tool
echo ==========================================
echo.

REM ========== Configuration ==========
set "CONDA_PATH=E:\software\miniconda3"
set "ENV_NAME=spriteframe"
set "OUTPUT_DIR=%~dp0portable_output"
REM ===================================

set "SOURCE_ENV=%CONDA_PATH%\envs\%ENV_NAME%"

echo [1/5] Checking source environment...
if not exist "!SOURCE_ENV!\python.exe" (
    echo Error: Environment not found at !SOURCE_ENV!
    echo Please check CONDA_PATH and ENV_NAME settings
    pause
    exit /b 1
)
echo Found: !SOURCE_ENV!
echo.

echo [2/5] Creating output directory...
if exist "!OUTPUT_DIR!" (
    echo Output directory exists, cleaning...
    rmdir /s /q "!OUTPUT_DIR!" 2>nul
)
mkdir "!OUTPUT_DIR!"
mkdir "!OUTPUT_DIR!\SpriteFrameStudio"
echo Done.
echo.

echo [3/5] Copying Python environment...
echo This may take 10-20 minutes, please wait...
xcopy "!SOURCE_ENV!" "!OUTPUT_DIR!\SpriteFrameStudio\python_env\" /E /H /C /I /Q /Y
if errorlevel 1 (
    echo Error: Failed to copy environment
    pause
    exit /b 1
)
echo Done.
echo.

echo [4/5] Copying project files...
xcopy "%~dp0src" "!OUTPUT_DIR!\SpriteFrameStudio\src\" /E /H /C /I /Q /Y
xcopy "%~dp0models" "!OUTPUT_DIR!\SpriteFrameStudio\models\" /E /H /C /I /Q /Y 2>nul
xcopy "%~dp0config" "!OUTPUT_DIR!\SpriteFrameStudio\config\" /E /H /C /I /Q /Y 2>nul
xcopy "%~dp0assets" "!OUTPUT_DIR!\SpriteFrameStudio\assets\" /E /H /C /I /Q /Y 2>nul
copy "%~dp0run.bat" "!OUTPUT_DIR!\SpriteFrameStudio\" /Y
copy "%~dp0README.md" "!OUTPUT_DIR!\SpriteFrameStudio\" /Y 2>nul

REM Copy rtmlib to project root (for dynamic import in pose_detector.py)
echo Copying rtmlib...
xcopy "%~dp0rtmlib" "!OUTPUT_DIR!\SpriteFrameStudio\rtmlib\" /E /H /C /I /Q /Y
echo Done.
echo.

echo [5/5] Cleaning unnecessary files...
REM Remove conda metadata
rmdir /s /q "!OUTPUT_DIR!\SpriteFrameStudio\python_env\conda-meta" 2>nul
REM Remove __pycache__
for /d /r "!OUTPUT_DIR!\SpriteFrameStudio" %%d in (__pycache__) do @if exist "%%d" rmdir /s /q "%%d"
REM Remove .pyc files
del /s /q "!OUTPUT_DIR!\SpriteFrameStudio\*.pyc" 2>nul
echo Done.
echo.

echo ==========================================
echo   Pack Complete!
echo ==========================================
echo.
echo Output location: !OUTPUT_DIR!\SpriteFrameStudio
echo.
echo Next steps:
echo 1. Compress SpriteFrameStudio folder to zip
echo 2. Share the zip file with users
echo 3. Users extract and run run.bat directly
echo.
echo Estimated size: 15-20 GB (GPU version with CUDA)
echo.

pause
endlocal
