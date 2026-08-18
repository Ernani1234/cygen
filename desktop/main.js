/**
 * Shell Electron do Cygen.
 *
 * Sobe o backend Python como processo filho, espera a linha `CYGEN_READY` no
 * stdout e só então mostra a janela. Esperar o sinal em vez de dormir um tempo
 * fixo evita a tela branca de "backend ainda não subiu" em máquinas lentas.
 */

'use strict';

const electron = require('electron');
const { spawn } = require('node:child_process');
const path = require('node:path');
const http = require('node:http');

// `ELECTRON_RUN_AS_NODE` faz o binário do Electron rodar como Node puro: o
// módulo `electron` volta sem `app`, e o erro que aparece é um
// "Cannot read properties of undefined" que não diz nada sobre a causa.
// Alguns terminais e ferramentas de desenvolvimento deixam essa variável
// definida no ambiente sem avisar.
if (!electron || !electron.app) {
  console.error(
    '\nO Cygen precisa ser iniciado pelo Electron, não pelo Node.\n' +
    (process.env.ELECTRON_RUN_AS_NODE
      ? 'A variável ELECTRON_RUN_AS_NODE está definida neste terminal e força\n'
        + 'esse comportamento. Remova-a e tente de novo:\n\n'
        + '  Windows (PowerShell):  Remove-Item Env:ELECTRON_RUN_AS_NODE\n'
        + '  macOS / Linux:         unset ELECTRON_RUN_AS_NODE\n'
      : 'Use `npm start` a partir da pasta desktop/.\n')
  );
  process.exit(1);
}

const { app, BrowserWindow, shell, dialog, nativeTheme, Menu } = electron;

const SERVER_DIR = path.join(__dirname, '..', 'server');
const IS_WINDOWS = process.platform === 'win32';

let backend = null;
let win = null;
let backendUrl = null;

/** Interpretadores a tentar, na ordem. */
function pythonCandidates() {
  const fromEnv = process.env.CYGEN_PYTHON;
  const list = fromEnv ? [fromEnv] : [];
  return list.concat(IS_WINDOWS ? ['py', 'python', 'python3'] : ['python3', 'python']);
}

function startBackend() {
  return new Promise((resolve, reject) => {
    const candidates = pythonCandidates();

    const tryNext = (index) => {
      if (index >= candidates.length) {
        reject(new Error(
          'Não encontrei um Python utilizável. Instale Python 3.10 ou superior, '
          + 'ou defina a variável CYGEN_PYTHON com o caminho do interpretador.'
        ));
        return;
      }

      const exe = candidates[index];
      const args = exe === 'py' ? ['-3', '-m', 'cygen'] : ['-m', 'cygen'];

      const child = spawn(exe, args, {
        cwd: SERVER_DIR,
        env: { ...process.env, PYTHONUNBUFFERED: '1', PYTHONIOENCODING: 'utf-8' },
        windowsHide: true,
      });

      let settled = false;
      let stderrTail = '';

      child.stdout.on('data', (chunk) => {
        const text = chunk.toString();
        process.stdout.write(`[cygen] ${text}`);

        const match = text.match(/CYGEN_READY\s+(\S+)/);
        if (match && !settled) {
          settled = true;
          backend = child;
          backendUrl = match[1];
          resolve(match[1]);
        }
      });

      child.stderr.on('data', (chunk) => {
        const text = chunk.toString();
        stderrTail = (stderrTail + text).slice(-1500);
        process.stderr.write(`[cygen:err] ${text}`);
      });

      child.on('error', () => { if (!settled) tryNext(index + 1); });

      child.on('exit', (code) => {
        if (!settled) {
          // Este interpretador não serviu: tenta o próximo, mas se for o
          // último, o erro precisa carregar o stderr para ser diagnosticável.
          if (index + 1 < candidates.length) {
            tryNext(index + 1);
          } else {
            reject(new Error(
              `O backend encerrou com código ${code}.\n\n${stderrTail || '(sem saída de erro)'}`
            ));
          }
        } else if (!app.isQuiting) {
          dialog.showErrorBox('Cygen', 'O backend foi encerrado inesperadamente.');
          app.quit();
        }
      });
    };

    tryNext(0);
    setTimeout(() => reject(new Error('O backend não respondeu em 45 segundos.')), 45_000);
  });
}

/** Confirma que a API está respondendo antes de carregar a página. */
function waitForHttp(url, attempts = 40) {
  return new Promise((resolve, reject) => {
    const probe = (left) => {
      const request = http.get(`${url}/api/health`, (response) => {
        response.resume();
        resolve();
      });
      request.on('error', () => {
        if (left <= 0) { reject(new Error('A API não respondeu.')); return; }
        setTimeout(() => probe(left - 1), 260);
      });
      request.setTimeout(2500, () => { request.destroy(); });
    };
    probe(attempts);
  });
}

function createWindow(url) {
  win = new BrowserWindow({
    width: 1380,
    height: 900,
    minWidth: 960,
    minHeight: 640,
    show: false,
    backgroundColor: nativeTheme.shouldUseDarkColors ? '#151228' : '#F7F5FB',
    titleBarStyle: IS_WINDOWS ? 'default' : 'hiddenInset',
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });

  win.loadURL(url);
  win.once('ready-to-show', () => win.show());

  // Links externos abrem no navegador do sistema, não dentro do app.
  win.webContents.setWindowOpenHandler(({ url: target }) => {
    if (/^https?:/.test(target)) shell.openExternal(target);
    return { action: 'deny' };
  });

  win.on('closed', () => { win = null; });
}

function buildMenu() {
  const template = [
    {
      label: 'Cygen',
      submenu: [
        { role: 'reload', label: 'Recarregar' },
        { role: 'toggleDevTools', label: 'Ferramentas de desenvolvimento' },
        { type: 'separator' },
        { role: 'quit', label: 'Sair' },
      ],
    },
    {
      label: 'Editar',
      submenu: [
        { role: 'undo', label: 'Desfazer' },
        { role: 'redo', label: 'Refazer' },
        { type: 'separator' },
        { role: 'cut', label: 'Recortar' },
        { role: 'copy', label: 'Copiar' },
        { role: 'paste', label: 'Colar' },
        { role: 'selectAll', label: 'Selecionar tudo' },
      ],
    },
    {
      label: 'Exibir',
      submenu: [
        { role: 'resetZoom', label: 'Zoom normal' },
        { role: 'zoomIn', label: 'Aumentar' },
        { role: 'zoomOut', label: 'Diminuir' },
        { type: 'separator' },
        { role: 'togglefullscreen', label: 'Tela cheia' },
      ],
    },
  ];
  Menu.setApplicationMenu(Menu.buildFromTemplate(template));
}

app.whenReady().then(async () => {
  buildMenu();
  try {
    const url = await startBackend();
    await waitForHttp(url);
    createWindow(url);
  } catch (error) {
    dialog.showErrorBox('Não foi possível iniciar o Cygen', String(error.message || error));
    app.quit();
  }
});

app.on('window-all-closed', () => { if (!IS_WINDOWS || true) app.quit(); });

app.on('before-quit', () => {
  app.isQuiting = true;
  if (backend && !backend.killed) {
    // No Windows um SIGTERM não derruba a árvore do uvicorn; taskkill sim.
    if (IS_WINDOWS) {
      spawn('taskkill', ['/pid', String(backend.pid), '/f', '/t'], { windowsHide: true });
    } else {
      backend.kill('SIGTERM');
    }
  }
});

app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0 && backendUrl) createWindow(backendUrl);
});
