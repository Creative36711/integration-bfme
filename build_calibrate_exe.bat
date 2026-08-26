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

set "PY_URLS=https://www.python.org/ftp/python/3.12.10/python-3.12.10-embed-amd64.zip https://www.python.org/ftp/python/3.11.9/python-3.11.9-embed-amd64.zip"
set "RUNTIME=%~dp0.runtime\python"
set "RUNTIME_PY=%RUNTIME%\python.exe"

set "PYCMD="
if exist "%RUNTIME_PY%" set "PYCMD="%RUNTIME_PY%""

rem Ищем поддерживаемый стабильный Python (3.12, 3.11, 3.10, 3.9, 3.8)
if not defined PYCMD (
    for %%V in (3.12 3.11 3.10 3.9 3.8) do (
        if not defined PYCMD (
            py -%%V -c "import sys" >nul 2>&1
            if not errorlevel 1 set "PYCMD=py -%%V"
        )
    )
)
if not defined PYCMD (
    py -3 -c "import sys; assert sys.version_info < (3, 13)" >nul 2>&1
    if not errorlevel 1 set "PYCMD=py -3"
)
if not defined PYCMD (
    python -c "import sys; assert sys.version_info < (3, 13)" >nul 2>&1
    if not errorlevel 1 set "PYCMD=python"
)

rem Если стабильный Python не найден — качаем портативный 3.12
if not defined PYCMD call :bootstrap_python
if not defined PYCMD (
    py -3 -c "import sys" >nul 2>&1
    if not errorlevel 1 set "PYCMD=py -3"
)
if not defined PYCMD (
    python -c "import sys" >nul 2>&1
    if not errorlevel 1 set "PYCMD=python"
)
if not defined PYCMD (
    echo [build] Python 3 не найден и скачать его не удалось.
    pause
    exit /b 1
)
echo [build] Python: %PYCMD%

set "VENV=.build\venv"
set "VPY=%VENV%\Scripts\python.exe"
if not exist "%VPY%" (
    echo [build] создаю окружение сборки %VENV% ...
    %PYCMD% -m venv "%VENV%"
    if not exist "%VPY%" (
        echo [build] не удалось создать venv через %PYCMD%, пробую портативный Python ...
        call :bootstrap_python
        if defined RUNTIME_PY (
            rmdir /s /q "%VENV%" >nul 2>&1
            "%RUNTIME_PY%" -m venv "%VENV%"
        )
    )
    if not exist "%VPY%" goto :err
)

rem Проверяем наличие pip в venv
"%VPY%" -m pip --version >nul 2>&1
if not errorlevel 1 goto :pip_ok
echo [build] в %VENV% нет pip - ставлю через ensurepip ...
"%VPY%" -m ensurepip --upgrade >nul 2>&1
"%VPY%" -m pip --version >nul 2>&1
if not errorlevel 1 goto :pip_ok

echo [build] ensurepip не сработал - пробую get-pip.py ...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop';[Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12;Invoke-WebRequest -Uri 'https://bootstrap.pypa.io/get-pip.py' -OutFile '%TEMP%\get-pip.py'" >nul 2>&1
if exist "%TEMP%\get-pip.py" (
    "%VPY%" "%TEMP%\get-pip.py" --no-warn-script-location >nul 2>&1
)
"%VPY%" -m pip --version >nul 2>&1
if not errorlevel 1 goto :pip_ok

rem Если в системном Python сломан pip (напр. Python 3.14 без wheel), переключаемся на портативный
echo [build] venv с %PYCMD% не поддерживает pip - переключаюсь на портативный Python 3.12 ...
call :bootstrap_python
if defined RUNTIME_PY (
    rmdir /s /q "%VENV%" >nul 2>&1
    "%RUNTIME_PY%" -m venv "%VENV%"
    "%VPY%" -m ensurepip --upgrade >nul 2>&1
    "%VPY%" -m pip --version >nul 2>&1
    if not errorlevel 1 goto :pip_ok
    if exist "%TEMP%\get-pip.py" "%VPY%" "%TEMP%\get-pip.py" --no-warn-script-location >nul 2>&1
    "%VPY%" -m pip --version >nul 2>&1
    if not errorlevel 1 goto :pip_ok
)

echo [build] ensurepip / get-pip не сработали.
goto :err

:pip_ok
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

:bootstrap_python
echo [build] Скачиваю портативный Python 3.12 в .runtime\ ...
if not exist "%~dp0.runtime" mkdir "%~dp0.runtime"
set "RT_ZIP=%TEMP%\python-embed-amd64.zip"
for %%U in (%PY_URLS%) do (
    if not exist "%RUNTIME_PY%" (
        echo [build]   качаю %%U
        powershell -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop';[Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12;Invoke-WebRequest -Uri '%%U' -OutFile '%RT_ZIP%';Expand-Archive -LiteralPath '%RT_ZIP%' -DestinationPath '%RUNTIME%' -Force"
    )
)
if not exist "%RUNTIME_PY%" exit /b 1
powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-ChildItem -Path '%RUNTIME%' -Filter '*._pth' | ForEach-Object { (Get-Content -LiteralPath $_.FullName) -replace '^\s*#\s*import site','import site' | Set-Content -LiteralPath $_.FullName -Encoding ASCII }"
echo [build]   ставлю pip в портативный Python...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop';[Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12;Invoke-WebRequest -Uri 'https://bootstrap.pypa.io/get-pip.py' -OutFile '%TEMP%\get-pip.py'"
if not exist "%TEMP%\get-pip.py" exit /b 1
"%RUNTIME_PY%" "%TEMP%\get-pip.py" --no-warn-script-location >nul 2>&1
set "PYCMD="%RUNTIME_PY%""
exit /b 0

:err
echo.
echo [build] ОШИБКА сборки - смотри вывод выше.
echo [build] Частые причины: нет интернета ^(pip^), блокировка антивирусом,
echo [build] неподдерживаемая версия Python ^(нужен 3.8-3.12^).
pause
exit /b 1
