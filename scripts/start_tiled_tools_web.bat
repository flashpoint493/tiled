@echo off
setlocal EnableExtensions

set "ROOT=%~dp0"
set "ROOT=%ROOT:~0,-1%"
set "VENV=%ROOT%\.venv"
set "HOST=127.0.0.1"
set "PREFERRED_PORT=8765"
set "PORT="

pushd "%ROOT%"

title Tiled Tools Web

echo ========================================
echo Tiled Tools Web
echo ========================================
echo Package directory: %ROOT%
echo Preferred URL: http://%HOST%:%PREFERRED_PORT%/
echo.

where py >nul 2>nul
if not errorlevel 1 (
    set "PY=py -3"
) else (
    where python >nul 2>nul
    if not errorlevel 1 (
        set "PY=python"
    ) else (
        echo [ERROR] Python 3.10+ is required but was not found.
        echo Please install Python from https://www.python.org/downloads/ and enable "Add python.exe to PATH".
        pause
        exit /b 1
    )
)

echo [1/4] Checking Python...
%PY% -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Python 3.10+ is required.
    %PY% --version
    pause
    exit /b 1
)
%PY% --version

if not exist "%VENV%\Scripts\python.exe" (
    echo.
    echo [2/4] Creating local virtual environment...
    %PY% -m venv "%VENV%"
    if errorlevel 1 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
) else (
    echo.
    echo [2/4] Local virtual environment already exists.
)

echo.
echo [3/4] Installing or updating dependencies...
"%VENV%\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 (
    echo [ERROR] Failed to update pip.
    pause
    exit /b 1
)
"%VENV%\Scripts\python.exe" -m pip install -r "%ROOT%\requirements.txt"
if errorlevel 1 (
    echo [ERROR] Failed to install dependencies.
    echo Check network access, then run this BAT again.
    pause
    exit /b 1
)

echo.
echo [4/4] Finding an available local port...
set "PORT="
set /a MAX_PORT=PREFERRED_PORT+99 >nul
set "PORT_PROBE=%TEMP%\tiled_tools_find_port_%RANDOM%%RANDOM%.py"

> "%PORT_PROBE%" echo import socket, sys
>> "%PORT_PROBE%" echo host = sys.argv[1]
>> "%PORT_PROBE%" echo start = int(sys.argv[2])
>> "%PORT_PROBE%" echo for port in range(start, start + 100):
>> "%PORT_PROBE%" echo     sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
>> "%PORT_PROBE%" echo     try:
>> "%PORT_PROBE%" echo         sock.bind((host, port))
>> "%PORT_PROBE%" echo     except OSError:
>> "%PORT_PROBE%" echo         continue
>> "%PORT_PROBE%" echo     finally:
>> "%PORT_PROBE%" echo         sock.close()
>> "%PORT_PROBE%" echo     print(port)
>> "%PORT_PROBE%" echo     raise SystemExit(0)
>> "%PORT_PROBE%" echo raise SystemExit(1)

for /f "usebackq delims=" %%P in (`"%VENV%\Scripts\python.exe" "%PORT_PROBE%" "%HOST%" "%PREFERRED_PORT%"`) do set "PORT=%%P"
del "%PORT_PROBE%" >nul 2>nul

if not defined PORT (
    echo [ERROR] Could not find an available port from %PREFERRED_PORT% to %MAX_PORT%.
    pause
    exit /b 1
)
if not "%PORT%"=="%PREFERRED_PORT%" (
    echo Preferred port %PREFERRED_PORT% is busy. Using port %PORT% instead.
)

echo.
echo Starting web service at http://%HOST%:%PORT%/
echo Browser will open automatically. Keep this window open while using the tool.
start "" "http://%HOST%:%PORT%/"
"%VENV%\Scripts\python.exe" -m tiled_tools serve --host %HOST% --port %PORT%

echo.
echo Service stopped.
pause
