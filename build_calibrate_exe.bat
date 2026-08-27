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

set "BUILD_PY="
set "VENV=.build\venv"
set "VPY=%VENV%\Scripts\python.exe"

rem 1. Проверяем существующий venv
if exist "%VPY%" (
    "%VPY%" -m pip --version >nul 2>&1
    if not errorlevel 1 set "BUILD_PY=%VPY%"
)

rem 2. Если в venv нет pip, пробуем восстановить ensurepip
if not defined BUILD_PY if exist "%VPY%" (
    "%VPY%" -m ensurepip --default-pip >nul 2>&1
    "%VPY%" -m pip --version >nul 2>&1
    if not errorlevel 1 set "BUILD_PY=%VPY%"
)

rem 3. Если venv сломан, удаляем и пересоздаём
if not defined BUILD_PY (
    if exist "%VENV%" rmdir /s /q "%VENV%"
    echo [build] создаю окружение сборки %VENV% ...
    %PYCMD% -m venv "%VENV%"
    if exist "%VPY%" (
        "%VPY%" -m pip --version >nul 2>&1
        if not errorlevel 1 set "BUILD_PY=%VPY%"
        if not defined BUILD_PY (
            "%VPY%" -m ensurepip --default-pip >nul 2>&1
            "%VPY%" -m pip --version >nul 2>&1
            if not errorlevel 1 set "BUILD_PY=%VPY%"
        )
    )
)

rem 4. Если venv без pip, используем системный Python
if not defined BUILD_PY (
    echo [build] venv не настроил pip, использую Python напрямую ...
    %PYCMD% -m pip --version >nul 2>&1
    if errorlevel 1 %PYCMD% -m ensurepip --default-pip >nul 2>&1
    %PYCMD% -m pip --version >nul 2>&1
    if not errorlevel 1 set "BUILD_PY=%PYCMD%"
)

rem 5. Если pip всё ещё нет, скачиваем get-pip.py
if not defined BUILD_PY (
    echo [build] пробую установить pip через get-pip.py ...
    powershell -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop';[Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12;Invoke-WebRequest -Uri 'https://bootstrap.pypa.io/get-pip.py' -OutFile '%TEMP%\get-pip.py'" >nul 2>&1
    if exist "%TEMP%\get-pip.py" (
        %PYCMD% "%TEMP%\get-pip.py" --no-warn-script-location >nul 2>&1
        %PYCMD% -m pip --version >nul 2>&1
        if not errorlevel 1 set "BUILD_PY=%PYCMD%"
    )
)

if not defined BUILD_PY (
    echo [build] ОШИБКА: pip не найден для %PYCMD%.
    goto :err
)

echo [build] ставлю pyinstaller + numpy ...
%BUILD_PY% -m pip install --upgrade pip wheel >nul 2>&1
%BUILD_PY% -m pip install numpy pyinstaller
if errorlevel 1 (
    echo [build] повторная попытка установки...
    %BUILD_PY% -m pip install numpy pyinstaller
)
if errorlevel 1 goto :err

echo [build] собираю exe ...
%BUILD_PY% -m PyInstaller --noconfirm --clean --distpath dist --workpath ".build\pyi" "packaging\calibrate.spec"
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
