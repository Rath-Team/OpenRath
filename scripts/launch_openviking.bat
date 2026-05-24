@echo off
setlocal EnableExtensions EnableDelayedExpansion
rem Launch a local OpenViking server (Docker) for memory-plane integration tests.
rem Mirrors scripts/launch_openviking.sh.

set "SCRIPT_DIR=%~dp0"
set "ROOT_DIR=%SCRIPT_DIR%.."
pushd "%ROOT_DIR%" || exit /b 1

where docker >nul 2>&1
if errorlevel 1 (
    echo error: docker is not on PATH 1>&2
    popd
    exit /b 1
)
docker info >nul 2>&1
if errorlevel 1 (
    echo error: Docker daemon is not running ^(or permission denied^). 1>&2
    popd
    exit /b 1
)

if "%OPEN_VIKING_IMAGE%"==""     set "OPEN_VIKING_IMAGE=ghcr.io/volcengine/openviking:latest"
if "%OPEN_VIKING_CONTAINER%"=="" set "OPEN_VIKING_CONTAINER=openrath-openviking"
if "%OPEN_VIKING_API_PORT%"==""  set "OPEN_VIKING_API_PORT=1933"
if "%OPEN_VIKING_UI_PORT%"==""   set "OPEN_VIKING_UI_PORT=8020"
if "%OPEN_VIKING_DATA_DIR%"==""  set "OPEN_VIKING_DATA_DIR=%USERPROFILE%\.openviking"
set "CONFIG_PATH=%OPEN_VIKING_DATA_DIR%\ov.conf"

if not exist "%OPEN_VIKING_DATA_DIR%" mkdir "%OPEN_VIKING_DATA_DIR%"

rem GLM (Zhipu / open.bigmodel.cn) OpenAI-compatible defaults — match OpenRath/.openrath/config.json.
set "GLM_DEFAULT_KEY=b07306ec6bb24dfb93c6a4da4c78e85b.TIM4UBLavr8vz5yG"
set "GLM_DEFAULT_BASE=https://open.bigmodel.cn/api/paas/v4"
if "%OPEN_VIKING_EMBEDDING_API_KEY%"=="" set "OPEN_VIKING_EMBEDDING_API_KEY=%GLM_DEFAULT_KEY%"
if "%OPEN_VIKING_EMBEDDING_API_BASE%"=="" set "OPEN_VIKING_EMBEDDING_API_BASE=%GLM_DEFAULT_BASE%"
if "%OPEN_VIKING_EMBEDDING_MODEL%"=="" set "OPEN_VIKING_EMBEDDING_MODEL=embedding-3"
if "%OPEN_VIKING_EMBEDDING_DIMENSION%"=="" set "OPEN_VIKING_EMBEDDING_DIMENSION=2048"
if "%OPEN_VIKING_VLM_API_KEY%"=="" set "OPEN_VIKING_VLM_API_KEY=%GLM_DEFAULT_KEY%"
if "%OPEN_VIKING_VLM_API_BASE%"=="" set "OPEN_VIKING_VLM_API_BASE=%GLM_DEFAULT_BASE%"
if "%OPEN_VIKING_VLM_MODEL%"=="" set "OPEN_VIKING_VLM_MODEL=glm-4.6v"

if not exist "%CONFIG_PATH%" (
    if "%OPEN_VIKING_ROOT_API_KEY%"=="" (
        for /f "delims=" %%K in ('python -c "import secrets; print('dev-root-' + secrets.token_hex(12))"') do set "OPEN_VIKING_ROOT_API_KEY=%%K"
    )
    echo creating %CONFIG_PATH% with auto-generated root key + GLM embedding/vlm config
    > "%CONFIG_PATH%" echo {
    >>"%CONFIG_PATH%" echo   "server": {
    >>"%CONFIG_PATH%" echo     "host": "0.0.0.0",
    >>"%CONFIG_PATH%" echo     "port": 1933,
    >>"%CONFIG_PATH%" echo     "root_api_key": "!OPEN_VIKING_ROOT_API_KEY!"
    >>"%CONFIG_PATH%" echo   },
    >>"%CONFIG_PATH%" echo   "embedding": {
    >>"%CONFIG_PATH%" echo     "dense": {
    >>"%CONFIG_PATH%" echo       "provider": "openai",
    >>"%CONFIG_PATH%" echo       "model": "!OPEN_VIKING_EMBEDDING_MODEL!",
    >>"%CONFIG_PATH%" echo       "api_key": "!OPEN_VIKING_EMBEDDING_API_KEY!",
    >>"%CONFIG_PATH%" echo       "api_base": "!OPEN_VIKING_EMBEDDING_API_BASE!",
    >>"%CONFIG_PATH%" echo       "dimension": !OPEN_VIKING_EMBEDDING_DIMENSION!,
    >>"%CONFIG_PATH%" echo       "input": "text",
    >>"%CONFIG_PATH%" echo       "encoding_format": "float"
    >>"%CONFIG_PATH%" echo     }
    >>"%CONFIG_PATH%" echo   },
    >>"%CONFIG_PATH%" echo   "vlm": {
    >>"%CONFIG_PATH%" echo     "provider": "openai",
    >>"%CONFIG_PATH%" echo     "model": "!OPEN_VIKING_VLM_MODEL!",
    >>"%CONFIG_PATH%" echo     "api_key": "!OPEN_VIKING_VLM_API_KEY!",
    >>"%CONFIG_PATH%" echo     "api_base": "!OPEN_VIKING_VLM_API_BASE!"
    >>"%CONFIG_PATH%" echo   }
    >>"%CONFIG_PATH%" echo }
    echo ==^> OPEN_VIKING_ROOT_API_KEY=!OPEN_VIKING_ROOT_API_KEY!
    echo     export this in your shell to talk to the server.
) else (
    echo using existing config: %CONFIG_PATH%
)

echo Checking existing containers using %OPEN_VIKING_IMAGE% ...
for /f "delims=" %%I in ('docker ps -a --filter "name=^%OPEN_VIKING_CONTAINER%$" --format "{{.ID}}"') do (
    echo removing previous container %OPEN_VIKING_CONTAINER% ^(%%I^)
    docker rm -f %%I >nul
)

echo pulling %OPEN_VIKING_IMAGE% ...
docker pull %OPEN_VIKING_IMAGE%

echo starting %OPEN_VIKING_CONTAINER% ^(API :%OPEN_VIKING_API_PORT% / UI :%OPEN_VIKING_UI_PORT%^) ...
docker run -d ^
    --name %OPEN_VIKING_CONTAINER% ^
    -p %OPEN_VIKING_API_PORT%:1933 ^
    -p %OPEN_VIKING_UI_PORT%:8020 ^
    -v "%OPEN_VIKING_DATA_DIR%:/app/.openviking" ^
    --restart unless-stopped ^
    %OPEN_VIKING_IMAGE%

echo.
echo wait for /health on http://127.0.0.1:%OPEN_VIKING_API_PORT% ...
for /l %%i in (1,1,30) do (
    curl -fsS "http://127.0.0.1:%OPEN_VIKING_API_PORT%/health" >nul 2>&1
    if not errorlevel 1 (
        echo   ok
        goto :ready
    )
    timeout /t 1 /nobreak >nul
)
:ready

echo.
echo OpenViking running:
echo   API:  http://127.0.0.1:%OPEN_VIKING_API_PORT%
echo   UI:   http://127.0.0.1:%OPEN_VIKING_UI_PORT%
echo   data: %OPEN_VIKING_DATA_DIR%
echo.
echo Logs:   docker logs -f %OPEN_VIKING_CONTAINER%
echo Stop:   docker stop %OPEN_VIKING_CONTAINER%
echo Remove: docker rm -f %OPEN_VIKING_CONTAINER%
echo.
echo For Rath integration tests, export:
echo   set OPEN_VIKING_URL=http://127.0.0.1:%OPEN_VIKING_API_PORT%
echo   set OPEN_VIKING_ROOT_API_KEY=^<the key printed above or from %CONFIG_PATH%^>

popd
endlocal
