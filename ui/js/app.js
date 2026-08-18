/* ==========================================================================
   Cygen — camada de interface

   Sem framework e sem build. O estado é um objeto único; qualquer mudança
   passa por `render()`. Para uma aplicação deste tamanho isso é mais fácil de
   seguir do que um grafo de componentes — e o arquivo abre em qualquer editor
   sem `npm install`.
   ========================================================================== */

'use strict';

const state = {
  view: 'studio',
  recording: false,
  paused: false,
  picker: false,
  recStartedAt: 0,
  liveSteps: [],
  flows: [],
  flow: null,          // fluxo aberto no momento
  outputs: {},         // { cypress: {filename, code}, playwright: {...} }
  activeTab: 'cypress',
  meta: null,
  providers: [],
  chat: [],
  liveTransport: 'ws',   // 'ws' enquanto o socket vive, 'poll' se ele cair
  project: null,         // projeto Cypress gerado: caminho, arquivos, comandos
  stepsTouched: false,   // o usuário já abriu/fechou o painel de passos?
  disabledSteps: new Set(),
  rejected: {},        // { índiceDoPasso: Set(regras recusadas) }
  verification: null,
};

/* ------------------------------------------------------------------ utils */

const $  = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

/** Escapa texto para inserção segura via innerHTML. */
function esc(value) {
  return String(value ?? '').replace(/[&<>"']/g, (c) => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
  ));
}

function icon(name, cls = '') {
  return `<svg viewBox="0 0 24 24" class="${cls}"><use href="#i-${name}"/></svg>`;
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
    body: options.body ? JSON.stringify(options.body) : undefined,
  });
  const text = await response.text();
  let data;
  try { data = text ? JSON.parse(text) : {}; } catch { data = { error: text }; }
  if (!response.ok) throw new Error(data.detail || data.error || `HTTP ${response.status}`);
  return data;
}

function toast(message, kind = 'info', ms = 4200) {
  const marks = { ok: 'check', danger: 'x', warn: 'warn', info: 'info' };
  const el = document.createElement('div');
  el.className = `toast ${kind}`;
  el.innerHTML = `<span class="toast-icon">${icon(marks[kind] || 'info')}</span><span>${esc(message)}</span>`;
  $('#toasts').append(el);
  setTimeout(() => {
    el.classList.add('out');
    el.addEventListener('animationend', () => el.remove(), { once: true });
  }, ms);
}

function relTime(seconds) {
  if (!seconds) return '';
  const diff = Date.now() / 1000 - seconds;
  if (diff < 60) return 'agora há pouco';
  if (diff < 3600) return `há ${Math.floor(diff / 60)} min`;
  if (diff < 86400) return `há ${Math.floor(diff / 3600)} h`;
  return `há ${Math.floor(diff / 86400)} d`;
}

function clock(seconds) {
  const m = String(Math.floor(seconds / 60)).padStart(2, '0');
  const s = String(Math.floor(seconds % 60)).padStart(2, '0');
  return `${m}:${s}`;
}

/* Tons por tipo de passo — a cor carrega significado, não só enfeite. */
const TONES = {
  visit:  { icon: 'nav',   tint: 'var(--sky-100)',    tone: 'var(--sky-600)' },
  click:  { icon: 'mouse', tint: 'var(--lav-100)',    tone: 'var(--lav-600)' },
  dblclick:{icon: 'mouse', tint: 'var(--lav-100)',    tone: 'var(--lav-600)' },
  type:   { icon: 'type',  tint: 'var(--mint-100)',   tone: 'var(--mint-600)' },
  select: { icon: 'list',  tint: 'var(--butter-100)', tone: 'var(--butter-600)' },
  check:  { icon: 'check', tint: 'var(--mint-100)',   tone: 'var(--mint-600)' },
  upload: { icon: 'save',  tint: 'var(--peach-100)',  tone: 'var(--peach-600)' },
  keypress:{icon: 'type',  tint: 'var(--peach-100)',  tone: 'var(--peach-600)' },
  navigation:{icon:'nav',  tint: 'var(--sky-100)',    tone: 'var(--sky-600)' },
  pick:   { icon: 'target',tint: 'var(--rose-100)',   tone: 'var(--rose-600)' },
};
const toneOf = (kind) => TONES[kind] || { icon: 'bolt', tint: 'var(--ink-100)', tone: 'var(--ink-500)' };

/* ------------------------------------------------------ realce de sintaxe */

/**
 * Tokenizador de JS/TS suficiente para leitura.
 *
 * Faz uma varredura única com um regex alternado, em vez de várias passadas
 * de replace. Passadas encadeadas corrompem o resultado: a segunda começa a
 * casar dentro do HTML que a primeira acabou de inserir.
 */
function highlight(code) {
  const KEYWORDS = /\b(const|let|var|function|return|if|else|await|async|import|from|export|new|describe|it|beforeEach|test|expect|true|false|null|undefined)\b/;
  const pattern = new RegExp([
    /\/\/[^\n]*/,                          // comentário de linha
    /\/\*[\s\S]*?\*\//,                    // comentário de bloco
    /'(?:\\.|[^'\\])*'/,                   // string simples
    /"(?:\\.|[^"\\])*"/,                   // string dupla
    /`(?:\\.|[^`\\])*`/,                   // template
    /\bcy\.[a-zA-Z]+/,                     // comandos Cypress
    /\bpage\.[a-zA-Z]+/,                   // comandos Playwright
    KEYWORDS.source,
    /\b\d+(?:\.\d+)?\b/,                   // número
    /\b[a-zA-Z_$][\w$]*(?=\()/,            // chamada de função
  ].map((r) => (typeof r === 'string' ? r : r.source)).join('|'), 'g');

  let out = '';
  let last = 0;
  for (const match of code.matchAll(pattern)) {
    const token = match[0];
    out += esc(code.slice(last, match.index));
    last = match.index + token.length;

    let cls = '';
    if (token.startsWith('//') || token.startsWith('/*')) cls = 'tok-com';
    else if (/^['"`]/.test(token)) cls = 'tok-str';
    else if (/^(cy|page)\./.test(token)) cls = 'tok-cy';
    else if (KEYWORDS.test(token) && new RegExp(`^(?:${KEYWORDS.source})$`).test(token)) cls = 'tok-key';
    else if (/^\d/.test(token)) cls = 'tok-num';
    else cls = 'tok-fn';

    out += `<span class="${cls}">${esc(token)}</span>`;
  }
  out += esc(code.slice(last));
  return out;
}

/* -------------------------------------------------------------- navegação */

function go(view) {
  state.view = view;
  $$('.view').forEach((el) => { el.hidden = el.id !== `view-${view}`; });
  $$('.nav-item').forEach((el) => el.classList.toggle('active', el.dataset.view === view));

  const titles = {
    studio:   ['Estúdio', 'Grave um fluxo e deixe o Oracle deduzir as verificações'],
    record:   ['Gravação', 'Cada passo aparece aqui no instante em que acontece'],
    flows:    ['Fluxos', 'Tudo que você já gravou'],
    code:     ['Código', 'Revise, gere e verifique o teste'],
    oracle:   ['Oracle', 'As regras que deduzem verificações, sem custo'],
    rules:    ['Assistente', 'Converse com o provedor configurado'],
    settings: ['Configurações', 'Preferências desta máquina'],
  };
  const [title, sub] = titles[view] || ['Cygen', ''];
  $('#topTitle').textContent = title;
  $('#topSub').textContent = sub;

  // Reinicia a animação de entrada da vista.
  const el = $(`#view-${view}`);
  if (el) { el.style.animation = 'none'; void el.offsetHeight; el.style.animation = ''; }

  if (view === 'flows') loadFlows();
  if (view === 'oracle') renderOracle();
  if (view === 'settings') renderSettings();
}

/* ----------------------------------------------------------------- tema */

function applyTheme(theme) {
  const resolved = theme === 'auto'
    ? (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light')
    : theme;
  document.documentElement.dataset.theme = resolved;
  $('#themeIcon').setAttribute('href', resolved === 'dark' ? '#i-sun' : '#i-moon');
  localStorage.setItem('cygen-theme', theme);
}

/* -------------------------------------------------------------- WebSocket */

let socket = null;
let wsAttempts = 0;

/**
 * O WebSocket é o caminho preferido para os passos ao vivo, não o único.
 *
 * Ele depende de o servidor ter a biblioteca `websockets` instalada
 * (`uvicorn[standard]`). Quando falta, o handshake devolve 404 — e o app
 * inteiro não pode parar por causa disso. Após algumas tentativas com recuo
 * progressivo, desistimos em silêncio e a tela de gravação passa a buscar os
 * passos por HTTP. Funciona igual, só atualiza um pouco menos rápido.
 */
function connect() {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  try {
    socket = new WebSocket(`${proto}://${location.host}/ws`);
  } catch {
    state.liveTransport = 'poll';
    return;
  }

  socket.onopen = () => { wsAttempts = 0; state.liveTransport = 'ws'; };

  socket.onmessage = (event) => {
    const { type, data } = JSON.parse(event.data);
    if (type === 'event') onLiveEvent(data);
    if (type === 'recording') {
      state.recording = data.active;
      renderRecordingState();
    }
    if (type === 'verify' && data.status === 'running') {
      toast('Executando o teste no navegador…', 'info');
    }
    if (type === 'project') {
      // `npm install` demora minutos na primeira vez. Sem mostrar o que esta
      // acontecendo, a tela parece travada e o usuario cancela.
      const line = $('#runLine');
      if (line && data.line) line.textContent = data.line.slice(0, 120);
    }
  };

  socket.onclose = () => {
    wsAttempts += 1;
    if (wsAttempts > 4) {
      state.liveTransport = 'poll';
      return;              // sem WebSocket disponível: seguimos por HTTP
    }
    setTimeout(connect, Math.min(1200 * wsAttempts, 6000));
  };
  socket.onerror = () => { try { socket.close(); } catch { /* já fechado */ } };
}

function onLiveEvent(event) {
  // Um passo provisório é substituído pela versão definitiva quando a
  // evidência termina de ser coletada.
  const existing = state.liveSteps.findIndex((s) => s.seq === event.seq);
  if (existing >= 0) state.liveSteps[existing] = event;
  else state.liveSteps.push(event);

  renderLiveTimeline();
  $('#recCount').textContent = `${state.liveSteps.filter((s) => !s.provisional).length} passos`;
}

/* ------------------------------------------------------------- gravação */

async function startRecording(url, browser = 'chromium') {
  if (!url || !url.trim()) { toast('Informe o endereço da aplicação.', 'warn'); return; }
  try {
    await api('/api/record/start', {
      method: 'POST',
      body: { url: url.trim(), browser, headless: false },
    });
    state.recording = true;
    state.paused = false;
    state.liveSteps = [];
    state.recStartedAt = Date.now();
    renderRecordingState();
    renderLiveTimeline();
    go('record');
    toast('Gravando. Navegue normalmente na janela que abriu.', 'ok');
    pollPreview();
  } catch (error) {
    toast(error.message, 'danger', 8000);
  }
}

async function stopRecording() {
  try {
    const result = await api('/api/record/stop', { method: 'POST' });
    state.recording = false;
    renderRecordingState();

    const collapsed = result.collapsed || 0;
    toast(
      collapsed > 0
        ? `${result.steps.length} passos — ${collapsed} eventos de ruído foram descartados.`
        : `${result.steps.length} passos capturados.`,
      'ok', 6000,
    );

    await openFlow(result.flowId);
  } catch (error) {
    toast(error.message, 'danger');
  }
}

/** Puxa quadros do navegador enquanto a gravação estiver ativa. */
async function pollPreview() {
  if (!state.recording) return;
  try {
    const shot = await api('/api/record/screenshot');
    if (shot.ok) {
      $('#recFrame').innerHTML = `<img src="data:image/jpeg;base64,${shot.image}" alt="">`;
    }
    const status = await api('/api/record/status');
    if (status.baseUrl) $('#recUrlNow').textContent = status.baseUrl;

    // Sem WebSocket, a contagem vem daqui. A timeline detalhada só aparece
    // ao parar a gravação, mas o usuário continua vendo que está gravando.
    if (state.liveTransport === 'poll') {
      $('#recCount').textContent = `${status.eventCount || 0} passos`;
    }
  } catch { /* a janela pode ter fechado; o próximo ciclo confirma */ }
  setTimeout(pollPreview, 1100);
}

function renderRecordingState() {
  $('#recChip').hidden = !state.recording;
  $('#navRec').hidden = !state.recording;
  $('#recStartCard').hidden = state.recording;
  $('#recLive').hidden = !state.recording;
  if (!state.recording) $('#recFrame').innerHTML = '<div class="muted small">gravação encerrada</div>';
}

setInterval(() => {
  if (!state.recording || !state.recStartedAt) return;
  $('#recTime').textContent = clock((Date.now() - state.recStartedAt) / 1000);
}, 500);

function renderLiveTimeline() {
  const host = $('#recTimeline');
  if (!state.liveSteps.length) {
    host.innerHTML = `<div class="empty" style="padding:32px">
      <div class="empty-art">${icon('mouse')}</div>
      <h3>Aguardando suas ações</h3>
      <p>Clique, digite e navegue na janela do navegador. Os passos aparecem aqui.</p>
    </div>`;
    return;
  }

  host.innerHTML = state.liveSteps.slice(-40).map((step) => {
    const tone = toneOf(step.type);
    const tags = [];
    if (step.networkCount) tags.push(`<span class="chip info">${step.networkCount} req</span>`);
    if (step.hasMutations) tags.push('<span class="chip">a tela reagiu</span>');
    if (step.consoleErrors) tags.push(`<span class="chip danger">${step.consoleErrors} erro JS</span>`);

    return `<div class="step ${step.provisional ? 'provisional' : ''}">
      <div class="step-icon" style="--tint:${tone.tint};--tone:${tone.tone}">${icon(tone.icon)}</div>
      <div class="step-body">
        <div class="step-label">${esc(step.label)}</div>
        ${tags.length ? `<div class="step-meta">${tags.join('')}</div>` : ''}
      </div>
    </div>`;
  }).join('');

  host.scrollTop = host.scrollHeight;
}

/* ------------------------------------------------------------------ fluxos */

async function loadFlows() {
  try {
    const { flows } = await api('/api/flows');
    state.flows = flows;
    $('#navFlows').textContent = flows.length;
    renderFlowList();
    renderRecent();
  } catch (error) {
    toast(error.message, 'danger');
  }
}

function flowCard(flow) {
  return `<div class="card hoverable" data-flow="${esc(flow.id)}" style="cursor:pointer">
    <div class="row between">
      <strong class="truncate">${esc(flow.name)}</strong>
      ${flow.verified ? '<span class="chip ok">verificado</span>' : ''}
    </div>
    <div class="small muted truncate" style="margin-top:3px">
      ${esc(flow.description || flow.baseUrl || 'sem descrição')}
    </div>
    <div class="row wrap" style="margin-top:11px;gap:6px">
      <span class="chip">${flow.stepCount} passos</span>
      <span class="chip accent">${flow.assertionCount} verificações</span>
    </div>
    <div class="row between" style="margin-top:11px">
      <span class="small faint">${relTime(flow.updatedAt)}</span>
      <button class="btn ghost sm" data-del="${esc(flow.id)}" title="Excluir">${icon('trash')}</button>
    </div>
  </div>`;
}

function renderFlowList() {
  const host = $('#flowList');
  if (!state.flows.length) {
    host.innerHTML = `<div class="empty" style="grid-column:1/-1">
      <div class="empty-art">${icon('flows')}</div>
      <h3>Nenhum fluxo ainda</h3>
      <p>Grave sua primeira jornada e o Cygen transforma em teste.</p>
      <button class="btn primary" data-goto="record">${icon('rec')} Gravar agora</button>
    </div>`;
    return;
  }
  host.innerHTML = state.flows.map(flowCard).join('');
}

function renderRecent() {
  const host = $('#recentFlows');
  const recent = state.flows.slice(0, 3);
  host.innerHTML = recent.length
    ? recent.map(flowCard).join('')
    : `<div class="card" style="grid-column:1/-1;text-align:center;padding:30px">
         <p class="muted" style="margin:0">Seus fluxos gravados aparecem aqui.</p>
       </div>`;
}

async function openFlow(flowId) {
  try {
    const flow = await api(`/api/flows/${flowId}`);
    state.flow = flow;
    state.disabledSteps = new Set();
    state.rejected = {};
    state.verification = flow.verification || null;
    state.outputs = {};

    $('#specName').value = flow.name === 'Gravação sem nome' ? '' : (flow.name || '');
    $('#specDesc').value = flow.description || '';
    $('#specBase').value = flow.baseUrl || '';
    $('#codeEmpty').hidden = true;
    $('#codeWork').hidden = false;
    $('#codeTitle').textContent = flow.name || 'Código gerado';

    renderSteps();
    $('#codeOut').innerHTML = '<span class="tok-com">// Clique em “Gerar código”.</span>';
    $('#genWarnings').innerHTML = '';
    $('#verifyReport').innerHTML = '';
    go('code');
  } catch (error) {
    toast(error.message, 'danger');
  }
}

/* --------------------------------------------------------- passos e código */

function renderSteps() {
  const host = $('#stepList');
  const steps = state.flow?.steps || [];

  if (!steps.length) {
    host.innerHTML = '<div class="callout warn">'
      + icon('warn') + '<div>Este fluxo não tem passos utilizáveis. '
      + 'Talvez a gravação tenha sido encerrada antes de qualquer interação.</div></div>';
    return;
  }

  host.innerHTML = steps.map((step) => {
    const tone = toneOf(step.kind);
    const off = state.disabledSteps.has(step.index);
    const selector = step.selector?.primary;
    const confidence = selector?.score ?? 0;
    const level = confidence >= 0.7 ? '' : confidence >= 0.45 ? 'mid' : 'low';

    const asserts = (step.assertions || [])
      .filter((a) => !a.raw && a.confidence > 0)
      .map((a) => {
        const rejected = state.rejected[step.index]?.has(a.rule);
        const args = a.args?.length ? `(${a.args.map((v) => JSON.stringify(v)).join(', ')})` : '';
        return `<div class="assert ${rejected ? '' : 'on'}"
                     data-step="${step.index}" data-rule="${esc(a.rule)}">
          <span class="assert-check">${icon('check')}</span>
          <span class="grow">
            <span class="assert-name">${esc(a.name)}${esc(args)}</span>
            <div class="assert-why">${esc(a.why)}</div>
          </span>
          <span class="assert-conf">${Math.round(a.confidence * 100)}%</span>
        </div>`;
      }).join('');

    return `<div class="step ${off ? 'disabled' : ''}">
      <div class="step-icon" style="--tint:${tone.tint};--tone:${tone.tone}">${icon(tone.icon)}</div>
      <div class="step-body">
        <div class="step-label">${esc(step.label)}</div>
        ${selector ? `
          <div class="step-meta">
            <code class="step-sel">${esc(selector.value)}</code>
            <span class="chip ${level === '' ? 'ok' : level === 'mid' ? 'warn' : 'danger'}">
              seletor ${Math.round(confidence * 100)}%
            </span>
          </div>
          <div class="meter" style="margin-top:7px">
            <div class="meter-fill ${level}" style="width:${Math.round(confidence * 100)}%"></div>
          </div>` : ''}
        ${(step.notes || []).map((n) => `<div class="step-note">${esc(n)}</div>`).join('')}
        ${asserts ? `<div class="asserts">${asserts}</div>` : ''}
      </div>
      <div class="step-actions">
        <button class="btn ghost sm" data-toggle-step="${step.index}"
                title="${off ? 'Incluir no teste' : 'Excluir do teste'}">
          ${icon(off ? 'check' : 'x')}
        </button>
      </div>
    </div>`;
  }).join('');

  const active = steps.length - state.disabledSteps.size;
  const checks = steps.reduce((sum, s) => sum + (s.assertions || []).length, 0);
  $('#stepSummary').textContent = `${active} passos · ${checks} verificações`;

  // Fluxos curtos cabem na tela sem atrapalhar, então abrem sozinhos. O
  // problema que o recolhimento resolve só existe a partir de certo tamanho.
  if (!state.stepsTouched) setStepsOpen(steps.length <= 5);
}

/** Abre ou fecha o painel de passos. */
function setStepsOpen(open) {
  $('#stepsPanel').classList.toggle('open', open);
  $('#stepsToggle').setAttribute('aria-expanded', String(open));
  $('#stepsHint').textContent = open ? 'ocultar' : 'mostrar';
}

async function generate() {
  if (!state.flow) return;
  const button = $('#btnGenerate');
  button.disabled = true;
  button.innerHTML = '<span class="spinner"></span> Gerando…';

  // Só o que o usuário recusou explicitamente. Enviar uma lista de aceites
  // seria enviar "aceite nada" na primeira geração, quando as assertions
  // ainda não existem — e o teste sairia sem verificação alguma.
  const rejected = {};
  for (const [index, rules] of Object.entries(state.rejected)) {
    if (rules.size) rejected[index] = [...rules];
  }

  try {
    const result = await api('/api/generate', {
      method: 'POST',
      body: {
        flowId: state.flow.id,
        name: $('#specName').value || state.flow.name || 'Fluxo gravado',
        description: $('#specDesc').value,
        baseUrl: $('#specBase').value,
        disabledSteps: [...state.disabledSteps],
        rejectedRules: rejected,
        splitGroups: $('#optSplit').checked,
        verbose: $('#optVerbose').checked,
      },
    });

    state.outputs = result.outputs;
    state.flow.steps = result.steps;
    state.activeTab = Object.keys(result.outputs)[0] || 'cypress';
    renderCode();
    renderSteps();
    renderWarnings(result);
    toast(`${result.stats.commands} comandos, ${result.stats.checks} verificações.`, 'ok');
  } catch (error) {
    toast(error.message, 'danger', 7000);
  } finally {
    button.disabled = false;
    button.innerHTML = `${icon('bolt')} Gerar código`;
  }
}

function renderCode() {
  const tabs = Object.entries(state.outputs);
  const names = { cypress: 'Cypress', playwright: 'Playwright', commands: 'commands.js' };

  $('#codeTabs').innerHTML = tabs.map(([key, out]) => `
    <button class="code-tab ${key === state.activeTab ? 'active' : ''}" data-tab="${key}">
      ${names[key] || key}
    </button>`).join('')
    + `<span class="grow"></span><span class="small faint" style="padding-right:8px">
         ${esc(state.outputs[state.activeTab]?.filename || '')}
       </span>`;

  const code = state.outputs[state.activeTab]?.code || '';
  $('#codeOut').innerHTML = highlight(code);
}

function renderWarnings(result) {
  const parts = [];

  if (result.warnings?.length) {
    parts.push(`<div class="callout warn" style="margin-bottom:12px">${icon('warn')}
      <div><strong>Pontos de atenção</strong>
      <ul style="margin:6px 0 0;padding-left:18px">
        ${result.warnings.map((w) => `<li>${esc(w)}</li>`).join('')}
      </ul></div></div>`);
  }

  if (result.envKeys?.length) {
    parts.push(`<div class="callout" style="margin-bottom:12px">${icon('info')}
      <div><strong>Credenciais fora do código.</strong> O teste lê as senhas de variáveis
      de ambiente — nenhuma senha foi escrita no arquivo. Antes de rodar, defina:
      <div class="mono small" style="margin-top:6px">
        ${result.envKeys.map((k) => `CYPRESS_${esc(k)}=…`).join('<br>')}
      </div></div></div>`);
  }

  if (result.suggestions?.length) {
    parts.push(`<div class="callout" style="margin-bottom:12px">${icon('sparkle')}
      <div><strong>Refatoração sugerida.</strong>
      ${result.suggestions.map((s) => esc(s.suggestion)).join(' ')}</div></div>`);
  }

  $('#genWarnings').innerHTML = parts.join('');
}

async function verify() {
  if (!state.flow) return;
  if (!Object.keys(state.outputs).length) { toast('Gere o código antes de verificar.', 'warn'); return; }

  const button = $('#btnVerify');
  button.disabled = true;
  button.innerHTML = '<span class="spinner"></span> Executando…';
  $('#verifyReport').innerHTML = `<div class="callout" style="margin-bottom:12px">${icon('info')}
    <div>Abrindo um navegador oculto e reproduzindo cada passo contra a aplicação real…</div></div>`;

  try {
    const result = await api('/api/verify', {
      method: 'POST',
      body: { flowId: state.flow.id, baseUrl: $('#specBase').value },
    });

    state.verification = result.report;
    if (result.code) {
      state.outputs.cypress = { ...state.outputs.cypress, code: result.code };
      renderCode();
    }
    renderVerification(result.report);

    if (result.report.healed) {
      toast(`${result.report.healed} seletor(es) curados automaticamente.`, 'ok', 6000);
    } else if (result.report.broken) {
      toast(`${result.report.broken} passo(s) não puderam ser resolvidos.`, 'warn', 6000);
    } else {
      toast('Todos os passos funcionaram.', 'ok');
    }
  } catch (error) {
    $('#verifyReport').innerHTML = `<div class="callout danger" style="margin-bottom:12px">
      ${icon('warn')}<div>${esc(error.message)}</div></div>`;
    toast(error.message, 'danger', 7000);
  } finally {
    button.disabled = false;
    button.innerHTML = `${icon('heal')} Verificar e curar`;
  }
}

function renderVerification(report) {
  const kind = report.broken ? 'warn' : report.healed ? 'info' : 'ok';
  const rows = report.steps
    .filter((s) => s.status !== 'skipped')
    .map((s) => {
      const badge = { ok: 'ok', healed: 'info', broken: 'danger' }[s.status] || '';
      const labels = { ok: 'ok', healed: 'curado', broken: 'falhou' };
      return `<div class="row" style="gap:8px;padding:5px 0;border-top:1px solid var(--border-soft)">
        <span class="chip ${badge}">${labels[s.status] || s.status}</span>
        <code class="mono small truncate grow">${esc(s.selector || s.op)}</code>
        ${s.message ? `<span class="small faint truncate" style="max-width:44ch"
          title="${esc(s.message)}">${esc(s.message)}</span>` : ''}
      </div>`;
    }).join('');

  $('#verifyReport').innerHTML = `<div class="callout ${kind}" style="margin-bottom:12px">
    ${icon(report.broken ? 'warn' : 'check')}
    <div class="grow">
      <strong>${esc(report.summary)}</strong>
      <div style="margin-top:8px">${rows}</div>
    </div></div>`;
}

/* ------------------------------------------------------------------ Oracle */

async function renderOracle() {
  if (!state.meta) {
    try { state.meta = await api('/api/meta'); }
    catch (error) { toast(error.message, 'danger'); return; }
  }
  const { oracle, assertions, providers } = state.meta;

  $('#oracleStats').innerHTML = [
    ['Regras de inferência', oracle.count, 'var(--lav-100)',
     'cada uma reconhece um padrão e explica o porquê'],
    ['Verificações catalogadas', assertions.total, 'var(--mint-100)',
     `em ${assertions.categories.length} categorias`],
    ['Custo por análise', 'R$ 0', 'var(--butter-100)',
     'roda local, sem chamar API nenhuma'],
  ].map(([label, value, tint, hint]) => `
    <div class="card stat" style="--tint:${tint}">
      <div class="stat-value">${value}</div>
      <div class="stat-label">${label}</div>
      <div class="stat-hint">${hint}</div>
    </div>`).join('');

  $('#ruleList').innerHTML = oracle.rules.map((rule) => `
    <div class="card">
      <div class="row between">
        <strong style="font-size:13.5px">${esc(rule.title)}</strong>
        <code class="mono small faint">${esc(rule.id)}</code>
      </div>
    </div>`).join('');

  renderAssertions('');
}

let assertCatalog = null;

async function renderAssertions(query) {
  if (!assertCatalog) {
    try { assertCatalog = (await api('/api/assertions')).catalog; }
    catch { return; }
  }

  const host = $('#assertList');
  const term = query.trim().toLowerCase();
  const groups = Object.entries(assertCatalog).map(([category, items]) => {
    const matches = items.filter((item) => !term
      || item.name.toLowerCase().includes(term)
      || item.description.toLowerCase().includes(term));
    return [category, matches];
  }).filter(([, items]) => items.length);

  if (!groups.length) {
    host.innerHTML = '<p class="muted" style="grid-column:1/-1">Nada encontrado.</p>';
    return;
  }

  host.innerHTML = groups.map(([category, items]) => `
    <div class="card">
      <div class="card-title">${esc(category)}</div>
      <div class="col" style="gap:9px">
        ${items.map((item) => `
          <div>
            <code class="mono" style="color:var(--accent);font-size:12px">${esc(item.name)}</code>
            <div class="small muted">${esc(item.description)}</div>
            <code class="mono small faint">${esc(item.example)}</code>
          </div>`).join('')}
      </div>
    </div>`).join('');
}

/* ------------------------------------------------------------- assistente */

async function loadProviders() {
  try {
    const { providers } = await api('/api/ai/providers');
    state.providers = providers;

    const select = $('#chatProvider');
    select.innerHTML = providers.map((p) => `
      <option value="${esc(p.id)}" ${p.configured ? '' : 'disabled'}>
        ${esc(p.label)}${p.configured ? '' : ' — sem chave'}
      </option>`).join('');
    select.value = state.meta?.settings?.provider || 'native';
    syncModels();
  } catch (error) {
    toast(error.message, 'danger');
  }
}

function syncModels() {
  const provider = state.providers.find((p) => p.id === $('#chatProvider').value);
  $('#chatModel').innerHTML = (provider?.models || [])
    .map((m) => `<option value="${esc(m.id)}">${esc(m.label)}</option>`).join('');
}

async function sendChat() {
  const input = $('#chatInput');
  const message = input.value.trim();
  if (!message) return;

  state.chat.push({ role: 'user', text: message });
  input.value = '';
  renderChat(true);

  try {
    const result = await api('/api/ai/chat', {
      method: 'POST',
      body: {
        message,
        code: state.outputs[state.activeTab]?.code || '',
        provider: $('#chatProvider').value,
        model: $('#chatModel').value,
        mode: $('#chatMode').value,
      },
    });

    state.chat.push({
      role: 'assistant',
      text: result.ok ? result.text : `⚠ ${result.error}`,
      usage: result.usage,
      elapsed: result.elapsedMs,
      provider: result.provider,
    });

    if (result.ok && result.usage.cost > 0) {
      $('#chatCost').textContent =
        `${result.usage.totalTokens} tokens · US$ ${result.usage.cost.toFixed(5)} · ${result.elapsedMs}ms`;
    }
  } catch (error) {
    state.chat.push({ role: 'assistant', text: `⚠ ${error.message}` });
  }
  renderChat();
}

function renderChat(pending = false) {
  const host = $('#chatLog');

  host.innerHTML = state.chat.map((msg) => {
    const mine = msg.role === 'user';
    // O relatório do Oracle é tabular: linhas, trechos de código e recuo
    // carregam significado. Fonte proporcional embaralharia o alinhamento.
    const isReport = !mine && msg.provider === 'native';

    const who = mine ? 'Você'
      : isReport ? 'Oracle · revisão local, custo zero'
      : 'Assistente';

    const body = isReport
      ? `<pre class="review-report">${highlightReview(msg.text)}</pre>`
      : `<div style="white-space:pre-wrap;line-height:1.62">${esc(msg.text)}</div>`;

    return `<div class="card" style="
        border-color:${mine ? 'var(--accent-line)' : isReport ? 'var(--info-line)' : 'var(--border-soft)'};
        background:${mine ? 'var(--accent-bg)' : 'var(--bg-elevated)'};
        margin-left:${mine ? '12%' : '0'};margin-right:${mine ? '0' : '4%'}">
      <div class="card-title" style="margin-bottom:6px">${esc(who)}</div>
      ${body}
      ${msg.usage?.cost > 0 ? `<div class="small faint" style="margin-top:8px">
        ${msg.usage.totalTokens} tokens · US$ ${msg.usage.cost.toFixed(5)}</div>` : ''}
    </div>`;
  }).join('') + (pending ? `<div class="card"><span class="spinner"></span>
      <span class="muted small" style="margin-left:8px">analisando…</span></div>` : '');

  host.scrollTop = host.scrollHeight;
}

/** Colore as marcas de severidade do relatório do Oracle. */
function highlightReview(text) {
  return esc(text)
    .replace(/^(✕ ERRO.*)$/gm,      '<span class="sev-err">$1</span>')
    .replace(/^(▲ ATENÇÃO.*)$/gm,   '<span class="sev-warn">$1</span>')
    .replace(/^(○ SUGESTÃO.*)$/gm,  '<span class="sev-hint">$1</span>')
    .replace(/^(✓ BOM.*)$/gm,       '<span class="sev-ok">$1</span>')
    .replace(/(nota \d+\/100)/,     '<span class="sev-score">$1</span>');
}

/* ---------------------------------------------------------- configurações */

async function renderSettings() {
  if (!state.meta) state.meta = await api('/api/meta');
  const s = state.meta.settings;

  $('#setCypress').checked = s.emitCypress;
  $('#setPlaywright').checked = s.emitPlaywright;
  $('#setAutoVerify').checked = s.autoVerify;
  $('#setHeadless').checked = s.headless;
  $('#setConfidence').value = s.minConfidence;
  $('#confLabel').textContent = `${s.minConfidence} — sugestões abaixo disso não aparecem`;
  $('#setAttrs').value = (s.preferredAttrs || []).join(', ');

  if (!state.providers.length) await loadProviders();

  $('#providerList').innerHTML = state.providers.map((p) => `
    <div class="row between" style="padding:7px 0;border-bottom:1px solid var(--border-soft)">
      <div class="grow">
        <div class="row" style="gap:7px">
          <strong style="font-size:13px">${esc(p.label)}</strong>
          ${p.local ? '<span class="chip">local</span>' : ''}
        </div>
        <div class="small faint">${p.envKeys.length ? esc(p.envKeys.join(' / ')) : 'não requer chave'}</div>
      </div>
      <span class="chip ${p.configured ? 'ok' : ''}">${p.configured ? 'pronto' : 'inativo'}</span>
    </div>`).join('');
}

async function saveSettings() {
  const values = {
    emitCypress: $('#setCypress').checked,
    emitPlaywright: $('#setPlaywright').checked,
    autoVerify: $('#setAutoVerify').checked,
    headless: $('#setHeadless').checked,
    minConfidence: parseFloat($('#setConfidence').value),
    preferredAttrs: $('#setAttrs').value.split(',').map((s) => s.trim()).filter(Boolean),
  };
  try {
    state.meta.settings = await api('/api/settings', { method: 'POST', body: { values } });
    toast('Configurações salvas.', 'ok', 2200);
  } catch (error) {
    toast(error.message, 'danger');
  }
}

/* ------------------------------------------------------- paleta de comandos */

const COMMANDS = [
  { label: 'Gravar um fluxo novo',   icon: 'rec',    run: () => go('record') },
  { label: 'Abrir o Estúdio',        icon: 'studio', run: () => go('studio') },
  { label: 'Ver fluxos salvos',      icon: 'flows',  run: () => go('flows') },
  { label: 'Ver o código gerado',    icon: 'code',   run: () => go('code') },
  { label: 'Gerar código agora',     icon: 'bolt',   run: () => generate() },
  { label: 'Verificar e curar',      icon: 'heal',   run: () => verify() },
  { label: 'Conhecer o Oracle',      icon: 'oracle', run: () => go('oracle') },
  { label: 'Falar com o assistente', icon: 'sparkle',run: () => go('rules') },
  { label: 'Configurações',          icon: 'cog',    run: () => go('settings') },
  { label: 'Alternar tema',          icon: 'moon',   run: () => toggleTheme() },
];

let paletteIndex = 0;

function openPalette() {
  $('#palette').hidden = false;
  $('#paletteInput').value = '';
  paletteIndex = 0;
  renderPalette('');
  $('#paletteInput').focus();
}

function closePalette() { $('#palette').hidden = true; }

function paletteMatches(query) {
  const term = query.trim().toLowerCase();
  return term ? COMMANDS.filter((c) => c.label.toLowerCase().includes(term)) : COMMANDS;
}

function renderPalette(query) {
  const items = paletteMatches(query);
  paletteIndex = Math.min(paletteIndex, Math.max(0, items.length - 1));
  $('#paletteList').innerHTML = items.length
    ? items.map((c, i) => `<div class="palette-item ${i === paletteIndex ? 'sel' : ''}" data-cmd="${i}">
        ${icon(c.icon)}<span>${esc(c.label)}</span>
        ${i === paletteIndex ? '<span class="k">enter</span>' : ''}
      </div>`).join('')
    : '<div class="palette-item muted">Nenhum comando corresponde.</div>';
}

function runPalette(index) {
  const items = paletteMatches($('#paletteInput').value);
  const command = items[index];
  if (command) { closePalette(); command.run(); }
}

function toggleTheme() {
  const current = localStorage.getItem('cygen-theme') || 'auto';
  const next = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
  applyTheme(next);
}

/* ------------------------------------------------------------------- eventos */

document.addEventListener('click', async (event) => {
  const target = event.target;

  const nav = target.closest('[data-view]');
  if (nav) { go(nav.dataset.view); return; }

  const goto = target.closest('[data-goto]');
  if (goto) { go(goto.dataset.goto); return; }

  const del = target.closest('[data-del]');
  if (del) {
    event.stopPropagation();
    if (!confirm('Excluir este fluxo? A gravação não poderá ser recuperada.')) return;
    try {
      await api(`/api/flows/${del.dataset.del}`, { method: 'DELETE' });
      toast('Fluxo excluído.', 'ok', 2200);
      loadFlows();
    } catch (error) { toast(error.message, 'danger'); }
    return;
  }

  const card = target.closest('[data-flow]');
  if (card) { openFlow(card.dataset.flow); return; }

  const tab = target.closest('[data-tab]');
  if (tab) { state.activeTab = tab.dataset.tab; renderCode(); return; }

  const toggle = target.closest('[data-toggle-step]');
  if (toggle) {
    const index = Number(toggle.dataset.toggleStep);
    state.disabledSteps.has(index)
      ? state.disabledSteps.delete(index)
      : state.disabledSteps.add(index);
    renderSteps();
    return;
  }

  const assert = target.closest('[data-rule]');
  if (assert) {
    const step = Number(assert.dataset.step);
    const rule = assert.dataset.rule;
    state.rejected[step] ??= new Set();
    state.rejected[step].has(rule)
      ? state.rejected[step].delete(rule)
      : state.rejected[step].add(rule);
    renderSteps();
    return;
  }

  if (target.closest('#stepsToggle')) {
    // Uma vez que o usuário decide, respeitamos a escolha dele: o próximo
    // `renderSteps` não volta a abrir ou fechar por conta própria.
    state.stepsTouched = true;
    setStepsOpen(!$('#stepsPanel').classList.contains('open'));
    return;
  }

  // Botoes do painel de projeto: renderizados dinamicamente, entao vivem na
  // delegacao em vez de um onclick fixo.
  if (target.closest('#btnRunSuite')) { runSuite(); return; }
  if (target.closest('#btnOpenCypress')) { openCypress(); return; }
  if (target.closest('#btnReveal')) {
    api('/api/project/reveal', { method: 'POST', body: { path: state.project.path } })
      .then((result) => {
        if (result.ok) toast('Pasta aberta no explorador.', 'ok', 2400);
        else toast(result.error || 'Não consegui abrir a pasta.', 'warn');
      })
      .catch((error) => toast(error.message, 'danger'));
    return;
  }
  if (target.closest('#btnCopyPath')) {
    navigator.clipboard.writeText(state.project.path)
      .then(() => toast('Caminho copiado.', 'ok', 2200))
      .catch(() => toast('Não consegui copiar.', 'warn'));
    return;
  }

  const paletteItem = target.closest('[data-cmd]');
  if (paletteItem) { runPalette(Number(paletteItem.dataset.cmd)); return; }

  if (target.closest('#palette') === null && !$('#palette').hidden) closePalette();
});

$('#themeBtn').onclick = toggleTheme;
$('#paletteHint').onclick = openPalette;

$('#quickStart').onclick = () => startRecording($('#quickUrl').value);
$('#quickUrl').addEventListener('keydown', (e) => {
  if (e.key === 'Enter') startRecording($('#quickUrl').value);
});

$('#recStart').onclick = () => startRecording($('#recUrl').value, $('#recBrowser').value);
$('#recUrl').addEventListener('keydown', (e) => {
  if (e.key === 'Enter') startRecording($('#recUrl').value, $('#recBrowser').value);
});
$('#recStop').onclick = stopRecording;

$('#recPause').onclick = async () => {
  state.paused = !state.paused;
  await api(`/api/record/${state.paused ? 'pause' : 'resume'}`, { method: 'POST' });
  $('#recPause').innerHTML = state.paused
    ? `${icon('play')} Retomar` : `${icon('pause')} Pausar`;
  toast(state.paused ? 'Gravação pausada.' : 'Gravando de novo.', 'info', 2200);
};

$('#recPick').onclick = async () => {
  state.picker = !state.picker;
  await api('/api/record/picker', { method: 'POST', body: { active: state.picker } });
  $('#recPick').classList.toggle('primary', state.picker);
  toast(state.picker
    ? 'Clique num elemento da página para criar uma verificação.'
    : 'Modo de apontar desligado.', 'info', 3200);
};

$('#btnGenerate').onclick = generate;
$('#btnVerify').onclick = verify;

$('#btnScaffold').onclick = async () => {
  if (!state.flow) return;
  if (!Object.keys(state.outputs).length) {
    toast('Gere o código antes de montar o projeto.', 'warn');
    return;
  }

  const button = $('#btnScaffold');
  button.disabled = true;
  button.innerHTML = '<span class="spinner"></span> Montando…';

  try {
    const result = await api('/api/scaffold', {
      method: 'POST',
      body: {
        flowId: state.flow.id,
        name: $('#specName').value || state.flow.name || 'Fluxo gravado',
        description: $('#specDesc').value,
        baseUrl: $('#specBase').value,
        disabledSteps: [...state.disabledSteps],
        verbose: $('#optVerbose').checked,
      },
    });
    renderScaffold(result);
    toast(`Projeto criado com ${result.fileList.length} arquivos.`, 'ok', 5200);
  } catch (error) {
    toast(error.message, 'danger', 7000);
  } finally {
    button.disabled = false;
    button.innerHTML = `${icon('package')} Gerar projeto completo`;
  }
};

/**
 * Mostra o projeto gerado com botoes que executam.
 *
 * A versao anterior exibia os comandos para copiar no terminal. Como o Cygen
 * sabe a pasta, sabe quais credenciais o teste pede e consegue chamar o npm,
 * pedir que o usuario faca isso a mao era so devolver o trabalho.
 */
function renderScaffold(result) {
  state.project = result;

  const commands = result.commands.length
    ? result.commands.map((c) => `
        <div style="padding:5px 0;border-top:1px solid var(--border-soft)">
          <code class="mono" style="color:var(--accent)">cy.${esc(c.name)}()</code>
          <div class="small muted">${esc(c.doc)}</div>
        </div>`).join('')
    : '<div class="small muted">Nenhuma repetição justificou um comando.</div>';

  // Um campo por credencial que o teste pede. Vão para `cypress.env.json`,
  // que o .gitignore do projeto já protege.
  const creds = result.envKeys.length
    ? `<div class="card-title mt" style="margin-bottom:8px">Credenciais</div>
       <div class="col" style="gap:8px">
         ${result.envKeys.map((k) => `
           <div class="field">
             <label for="env-${esc(k)}">CYPRESS_${esc(k)}</label>
             <input class="input" id="env-${esc(k)}" data-env="${esc(k)}"
                    type="password" autocomplete="off"
                    placeholder="o valor real, para o teste conseguir entrar">
           </div>`).join('')}
       </div>
       <div class="hint" style="margin-top:6px">
         Salvas em <code class="mono">cypress.env.json</code>, que o
         <code class="mono">.gitignore</code> do projeto já ignora.
       </div>`
    : '';

  $('#scaffoldResult').innerHTML = `
    <div class="callout ok" style="margin-top:14px;display:block">
      <div class="row" style="gap:10px;margin-bottom:12px">
        ${icon('package')}
        <strong>Projeto pronto</strong>
        <span class="chip ok">${result.fileList.length} arquivos</span>
      </div>

      <div class="small muted" style="margin-bottom:4px">Criado em</div>
      <code class="mono small" style="display:block;padding:8px 11px;
            background:var(--bg-sunken);border-radius:var(--r);word-break:break-all">
        ${esc(result.path)}
      </code>

      ${creds}

      <div class="row wrap mt" style="gap:9px">
        <button class="btn primary" id="btnRunSuite">
          ${icon('play')} Rodar agora
        </button>
        <button class="btn" id="btnOpenCypress">
          ${icon('rec')} Abrir o Cypress
        </button>
        <button class="btn" id="btnReveal" title="Abre a pasta no explorador de arquivos">
          ${icon('folder')} Ver pasta
        </button>
        <button class="btn ghost" id="btnCopyPath" title="Copia o caminho">
          ${icon('copy')} Copiar caminho
        </button>
      </div>
      <div class="hint" style="margin-top:7px">
        Na primeira vez o Cypress é baixado — alguns minutos. Depois é imediato.
      </div>

      <div id="runOutput"></div>

      <details style="margin-top:14px">
        <summary class="small muted" style="cursor:pointer">
          Ver arquivos e comandos gerados
        </summary>
        <div class="grid c2 mt" style="gap:14px;align-items:start">
          <div>
            <div class="card-title" style="margin-bottom:6px">Arquivos</div>
            ${result.fileList.map((f) => `
              <div class="mono small" style="color:var(--text-muted)">${esc(f)}</div>
            `).join('')}
          </div>
          <div>
            <div class="card-title" style="margin-bottom:6px">Comandos extraídos</div>
            ${commands}
          </div>
        </div>
      </details>
    </div>`;
}

/** Valores digitados nos campos de credencial. */
function projectEnv() {
  const out = {};
  $$('[data-env]').forEach((input) => {
    if (input.value.trim()) out[input.dataset.env] = input.value;
  });
  return out;
}

/** Área de progresso e resultado da execução. */
function runLog(html) { $('#runOutput').innerHTML = html; }

function renderRunResult(result) {
  if (!result.ok && result.error) {
    runLog(`<div class="callout danger" style="margin-top:12px">
      ${icon('warn')}<div><strong>Não foi possível rodar</strong>
      <div class="small" style="margin-top:5px">${esc(result.error)}</div></div></div>`);
    return;
  }

  const passed = result.failing === 0 && result.tests > 0;
  const failures = (result.failures || []).map((f) => `
    <div style="margin-top:9px;padding-top:9px;border-top:1px solid var(--border-soft)">
      <strong class="small">${esc(f.title)}</strong>
      <pre class="mono small" style="margin:5px 0 0;white-space:pre-wrap;
           color:var(--text-muted)">${esc(f.message)}</pre>
    </div>`).join('');

  runLog(`<div class="callout ${passed ? 'ok' : 'warn'}" style="margin-top:12px;display:block">
    <div class="row" style="gap:10px">
      ${icon(passed ? 'check' : 'warn')}
      <strong>${passed
        ? `Passou — ${result.passing} de ${result.tests}`
        : `${result.failing} de ${result.tests} falharam`}</strong>
      <span class="chip">${((result.durationMs || 0) / 1000).toFixed(1)}s</span>
    </div>
    ${failures}
  </div>`);
}

async function runSuite() {
  if (!state.project) return;
  const button = $('#btnRunSuite');
  button.disabled = true;
  button.innerHTML = '<span class="spinner"></span> Rodando…';
  runLog(`<div class="callout" style="margin-top:12px">
    <span class="spinner"></span>
    <div id="runLine" class="small muted">preparando…</div></div>`);

  try {
    const result = await api('/api/project/run', {
      method: 'POST',
      body: { path: state.project.path, env: projectEnv() },
    });
    renderRunResult(result);
    if (result.tests > 0) {
      toast(result.failing === 0
        ? `Passou: ${result.passing} de ${result.tests}.`
        : `${result.failing} de ${result.tests} falharam.`,
        result.failing === 0 ? 'ok' : 'warn', 6000);
    }
  } catch (error) {
    renderRunResult({ ok: false, error: error.message });
  } finally {
    button.disabled = false;
    button.innerHTML = `${icon('play')} Rodar agora`;
  }
}

async function openCypress() {
  if (!state.project) return;
  const button = $('#btnOpenCypress');
  button.disabled = true;
  button.innerHTML = '<span class="spinner"></span> Abrindo…';
  runLog(`<div class="callout" style="margin-top:12px">
    <span class="spinner"></span>
    <div id="runLine" class="small muted">preparando…</div></div>`);

  try {
    const result = await api('/api/project/open', {
      method: 'POST',
      body: { path: state.project.path, env: projectEnv() },
    });
    if (result.ok) {
      runLog(`<div class="callout ok" style="margin-top:12px">${icon('check')}
        <div>${esc(result.message)}</div></div>`);
      toast('Cypress abrindo.', 'ok');
    } else {
      runLog(`<div class="callout danger" style="margin-top:12px">${icon('warn')}
        <div>${esc(result.error || 'Falha ao abrir.')}</div></div>`);
    }
  } catch (error) {
    toast(error.message, 'danger', 7000);
  } finally {
    button.disabled = false;
    button.innerHTML = `${icon('rec')} Abrir o Cypress`;
  }
}

$('#btnCopy').onclick = async () => {
  const code = state.outputs[state.activeTab]?.code || '';
  if (!code) { toast('Nada para copiar ainda.', 'warn'); return; }
  await navigator.clipboard.writeText(code);
  toast('Código copiado.', 'ok', 2000);
};

$('#btnSave').onclick = async () => {
  const output = state.outputs[state.activeTab];
  if (!output) { toast('Gere o código primeiro.', 'warn'); return; }
  try {
    const result = await api('/api/export', {
      method: 'POST',
      body: {
        name: $('#specName').value || 'teste',
        code: output.code,
        extension: state.activeTab === 'playwright' ? '.spec.ts' : '.cy.js',
      },
    });
    toast(`Salvo em ${result.path}`, 'ok', 6500);
  } catch (error) { toast(error.message, 'danger'); }
};

/**
 * "Pedir revisão à IA" precisa revisar, não preencher um campo.
 *
 * O comportamento anterior levava para a aba do assistente com a pergunta
 * digitada e parava aí, esperando outro clique. Como o código já está em mãos
 * e a pergunta é sempre a mesma, esse clique extra não decidia nada.
 */
$('#btnAsk').onclick = () => {
  const code = state.outputs[state.activeTab]?.code || '';
  if (!code) { toast('Gere o código antes de pedir a revisão.', 'warn'); return; }

  go('rules');
  $('#chatMode').value = 'review';
  $('#chatInput').value = 'Revise este teste e aponte o que pode quebrar em produção.';
  sendChat();
};

$('#chatSend').onclick = sendChat;
$('#chatInput').addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) sendChat();
});
$('#chatProvider').onchange = syncModels;

$('#assertSearch').addEventListener('input', (e) => renderAssertions(e.target.value));

$('#setConfidence').addEventListener('input', (e) => {
  $('#confLabel').textContent = `${e.target.value} — sugestões abaixo disso não aparecem`;
});
['#setCypress', '#setPlaywright', '#setAutoVerify', '#setHeadless',
 '#setConfidence', '#setAttrs'].forEach((sel) => {
  $(sel).addEventListener('change', saveSettings);
});

$('#btnHealth').onclick = async () => {
  const row = $('#healthRow');
  row.innerHTML = '<span class="spinner"></span> <span class="muted small">verificando…</span>';
  try {
    const health = await api('/api/health');
    const browser = health.browser;
    row.innerHTML = `
      <span class="chip ${browser.ok ? 'ok' : 'danger'}">
        navegador ${browser.ok ? (browser.version || 'pronto') : 'indisponível'}
      </span>
      <span class="chip">${health.providers.providers} provedores</span>
      <span class="chip accent">${health.providers.configured} configurados</span>
      ${browser.ok ? '' : `<div class="callout danger" style="width:100%;margin-top:10px">
        ${icon('warn')}<div>${esc(browser.error || '')}<br>
        <code class="mono small">python -m playwright install chromium</code></div></div>`}`;
  } catch (error) {
    row.innerHTML = `<div class="callout danger" style="width:100%">${icon('warn')}
      <div>${esc(error.message)}</div></div>`;
  }
};

$('#paletteInput').addEventListener('input', (e) => { paletteIndex = 0; renderPalette(e.target.value); });
$('#paletteInput').addEventListener('keydown', (e) => {
  const items = paletteMatches(e.target.value);
  if (e.key === 'ArrowDown') { e.preventDefault(); paletteIndex = (paletteIndex + 1) % items.length; renderPalette(e.target.value); }
  if (e.key === 'ArrowUp')   { e.preventDefault(); paletteIndex = (paletteIndex - 1 + items.length) % items.length; renderPalette(e.target.value); }
  if (e.key === 'Enter')     { e.preventDefault(); runPalette(paletteIndex); }
  if (e.key === 'Escape')    closePalette();
});

document.addEventListener('keydown', (e) => {
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); openPalette(); }
  if (e.key === 'Escape' && !$('#palette').hidden) closePalette();
  if ((e.ctrlKey || e.metaKey) && e.key === 'Enter' && state.view === 'code') { e.preventDefault(); generate(); }
});

/* ---------------------------------------------------------------- arranque */

async function boot() {
  applyTheme(localStorage.getItem('cygen-theme') || 'auto');
  connect();

  try {
    state.meta = await api('/api/meta');
  } catch {
    toast('Não consegui falar com o backend do Cygen.', 'danger', 9000);
    return;
  }

  const { oracle, assertions, providers } = state.meta;
  $('#stats').innerHTML = [
    ['Regras do Oracle', oracle.count, 'var(--lav-100)', 'deduzem verificações sem IA paga'],
    ['Verificações', assertions.total, 'var(--mint-100)', `${assertions.categories.length} categorias`],
    ['Provedores de IA', providers.providers, 'var(--sky-100)', `${providers.configured} prontos para uso`],
    ['Custo por análise', 'R$ 0', 'var(--butter-100)', 'o Oracle roda local'],
  ].map(([label, value, tint, hint]) => `
    <div class="card stat" style="--tint:${tint}">
      <div class="stat-value">${value}</div>
      <div class="stat-label">${label}</div>
      <div class="stat-hint">${hint}</div>
    </div>`).join('');

  $('#changes').innerHTML = [
    ['Seletores que resistem', 'Cada elemento recebe um seletor primário e reservas, ranqueados por unicidade real na página. Classes de framework e ids gerados são descartados.'],
    ['Verificações deduzidas', `${oracle.count} regras olham o que a tela fez — rede, DOM, rota, storage — e propõem a assertion correspondente, com a justificativa.`],
    ['O teste se prova', 'O Cygen roda o próprio teste antes de entregar. Se um seletor falha, ele troca pela reserva e reescreve.'],
    ['Senha nunca no código', 'Campos de credencial viram Cypress.env(). O valor não é gravado em lugar nenhum.'],
  ].map(([title, text]) => `
    <div>
      <strong style="font-size:13px">${esc(title)}</strong>
      <div class="muted" style="line-height:1.55">${esc(text)}</div>
    </div>`).join('');

  await loadFlows();
  await loadProviders();

  // Se o backend foi reiniciado no meio de uma gravação, a UI reflete isso.
  try {
    const status = await api('/api/record/status');
    if (status.recording) {
      state.recording = true;
      state.recStartedAt = Date.now() - (status.duration || 0) * 1000;
      renderRecordingState();
      pollPreview();
    }
  } catch { /* sem sessão ativa */ }
}

boot();
