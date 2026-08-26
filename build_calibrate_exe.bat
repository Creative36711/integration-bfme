@echo off
rem ==========================================================================
rem  Сборка однофайлового калибратора:  dist\Calibrate\Calibrate.exe
rem
rem  Запуск: двойной клик. Нужны Python 3 (только на ЭТОЙ машине) и интернет.
rem  Результат - папка dist\Calibrate\ и архив dist\Calibrate.zip, которые
rem  можно отдать любому пользователю: Python и numpy ему не понадобятся.
rem ==========================================================================
setlocal EnableExtensions
chcp 65001 >nul
title Сборка Calibrate.exe (PyInstaller)
cd /d "%~dp0"

set "PYCMD="
if exist ".runtime\python\python.exe" set "PYCMD=".runtime\python\python.exe""
if not defined PYCMD (
    py -3 -c "import sys" >nul 2>&1
    if not errorlevel 1 set "PYCMD=py -3"
)
if not defined PYCMD (
    python -c "import sys" >nul 2>&1
    if not errorlevel 1 set "PYCMD=python"
)
if not defined PYCMD (
    echo [build] Python 3 не найден. Поставь его с https://www.python.org/downloads/
    echo [build] или сначала запусти calibrate.bat - он скачает портативный Python.
    pause
    exit /b 1
)
echo [build] Python: %PYCMD%

set "VENV=.build\venv"
set "VPY=%VENV%\Scripts\python.exe"
if not exist "%VPY%" (
    echo [build] создаю окружение сборки %VENV% ...
    %PYCMD% -m venv "%VENV%"
    if not exist "%VPY%" goto :err
)

echo [build] ставлю pyinstaller + numpy ...
"%VPY%" -m pip install --upgrade pip wheel >nul 2>&1
"%VPY%" -m pip install numpy pyinstaller
if errorlevel 1 goto :err

echo [build] собираю exe ...
"%VPY%" -m PyInstaller --noconfirm --clean --distpath dist --workpath ".build\pyi" "packaging\calibrate.spec"
if errorlevel 1 goto :err
if not exist "dist\calibrate.exe" goto :err

echo [build] собираю папку для раздачи ...
set "OUT=dist\Calibrate"
if exist "%OUT%" rmdir /s /q "%OUT%"
mkdir "%OUT%\config"
copy /y "dist\calibrate.exe" "%OUT%\Calibrate.exe" >nul
copy /y "packaging\dist_readme.txt" "%OUT%\README.txt" >nul
copy /y "config\config.json" "%OUT%\config\config.json" >nul
copy /y "config\menu_positions.json" "%OUT%\config\menu_positions.json" >nul
if exist "config\menu_marker.npy"  copy /y "config\menu_marker.npy"  "%OUT%\config\" >nul
if exist "config\menu_marker.json" copy /y "config\menu_marker.json" "%OUT%\config\" >nul

powershell -NoProfile -ExecutionPolicy Bypass -Command "if (Test-Path 'dist\Calibrate.zip') { Remove-Item 'dist\Calibrate.zip' -Force }; Compress-Archive -Path 'dist\Calibrate\*' -DestinationPath 'dist\Calibrate.zip'"

echo.
echo [build] ГОТОВО
echo [build]   exe:   %~dp0%OUT%\Calibrate.exe
echo [build]   архив: %~dp0dist\Calibrate.zip   ^(его и раздаём^)
echo [build] Папку Calibrate можно положить куда угодно - exe ищет игру
echo [build] в реестре и в config\config.json, маркеры пишет в config\.
echo.
pause
exit /b 0

:err
echo.
echo [build] ОШИБКА сборки - смотри вывод выше.
echo [build] Частые причины: нет интернета ^(pip^), блокировка антивирусом,
echo [build] старый Python ^(нужен 3.8+^).
pause
exit /b 1
