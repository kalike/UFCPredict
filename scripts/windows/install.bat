@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul

REM ============================================================
REM  UFC Lab - Instalación desde cero en Windows
REM  Uso: clonar el repo y ejecutar scripts\windows\install.bat
REM  Requisitos previos (deben estar instalados):
REM    - Python 3.13+   (https://www.python.org/downloads/)
REM    - Node.js 20+    (https://nodejs.org/)
REM    - Docker Desktop (https://www.docker.com/products/docker-desktop/)
REM  PostgreSQL corre en un contenedor Docker: el script lo crea
REM  o lo arranca si ya existe. No hace falta psql en local.
REM ============================================================

REM --- Configuración (editable o vía variables de entorno) ---
if not defined UFC_LAB_DB_HOST set "UFC_LAB_DB_HOST=localhost"
if not defined UFC_LAB_DB_PORT set "UFC_LAB_DB_PORT=5432"
if not defined UFC_LAB_DB_USER set "UFC_LAB_DB_USER=postgres"
if not defined UFC_LAB_DB_NAME set "UFC_LAB_DB_NAME=ufc_lab"
REM Nombre del contenedor de PostgreSQL (se crea si no existe)
if not defined UFC_LAB_PG_CONTAINER set "UFC_LAB_PG_CONTAINER=ufc-lab-postgres"
if not defined UFC_LAB_PG_IMAGE set "UFC_LAB_PG_IMAGE=postgres:16"
REM Poner SKIP_PLAYWRIGHT=1 para omitir la descarga de Chromium (scrapers)
if not defined SKIP_PLAYWRIGHT set "SKIP_PLAYWRIGHT=0"

REM Raíz del repo = dos niveles por encima de este script
pushd "%~dp0..\.."
set "REPO_ROOT=%CD%"
echo.
echo === UFC Lab: instalación en %REPO_ROOT% ===
echo.

REM ============================================================
REM 1. Verificar prerequisitos
REM ============================================================
echo [1/7] Verificando prerequisitos...

set "PYTHON_CMD="
py -3.13 --version >nul 2>&1 && set "PYTHON_CMD=py -3.13"
if not defined PYTHON_CMD (
    python --version 2>nul | findstr /R "3\.1[3-9]" >nul && set "PYTHON_CMD=python"
)
if not defined PYTHON_CMD (
    echo [ERROR] No se encontró Python 3.13 o superior.
    echo         Instálalo desde https://www.python.org/downloads/ y marca "Add to PATH".
    goto :fail
)
for /f "tokens=*" %%v in ('%PYTHON_CMD% --version') do echo   Python: %%v

where node >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Node.js no está en el PATH. Instala Node 20+ desde https://nodejs.org/
    goto :fail
)
for /f "tokens=*" %%v in ('node --version') do echo   Node:   %%v

docker info >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Docker no está disponible. Comprueba que Docker Desktop está
    echo         instalado y arrancado antes de ejecutar este script.
    goto :fail
)
for /f "tokens=*" %%v in ('docker --version') do echo   Docker: %%v

REM ============================================================
REM 2. Crear entorno virtual
REM ============================================================
echo.
echo [2/7] Creando entorno virtual (.venv)...
if not exist "%REPO_ROOT%\.venv\Scripts\python.exe" (
    %PYTHON_CMD% -m venv "%REPO_ROOT%\.venv"
    if errorlevel 1 goto :fail
) else (
    echo   Ya existe, se reutiliza.
)
set "VENV_PY=%REPO_ROOT%\.venv\Scripts\python.exe"

REM ============================================================
REM 3. Instalar paquetes Python (core + API en modo editable)
REM ============================================================
echo.
echo [3/7] Instalando dependencias Python (puede tardar varios minutos: torch, catboost...)...
if not exist "%REPO_ROOT%\packages\ufc_core\pyproject.toml" (
    echo [ERROR] No se encuentra packages\ufc_core\pyproject.toml en %REPO_ROOT%.
    echo         Comprueba que el repositorio está clonado completo.
    goto :fail
)
"%VENV_PY%" -m pip install --upgrade pip
if errorlevel 1 goto :fail
REM Instalar con "pip install -e ." desde cada directorio: pasar la ruta
REM absoluta a -e falla cuando contiene espacios.
cd /d "%REPO_ROOT%\packages\ufc_core"
"%VENV_PY%" -m pip install -e .
if errorlevel 1 goto :fail
cd /d "%REPO_ROOT%\apps\lab-api"
"%VENV_PY%" -m pip install -e .
if errorlevel 1 goto :fail
cd /d "%REPO_ROOT%"

REM ============================================================
REM 4. Navegador de Playwright (scrapers)
REM ============================================================
echo.
if "%SKIP_PLAYWRIGHT%"=="1" (
    echo [4/7] Playwright omitido ^(SKIP_PLAYWRIGHT=1^).
) else (
    echo [4/7] Descargando Chromium para Playwright ^(scrapers^)...
    "%VENV_PY%" -m playwright install chromium
    if errorlevel 1 (
        echo [AVISO] Falló la descarga de Chromium. Los scrapers no funcionarán
        echo         hasta ejecutar: .venv\Scripts\python -m playwright install chromium
    )
)

REM ============================================================
REM 5. Contenedor de PostgreSQL + base de datos
REM ============================================================
echo.
echo [5/7] Configurando PostgreSQL en Docker (contenedor "%UFC_LAB_PG_CONTAINER%")...

if not defined UFC_LAB_DB_PASS (
    set /p "UFC_LAB_DB_PASS=  Contraseña para el usuario %UFC_LAB_DB_USER% de PostgreSQL: "
)

docker container inspect "%UFC_LAB_PG_CONTAINER%" >nul 2>&1
if errorlevel 1 (
    echo   Creando contenedor ^(imagen %UFC_LAB_PG_IMAGE%, puerto %UFC_LAB_DB_PORT%^)...
    docker run -d --name "%UFC_LAB_PG_CONTAINER%" ^
        -e POSTGRES_USER=%UFC_LAB_DB_USER% ^
        -e "POSTGRES_PASSWORD=!UFC_LAB_DB_PASS!" ^
        -p %UFC_LAB_DB_PORT%:5432 ^
        -v ufc-lab-pgdata:/var/lib/postgresql/data ^
        --restart unless-stopped ^
        %UFC_LAB_PG_IMAGE%
    if errorlevel 1 goto :fail
) else (
    for /f "tokens=*" %%s in ('docker container inspect -f "{{.State.Running}}" "%UFC_LAB_PG_CONTAINER%"') do set "PG_RUNNING=%%s"
    if /i not "!PG_RUNNING!"=="true" (
        echo   El contenedor existe pero está parado; arrancándolo...
        docker start "%UFC_LAB_PG_CONTAINER%" >nul
        if errorlevel 1 goto :fail
    ) else (
        echo   El contenedor ya está en marcha.
    )
)

echo   Esperando a que PostgreSQL acepte conexiones...
set /a PG_TRIES=0
:waitpg
REM -h localhost fuerza TCP: así no damos por listo el servidor temporal que
REM el entrypoint usa durante la inicialización (solo escucha por socket)
docker exec "%UFC_LAB_PG_CONTAINER%" pg_isready -h localhost -U %UFC_LAB_DB_USER% >nul 2>&1 && goto :pgready
set /a PG_TRIES+=1
if %PG_TRIES% geq 30 (
    echo [ERROR] PostgreSQL no respondió tras 60 segundos. Revisa los logs con:
    echo         docker logs %UFC_LAB_PG_CONTAINER%
    goto :fail
)
timeout /t 2 /nobreak >nul
goto :waitpg
:pgready

REM Si el volumen ufc-lab-pgdata sobrevive de una instalación anterior, el
REM contenedor ignora POSTGRES_PASSWORD; fijamos la contraseña real a la
REM introducida para que migraciones y API siempre conecten.
docker exec "%UFC_LAB_PG_CONTAINER%" psql -U %UFC_LAB_DB_USER% -d postgres -c "ALTER USER %UFC_LAB_DB_USER% WITH PASSWORD '!UFC_LAB_DB_PASS!'" >nul
if errorlevel 1 (
    echo [ERROR] No se pudo fijar la contraseña en PostgreSQL. Revisa:
    echo         docker logs %UFC_LAB_PG_CONTAINER%
    goto :fail
)

echo   Creando base de datos "%UFC_LAB_DB_NAME%" (si no existe)...
REM "already exists" no es un error; cualquier otro ERROR sí
docker exec "%UFC_LAB_PG_CONTAINER%" psql -U %UFC_LAB_DB_USER% -d postgres -c "CREATE DATABASE %UFC_LAB_DB_NAME%" 2>&1 | findstr /C:"ERROR" | findstr /V /C:"already exists"
if not errorlevel 1 goto :fail

REM Verificar que la base es accesible
docker exec "%UFC_LAB_PG_CONTAINER%" psql -U %UFC_LAB_DB_USER% -d %UFC_LAB_DB_NAME% -tAc "SELECT 1" 2>nul | findstr "1" >nul
if errorlevel 1 (
    echo [ERROR] La base de datos "%UFC_LAB_DB_NAME%" no está accesible.
    goto :fail
)
echo   Base de datos lista.

REM ============================================================
REM 6. Aplicar migraciones Alembic
REM ============================================================
echo.
echo [6/7] Aplicando migraciones...
cd /d "%REPO_ROOT%\packages\ufc_core"
REM env.py solo lee la URL de alembic.ini (usuario "ufc" hardcodeado) o de
REM "-x db_url=...": pasamos la conexion del contenedor por esa via.
"%REPO_ROOT%\.venv\Scripts\alembic.exe" -x "db_url=postgresql+psycopg2://%UFC_LAB_DB_USER%:!UFC_LAB_DB_PASS!@%UFC_LAB_DB_HOST%:%UFC_LAB_DB_PORT%/%UFC_LAB_DB_NAME%" upgrade head
if errorlevel 1 (
    echo [ERROR] Fallaron las migraciones. Si la contraseña introducida no coincide
    echo         con la del contenedor existente, es la causa más probable.
    goto :fail
)
cd /d "%REPO_ROOT%"

REM ============================================================
REM 7. Instalar frontend
REM ============================================================
echo.
echo [7/7] Instalando dependencias del frontend (npm)...
cd /d "%REPO_ROOT%\apps\lab-ui"
call npm install
if errorlevel 1 goto :fail
cd /d "%REPO_ROOT%"

REM ============================================================
REM Generar scripts de arranque y archivo de entorno
REM ============================================================
> "%REPO_ROOT%\scripts\windows\env.bat" (
    echo @echo off
    echo set "UFC_LAB_DB_HOST=%UFC_LAB_DB_HOST%"
    echo set "UFC_LAB_DB_PORT=%UFC_LAB_DB_PORT%"
    echo set "UFC_LAB_DB_USER=%UFC_LAB_DB_USER%"
    echo set "UFC_LAB_DB_PASS=!UFC_LAB_DB_PASS!"
    echo set "UFC_LAB_DB_NAME=%UFC_LAB_DB_NAME%"
    echo set "UFC_LAB_PG_CONTAINER=%UFC_LAB_PG_CONTAINER%"
)

> "%REPO_ROOT%\start-api.bat" (
    echo @echo off
    echo call "%%~dp0scripts\windows\env.bat"
    echo docker start "%%UFC_LAB_PG_CONTAINER%%" ^>nul 2^>^&1
    echo cd /d "%%~dp0"
    echo ".venv\Scripts\uvicorn.exe" lab_api.main:app --port 8101 --reload
)

> "%REPO_ROOT%\start-ui.bat" (
    echo @echo off
    echo cd /d "%%~dp0apps\lab-ui"
    echo call npm run dev
)

echo.
echo ============================================================
echo  Instalación completada.
echo    - API:  start-api.bat   (http://localhost:8101)
echo    - UI:   start-ui.bat    (http://localhost:5174)
echo    - PostgreSQL: contenedor Docker "%UFC_LAB_PG_CONTAINER%"
echo    - Credenciales de DB guardadas en scripts\windows\env.bat
echo ============================================================
popd
endlocal
exit /b 0

:fail
echo.
echo [ERROR] La instalación se detuvo por un fallo en el paso anterior.
popd
endlocal
exit /b 1
