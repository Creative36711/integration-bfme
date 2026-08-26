@echo off
rem ==========================================================================
rem  BFME2: RotWK - калибровка координат (F9) и маркера готовности (F8)
rem
rem  ЗАПУСК: двойной клик по этому файлу.
rem  Python ставить НЕ обязательно: если его нет, скрипт сам скачает
rem  портативный Python (~11 МБ, один раз, в папку .runtime\) и поставит numpy.
rem
rem  Ключи tools\calibrate.py можно передавать этому bat:
rem      calibrate.bat --attach
rem      calibrate.bat --exe "D:\Games\RotWK\lotrbfme2ep1.exe"
rem      calibrate.bat --no-resolution
rem
rem  Игра должна быть ЗАКРЫТА (лаунчер не откроет второй экземпляр).
rem ==========================================================================
setlocal EnableExtensions
chcp 65001 >nul
title BFME2: RotWK - калибровка  (F8 маркер / F9 координата / F10 выход)
cd /d "%~dp0"

set "PYUTF8=1"
set "PYTHONIOENCODING=utf-8"
set "RUNTIME=%~dp0.runtime\python"
set "RUNTIME_PY=%RUNTIME%\python.exe"
set "PY_URLS=https://www.python.org/ftp/python/3.12.10/python-3.12.10-embed-amd64.zip https://www.python.org/ftp/python/3.11.9/python-3.11.9-embed-amd64.zip"

rem --- 1. Права администратора -------------------------------------------
rem Игра запускается повышенной, а UIPI молча выбрасывает клики, посланные
rem из непровышенного процесса. Повышаемся сразу - и в одном окне.
rem Проверка идёт через PowerShell (IsInRole), а не через "net session":
rem последний зависит от службы "Сервер" и может соврать.
set "NO_PS="
set "IS_ADMIN="
where powershell >nul 2>&1
if errorlevel 1 set "NO_PS=1"
if not defined NO_PS (
    powershell -NoProfile -Command "if (([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) { exit 0 } else { exit 1 }" >nul 2>&1
    if not errorlevel 1 set "IS_ADMIN=1"
)
rem Нет PowerShell -> не повышаемся здесь: tools\calibrate.py повысится сам.
if not defined NO_PS if not defined IS_ADMIN goto :elevate
goto :after_elevate

:elevate
echo [cal] Запрашиваю права администратора (UAC) - нажми "Да"...
powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath '%~f0' -ArgumentList '%*' -Verb RunAs"
if errorlevel 1 echo [cal] Повысить права не удалось. Кликни правой кнопкой - "Запуск от имени администратора".
exit /b 0

:after_elevate

rem --- 2. Ищем Python: портативный -> стабильный -> py -> скачать ---------
set "PYCMD="
if exist "%RUNTIME_PY%" set "PYCMD="%RUNTIME_PY%""

if not defined PYCMD (
    for %%V in (3.12 3.11 3.10 3.9 3.8) do (
        if not defined PYCMD (
            py -%%V -c "import sys" >nul 2>&1
            if not errorlevel 1 set "PYCMD=py -%%V"
        )
    )
)
if not defined PYCMD (
    py -3 -c "import sys; assert sys.version_info < (3, 14)" >nul 2>&1
    if not errorlevel 1 set "PYCMD=py -3"
)
if not defined PYCMD (
    python -c "import sys; assert sys.version_info < (3, 14)" >nul 2>&1
    if not errorlevel 1 set "PYCMD=python"
)
if not defined PYCMD call :bootstrap_python
if not defined PYCMD (
    py -3 -c "import sys" >nul 2>&1
    if not errorlevel 1 set "PYCMD=py -3"
)
if not defined PYCMD (
    python -c "import sys" >nul 2>&1
    if not errorlevel 1 set "PYCMD=python"
)
if not defined PYCMD goto :no_python
echo [cal] Python: %PYCMD%

rem --- 3. numpy (нужен для захвата маркера F8) ---------------------------
%PYCMD% -c "import numpy" >nul 2>&1
if errorlevel 1 (
    echo [cal] numpy не найден - устанавливаю ^(нужен интернет^)...
    %PYCMD% -m pip install --no-warn-script-location numpy
    %PYCMD% -c "import numpy" >nul 2>&1
    if errorlevel 1 (
        echo [cal] pip не сработал - пробую get-pip.py ...
        powershell -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop';[Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12;Invoke-WebRequest -Uri 'https://bootstrap.pypa.io/get-pip.py' -OutFile '%TEMP%\get-pip.py'" >nul 2>&1
        if exist "%TEMP%\get-pip.py" %PYCMD% "%TEMP%\get-pip.py" --no-warn-script-location >nul 2>&1
        %PYCMD% -m pip install --no-warn-script-location numpy >nul 2>&1
    )
    %PYCMD% -c "import numpy" >nul 2>&1
    if errorlevel 1 (
        echo [cal] numpy установить не удалось: маркер ^(F8^) не сохранится,
        echo [cal] координаты ^(F9^) сниматься будут. Поставь вручную:
        echo [cal]     %PYCMD% -m pip install numpy
        choice /c YN /m "Продолжить без numpy?"
        if errorlevel 2 exit /b 1
    )
)

rem --- 4. Запуск калибровки ---------------------------------------------
echo.
%PYCMD% "%~dp0tools\calibrate.py" --no-pause %*
set "RC=%errorlevel%"
echo.
if "%RC%"=="0" (echo [cal] Готово.) else (echo [cal] Завершено с кодом %RC%)
echo [cal] лог:        %~dp0calibrate_log.txt
echo [cal] координаты: %~dp0config\calibrate_coords.txt
echo [cal] маркер:     %~dp0config\menu_marker.npy + menu_marker.json
pause
exit /b %RC%


:bootstrap_python
echo [cal] Python не найден - ставлю портативный в .runtime\ ...
if not exist "%~dp0.runtime" mkdir "%~dp0.runtime"
set "RT_ZIP=%TEMP%\python-embed-amd64.zip"
for %%U in (%PY_URLS%) do (
    if not exist "%RUNTIME_PY%" (
        echo [cal]   качаю %%U
        powershell -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop';[Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12;Invoke-WebRequest -Uri '%%U' -OutFile '%RT_ZIP%';Expand-Archive -LiteralPath '%RT_ZIP%' -DestinationPath '%RUNTIME%' -Force"
    )
)
if not exist "%RUNTIME_PY%" exit /b 1
rem Портативный Python по умолчанию не подключает site-packages - включаем.
powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-ChildItem -Path '%RUNTIME%' -Filter '*._pth' | ForEach-Object { (Get-Content -LiteralPath $_.FullName) -replace '^\s*#\s*import site','import site' | Set-Content -LiteralPath $_.FullName -Encoding ASCII }"
echo [cal]   ставлю pip...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop';[Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12;Invoke-WebRequest -Uri 'https://bootstrap.pypa.io/get-pip.py' -OutFile '%TEMP%\get-pip.py'"
if not exist "%TEMP%\get-pip.py" exit /b 1
"%RUNTIME_PY%" "%TEMP%\get-pip.py" --no-warn-script-location >nul 2>&1
set "PYCMD="%RUNTIME_PY%""
exit /b 0


:no_python
echo.
echo [cal] Python 3 не найден, и скачать его не удалось (нет интернета?).
echo [cal] Варианты:
echo [cal]   1^) поставь Python 3: https://www.python.org/downloads/windows/
echo [cal]      ^(при установке отметь "Add python.exe to PATH"^);
echo [cal]   2^) собери exe на машине с Python: build_calibrate_exe.bat
echo [cal]      -^> dist\Calibrate\Calibrate.exe ^(Python вообще не нужен^).
echo.
pause
exit /b 1
