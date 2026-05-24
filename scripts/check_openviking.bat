@echo off
setlocal enabledelayedexpansion
rem Sanity-check optional OpenViking: Python extra imports and server /health endpoint.
rem Uses OPEN_VIKING_URL from the environment (default http://127.0.0.1:1933).

pushd "%~dp0\.."

if "%OPEN_VIKING_URL%"=="" (
    set BASE_URL=http://127.0.0.1:1933
) else (
    set BASE_URL=%OPEN_VIKING_URL%
)
set HEALTH_URL=%BASE_URL%/health

echo repo root: %CD%
echo OpenViking API base: %BASE_URL%

where uv >nul 2>&1
if errorlevel 1 (
    echo error: uv is not on PATH ^(https://docs.astral.sh/uv/^) 1>&2
    popd
    exit /b 1
)

echo.
echo [1/2] optional dependency: openviking (uv --extra openviking)
uv run --extra openviking python -c "import openviking; print(getattr(openviking, '__version__', '?'))"
if errorlevel 1 (
    echo error: cannot import openviking. Try: uv sync --extra openviking 1>&2
    popd
    exit /b 1
)
echo       ok

where curl >nul 2>&1
if errorlevel 1 (
    echo note: curl not on PATH; skipping /health probe.
    echo.
    echo OpenViking SDK import check passed ^(no server probe^).
    popd
    exit /b 0
)

echo.
echo [2/2] HTTP GET %HEALTH_URL%
curl -sS --connect-timeout 5 --max-time 15 -o nul -w "%%{http_code}" "%HEALTH_URL%" > "%TEMP%\ov_code.txt"
set /p HTTP_CODE=<"%TEMP%\ov_code.txt"
del "%TEMP%\ov_code.txt"
if not "%HTTP_CODE%"=="200" (
    echo warning: expected HTTP 200 from /health, got %HTTP_CODE% 1>&2
    echo hint: start the server with scripts\launch_openviking.bat, or set OPEN_VIKING_URL. 1>&2
    popd
    exit /b 0
)
echo       ok (%HTTP_CODE%)

echo.
echo OpenViking check passed.
popd
endlocal
