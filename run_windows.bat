@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo ============================================
echo  Geo Point Estimator - inicializacao
echo ============================================
echo Pasta atual: %CD%
echo.

set "PYCMD="
for %%P in (py python python3) do (
  if not defined PYCMD (
    %%P -c "import sys" >nul 2>nul && set "PYCMD=%%P"
  )
)
if not defined PYCMD (
  echo [ERRO] Python real nao encontrado ^(apenas o atalho da Microsoft Store^).
  echo Instale em https://www.python.org/downloads/windows/ marcando "Add Python to PATH".
  echo.
  pause
  exit /b 1
)

echo Python encontrado: %PYCMD%
%PYCMD% --version
echo.

echo Verificando dependencias ^(geographiclib, rasterio, numpy^)...
%PYCMD% -c "import geographiclib, rasterio, numpy" >nul 2>nul
if errorlevel 1 (
  echo Instalando dependencias ^(so na primeira vez^)...
  %PYCMD% -m pip install -r requirements.txt
)
echo.

if not exist "app.py" (
  echo [ERRO] app.py nao encontrado em %CD%
  pause
  exit /b 1
)

echo Iniciando o servidor... NAO feche esta janela enquanto usar o app.
echo Saida tambem gravada em run_log.txt
echo --------------------------------------------
echo.

%PYCMD% app.py 1> "run_log.txt" 2>&1
type "run_log.txt"

echo.
echo --------------------------------------------
echo O servidor encerrou.
echo Se houve erro acima, me envie o arquivo run_log.txt.
echo.
pause
