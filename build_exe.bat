@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo ============================================
echo  Gerador de executavel - Geo Point Estimator
echo ============================================
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

echo Usando Python: %PYCMD%
%PYCMD% --version
echo.

echo Instalando dependencias e PyInstaller...
%PYCMD% -m pip install --upgrade pip >nul 2>nul
%PYCMD% -m pip install -r requirements.txt pyinstaller
if errorlevel 1 (
  echo [ERRO] Falha ao instalar dependencias.
  pause
  exit /b 1
)
echo.

echo Gerando o executavel ^(pode demorar alguns minutos^)...
%PYCMD% -m PyInstaller --onefile --name geo-point-estimator --console ^
  --collect-all rasterio ^
  --collect-all geographiclib ^
  --collect-submodules app ^
  app.py
if errorlevel 1 (
  echo [ERRO] Falha ao gerar o executavel.
  pause
  exit /b 1
)

echo.
echo ============================================
echo  PRONTO! Executavel em:  dist\geo-point-estimator.exe
echo ============================================
echo.
pause
