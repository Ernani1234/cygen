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
  disabledSteps: new Set(),
  rejected: {},        // { índiceDoPasso: Set(regras recusadas) }
  verification: null,
  pane: 'code',          // aba da coluna direita: code | diag | project
  openSteps: new Set(),  // passos com o detalhe aberto
  // Código editado à mão, por aba. Uma aba ausente aqui usa o código gerado;
  // presente, o do usuário vence — inclusive na hora de montar o projeto.
  edits: {},
  suites: [],            // resumo de todas as sequências
  suite: null,           // sequência aberta, já com os fluxos resolvidos
  suiteOutputs: {},      // arquivos gerados da sequência
  suiteTab: 'cypress',   // arquivo aberto no editor da sequência
  autoSteps: [],         // passos que o agente já deu
  autoRunning: false,
  autoAmbienteOk: false, // o usuário confirmou o alvo desta sessão
  stepFilter: 'all',     // all | weak | pinned | issues
  stepQuery: '',
  // O projeto no disco foi gerado antes da última troca de seletor? Enquanto
  // for verdade, rodar de novo testaria o seletor antigo — e o usuário
  // concluiria que a troca não funcionou.
  projectStale: false,
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
    suites:   ['Sequências', 'Vários fluxos num arquivo, na ordem em que rodam'],
    auto:     ['Auto-teste', 'A IA explora o sistema e grava os fluxos'],
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
  if (view === 'suites') {
    // A lista de fluxos alimenta o seletor "adicionar um fluxo".
    loadFlows();
    if (!state.suite) loadSuites();
  }
  if (view === 'auto') {
    (state.providers.length ? Promise.resolve() : loadProviders())
      .then(renderAutoProviders);
  }
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
    if (type === 'autotest') {
      // Os passos chegam pelo socket para a tela acompanhar em tempo real,
      // do mesmo jeito que a gravação manual.
      if (data.tipo === 'passo' || data.tipo === 'marco' || data.tipo === 'bloqueado') {
        state.autoSteps.push(data);
        renderAutoSteps();
        if (data.url) $('#autoUrlNow').textContent = data.url;
        $('#autoSummary').textContent =
          `${state.autoSteps.filter((s) => s.tipo === 'passo').length} passos · `
          + `${state.autoSteps.filter((s) => s.tipo === 'marco').length} fluxos`;
      }
    }
    if (type === 'project') {
      // `npm install` demora minutos na primeira vez. Sem mostrar o que esta
      // acontecendo, a tela parece travada e o usuario cancela.
      if (data.line) {
        $$('.run-line').forEach((el) => { el.textContent = data.line.slice(0, 120); });
      }
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
      <strong class="truncate" data-flow-name="${esc(flow.id)}">${esc(flow.name)}</strong>
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
      <span class="row" style="gap:2px">
        <button class="btn ghost sm" data-rename="${esc(flow.id)}"
                title="Renomear — muda também o nome do arquivo gerado">${icon('type')}</button>
        <button class="btn ghost sm" data-dup="${esc(flow.id)}"
                title="Duplicar — útil para o próximo teste da sequência">${icon('copy')}</button>
        <button class="btn ghost sm" data-del="${esc(flow.id)}" title="Excluir">${icon('trash')}</button>
      </span>
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

/**
 * Renomeia direto no cartão, trocando o título por um campo.
 *
 * Sem diálogo: o Electron não implementa `window.prompt`, e um `alert` para
 * pedir texto não existe. Editar no lugar também é menos passo — o nome novo
 * aparece onde o antigo estava.
 */
function startRename(flowId, card) {
  // O mesmo fluxo aparece em dois lugares — na lista e nos recentes do
  // Estúdio. Procurar por seletor global acharia o cartão da vista escondida,
  // e o campo de edição nasceria invisível.
  const label = card
    ? $(`[data-flow-name="${flowId}"]`, card)
    : $(`[data-flow-name="${flowId}"]`);
  if (!label) return;

  const original = state.flows.find((f) => f.id === flowId)?.name || label.textContent;
  const input = document.createElement('input');
  input.className = 'input sm grow';
  input.dataset.renameInput = flowId;
  input.value = original;
  label.replaceWith(input);
  input.focus();
  input.select();

  let done = false;
  const finish = async (save) => {
    if (done) return;
    done = true;
    const nome = input.value.trim();

    if (!save || !nome || nome === original) { loadFlows(); return; }
    try {
      await api(`/api/flows/${flowId}`, { method: 'PATCH', body: { name: nome } });
      toast(`Renomeado para “${nome}”. Gere o código para o arquivo acompanhar.`,
            'ok', 5000);
      // O fluxo aberto na outra tela também mudou de nome.
      if (state.flow?.id === flowId) {
        state.flow.name = nome;
        $('#specName').value = nome;
        $('#codeTitle').textContent = nome;
      }
    } catch (error) {
      toast(error.message, 'danger');
    }
    loadFlows();
  };

  input.addEventListener('keydown', (event) => {
    if (event.key === 'Enter') { event.preventDefault(); finish(true); }
    if (event.key === 'Escape') { event.preventDefault(); finish(false); }
  });
  input.addEventListener('blur', () => finish(true));
}

async function openFlow(flowId) {
  try {
    const flow = await api(`/api/flows/${flowId}`);
    state.flow = flow;
    state.disabledSteps = new Set();
    state.rejected = {};
    state.verification = flow.verification || null;
    // O código gerado da última vez volta com o fluxo. Antes, reabrir mostrava
    // uma tela vazia pedindo para gerar de novo — mesmo quando nada havia
    // mudado. O trabalho estava feito; só não era mostrado.
    state.outputs = flow.outputs || {};
    state.activeTab = Object.keys(state.outputs)[0] || 'cypress';
    state.openSteps = new Set();
    state.edits = { ...(flow.edits || {}) };
    state.stepFilter = 'all';
    state.stepQuery = '';
    state.project = null;
    state.projectStale = false;
    $('#stepSearch').value = '';
    $('#scaffoldResult').innerHTML = '';
    $('#projectStale').innerHTML = '';
    $('#projectEmpty').hidden = false;
    // O projeto deste fluxo pode já existir de uma sessão anterior.
    restoreProject(flow.projectPath, '#scaffoldResult', '#projectEmpty');
    setWorkState('');
    setPane('code');

    $('#specName').value = flow.name === 'Gravação sem nome' ? '' : (flow.name || '');
    $('#specDesc').value = flow.description || '';
    $('#specBase').value = flow.baseUrl || '';
    $('#codeEmpty').hidden = true;
    $('#codeWork').hidden = false;
    $('#codeTitle').textContent = flow.name || 'Código gerado';

    renderSteps();
    if (Object.keys(state.outputs).length) {
      renderCode();
      setWorkState(flow.generatedAt ? `gerado ${relTime(flow.generatedAt)}` : '');
    } else {
      const input = $('#codeInput');
      input.value = '';
      input.readOnly = true;
      paintCode('// Clique em “Gerar código”.');
    }
    $('#genWarnings').innerHTML = '';
    $('#verifyReport').innerHTML = '';
    syncDiagBadge();
    go('code');
  } catch (error) {
    toast(error.message, 'danger');
  }
}

/* --------------------------------------------------------- passos e código */

/** Nível de confiança de um seletor, para cor e filtro. */
function confLevel(score) {
  return score >= 0.7 ? 'ok' : score >= 0.45 ? 'warn' : 'danger';
}

/** O que a verificação disse sobre este passo, se ela já rodou. */
function verifyStatus(index) {
  return (state.verification?.steps || []).find((s) => s.index === index) || null;
}

/** O passo passa pelo filtro e pela busca ativos? */
function stepMatches(step) {
  const query = state.stepQuery.trim().toLowerCase();
  if (query) {
    const haystack = [
      step.label,
      step.selector?.primary?.value,
      ...(step.selector?.candidates || []).map((c) => c.value),
    ].join(' ').toLowerCase();
    if (!haystack.includes(query)) return false;
  }

  const score = step.selector?.primary?.score ?? 1;
  const status = verifyStatus(step.index)?.status;
  switch (state.stepFilter) {
    case 'weak':   return Boolean(step.selector) && score < 0.7;
    case 'pinned': return Boolean(step.selectorOverride);
    case 'issues': return status === 'broken' || status === 'healed'
                       || (Boolean(step.selector) && score < 0.45);
    default:       return true;
  }
}

function renderSteps() {
  const host = $('#stepList');
  const steps = state.flow?.steps || [];

  if (!steps.length) {
    host.innerHTML = '<div class="callout warn">'
      + icon('warn') + '<div>Este fluxo não tem passos utilizáveis. '
      + 'Talvez a gravação tenha sido encerrada antes de qualquer interação.</div></div>';
    $('#stepSummary').textContent = '—';
    return;
  }

  const visible = steps.filter(stepMatches);

  host.innerHTML = visible.length
    ? visible.map(stepCardHTML).join('')
    : `<div class="empty" style="padding:30px 12px">
         <p class="muted" style="margin:0">Nenhum passo corresponde ao filtro.</p>
       </div>`;

  const active = steps.length - state.disabledSteps.size;
  const checks = steps.reduce((sum, s) => sum + (s.assertions || []).length, 0);
  const hidden = steps.length - visible.length;
  $('#stepSummary').textContent =
    `${active}/${steps.length} passos · ${checks} verif.`
    + (hidden ? ` · ${hidden} ocultos` : '');
  $('#stepSummary').title =
    `${active} de ${steps.length} passos entram no teste, com ${checks} verificações`
    + (hidden ? `. ${hidden} passos estão fora do filtro atual.` : '.');

  renderFilterCounts(steps);
}

/** Quantos passos cada filtro traria — saber antes de clicar. */
function renderFilterCounts(steps) {
  const saved = { filter: state.stepFilter, query: state.stepQuery };
  state.stepQuery = '';
  const counts = {};
  for (const key of ['all', 'weak', 'pinned', 'issues']) {
    state.stepFilter = key;
    counts[key] = steps.filter(stepMatches).length;
  }
  state.stepFilter = saved.filter;
  state.stepQuery = saved.query;

  $$('#stepFilters .seg-item').forEach((el) => {
    const key = el.dataset.filter;
    el.classList.toggle('active', key === state.stepFilter);
    const n = counts[key];
    el.querySelector('.n')?.remove();
    if (n) el.insertAdjacentHTML('beforeend', `<span class="n">${n}</span>`);
  });
}

function stepCardHTML(step) {
  const tone = toneOf(step.kind);
  const off = state.disabledSteps.has(step.index);
  const open = state.openSteps.has(step.index);
  const selector = step.selector?.primary;
  const score = selector?.score ?? 0;
  const level = confLevel(score);
  const pinned = Boolean(step.selectorOverride);
  const status = verifyStatus(step.index);

  const chips = [];
  if (selector) {
    chips.push(`<span class="chip ${level}">${Math.round(score * 100)}%</span>`);
  }
  if (pinned) chips.push(`<span class="chip accent">${icon('target')} fixado</span>`);
  if (status?.status === 'healed') chips.push('<span class="chip info">curado</span>');
  if (status?.status === 'broken') chips.push('<span class="chip danger">não resolveu</span>');
  const nChecks = (step.assertions || []).filter((a) => !a.raw && a.confidence > 0).length;
  if (nChecks) chips.push(`<span class="chip">${nChecks} verif.</span>`);

  return `<div class="step ${off ? 'disabled' : ''} ${open ? 'open' : ''} ${pinned ? 'pinned' : ''}">
    <div class="step-num">${step.index + 1}</div>
    <div class="grow" style="min-width:0">
      <button class="step-head" data-open-step="${step.index}"
              aria-expanded="${open}">
        ${icon('chevron', 'step-chevron')}
        <div class="step-icon" style="--tint:${tone.tint};--tone:${tone.tone}">${icon(tone.icon)}</div>
        <div class="grow" style="min-width:0">
          <div class="step-label">${esc(step.label)}</div>
          ${selector ? `<div class="step-meta">
            <code class="step-sel truncate" style="max-width:100%">${esc(selector.value)}</code>
          </div>` : ''}
          ${chips.length ? `<div class="step-meta">${chips.join('')}</div>` : ''}
        </div>
      </button>

      <div class="step-detail"><div>
        ${open ? stepDetailHTML(step, status) : ''}
      </div></div>
    </div>
    <div class="step-actions">
      <button class="btn ghost sm" data-toggle-step="${step.index}"
              title="${off ? 'Incluir no teste' : 'Excluir do teste'}">
        ${icon(off ? 'check' : 'x')}
      </button>
    </div>
  </div>`;
}

function stepDetailHTML(step, status) {
  const notes = (step.notes || []).map((n) => `<div class="step-note">${esc(n)}</div>`).join('');

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

  return `
    ${notes}
    ${status?.message ? `<div class="callout ${status.status === 'broken' ? 'warn' : ''}"
        style="margin-top:10px;padding:9px 11px">
      ${icon(status.status === 'broken' ? 'warn' : 'info')}
      <div class="small">${esc(status.message)}</div></div>` : ''}
    ${step.selector ? selectorEditorHTML(step) : ''}
    ${asserts ? `<div class="detail-title">Verificações deste passo</div>
                 <div class="asserts">${asserts}</div>` : ''}`;
}

/**
 * Editor de seletor.
 *
 * Mostra os candidatos que o motor gerou — todos, com a nota e o motivo de
 * cada um — e deixa escolher qual vai para o teste. Os que não forem
 * escolhidos continuam no arquivo como reserva do `cy.alvo`, então a escolha
 * define a ordem de tentativa, não descarta o resto.
 */
function selectorEditorHTML(step) {
  const plan = step.selector || {};
  const current = plan.primary?.value || '';
  const override = step.selectorOverride;

  // Fluxos gravados antes desta tela guardaram só o primário e as reservas.
  // Mostrar "nenhum candidato" para eles seria mentir: os candidatos existem,
  // só não foram salvos. Reconstruímos a lista com o que há, e a próxima
  // geração traz o ranking completo.
  const candidates = plan.candidates?.length
    ? plan.candidates
    : [plan.primary, ...(plan.fallbacks || [])].filter(Boolean);
  const partial = !plan.candidates?.length && candidates.length > 0;

  const manual = override && !candidates.some((c) => c.value === override.value)
    ? [{ value: override.value, kind: 'manual', engine: override.engine || 'css',
         score: 1, matches: null,
         why: 'Escrito por você. A verificação contra a aplicação é quem diz se resolve.' }]
    : [];

  const rows = [...manual, ...candidates].map((c) => {
    const on = c.value === current;
    const pct = Math.round((c.score || 0) * 100);
    const matches = c.matches === null || c.matches === undefined
      ? '' : `<span class="sel-kind">${c.matches} no DOM</span>`;
    // A nota vai na linha dos rótulos, não flutuando à direita: espremida
    // contra a borda ela quebrava o próprio seletor em duas linhas, que é
    // justamente o texto que precisa ser lido de uma vez.
    return `<div class="sel-cand ${on ? 'on' : ''}"
                 data-pick-step="${step.index}"
                 data-pick-value="${esc(c.value)}"
                 data-pick-engine="${esc(c.engine || 'css')}">
      <span class="sel-radio"></span>
      <span class="grow" style="min-width:0">
        <code class="sel-value">${esc(c.value)}</code>
        <div class="row" style="gap:6px;flex-wrap:wrap;margin-top:5px">
          <span class="sel-score ${confLevel(c.score || 0)}">${pct}%</span>
          <span class="sel-kind">${esc(c.kind)}</span>
          ${matches}
        </div>
        <div class="sel-why">${esc(c.why || '')}</div>
      </span>
    </div>`;
  }).join('');

  return `
    <div class="detail-title">
      <span class="grow">Seletor do elemento</span>
      ${override ? `<button class="btn ghost sm" data-unpin="${step.index}"
            style="padding:3px 8px;font-size:11px">voltar ao automático</button>` : ''}
    </div>
    <div class="small muted" style="margin-bottom:7px">
      O primeiro é o que o teste usa; os outros entram como reserva, tentados
      em ordem quando ele falha.
      ${partial ? 'Este fluxo foi gravado antes: clique em “Gerar código” para '
                + 'ver todos os candidatos com a nota de cada um.' : ''}
    </div>
    ${rows || '<div class="small muted">Nenhum candidato foi derivado deste elemento.</div>'}
    <div class="sel-custom">
      <select class="input" data-custom-engine="${step.index}">
        <option value="css">CSS</option>
        <option value="text">Texto</option>
        <option value="xpath">XPath</option>
      </select>
      <input class="input grow" data-custom-input="${step.index}"
             placeholder="[data-cy=&quot;entrar&quot;]" autocomplete="off"
             value="${esc(override && !plan.candidates?.some((c) => c.value === override.value)
                          ? override.value : '')}">
      <button class="btn sm" data-custom-apply="${step.index}">Usar</button>
    </div>`;
}

/**
 * Fixa um seletor para um passo e regenera.
 *
 * A escolha vai para o disco antes de qualquer coisa: `Gerar código`
 * recalcula todos os planos do zero, e uma escolha que vivesse só na tela
 * seria apagada pelo próprio clique que deveria aplicá-la.
 */
async function pinSelector(index, value, engine = 'css') {
  if (!state.flow) return;
  try {
    await api(`/api/flows/${state.flow.id}/steps/${index}/selector`, {
      method: 'PUT',
      body: { value, engine },
    });

    const step = (state.flow.steps || []).find((s) => s.index === index);
    if (step) {
      step.selectorOverride = value ? { value, engine, source: 'manual' } : null;
    }

    // O projeto no disco continua com o seletor anterior até ser regerado.
    if (state.project) state.projectStale = true;

    await generate({ quiet: true });
    renderProjectStale();
    toast(value ? 'Seletor fixado e código regerado.' : 'Voltou ao seletor automático.',
          'ok', 3000);
  } catch (error) {
    toast(error.message, 'danger', 6000);
  }
}

/* Alterna a aba da coluna direita. */
function setPane(name) {
  state.pane = name;
  $$('.work-tab').forEach((el) => el.classList.toggle('active', el.dataset.pane === name));
  $$('.work-pane').forEach((el) => { el.hidden = el.id !== `pane-${name}`; });
}

async function generate({ quiet = false, keepEdits = false } = {}) {
  if (!state.flow) return;

  // Gerar reescreve os arquivos. Quem editou à mão precisa saber disso antes,
  // não depois: o texto perdido não volta.
  const edited = keepEdits ? [] : Object.keys(state.edits);
  if (edited.length) {
    const quais = edited.map((t) => TAB_NAMES[t] || t).join(', ');
    if (!confirm(`Você editou o código de: ${quais}.\n\n`
                 + 'Gerar de novo substitui essas edições pelo código que o '
                 + 'Cygen escreve a partir dos passos. Continuar?')) return;
    for (const tab of edited) {
      delete state.edits[tab];
      await persistEdits(tab);
    }
  }

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
        fixtures: $('#optFixtures').checked,
      },
    });

    state.outputs = result.outputs;
    state.flow.steps = result.steps;
    state.activeTab = Object.keys(result.outputs)[0] || 'cypress';
    renderCode();
    renderSteps();
    renderWarnings(result);
    setWorkState(`${result.stats.commands} comandos · ${result.stats.checks} verificações`);
    if (!quiet) {
      toast(`${result.stats.commands} comandos, ${result.stats.checks} verificações.`, 'ok');
    }
  } catch (error) {
    toast(error.message, 'danger', 7000);
  } finally {
    button.disabled = false;
    button.innerHTML = `${icon('bolt')} Gerar código`;
  }
}

/** O código que vale para esta aba: o editado, se houver; o gerado, se não. */
function currentCode(tab = state.activeTab) {
  return state.edits[tab] ?? state.outputs[tab]?.code ?? '';
}

const TAB_NAMES = { cypress: 'Cypress', playwright: 'Playwright', commands: 'commands.js' };

function renderCode() {
  renderCodeTabs();

  const code = currentCode();
  const input = $('#codeInput');
  // Antes de gerar não há arquivo para editar: o que se digitasse aqui não
  // pertenceria a aba nenhuma e sumiria na primeira geração.
  input.readOnly = !Object.keys(state.outputs).length;
  // Só reescreve o textarea quando o conteúdo mudou de fato: atribuir `value`
  // enquanto o usuário digita levaria o cursor para o fim a cada tecla.
  if (input.value !== code) input.value = code;
  paintCode(code);
}

/**
 * Só a barra de abas.
 *
 * Existe separada porque digitar muda o estado da barra — a aba ganha o ponto,
 * aparece o aviso de editado — sem que se possa redesenhar o editor junto: o
 * `renderCode` completo reatribuiria `value` e jogaria o cursor para o fim do
 * arquivo no meio da frase.
 */
function renderCodeTabs() {
  const tabs = Object.entries(state.outputs);
  const edited = state.edits[state.activeTab] !== undefined;

  $('#codeTabs').innerHTML = tabs.map(([key]) => `
    <button class="code-tab ${key === state.activeTab ? 'active' : ''}" data-tab="${key}">
      ${TAB_NAMES[key] || key}${state.edits[key] !== undefined ? '<span class="dot"></span>' : ''}
    </button>`).join('')
    + '<span class="grow"></span>'
    + (edited ? `<span class="code-flag">${icon('warn')} editado por você</span>
        <button class="btn ghost sm" id="btnRevertCode"
                title="Volta ao código que o Cygen gerou">desfazer edição</button>` : '')
    + `<span class="small faint" style="padding:0 8px">
         ${esc(state.outputs[state.activeTab]?.filename || '')}
       </span>`;
}

/** Limite acima do qual o realce sai de cena: colorir a cada tecla um arquivo
 *  desse tamanho travaria a digitação, e um teste assim não existe na prática. */
const HIGHLIGHT_LIMIT = 120000;

/** Repinta o realce sob o textarea. */
function paintCode(code) {
  // A última linha precisa de um `\n` extra: sem ele, o realce fica um passo
  // mais curto que o textarea e a rolagem dos dois desencontra no fim.
  $('#codeOut').innerHTML = code.length > HIGHLIGHT_LIMIT
    ? esc(code + '\n')
    : highlight(code + '\n');
}

/**
 * Registra o que o usuário digitou.
 *
 * A edição é do arquivo, não da sessão: vai para o fluxo em disco, senão
 * fechar a janela desfaria o trabalho. Guardamos também quando o texto volta a
 * ser idêntico ao gerado — aí a edição deixa de existir, e o aviso some junto.
 */
let saveCodeTimer = null;

function onCodeInput(value) {
  const tab = state.activeTab;
  const generated = state.outputs[tab]?.code ?? '';
  const antes = state.edits[tab] !== undefined;

  if (value === generated) delete state.edits[tab];
  else state.edits[tab] = value;

  paintCode(value);
  // A barra só é redesenhada quando o estado dela muda de fato — a cada tecla
  // seria trabalho jogado fora.
  if (antes !== (state.edits[tab] !== undefined)) renderCodeTabs();
  markProjectStale();

  clearTimeout(saveCodeTimer);
  saveCodeTimer = setTimeout(() => persistEdits(tab), 700);
}

async function persistEdits(tab) {
  if (!state.flow) return;
  try {
    await api(`/api/flows/${state.flow.id}/code`, {
      method: 'PUT',
      body: { tab, code: state.edits[tab] ?? null },
    });
  } catch (error) {
    toast(`Não consegui salvar a edição: ${error.message}`, 'danger', 7000);
  }
}

/** Descarta a edição da aba atual e volta ao código gerado. */
async function revertCode() {
  const tab = state.activeTab;
  if (state.edits[tab] === undefined) return;
  if (!confirm('Desfazer sua edição e voltar ao código que o Cygen gerou?')) return;

  delete state.edits[tab];
  clearTimeout(saveCodeTimer);
  await persistEdits(tab);
  renderCode();
  markProjectStale();
  toast('Edição desfeita.', 'ok', 2600);
}

/**
 * Renomeia o fluxo aberto e propaga a mudança.
 *
 * O nome não é rótulo: ele vira o `describe` do teste, o nome do arquivo
 * `.cy.js` e o da pasta do projeto. Por isso salvar aqui não basta — o código
 * precisa ser reemitido, senão o arquivo continuaria anunciando o nome antigo
 * enquanto a lista já mostra o novo.
 */
let flowMetaTimer = null;

function saveFlowMeta({ now = false } = {}) {
  if (!state.flow) return;
  clearTimeout(flowMetaTimer);

  const enviar = async () => {
    const body = {
      name: $('#specName').value.trim() || state.flow.name || 'Fluxo gravado',
      description: $('#specDesc').value,
      baseUrl: $('#specBase').value,
    };
    const renomeou = body.name !== state.flow.name;

    try {
      const saved = await api(`/api/flows/${state.flow.id}`, { method: 'PATCH', body });
      state.flow = { ...state.flow, ...saved };
      $('#codeTitle').textContent = saved.name;

      if (renomeou && Object.keys(state.outputs).length) {
        // O `describe` e o nome do arquivo saem daqui: reemitir é o que faz o
        // novo nome existir de fato. Edições manuais são preservadas.
        await generate({ quiet: true, keepEdits: true });
        markProjectStale();
      }
    } catch (error) {
      toast(error.message, 'danger');
    }
  };

  if (now) return enviar();
  flowMetaTimer = setTimeout(enviar, 700);
}

/** Resumo curto na barra de trabalho — o estado do que está em mãos. */
function setWorkState(text) {
  const chip = $('#workState');
  chip.hidden = !text;
  chip.textContent = text || '';
}

/**
 * Aviso de que o projeto no disco está atrás do código atual.
 *
 * Trocar um seletor e clicar em "Rodar agora" sem regerar rodaria o arquivo
 * antigo — e o usuário concluiria que a troca não funcionou, quando na
 * verdade ela nem chegou ao disco.
 */
/**
 * Traz de volta o painel de um projeto que já está no disco.
 *
 * O projeto sobrevive à sessão — fica em Documentos, com as dependências
 * instaladas e as credenciais gravadas. A tela é que não sabia disso e pedia
 * para gerar de novo toda vez, como se nada existisse. Aqui ela pergunta ao
 * backend e redesenha o painel inteiro: rodar, abrir o Cypress, ver a pasta.
 *
 * Falhar aqui não é erro: o projeto pode ter sido apagado à mão, e nesse caso
 * o estado vazio (com o botão de gerar) é exatamente a resposta certa.
 */
async function restoreProject(path, host, empty) {
  if (!path) return false;
  try {
    const info = await api(`/api/project/status?path=${encodeURIComponent(path)}`);
    if (!info.ok) return false;
    renderScaffold({ ...info, commands: [], restored: true,
                     envKeys: info.envKeys || [] }, { host, empty });
    return true;
  } catch {
    return false;
  }
}

/** Qualquer mudança no que entra no teste desatualiza o projeto em disco. */
function markProjectStale() {
  // Sai cedo quando já está marcado: isto é chamado a cada tecla no editor.
  if (!state.project || state.projectStale) return;
  state.projectStale = true;
  renderProjectStale();
}

function renderProjectStale() {
  const host = $('#projectStale');
  if (!host) return;
  host.innerHTML = state.projectStale && state.project ? `
    <div class="callout warn" style="margin-bottom:12px">${icon('warn')}
      <div class="grow"><strong>O projeto no disco está desatualizado.</strong>
      <div class="small" style="margin-top:3px">Você trocou um seletor depois de
      gerá-lo. Gere de novo para o arquivo em disco receber a mudança — as
      dependências já instaladas são preservadas.</div></div>
    </div>` : '';
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
  syncDiagBadge();
}

/**
 * Sinaliza na aba quantos pontos pedem atenção.
 *
 * Com o diagnóstico fora da tela principal, ele precisa se anunciar — senão
 * um aviso sobre seletor fraco fica escondido atrás de uma aba que ninguém
 * tem motivo para abrir.
 */
function syncDiagBadge() {
  const warnings = $$('#genWarnings .callout.warn').length;
  const broken = state.verification?.broken || 0;
  const total = warnings + broken;

  const badge = $('#diagBadge');
  badge.hidden = !total;
  badge.textContent = total;

  const empty = $('#diagEmpty');
  if (empty) {
    empty.hidden = Boolean($('#genWarnings').innerHTML.trim()
                           || $('#verifyReport').innerHTML.trim());
  }
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
      // A cura reescreve o spec. Se há edição manual, ela continua no ar: o
      // texto do usuário não é descartado por um efeito colateral de outro
      // botão. O código curado fica disponível em "desfazer edição".
      if (state.edits.cypress !== undefined) {
        toast('Seus ajustes no código foram mantidos. Para ver a versão curada, '
              + 'use “desfazer edição”.', 'warn', 7000);
      }
      renderCode();
    }
    renderVerification(result.report);
    // O relatório muda o estado de cada passo: curado, quebrado, ok.
    renderSteps();
    setPane('diag');

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
  syncDiagBadge();
}

/* --------------------------------------------------------------- auto-teste */

/**
 * O auto-teste depende de um provedor de IA com chave.
 *
 * Não é uma trava artificial: o Oracle deduz as verificações do que aconteceu,
 * mas não escolhe o próximo clique. Sem modelo, não há decisão — e dizer isso
 * antes de o botão falhar é mais honesto do que deixar tentar.
 */
function renderAutoProviders() {
  const utilizaveis = state.providers.filter((p) => p.id !== 'native');
  const select = $('#autoProvider');
  const escolhido = select.value;

  const peso = (p) => (p.configured ? 4 : 0) + (p.free ? 2 : 0);
  select.innerHTML = [...utilizaveis]
    .sort((a, b) => peso(b) - peso(a))
    .map((p) => `<option value="${esc(p.id)}">${esc(p.label)}${
      p.configured ? '' : p.free ? ' — grátis, falta a chave' : ' — falta a chave'
    }</option>`).join('');
  if (escolhido) select.value = escolhido;

  syncAutoModels();
}

function syncAutoModels() {
  const provider = state.providers.find((p) => p.id === $('#autoProvider').value);
  $('#autoModel').innerHTML = (provider?.models || [])
    .map((m) => `<option value="${esc(m.id)}">${esc(m.label)}</option>`).join('');

  const aviso = $('#autoKeyWarn');
  if (!provider) { aviso.innerHTML = ''; return; }

  aviso.innerHTML = provider.configured ? `
    <div class="callout ok mt" style="padding:9px 11px">${icon('check')}
      <div class="small">${esc(provider.label)} está pronto. A chave fica
      guardada nesta máquina — não será pedida de novo.</div></div>`
    : `<div class="callout warn mt" style="padding:9px 11px">${icon('warn')}
      <div class="small grow">
        <strong>${esc(provider.label)} precisa de uma chave.</strong>
        ${provider.freeTier ? esc(provider.freeTier) : ''}
        <div class="row mt" style="gap:7px">
          <input class="input sm grow" type="password" autocomplete="off"
                 id="autoKeyInput" placeholder="${esc(provider.envKeys[0] || 'chave')}">
          <button class="btn sm" id="btnAutoKey" style="flex:none">Salvar chave</button>
          ${provider.signup ? `<a class="btn ghost sm" target="_blank" rel="noopener"
             href="${esc(provider.signup)}" style="flex:none">pegar chave</a>` : ''}
        </div>
      </div></div>`;
}

function renderAutoSteps() {
  const host = $('#autoSteps');
  const passos = state.autoSteps;
  if (!passos.length) {
    host.innerHTML = `<div class="empty" style="padding:24px 12px">
      <p class="muted small" style="margin:0">A IA está observando a primeira tela…</p>
    </div>`;
    return;
  }

  host.innerHTML = passos.map((p) => {
    const marco = p.tipo === 'marco';
    const bloqueado = p.tipo === 'bloqueado';
    const tint = marco ? 'var(--mint-100)' : bloqueado ? 'var(--rose-100)' : 'var(--lav-100)';
    const tone = marco ? 'var(--mint-600)' : bloqueado ? 'var(--rose-600)' : 'var(--lav-600)';
    const texto = marco ? `Fluxo concluído: ${p.nome}`
      : bloqueado ? p.motivo
      : (p.descricao || '');
    return `<div class="step ${bloqueado ? 'disabled' : ''}">
      <div class="step-icon" style="--tint:${tint};--tone:${tone}">
        ${icon(marco ? 'check' : bloqueado ? 'warn' : 'mouse')}
      </div>
      <div class="step-body">
        <div class="step-label">${esc(texto)}</div>
        ${p.porque ? `<div class="step-note">${esc(p.porque)}</div>` : ''}
      </div>
    </div>`;
  }).join('');
  host.scrollTop = host.scrollHeight;
}

async function startAuto() {
  const url = $('#autoUrl').value.trim();
  if (!url) { toast('Informe o endereço do sistema.', 'warn'); return; }

  const body = {
    baseUrl: url,
    objetivo: $('#autoGoal').value,
    regras: $('#autoRules').value,
    escopo: $('#autoScope').value,
    login: {
      usuario: $('#autoUser').value,
      senha: $('#autoPass').value,
      instrucoes: $('#autoLoginHow').value,
    },
    provider: $('#autoProvider').value,
    model: $('#autoModel').value,
    maxPassos: Number($('#autoSteps').value) || 40,
    headless: $('#autoHeadless').checked,
    permitirDestrutivo: $('#autoDestrutivo').checked,
    confirmoAmbiente: state.autoAmbienteOk,
  };

  state.autoSteps = [];
  state.autoRunning = true;
  $('#autoRun').hidden = false;
  $('#btnAutoStop').hidden = false;
  $('#navAuto').hidden = false;
  $('#autoResult').innerHTML = '';
  renderAutoSteps();
  pollAutoFrame();

  const botao = $('#btnAutoStart');
  botao.disabled = true;
  botao.innerHTML = '<span class="spinner"></span> Explorando…';

  try {
    const result = await api('/api/autotest/start', { method: 'POST', body });
    renderAutoResult(result);
    await loadFlows();
  } catch (error) {
    // O aviso de ambiente é uma pergunta, não uma falha: confirmado uma vez,
    // a execução segue sem repetir a dúvida.
    if (/ambiente de teste/i.test(error.message)) {
      state.autoRunning = false;
      botao.disabled = false;
      botao.innerHTML = `${icon('sparkle')} Iniciar auto-teste`;
      if (confirm(`${error.message}\n\nRodar mesmo assim?`)) {
        state.autoAmbienteOk = true;
        return startAuto();
      }
      $('#autoRun').hidden = true;
      return;
    }
    toast(error.message, 'danger', 9000);
    $('#autoRun').hidden = true;
  } finally {
    state.autoRunning = false;
    botao.disabled = false;
    botao.innerHTML = `${icon('sparkle')} Iniciar auto-teste`;
    $('#btnAutoStop').hidden = true;
    $('#navAuto').hidden = true;
  }
}

function renderAutoResult(result) {
  const salvos = result.salvos || [];
  const linhas = salvos.map((f) => `
    <div class="row between" style="padding:7px 0;border-top:1px solid var(--border-soft)">
      <div class="grow"><strong class="small">${esc(f.name)}</strong>
        <div class="small faint">${f.stepCount} passos</div></div>
      <button class="btn sm" data-flow="${esc(f.id)}">Abrir</button>
    </div>`).join('');

  $('#autoResult').innerHTML = `
    <div class="callout ${salvos.length ? 'ok' : 'warn'}" style="margin-top:14px;display:block">
      <div class="row wrap" style="gap:9px;margin-bottom:10px">
        ${icon(salvos.length ? 'check' : 'warn')}
        <strong>${salvos.length
          ? `${salvos.length} fluxo(s) gravados`
          : 'A exploração terminou sem fluxos utilizáveis'}</strong>
        <span class="chip">${result.passos?.length || 0} passos</span>
        <span class="chip">${result.telas || 0} telas</span>
        <span class="chip">${result.chamadas || 0} chamadas à IA</span>
        ${result.custo ? `<span class="chip">US$ ${result.custo}</span>` : ''}
      </div>
      ${result.error ? `<div class="small" style="color:var(--danger)">${esc(result.error)}</div>` : ''}
      ${linhas}
      ${salvos.length ? `<div class="hint" style="margin-top:9px">
        Revise cada fluxo como um gravado à mão — os seletores e as verificações
        passaram pelo mesmo Oracle.</div>` : ''}
    </div>`;
}

/** Espelha o navegador do agente enquanto ele explora. */
async function pollAutoFrame() {
  if (!state.autoRunning) return;
  try {
    const shot = await api('/api/record/screenshot');
    if (shot.ok) {
      $('#autoFrame').innerHTML = `<img src="data:image/jpeg;base64,${shot.image}" alt="">`;
    }
  } catch { /* o navegador pode estar entre páginas */ }
  setTimeout(pollAutoFrame, 1200);
}

/* -------------------------------------------------------------- sequências */

async function loadSuites() {
  try {
    const { suites } = await api('/api/suites');
    state.suites = suites;
    $('#navSuites').textContent = suites.length;
    renderSuiteList();
  } catch (error) {
    toast(error.message, 'danger');
  }
}

function renderSuiteList() {
  const host = $('#suiteList');
  if (!state.suites.length) {
    host.innerHTML = `<div class="empty" style="grid-column:1/-1">
      <div class="empty-art">${icon('list')}</div>
      <h3>Nenhuma sequência ainda</h3>
      <p>Uma sequência junta vários fluxos num arquivo só — cadastrar, aprovar
         e consultar viram três <code class="mono">it()</code> que rodam na ordem.</p>
    </div>`;
    return;
  }

  host.innerHTML = state.suites.map((suite) => `
    <div class="card hoverable" data-suite="${esc(suite.id)}" style="cursor:pointer">
      <div class="row between">
        <strong class="truncate">${esc(suite.name)}</strong>
        ${suite.isolate ? '' : '<span class="chip accent">encadeada</span>'}
      </div>
      <div class="small muted truncate" style="margin-top:3px">
        ${esc(suite.description || suite.baseUrl || 'sem descrição')}
      </div>
      <div class="row wrap" style="margin-top:11px;gap:6px">
        <span class="chip">${suite.testCount} teste${suite.testCount === 1 ? '' : 's'}</span>
      </div>
      <div class="row between" style="margin-top:11px">
        <span class="small faint">${relTime(suite.updatedAt)}</span>
        <button class="btn ghost sm" data-del-suite="${esc(suite.id)}"
                title="Excluir a sequência">${icon('trash')}</button>
      </div>
    </div>`).join('');
}

async function openSuite(suiteId) {
  try {
    const suite = await api(`/api/suites/${suiteId}`);
    state.suite = suite;
    state.suiteOutputs = suite.outputs || {};
    state.project = null;

    $('#suiteBrowse').hidden = true;
    $('#suiteWork').hidden = false;
    $('#suiteTitle').textContent = suite.name;
    $('#suiteSub').textContent = suite.description
      || 'Cada fluxo abaixo vira um it() no arquivo da sequência.';
    $('#suiteName').value = suite.name;
    $('#suiteDesc').value = suite.description || '';
    $('#suiteBase').value = suite.baseUrl || '';
    $('#suiteIsolate').checked = Boolean(suite.isolate);
    $('#suiteScaffoldResult').innerHTML = '';
    $('#suiteProjectEmpty').hidden = false;
    renderSuitePathHint();
    restoreProject(suite.projectPath, '#suiteScaffoldResult', '#suiteProjectEmpty');
    setSuitePane('code');

    renderSuiteFlows();
    renderSuiteCode();
  } catch (error) {
    toast(error.message, 'danger');
  }
}

function closeSuite() {
  state.suite = null;
  state.project = null;
  $('#suiteWork').hidden = true;
  $('#suiteBrowse').hidden = false;
  $('#suiteTitle').textContent = 'Sequências';
  $('#suiteSub').textContent = 'Vários fluxos num arquivo só, na ordem em que devem rodar.';
  loadSuites();
}

function setSuitePane(name) {
  $$('[data-suite-pane]').forEach((el) =>
    el.classList.toggle('active', el.dataset.suitePane === name));
  $$('#suiteWork .work-pane').forEach((el) => {
    el.hidden = el.id !== `suitepane-${name}`;
  });
}

/**
 * Os testes da sequência, na ordem de execução.
 *
 * A ordem é o conteúdo aqui, não um detalhe de apresentação: numa sequência
 * encadeada o segundo teste depende do estado que o primeiro deixou. Por isso
 * cada linha mostra a posição e traz os botões para movê-la.
 */
function renderSuiteFlows() {
  const host = $('#suiteFlows');
  const flows = state.suite?.flows || [];

  host.innerHTML = flows.length
    ? flows.map((flow, i) => `
        <div class="step">
          <div class="step-num">${i + 1}</div>
          <div class="step-icon" style="--tint:var(--lav-100);--tone:var(--lav-600)">
            ${icon('code')}
          </div>
          <div class="step-body">
            <div class="step-label">${esc(flow.name)}</div>
            <div class="step-meta">
              <span class="chip">${flow.stepCount} passos</span>
              ${flow.edited.length ? '<span class="chip warn">código editado</span>' : ''}
            </div>
          </div>
          <div class="step-actions">
            <button class="btn ghost sm" data-suite-move="${i}" data-dir="-1"
                    title="Subir" ${i === 0 ? 'disabled' : ''}>↑</button>
            <button class="btn ghost sm" data-suite-move="${i}" data-dir="1"
                    title="Descer" ${i === flows.length - 1 ? 'disabled' : ''}>↓</button>
            <button class="btn ghost sm" data-suite-open="${esc(flow.id)}"
                    title="Abrir o fluxo">${icon('code')}</button>
            <button class="btn ghost sm" data-suite-remove="${i}"
                    title="Tirar da sequência">${icon('x')}</button>
          </div>
        </div>`).join('')
    : `<div class="empty" style="padding:26px 12px">
         <p class="muted small" style="margin:0">Nenhum teste ainda. Escolha um fluxo
         acima para começar a sequência.</p>
       </div>`;

  $('#suiteSummary').textContent =
    `${flows.length} teste${flows.length === 1 ? '' : 's'} · roda de cima para baixo`;

  // O seletor mostra só o que ainda não está na sequência: repetir o mesmo
  // fluxo duas vezes produziria dois `it()` idênticos.
  const usados = new Set(flows.map((f) => f.id));
  $('#suiteAddPick').innerHTML = '<option value="">Adicionar um fluxo…</option>'
    + state.flows.filter((f) => !usados.has(f.id))
        .map((f) => `<option value="${esc(f.id)}">${esc(f.name)}</option>`).join('');
}

/** Mesma regra de nome que o backend usa para a pasta do projeto. */
function slugify(text) {
  return (text || '')
    .normalize('NFKD').replace(/[̀-ͯ]/g, '')
    .replace(/[^\w\s-]/g, '').trim()
    .replace(/[\s_-]+/g, '-')
    .toLowerCase()
    .slice(0, 60) || 'fluxo';
}

/**
 * Onde o projeto da sequência vai ser criado.
 *
 * Mostrado antes de existir: "onde isso vai parar no disco?" é a primeira
 * pergunta de quem vai abrir o projeto no editor, e esperar o projeto existir
 * para responder deixava a tela muda justamente na hora da dúvida.
 */
function renderSuitePathHint() {
  const hint = $('#suitePathHint');
  const base = state.meta?.paths?.projects;
  if (!hint || !base || !state.suite) return;
  hint.textContent = `${base}\\seq-${slugify(state.suite.name)}`;
}

const SUITE_TAB_NAMES = {
  cypress: 'Sequência', commands: 'commands.js', elementos: 'elementos.json',
};

/**
 * O código da sequência, agora em mais de um arquivo.
 *
 * A sequência distribui o que roda entre o `.cy.js` — a ordem dos testes — e o
 * `commands.js`, onde cada fluxo mora inteiro. Mostrar só o primeiro daria a
 * impressão de que o teste não faz nada.
 */
function renderSuiteCode() {
  const abas = Object.entries(state.suiteOutputs || {});
  if (!abas.length) {
    $('#suiteCodeTabs').innerHTML = '<span class="code-tab active">Cypress</span>';
    $('#suiteCodeOut').innerHTML =
      '<span class="tok-com">// Clique em “Gerar código”.</span>';
    return;
  }

  if (!state.suiteOutputs[state.suiteTab]) state.suiteTab = abas[0][0];

  $('#suiteCodeTabs').innerHTML = abas.map(([key]) => `
    <button class="code-tab ${key === state.suiteTab ? 'active' : ''}"
            data-suite-file="${key}">${SUITE_TAB_NAMES[key] || key}</button>`).join('')
    + `<span class="grow"></span><span class="small faint" style="padding:0 8px">
         ${esc(state.suiteOutputs[state.suiteTab]?.filename || '')}</span>`;

  $('#suiteCodeOut').innerHTML =
    highlight(state.suiteOutputs[state.suiteTab]?.code || '');
}

/** Grava o cabeçalho e a ordem. Chamado a cada mudança, com folga para digitar. */
let suiteSaveTimer = null;

function saveSuite({ now = false } = {}) {
  if (!state.suite) return Promise.resolve();
  clearTimeout(suiteSaveTimer);

  const enviar = async () => {
    const body = {
      name: $('#suiteName').value.trim() || 'Sequência sem nome',
      description: $('#suiteDesc').value,
      baseUrl: $('#suiteBase').value,
      flowIds: (state.suite.flows || []).map((f) => f.id),
      isolate: $('#suiteIsolate').checked,
    };
    try {
      const saved = await api(`/api/suites/${state.suite.id}`, { method: 'PATCH', body });
      state.suite = { ...state.suite, ...saved };
      $('#suiteTitle').textContent = saved.name;
      renderSuitePathHint();      // o nome define a pasta
    } catch (error) {
      toast(error.message, 'danger');
    }
  };

  if (now) return enviar();
  suiteSaveTimer = setTimeout(enviar, 600);
  return Promise.resolve();
}

async function suiteAddFlow(flowId) {
  if (!flowId || !state.suite) return;
  const flow = state.flows.find((f) => f.id === flowId);
  if (!flow) return;
  state.suite.flows = [...(state.suite.flows || []), {
    id: flow.id, name: flow.name, description: flow.description,
    baseUrl: flow.baseUrl, stepCount: flow.stepCount, edited: [],
  }];
  renderSuiteFlows();
  await saveSuite({ now: true });
  toast(`“${flow.name}” entrou na sequência.`, 'ok', 2600);
}

async function generateSuite() {
  if (!state.suite) return;
  if (!(state.suite.flows || []).length) {
    toast('Inclua ao menos um fluxo na sequência.', 'warn');
    return;
  }

  const button = $('#btnSuiteGenerate');
  button.disabled = true;
  button.innerHTML = '<span class="spinner"></span> Gerando…';
  try {
    await saveSuite({ now: true });
    const result = await api(`/api/suites/${state.suite.id}/generate`, {
      method: 'POST',
      body: { verbose: true, fixtures: $('#suiteFixtures').checked },
    });
    state.suiteOutputs = result.outputs;
    renderSuiteCode();

    const chip = $('#suiteState');
    chip.hidden = false;
    chip.textContent = `${result.stats.tests} testes · ${result.stats.checks} verificações`;
    toast(`${result.stats.tests} testes num arquivo só.`, 'ok');
  } catch (error) {
    toast(error.message, 'danger', 7000);
  } finally {
    button.disabled = false;
    button.innerHTML = `${icon('bolt')} Gerar código`;
  }
}

async function scaffoldSuite() {
  if (!state.suite) return;
  const button = $('#btnSuiteScaffold');
  button.disabled = true;
  button.innerHTML = '<span class="spinner"></span> Montando…';
  try {
    await saveSuite({ now: true });
    const result = await api(`/api/suites/${state.suite.id}/scaffold`, {
      method: 'POST',
      body: { verbose: true, fixtures: $('#suiteFixtures').checked },
    });
    renderScaffold(result, { host: '#suiteScaffoldResult', empty: '#suiteProjectEmpty' });
    setSuitePane('project');
    toast(result.installed
      ? 'Projeto da sequência atualizado. Dependências preservadas.'
      : `Projeto criado com ${result.fileList.length} arquivos.`, 'ok', 5200);
  } catch (error) {
    toast(error.message, 'danger', 7000);
  } finally {
    button.disabled = false;
    button.innerHTML = `${icon('package')} Gerar projeto completo`;
  }
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

    // Os não configurados continuam na lista, e escolhíveis: o app avisa o
    // que falta em vez de esconder a opção. Desabilitar era pior — a pessoa
    // via o provedor cinza e não tinha como saber o que fazer a respeito.
    const select = $('#chatProvider');
    // Peso: nativo primeiro (é o padrão e sempre funciona), depois os que
    // já têm chave, depois os gratuitos. Quem exige cartão fica por último.
    const peso = (p) => (p.id === 'native' ? 8 : 0)
      + (p.configured ? 4 : 0) + (p.free ? 2 : 0);
    const ordenados = [...providers].sort((a, b) => peso(b) - peso(a));

    select.innerHTML = ordenados.map((p) => {
      const marcas = [p.free ? 'grátis' : '', p.configured ? '' : 'sem chave']
        .filter(Boolean).join(', ');
      return `<option value="${esc(p.id)}">
        ${esc(p.label)}${marcas ? ` — ${marcas}` : ''}
      </option>`;
    }).join('');
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
        // A revisão tem que olhar o que está na tela, inclusive o que foi
        // escrito à mão — que é justamente a parte que ninguém revisou ainda.
        code: currentCode(),
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

  renderPaths();

  if (!state.providers.length) await loadProviders();

  renderProviderList();
}

/**
 * Provedores, com os gratuitos na frente.
 *
 * A ordem responde à pergunta que a lista provoca: "qual eu uso sem pagar?".
 * E cada um traz o campo da chave ali mesmo — a alternativa era mandar a
 * pessoa definir variável de ambiente e reiniciar o app antes de descobrir se
 * o provedor presta.
 */
function renderProviderList() {
  const ordenados = [...state.providers].sort((a, b) =>
    (b.free ? 1 : 0) - (a.free ? 1 : 0));

  $('#providerList').innerHTML = ordenados.map((p) => `
    <div style="padding:10px 0;border-bottom:1px solid var(--border-soft)">
      <div class="row between" style="gap:8px">
        <div class="row grow" style="gap:7px;min-width:0">
          <strong style="font-size:13px">${esc(p.label)}</strong>
          ${p.free ? '<span class="chip ok">grátis</span>' : ''}
          ${p.local ? '<span class="chip">local</span>' : ''}
        </div>
        <span class="chip ${p.configured ? 'ok' : ''}">${p.configured ? 'pronto' : 'inativo'}</span>
      </div>

      ${p.freeTier ? `<div class="small muted" style="margin-top:4px">${esc(p.freeTier)}</div>` : ''}

      ${p.envKeys.length ? `
        <div class="row" style="gap:7px;margin-top:8px">
          <input class="input sm grow" type="password" autocomplete="off"
                 data-key-for="${esc(p.id)}"
                 placeholder="${esc(p.envKeys[0])} — cole a chave aqui">
          <button class="btn sm" data-save-key="${esc(p.id)}" style="flex:none">Usar</button>
          ${p.signup ? `<a class="btn ghost sm" href="${esc(p.signup)}"
             target="_blank" rel="noopener" style="flex:none">pegar chave</a>` : ''}
        </div>
        <div class="hint" style="margin-top:4px">
          Vale só enquanto o Cygen estiver aberto. Para fixar, defina
          <code class="mono">${esc(p.envKeys[0])}</code> no ambiente.
        </div>` : ''}
    </div>`).join('');
}

/** As pastas do Cygen, com o botão que abre cada uma no explorador. */
function renderPaths() {
  const paths = state.meta?.paths;
  if (!paths) return;

  const linhas = [
    ['projects', 'Projetos Cypress', paths.projects,
     'um por fluxo e um por sequência, prontos para npm install && npm test'],
    ['suites', 'Sequências', paths.suites,
     'a ordem dos testes e o nome do arquivo, em JSON'],
    ['data', 'Fluxos e preferências', paths.data,
     'as gravações e as configurações desta máquina'],
    ['exports', 'Specs exportados', paths.exports,
     'o que sai de “Salvar só o spec”'],
  ];

  $('#pathList').innerHTML = linhas.map(([key, titulo, caminho, hint]) => `
    <div class="row between" style="gap:10px;padding:9px 0;
         border-bottom:1px solid var(--border-soft)">
      <div class="grow" style="min-width:0">
        <strong style="font-size:13px">${esc(titulo)}</strong>
        <div class="small faint">${esc(hint)}</div>
        <code class="mono small" style="word-break:break-all">${esc(caminho)}</code>
      </div>
      <button class="btn ghost sm" data-open-dir="${key}" style="flex:none">
        ${icon('folder')} Abrir
      </button>
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

  // Renomear e duplicar vêm antes do card: os botões vivem dentro dele, e
  // `closest` casaria primeiro com o cartão — abrindo o fluxo em vez de agir.
  const rename = target.closest('[data-rename]');
  if (rename) {
    event.stopPropagation();
    startRename(rename.dataset.rename, rename.closest('.card'));
    return;
  }

  // Clique dentro do campo de renomear não pode abrir o fluxo.
  if (target.closest('[data-rename-input]')) { event.stopPropagation(); return; }

  const dup = target.closest('[data-dup]');
  if (dup) {
    event.stopPropagation();
    api(`/api/flows/${dup.dataset.dup}/duplicate`, { method: 'POST' })
      .then(async (flow) => {
        toast(`Cópia criada: “${flow.name}”. Edite o que mudar entre os dois testes.`,
              'ok', 5000);
        await loadFlows();
        openFlow(flow.id);
      })
      .catch((error) => toast(error.message, 'danger'));
    return;
  }

  const card = target.closest('[data-flow]');
  if (card) { openFlow(card.dataset.flow); return; }

  const tab = target.closest('[data-tab]');
  if (tab) {
    // Trocar de aba não pode perder o que ainda está no debounce.
    clearTimeout(saveCodeTimer);
    persistEdits(state.activeTab);
    state.activeTab = tab.dataset.tab;
    renderCode();
    return;
  }

  if (target.closest('#btnRevertCode')) { revertCode(); return; }

  const toggle = target.closest('[data-toggle-step]');
  if (toggle) {
    const index = Number(toggle.dataset.toggleStep);
    state.disabledSteps.has(index)
      ? state.disabledSteps.delete(index)
      : state.disabledSteps.add(index);
    markProjectStale();
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
    markProjectStale();
    renderSteps();
    return;
  }

  const stepHead = target.closest('[data-open-step]');
  if (stepHead) {
    const index = Number(stepHead.dataset.openStep);
    state.openSteps.has(index)
      ? state.openSteps.delete(index)
      : state.openSteps.add(index);
    renderSteps();
    return;
  }

  const pick = target.closest('[data-pick-step]');
  if (pick) {
    pinSelector(Number(pick.dataset.pickStep),
                pick.dataset.pickValue, pick.dataset.pickEngine);
    return;
  }

  const unpin = target.closest('[data-unpin]');
  if (unpin) { pinSelector(Number(unpin.dataset.unpin), ''); return; }

  const apply = target.closest('[data-custom-apply]');
  if (apply) {
    const index = Number(apply.dataset.customApply);
    const input = $(`[data-custom-input="${index}"]`);
    const engine = $(`[data-custom-engine="${index}"]`).value;
    const value = input.value.trim();
    if (!value) { toast('Escreva um seletor antes de aplicar.', 'warn'); return; }
    // Um seletor CSS inválido só falharia na execução, com uma mensagem do
    // Cypress que não aponta para o campo onde ele foi digitado.
    if (engine === 'css') {
      try { document.querySelector(value); }
      catch { toast('Esse seletor CSS não é válido.', 'danger', 5000); return; }
    }
    pinSelector(index, value, engine);
    return;
  }

  const pane = target.closest('[data-pane]');
  if (pane) { setPane(pane.dataset.pane); return; }

  const filter = target.closest('[data-filter]');
  if (filter) { state.stepFilter = filter.dataset.filter; renderSteps(); return; }

  if (target.closest('#btnCollapseAll')) {
    state.openSteps.clear();
    renderSteps();
    return;
  }

  if (target.closest('#btnMeta')) {
    const meta = $('#workMeta');
    meta.hidden = !meta.hidden;
    $('#btnMeta').setAttribute('aria-expanded', String(!meta.hidden));
    return;
  }

  // Botões do painel de projeto. São renderizados dinamicamente e o painel
  // aparece em dois lugares — fluxo e sequência —, então a ação vive num
  // `data-act` em vez de um id, que colidiria entre as duas telas.
  const act = target.closest('[data-act]');
  if (act) { projectAction(act.dataset.act); return; }

  if (target.closest('#btnAutoKey')) {
    const provider = $('#autoProvider').value;
    api('/api/ai/key', { method: 'POST',
                         body: { provider, key: $('#autoKeyInput').value } })
      .then(async (result) => {
        if (!result.configured) { toast('A chave não foi aceita.', 'warn'); return; }
        toast('Chave salva nesta máquina. Não será pedida de novo.', 'ok', 5000);
        await loadProviders();
        renderAutoProviders();
      })
      .catch((error) => toast(error.message, 'danger', 7000));
    return;
  }

  if (target.closest('#btnAutoStop') || target.closest('#btnAutoStop2')) {
    api('/api/autotest/stop', { method: 'POST' })
      .then(() => toast('Parando após o passo atual…', 'info', 4000))
      .catch(() => {});
    return;
  }

  const saveEnv = target.closest('[data-save-env]');
  if (saveEnv) { salvarCredencial(saveEnv.dataset.saveEnv); return; }

  const saveKey = target.closest('[data-save-key]');
  if (saveKey) {
    const id = saveKey.dataset.saveKey;
    const campo = $(`[data-key-for="${id}"]`);
    api('/api/ai/key', { method: 'POST', body: { provider: id, key: campo.value } })
      .then(async (result) => {
        campo.value = '';
        toast(result.configured
          ? `Chave aceita. ${result.provider} está pronto para uso no assistente.`
          : `Chave removida de ${result.provider}.`, 'ok', 4500);
        await loadProviders();
        renderProviderList();
      })
      .catch((error) => toast(error.message, 'danger', 6000));
    return;
  }

  const openDir = target.closest('[data-open-dir]');
  if (openDir) {
    api('/api/reveal', { method: 'POST', body: { what: openDir.dataset.openDir } })
      .then((result) => {
        if (!result.ok) toast(result.error || 'Não consegui abrir a pasta.', 'warn');
      })
      .catch((error) => toast(error.message, 'danger'));
    return;
  }

  /* --- sequências --- */

  const delSuite = target.closest('[data-del-suite]');
  if (delSuite) {
    event.stopPropagation();
    if (!confirm('Excluir esta sequência? Os fluxos dela continuam salvos.')) return;
    api(`/api/suites/${delSuite.dataset.delSuite}`, { method: 'DELETE' })
      .then(() => { toast('Sequência excluída.', 'ok', 2200); loadSuites(); })
      .catch((error) => toast(error.message, 'danger'));
    return;
  }

  const suiteCard = target.closest('[data-suite]');
  if (suiteCard) { openSuite(suiteCard.dataset.suite); return; }

  const suiteFile = target.closest('[data-suite-file]');
  if (suiteFile) {
    state.suiteTab = suiteFile.dataset.suiteFile;
    renderSuiteCode();
    return;
  }

  const suitePane = target.closest('[data-suite-pane]');
  if (suitePane) { setSuitePane(suitePane.dataset.suitePane); return; }

  const move = target.closest('[data-suite-move]');
  if (move) {
    const from = Number(move.dataset.suiteMove);
    const to = from + Number(move.dataset.dir);
    const flows = state.suite.flows;
    if (to < 0 || to >= flows.length) return;
    [flows[from], flows[to]] = [flows[to], flows[from]];
    renderSuiteFlows();
    saveSuite({ now: true });
    return;
  }

  const removeFlow = target.closest('[data-suite-remove]');
  if (removeFlow) {
    state.suite.flows.splice(Number(removeFlow.dataset.suiteRemove), 1);
    renderSuiteFlows();
    saveSuite({ now: true });
    return;
  }

  const suiteOpenFlow = target.closest('[data-suite-open]');
  if (suiteOpenFlow) { openFlow(suiteOpenFlow.dataset.suiteOpen); return; }


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

$('#btnGenerate').onclick = () => generate();
$('#btnVerify').onclick = verify;

// Nome, descrição e URL do fluxo salvam sozinhos. Antes só eram aplicados ao
// gerar o código — quem editasse o nome e fechasse a tela perdia a mudança.
['#specName', '#specDesc', '#specBase'].forEach((sel) => {
  $(sel).addEventListener('input', () => saveFlowMeta());
  $(sel).addEventListener('blur', () => saveFlowMeta({ now: true }));
});

/* --------------------------------------------------------- sequências: UI */

/**
 * Cria a sequência e abre direto no campo do nome.
 *
 * A primeira versão pedia o nome num `window.prompt`. Funciona no navegador e
 * não funciona aqui: o Electron não implementa `prompt` — ele lança, a função
 * morre no meio e o clique não faz nada visível. Nada de diálogo, então: a
 * sequência nasce com nome provisório e o campo já vem focado e selecionado,
 * o que é menos passo do que responder a um diálogo.
 */
$('#btnAutoStart').onclick = startAuto;
$('#autoProvider').onchange = syncAutoModels;

$('#btnNewSuite').onclick = async () => {
  const button = $('#btnNewSuite');
  button.disabled = true;
  try {
    const suite = await api('/api/suites', {
      method: 'POST',
      body: { name: 'Nova sequência', flowIds: [] },
    });
    await loadSuites();
    await openSuite(suite.id);

    $('#suiteMeta').hidden = false;
    $('#btnSuiteMeta').setAttribute('aria-expanded', 'true');
    $('#suiteName').focus();
    $('#suiteName').select();
    toast('Dê um nome à sequência — ele vira o nome do arquivo.', 'info', 5000);
  } catch (error) {
    toast(error.message, 'danger', 7000);
  } finally {
    button.disabled = false;
  }
};

$('#btnBackSuites').onclick = closeSuite;
$('#btnSuiteGenerate').onclick = generateSuite;
$('#btnSuiteScaffold').onclick = scaffoldSuite;
$('#btnSuiteAdd').onclick = () => {
  const pick = $('#suiteAddPick');
  suiteAddFlow(pick.value);
  pick.value = '';
};

$('#btnSuiteMeta').onclick = () => {
  const meta = $('#suiteMeta');
  meta.hidden = !meta.hidden;
  $('#btnSuiteMeta').setAttribute('aria-expanded', String(!meta.hidden));
};

['#suiteName', '#suiteDesc', '#suiteBase'].forEach((sel) => {
  $(sel).addEventListener('input', () => saveSuite());
});
$('#suiteIsolate').addEventListener('change', () => {
  saveSuite({ now: true });
  toast($('#suiteIsolate').checked
    ? 'Testes independentes: cada um recomeça com sessão limpa.'
    : 'Sequência encadeada: os testes continuam de onde o anterior parou.',
    'info', 5000);
});

$('#btnSuiteCopy').onclick = async () => {
  const code = state.suiteOutputs?.[state.suiteTab]?.code;
  if (!code) { toast('Gere o código primeiro.', 'warn'); return; }
  await navigator.clipboard.writeText(code);
  toast('Código copiado.', 'ok', 2000);
};

$('#btnSuiteSave').onclick = async () => {
  const out = state.suiteOutputs?.[state.suiteTab];
  if (!out) { toast('Gere o código primeiro.', 'warn'); return; }
  try {
    const result = await api('/api/export', {
      method: 'POST',
      // A extensão acompanha o arquivo aberto: salvar o `commands.js` com
      // sufixo `.cy.js` faria o Cypress tentar rodá-lo como spec.
      body: {
        name: state.suiteTab === 'cypress' ? state.suite.name : out.filename,
        code: out.code,
        extension: state.suiteTab === 'cypress' ? '.cy.js'
          : state.suiteTab === 'elementos' ? '.json' : '.js',
      },
    });
    toast(`Salvo em ${result.path}`, 'ok', 6500);
  } catch (error) { toast(error.message, 'danger'); }
};

// Busca por passo. Sem debounce: o filtro roda sobre um array na memória, e
// esperar para responder só faria a digitação parecer travada.
$('#stepSearch').addEventListener('input', (event) => {
  state.stepQuery = event.target.value;
  renderSteps();
});

/* ------------------------------------------------------------------ editor */

const codeInput = $('#codeInput');

codeInput.addEventListener('input', (event) => onCodeInput(event.target.value));

// O realce é um segundo elemento por baixo: ele não rola sozinho.
codeInput.addEventListener('scroll', () => {
  const pre = $('#codeOut').parentElement;
  pre.scrollTop = codeInput.scrollTop;
  pre.scrollLeft = codeInput.scrollLeft;
});

codeInput.addEventListener('keydown', (event) => {
  // Tab dentro do editor indenta, em vez de pular para o próximo controle —
  // que é o que o navegador faria, e ninguém espera isso escrevendo código.
  if (event.key === 'Tab') {
    event.preventDefault();
    const { selectionStart: start, selectionEnd: end, value } = codeInput;
    codeInput.value = `${value.slice(0, start)}  ${value.slice(end)}`;
    codeInput.selectionStart = codeInput.selectionEnd = start + 2;
    onCodeInput(codeInput.value);
    return;
  }

  // Enter mantém a indentação da linha atual: sem isso, todo bloco novo começa
  // na coluna zero e o arquivo vira uma escada ao contrário.
  if (event.key === 'Enter') {
    const { selectionStart: start, value } = codeInput;
    const linha = value.slice(0, start).split('\n').pop();
    const recuo = (linha.match(/^[ \t]*/) || [''])[0];
    const extra = /[{([]$/.test(linha.trimEnd()) ? '  ' : '';
    if (!recuo && !extra) return;
    event.preventDefault();
    const insercao = `\n${recuo}${extra}`;
    codeInput.setRangeText(insercao, start, codeInput.selectionEnd, 'end');
    onCodeInput(codeInput.value);
  }
});

// Ctrl+S salva na hora, em vez de esperar o debounce ou abrir o diálogo do
// navegador para salvar a página inteira.
codeInput.addEventListener('keydown', (event) => {
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 's') {
    event.preventDefault();
    clearTimeout(saveCodeTimer);
    persistEdits(state.activeTab).then(() => toast('Edição salva.', 'ok', 2000));
  }
});

// Enter no campo de seletor próprio aplica, como em qualquer formulário.
document.addEventListener('keydown', (event) => {
  if (event.key !== 'Enter') return;
  const input = event.target.closest?.('[data-custom-input]');
  if (!input) return;
  event.preventDefault();
  $(`[data-custom-apply="${input.dataset.customInput}"]`)?.click();
});

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
        fixtures: $('#optFixtures').checked,
      },
    });
    renderScaffold(result);
    setPane('project');
    toast(result.edited?.length
      ? `Projeto gerado com ${result.edited.length} arquivo(s) na sua versão editada.`
      : result.installed
        ? 'Projeto atualizado. As dependências instaladas foram preservadas.'
        : `Projeto criado com ${result.fileList.length} arquivos.`, 'ok', 5200);
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
function renderScaffold(result, { host = '#scaffoldResult', empty = '#projectEmpty' } = {}) {
  // `host` guarda de onde este projeto veio. O painel aparece na tela do fluxo
  // e na da sequência; sem isso, rodar a sequência escreveria o resultado no
  // painel do fluxo, que está noutra vista.
  state.project = { ...result, host };
  state.projectStale = false;
  renderProjectStale();
  if (empty) $(empty).hidden = true;

  // Num painel restaurado não sabemos os comandos — eles vivem no arquivo,
  // não no estado. Dizer "nenhuma repetição justificou um comando" seria
  // afirmar o que não foi verificado.
  const commands = result.commands?.length
    ? result.commands.map((c) => `
        <div style="padding:5px 0;border-top:1px solid var(--border-soft)">
          <code class="mono" style="color:var(--accent)">cy.${esc(c.name)}()</code>
          <div class="small muted">${esc(c.doc)}</div>
        </div>`).join('')
    : result.restored
      ? `<div class="small muted">Abra
         <code class="mono">cypress/support/commands.js</code> na pasta do
         projeto para ver os comandos gerados.</div>`
      : '<div class="small muted">Nenhuma repetição justificou um comando.</div>';

  // Um campo por credencial que o teste pede. Vão para `cypress.env.json`,
  // que o .gitignore do projeto já protege. Uma credencial já salva mostra
  // isso e vem vazia: repetir o valor no campo não ajudaria ninguém, e
  // apresentar um campo em branco sem explicação dá a impressão de que o
  // Cygen esqueceu o que foi digitado.
  const salvas = new Set(result.savedKeys || []);
  const creds = result.envKeys.length
    ? `<div class="card-title mt" style="margin-bottom:8px">Credenciais</div>
       <div class="col" style="gap:8px">
         ${result.envKeys.map((k) => `
           <div class="field">
             <label for="env-${esc(k)}">
               CYPRESS_${esc(k)}
               ${salvas.has(k) ? '<span class="chip ok">salva</span>' : ''}
             </label>
             <div class="row" style="gap:7px">
               <input class="input grow" id="env-${esc(k)}" data-env="${esc(k)}"
                      type="password" autocomplete="off"
                      placeholder="${salvas.has(k)
                        ? 'já guardada — preencha só para trocar'
                        : 'o valor real, para o teste conseguir entrar'}">
               <button class="btn sm" data-save-env="${esc(k)}" style="flex:none">
                 ${salvas.has(k) ? 'Trocar' : 'Salvar'}
               </button>
             </div>
           </div>`).join('')}
       </div>
       <div class="hint" style="margin-top:6px">
         Guardadas em <code class="mono">cypress.env.json</code>, dentro do
         projeto. O <code class="mono">.gitignore</code> dele já ignora esse
         arquivo, então elas ficam nesta máquina e valem para toda execução —
         inclusive por <code class="mono">npm test</code> no terminal.
       </div>`
    : '';

  $(host).innerHTML = `
    <div class="callout ok" style="margin-top:14px;display:block">
      <div class="row" style="gap:10px;margin-bottom:12px">
        ${icon('package')}
        <strong>Projeto pronto</strong>
        <span class="chip ok">${result.fileList.length} arquivos</span>
        ${result.restored ? '<span class="chip">já estava no disco</span>' : ''}
        ${result.installed ? '<span class="chip ok">dependências instaladas</span>' : ''}
      </div>

      ${result.edited?.length ? `
        <div class="callout" style="margin-bottom:11px;padding:9px 11px">
          ${icon('info')}<div class="small">Gravado com a sua versão de
          ${result.edited.map((f) => `<code class="mono">${esc(f)}</code>`).join(', ')}
          — o gerador não sobrescreveu esses arquivos.</div>
        </div>` : ''}

      <div class="small muted" style="margin-bottom:4px">Criado em</div>
      <code class="mono small" style="display:block;padding:8px 11px;
            background:var(--bg-sunken);border-radius:var(--r);word-break:break-all">
        ${esc(result.path)}
      </code>

      ${creds}

      <div class="row wrap mt" style="gap:9px">
        <button class="btn primary" data-act="run">
          ${icon('play')} Rodar agora
        </button>
        <button class="btn" data-act="open">
          ${icon('rec')} Abrir o Cypress
        </button>
        <button class="btn" data-act="reveal" title="Abre a pasta no explorador de arquivos">
          ${icon('folder')} Ver pasta
        </button>
        <button class="btn ghost" data-act="copy-path" title="Copia o caminho">
          ${icon('copy')} Copiar caminho
        </button>
      </div>
      <div class="hint" style="margin-top:7px">
        Na primeira vez o Cypress é baixado — alguns minutos. Depois é imediato.
      </div>

      <div class="run-output"></div>

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

/**
 * Grava uma credencial no projeto.
 *
 * Vai para o disco assim que é digitada, não só quando alguém clica em rodar.
 * A diferença aparece na visita seguinte: o valor continua lá, e o painel
 * mostra "salva" em vez de um campo vazio pedindo de novo.
 */
async function salvarCredencial(chave) {
  if (!state.project) return;
  const campo = $(`${state.project.host} [data-env="${chave}"]`);
  const valor = (campo?.value || '').trim();
  if (!valor) { toast('Digite o valor antes de salvar.', 'warn'); return; }

  try {
    const result = await api('/api/project/env', {
      method: 'POST',
      body: { path: state.project.path, env: { [chave]: valor } },
    });
    campo.value = '';
    state.project.savedKeys = result.savedKeys;
    renderScaffold(state.project, { host: state.project.host, empty: null });
    toast(`CYPRESS_${chave} guardada no projeto. Não será pedida de novo.`,
          'ok', 5000);
  } catch (error) {
    toast(error.message, 'danger', 6000);
  }
}

/** Valores digitados nos campos de credencial do projeto ativo. */
function projectEnv() {
  const out = {};
  $$(`${state.project?.host || ''} [data-env]`).forEach((input) => {
    if (input.value.trim()) out[input.dataset.env] = input.value;
  });
  return out;
}

/** Área de progresso e resultado da execução, dentro do painel ativo. */
function runLog(html) {
  const area = $(`${state.project.host} .run-output`);
  if (area) area.innerHTML = html;
}

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

  // Um teste que passou usando reserva não é um teste saudável: o seletor
  // primário já não encontra o elemento. Passar em silêncio esconde isso até
  // a reserva cair também — e aí não sobra nada para curar.
  // As mensagens de encerramento que cada teste imprimiu. Ficam à vista
  // porque são o resumo em linguagem de gente do que a suíte acabou de fazer.
  const notas = (result.notas || []).length ? `
    <div style="margin-top:9px;padding-top:9px;border-top:1px solid var(--border-soft)">
      ${result.notas.map((n) => `
        <div class="small" style="color:var(--ok)">${esc(n)}</div>`).join('')}
    </div>` : '';

  const reservas = (result.reservas || []).length ? `
    <div style="margin-top:9px;padding-top:9px;border-top:1px solid var(--border-soft)">
      <strong class="small">Seletores que precisaram de reserva</strong>
      <div class="small muted" style="margin-top:3px">
        Funcionaram desta vez pela alternativa. Vale pedir um
        <code class="mono">data-cy</code> nesses elementos.</div>
      ${result.reservas.map((r) => `
        <pre class="mono small" style="margin:5px 0 0;white-space:pre-wrap;
             color:var(--text-muted)">${esc(r.from)}\n  → ${esc(r.to)}</pre>`).join('')}
    </div>` : '';

  runLog(`<div class="callout ${passed ? 'ok' : 'warn'}" style="margin-top:12px;display:block">
    <div class="row" style="gap:10px">
      ${icon(passed ? 'check' : 'warn')}
      <strong>${passed
        ? `Passou — ${result.passing} de ${result.tests}`
        : `${result.failing} de ${result.tests} falharam`}</strong>
      <span class="chip">${((result.durationMs || 0) / 1000).toFixed(1)}s</span>
      ${(result.reservas || []).length
        ? `<span class="chip warn">${result.reservas.length} com reserva</span>` : ''}
    </div>
    ${notas}
    ${failures}
    ${reservas}
  </div>`);
}

/** Ações do painel de projeto, seja ele de um fluxo ou de uma sequência. */
function projectAction(act) {
  if (!state.project) return;
  if (act === 'run') return runProject();
  if (act === 'open') return openCypress();
  if (act === 'reveal') {
    return api('/api/project/reveal', { method: 'POST', body: { path: state.project.path } })
      .then((result) => {
        if (result.ok) toast('Pasta aberta no explorador.', 'ok', 2400);
        else toast(result.error || 'Não consegui abrir a pasta.', 'warn');
      })
      .catch((error) => toast(error.message, 'danger'));
  }
  if (act === 'copy-path') {
    return navigator.clipboard.writeText(state.project.path)
      .then(() => toast('Caminho copiado.', 'ok', 2200))
      .catch(() => toast('Não consegui copiar.', 'warn'));
  }
}

/** O botão de uma ação, dentro do painel do projeto ativo. */
function actButton(act) {
  return $(`${state.project.host} [data-act="${act}"]`);
}

async function runProject() {
  const button = actButton('run');
  button.disabled = true;
  button.innerHTML = '<span class="spinner"></span> Rodando…';
  runLog(`<div class="callout" style="margin-top:12px">
    <span class="spinner"></span>
    <div class="run-line small muted">preparando…</div></div>`);

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
  const button = actButton('open');
  button.disabled = true;
  button.innerHTML = '<span class="spinner"></span> Abrindo…';
  runLog(`<div class="callout" style="margin-top:12px">
    <span class="spinner"></span>
    <div class="run-line small muted">preparando…</div></div>`);

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
  const code = currentCode();
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
        code: currentCode(),
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
  const code = currentCode();
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
