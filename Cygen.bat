@echo off
rem ===========================================================================
rem  Cygen - inicializador
rem
rem  De um clique duplo ao app rodando. Verifica o ambiente, instala o que
rem  faltar e sobe a aplicacao.
rem
rem  Roda em cmd.exe, nao em PowerShell, o que evita de saida dois problemas:
rem  a politica de execucao que bloqueia npm.ps1, e o operador && que o
rem  PowerShell 5.1 nao reconhece.
rem
rem  IMPORTANTE: este arquivo e ASCII puro, sem acentos. O cmd.exe le arquivos
rem  de lote na pagina de codigo OEM do console (850 no Brasil), nao em UTF-8.
rem  Um unico caractere acentuado corrompe o parsing de linhas inteiras.
rem
rem  Uso:
rem    Cygen.bat          inicia o aplicativo de desktop
rem    Cygen.bat web      inicia so o backend e abre no navegador
rem    Cygen.bat setup    apenas instala as dependencias e sai
rem ===========================================================================

setlocal EnableDelayedExpansion
cd /d "%~dp0"
title Cygen

rem O Electron roda como Node puro quando esta variavel esta definida, e o app
rem falha com um erro que nao explica a causa. Limpamos so nesta sessao.
set "ELECTRON_RUN_AS_NODE="
set "PYTHONIOENCODING=utf-8"

set "MODO=%~1"
if /i "%MODO%"=="" set "MODO=desktop"

echo.
echo   Cygen
echo   ---------------------------------------------------------------
echo.

rem ---------------------------------------------------------------------------
rem  1. Python
rem ---------------------------------------------------------------------------

set "PY="
py -3 --version >nul 2>&1
if not errorlevel 1 set "PY=py -3"
if not defined PY (
  python --version >nul 2>&1
  if not errorlevel 1 set "PY=python"
)
if not defined PY (
  python3 --version >nul 2>&1
  if not errorlevel 1 set "PY=python3"
)

if not defined PY (
  echo   [X] Python nao encontrado.
  echo.
  echo       Instale a versao 3.10 ou superior em https://python.org/downloads
  echo       Marque "Add Python to PATH" durante a instalacao.
  goto :erro
)

for /f "tokens=2" %%v in ('!PY! --version 2^>^&1') do set "PYVER=%%v"
echo   [ok] Python !PYVER!

rem ---------------------------------------------------------------------------
rem  2. Dependencias Python
rem ---------------------------------------------------------------------------

!PY! -c "import fastapi, uvicorn, httpx, playwright, pydantic" >nul 2>&1
if errorlevel 1 (
  echo   [..] Instalando dependencias Python. Demora um pouco na primeira vez.
  !PY! -m pip install -r "server\requirements.txt" --quiet --disable-pip-version-check
  if errorlevel 1 (
    echo   [X] Falha ao instalar as dependencias.
    echo       Tente manualmente:  !PY! -m pip install -r server\requirements.txt
    goto :erro
  )
  echo   [ok] Dependencias instaladas
) else (
  echo   [ok] Dependencias Python
)

rem ---------------------------------------------------------------------------
rem  3. Navegador do Playwright
rem ---------------------------------------------------------------------------

rem `if exist` com curinga nao funciona para pastas; um laco /d resolve.
set "TEM_CHROMIUM="
for /d %%d in ("%LOCALAPPDATA%\ms-playwright\chromium-*") do set "TEM_CHROMIUM=1"

if not defined TEM_CHROMIUM (
  echo   [..] Baixando o Chromium do Playwright ^(cerca de 150 MB, so desta vez^)
  !PY! -m playwright install chromium
  if errorlevel 1 (
    echo   [X] Falha ao baixar o navegador.
    echo       Tente manualmente:  !PY! -m playwright install chromium
    goto :erro
  )
  echo   [ok] Navegador instalado
) else (
  echo   [ok] Navegador do Playwright
)

if /i "%MODO%"=="setup" (
  echo.
  echo   Tudo pronto. Rode Cygen.bat para iniciar.
  echo.
  goto :fim
)

rem ---------------------------------------------------------------------------
rem  4. Escolha do modo
rem ---------------------------------------------------------------------------

if /i "%MODO%"=="web" goto :web

where node >nul 2>&1
if errorlevel 1 (
  echo   [!]  Node.js nao encontrado - abrindo no navegador.
  echo        Para a versao desktop, instale o Node em https://nodejs.org
  goto :web
)

if not exist "desktop\node_modules\electron" (
  echo   [..] Instalando o Electron ^(cerca de 200 MB, so desta vez^)
  pushd desktop
  call npm.cmd install --no-audit --no-fund
  set "NPM_ERRO=!errorlevel!"
  popd
  if not "!NPM_ERRO!"=="0" (
    echo   [!]  Falha ao instalar o Electron - abrindo no navegador.
    goto :web
  )
  echo   [ok] Electron instalado
) else (
  echo   [ok] Electron
)

rem ---------------------------------------------------------------------------
rem  5a. Desktop
rem ---------------------------------------------------------------------------

echo.
echo   Iniciando o Cygen...
echo   Feche a janela do aplicativo para encerrar.
echo.
pushd desktop
call npm.cmd start
set "SAIDA=!errorlevel!"
popd

if not "!SAIDA!"=="0" (
  echo.
  echo   [X] O aplicativo encerrou com erro ^(codigo !SAIDA!^).
  echo       Tente o modo navegador:  Cygen.bat web
  goto :erro
)
goto :fim

rem ---------------------------------------------------------------------------
rem  5b. Navegador
rem ---------------------------------------------------------------------------

:web
echo.
echo   Iniciando o backend...
echo   O navegador abre sozinho. Feche esta janela para encerrar.
echo.

rem Abre o navegador depois de uma pausa, para o servidor ja estar de pe.
rem A espera usa `ping` e nao `timeout` de proposito: `timeout` exige um
rem console interativo e aborta com "nao ha suporte para o redirecionamento
rem de entrada" quando o .bat roda a partir de um script, de um agendador ou
rem com a saida canalizada. O `ping` para o proprio host espera igual e
rem funciona em qualquer contexto.
start "" /b cmd /c "ping -n 5 127.0.0.1 >nul & start "" http://127.0.0.1:8756"

pushd server
!PY! -m cygen --port 8756
popd
goto :fim

rem ---------------------------------------------------------------------------

:erro
echo.
pause
endlocal
exit /b 1

:fim
endlocal
exit /b 0
