@echo off
rem ==========================================================================
rem  Сборка однофайлового приложения моста: dist\Main\Main.exe
rem
rem  Запуск: двойной клик. Нужны Python 3 (только на ЭТОЙ машине) и интернет.
rem  Результат - папка dist\Main\ и архив dist\Main.zip, которые
rem  можно отдать любому пользователю: Python и numpy ему не понадобятся.
rem ==========================================================================
setlocal EnableExtensions
chcp 65001 >nul
title Сборка Main.exe (PyInstaller)
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
"%VPY%" -m PyInstaller --noconfirm --clean --distpath dist --workpath ".build\pyi_main" "packaging\main.spec"
if errorlevel 1 goto :err
if not exist "dist\Main.exe" goto :err

echo [build] собираю папку для раздачи ...
set "OUT=dist\Main"
if exist "%OUT%" rmdir /s /q "%OUT%"
mkdir "%OUT%\config"
copy /y "dist\Main.exe" "%OUT%\Main.exe" >nul
copy /y "packaging\main_readme.txt" "%OUT%\README.txt" >nul
copy /y "config\config.json" "%OUT%\config\config.json" >nul
copy /y "config\menu_positions.json" "%OUT%\config\menu_positions.json" >nul
if exist "config\menu_marker.npy"  copy /y "config\menu_marker.npy"  "%OUT%\config\" >nul
if exist "config\menu_marker.json" copy /y "config\menu_marker.json" "%OUT%\config\" >nul
if exist "_coordinates.txt" copy /y "_coordinates.txt" "%OUT%\" >nul
if exist "coordinates.txt" copy /y "coordinates.txt" "%OUT%\" >nul

powershell -NoProfile -ExecutionPolicy Bypass -Command "if (Test-Path 'dist\Main.zip') { Remove-Item 'dist\Main.zip' -Force }; Compress-Archive -Path 'dist\Main\*' -DestinationPath 'dist\Main.zip'"

echo.
echo [build] ГОТОВО
echo [build]   exe:   %~dp0%OUT%\Main.exe
echo [build]   архив: %~dp0dist\Main.zip   ^(его и раздаём^)
echo [build] Exe ищет coordinates.txt или _coordinates.txt рядом с собой.
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
