@echo off
rem ==========================================================================
rem  Сборка однофайлового калибратора:  dist\Calibrate\Calibrate.exe
rem
rem  Запуск: двойной клик. Нужен интернет (для загрузки pyinstaller/numpy).
rem  Если системный Python отсутствует или сломан, скрипт автоматически
rem  скачает чистый портативный Python в .runtime\ и соберёт exe.
rem
rem  Результат - папка dist\Calibrate\ и архив dist\Calibrate.zip, которые
rem  можно отдать любому пользователю: Python и numpy ему не понадобятся.
rem ==========================================================================
setlocal EnableExtensions
chcp 65001 >nul
title Сборка Calibrate.exe (PyInstaller)
cd /d "%~dp0"

set "RUNTIME=%~dp0.runtime\python"
set "RUNTIME_PY=%RUNTIME%\python.exe"
set "PY_URLS=https://www.python.org/ftp/python/3.12.10/python-3.12.10-embed-amd64.zip https://www.python.org/ftp/python/3.11.9/python-3.11.9-embed-amd64.zip"

set "PYCMD="

rem 1. Проверяем готовый портативный Python в .runtime\
if exist "%RUNTIME_PY%" (
    "%RUNTIME_PY%" -m pip --version >nul 2>&1
    if not errorlevel 1 (
        set "PYCMD="%RUNTIME_PY%""
        echo [build] Использую портативный Python: .runtime\python
    )
)

rem 2. Проверяем системный Python (py -3 или python)
if not defined PYCMD (
    py -3 -m pip --version >nul 2>&1
    if not errorlevel 1 (
        set "PYCMD=py -3"
        echo [build] Найден системный Python: py -3
    )
)
if not defined PYCMD (
    python -m pip --version >nul 2>&1
    if not errorlevel 1 (
        set "PYCMD=python"
        echo [build] Найден системный Python: python
    )
)

rem 3. Если системный Python есть, но без pip — пробуем ensurepip
if not defined PYCMD (
    py -3 -c "import sys" >nul 2>&1
    if not errorlevel 1 (
        echo [build] В py -3 нет pip, пробую восстановить ensurepip...
        py -3 -m ensurepip --default-pip >nul 2>&1
        py -3 -m pip --version >nul 2>&1
        if not errorlevel 1 set "PYCMD=py -3"
    )
)
if not defined PYCMD (
    python -c "import sys" >nul 2>&1
    if not errorlevel 1 (
        echo [build] В python нет pip, пробую восстановить ensurepip...
        python -m ensurepip --default-pip >nul 2>&1
        python -m pip --version >nul 2>&1
        if not errorlevel 1 set "PYCMD=python"
    )
)

rem 4. Если Python нет или pip сломан — скачиваем портативный Python в .runtime\
if not defined PYCMD (
    echo [build] Системный Python не найден или не имеет рабочего pip.
    echo [build] Скачиваю чистый портативный Python в .runtime\ ...
    call :bootstrap_python
)

if not defined PYCMD (
    echo.
    echo [build] ОШИБКА: Не удалось инициализировать Python с pip.
    goto :err
)

rem 5. Пробуем создать изолированный venv, если это не embed-python
set "BUILD_PY=%PYCMD%"
set "VENV=.build\venv"
set "VPY=%VENV%\Scripts\python.exe"

if not exist "%RUNTIME_PY%" (
    if exist "%VENV%" rmdir /s /q "%VENV%" >nul 2>&1
    %PYCMD% -m venv "%VENV%" >nul 2>&1
    if exist "%VPY%" (
        "%VPY%" -m pip --version >nul 2>&1
        if not errorlevel 1 (
            set "BUILD_PY="%VPY%""
        )
    )
)

echo [build] ставлю pyinstaller + numpy ...
%BUILD_PY% -m pip install --upgrade pip wheel >nul 2>&1
%BUILD_PY% -m pip install --no-warn-script-location numpy pyinstaller
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

:bootstrap_python
if not exist "%~dp0.runtime" mkdir "%~dp0.runtime"
set "RT_ZIP=%TEMP%\python-embed-amd64.zip"
for %%U in (%PY_URLS%) do (
    if not exist "%RUNTIME_PY%" (
        echo [build]   качаю %%U ...
        powershell -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop';[Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12;Invoke-WebRequest -Uri '%%U' -OutFile '%RT_ZIP%';Expand-Archive -LiteralPath '%RT_ZIP%' -DestinationPath '%RUNTIME%' -Force"
    )
)
if not exist "%RUNTIME_PY%" exit /b 1
powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-ChildItem -Path '%RUNTIME%' -Filter '*._pth' | ForEach-Object { (Get-Content -LiteralPath $_.FullName) -replace '^\s*#\s*import site','import site' | Set-Content -LiteralPath $_.FullName -Encoding ASCII }"
echo [build]   ставлю pip...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop';[Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12;Invoke-WebRequest -Uri 'https://bootstrap.pypa.io/get-pip.py' -OutFile '%TEMP%\get-pip.py'"
if not exist "%TEMP%\get-pip.py" exit /b 1
"%RUNTIME_PY%" "%TEMP%\get-pip.py" --no-warn-script-location >nul 2>&1
set "PYCMD="%RUNTIME_PY%""
exit /b 0

:err
echo.
echo [build] ОШИБКА сборки - смотри вывод выше.
echo [build] Частые причины: нет интернета ^(pip^), блокировка антивирусом,
echo [build] старый Python ^(нужен 3.8+^).
pause
exit /b 1
