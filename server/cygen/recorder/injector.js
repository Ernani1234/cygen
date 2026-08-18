/**
 * Gravador injetado do Cygen.
 *
 * Roda dentro da página via `add_init_script` do Playwright — o que significa
 * que ele é reinstalado automaticamente a cada navegação, iframe e recarga.
 * Era exatamente esse o furo da v2: os listeners eram injetados uma vez por
 * `execute_script`, e qualquer navegação os apagava silenciosamente. Numa SPA
 * com rotas em hash isso passava despercebido até o teste gerado vir vazio.
 *
 * Responsabilidades:
 *   1. Descrever elementos com riqueza suficiente para o motor de seletores
 *   2. Verificar unicidade dos candidatos na página real, na hora
 *   3. Fotografar o DOM antes/depois de cada ação e produzir o diff
 *   4. Detectar rotas de SPA (pushState/replaceState/hashchange)
 *   5. Registrar erros de console e alterações de localStorage
 */

(() => {
  if (window.__cygenInstalled) return;
  window.__cygenInstalled = true;

  const SETTLE_MS = 700;      // janela de observação após cada ação
  const MAX_TEXT = 200;
  const MAX_NODES = 12;

  let seq = 0;
  const pending = new Map();  // ações aguardando a janela de estabilização

  // --- transporte ---------------------------------------------------------
  // `cygenEmit` é exposto pelo Playwright via expose_binding. Se ainda não
  // existir (script rodou antes do binding), enfileiramos.
  const outbox = [];
  function emit(event) {
    if (typeof window.cygenEmit === 'function') {
      try { window.cygenEmit(event); return; } catch (e) { /* cai no buffer */ }
    }
    outbox.push(event);
    if (outbox.length > 500) outbox.shift();
  }
  window.__cygenDrain = () => outbox.splice(0, outbox.length);

  // --- utilidades de DOM --------------------------------------------------

  const ATTRS_OF_INTEREST = [
    'data-cy', 'data-test', 'data-testid', 'data-test-id', 'data-qa',
    'data-automation-id', 'data-e2e', 'id', 'name', 'type', 'role',
    'aria-label', 'aria-labelledby', 'aria-expanded', 'aria-selected',
    'aria-checked', 'aria-invalid', 'aria-live', 'placeholder', 'title',
    'alt', 'href', 'value', 'disabled', 'checked', 'autocomplete', 'for',
  ];

  function textOf(el) {
    if (!el) return '';
    // innerText respeita CSS (não traz conteúdo oculto), ao contrário de
    // textContent — é o que o usuário de fato enxerga.
    const raw = (el.innerText || el.textContent || '').trim();
    return raw.length > MAX_TEXT ? raw.slice(0, MAX_TEXT) : raw;
  }

  function attrsOf(el) {
    const out = {};
    if (!el || !el.getAttribute) return out;
    for (const name of ATTRS_OF_INTEREST) {
      if (el.hasAttribute && el.hasAttribute(name)) {
        out[name] = el.getAttribute(name);
      }
    }
    return out;
  }

  function classListOf(el) {
    if (!el || !el.classList) return [];
    return Array.from(el.classList).slice(0, 20);
  }

  function xpathOf(el) {
    if (!el || el.nodeType !== 1) return '';
    if (el.id && !/\d{4,}|[0-9a-f]{8}-/.test(el.id)) {
      return `//*[@id="${el.id}"]`;
    }
    const parts = [];
    let node = el;
    while (node && node.nodeType === 1 && node !== document.body) {
      let index = 1;
      let sibling = node.previousElementSibling;
      while (sibling) {
        if (sibling.tagName === node.tagName) index++;
        sibling = sibling.previousElementSibling;
      }
      parts.unshift(`${node.tagName.toLowerCase()}[${index}]`);
      node = node.parentElement;
      if (parts.length > 12) break;
    }
    return '/html/body/' + parts.join('/');
  }

  // Identidade estável durante a sessão: permite ao compilador de intenção
  // saber que dois eventos tocaram o mesmo nó.
  let nodeCounter = 0;
  const nodeIds = new WeakMap();
  function nodeIdOf(el) {
    if (!el) return null;
    if (!nodeIds.has(el)) nodeIds.set(el, `n${++nodeCounter}`);
    return nodeIds.get(el);
  }

  /**
   * Conta quantos elementos casam com um seletor. É a verificação de
   * unicidade que o motor de seletores usa para pontuar candidatos — sem ela
   * o ranking seria só um palpite sobre o nome do atributo.
   */
  function countMatches(selector) {
    try {
      return document.querySelectorAll(selector).length;
    } catch (e) {
      return 0;
    }
  }

  /** Gera os mesmos candidatos que o motor Python, para poder medi-los. */
  function candidateSelectors(el) {
    const out = [];
    const attrs = attrsOf(el);
    const tag = el.tagName ? el.tagName.toLowerCase() : '';

    for (const a of ['data-cy', 'data-test', 'data-testid', 'data-test-id',
                     'data-qa', 'data-automation-id', 'data-e2e']) {
      if (attrs[a]) out.push(`[${a}="${cssEscape(attrs[a])}"]`);
    }
    for (const a of ['aria-label', 'role', 'placeholder', 'title', 'alt']) {
      if (attrs[a]) {
        const base = `[${a}="${cssEscape(attrs[a])}"]`;
        out.push(base);
        if (tag && (a === 'role' || a === 'placeholder' || a === 'title')) {
          out.push(`${tag}${base}`);
        }
      }
    }
    if (attrs.id) {
      out.push(`#${attrs.id}`);
      out.push(`[id="${cssEscape(attrs.id)}"]`);
    }
    if (attrs.name) {
      out.push(`[name="${cssEscape(attrs.name)}"]`);
      if (['input', 'select', 'textarea'].includes(tag)) {
        out.push(`${tag}[name="${cssEscape(attrs.name)}"]`);
      }
    }
    const classes = classListOf(el);
    if (classes.length) {
      out.push((tag || '') + classes.slice(0, 2).map((c) => `.${cssEscape(c)}`).join(''));
    }
    return out;
  }

  function cssEscape(value) {
    if (window.CSS && CSS.escape) {
      // Só escapamos para uso dentro de aspas; CSS.escape é agressivo demais
      // para valores de atributo entre aspas.
      return String(value).replace(/\\/g, '\\\\').replace(/"/g, '\\"');
    }
    return String(value).replace(/\\/g, '\\\\').replace(/"/g, '\\"');
  }

  /** Ancestral mais próximo que carrega um atributo de teste. */
  function testAnchorOf(el) {
    let node = el ? el.parentElement : null;
    let depth = 0;
    while (node && depth < 6) {
      const attrs = attrsOf(node);
      for (const a of ['data-cy', 'data-testid', 'data-test', 'data-qa']) {
        if (attrs[a]) {
          return {
            selector: `[${a}="${cssEscape(attrs[a])}"]`,
            relative: el.tagName ? el.tagName.toLowerCase() : '',
          };
        }
      }
      node = node.parentElement;
      depth++;
    }
    return null;
  }

  function describe(el, { withMatches = true } = {}) {
    if (!el || el.nodeType !== 1) return {};
    const desc = {
      nodeId: nodeIdOf(el),
      tag: el.tagName.toLowerCase(),
      text: textOf(el),
      classList: classListOf(el),
      attributes: attrsOf(el),
      xpath: xpathOf(el),
      testAnchor: testAnchorOf(el),
    };
    if (el.value !== undefined && el.type !== 'password') {
      desc.attributes.value = String(el.value).slice(0, 120);
    }
    if (withMatches) {
      const counts = {};
      for (const sel of candidateSelectors(el)) {
        counts[sel] = countMatches(sel);
      }
      desc.matchCounts = counts;
    }
    return desc;
  }

  function ancestorsOf(el, limit = 6) {
    const out = [];
    let node = el ? el.parentElement : null;
    while (node && out.length < limit && node !== document.body) {
      out.push(describe(node, { withMatches: false }));
      node = node.parentElement;
    }
    return out;
  }

  /**
   * Elementos que estão sob o ponto do clique, em ordem de empilhamento.
   *
   * Frameworks posicionam camadas de ripple e overlays *por cima* do controle
   * real, às vezes como irmãos e não como filhos. Nesse arranjo, subir pela
   * árvore nunca encontra o botão — ele não é ancestral do overlay, está
   * atrás dele. `elementsFromPoint` enxerga o que a árvore esconde.
   */
  function beneathPoint(x, y, limit = 5) {
    if (typeof x !== 'number' || typeof y !== 'number') return [];
    try {
      const stack = document.elementsFromPoint(x, y) || [];
      return stack
        .slice(1, limit + 1)                    // [0] é o próprio alvo
        .filter((node) => node && node.nodeType === 1 && node !== document.body
                          && node !== document.documentElement)
        .map((node) => describe(node, { withMatches: false }));
    } catch (e) {
      return [];
    }
  }

  /**
   * Resolve o alvo real de um evento, atravessando shadow DOM.
   * `event.target` num web component devolve o host, não o elemento interno.
   */
  function realTarget(event) {
    if (event.composedPath) {
      const path = event.composedPath();
      if (path && path.length) {
        for (const node of path) {
          if (node && node.nodeType === 1) return node;
        }
      }
    }
    return event.target;
  }

  // --- observação de mutações --------------------------------------------

  /**
   * Buffer de mutações com carimbo de tempo.
   *
   * As janelas de estabilização de duas ações se sobrepõem: o usuário clica
   * enquanto a digitação anterior ainda está assentando. Com um buffer único
   * esvaziado no início de cada ação, a segunda ação apagava as mutações da
   * primeira, e a primeira acabava colhendo as da segunda — a evidência ia
   * parar no passo errado. Guardar o instante de cada mutação permite que
   * cada ação leia exatamente a sua fatia, sem destruir a das outras.
   */
  let mutationBuffer = [];
  const observer = new MutationObserver((records) => {
    const at = Date.now();
    for (const r of records) mutationBuffer.push({ at, record: r });
    if (mutationBuffer.length > 4000) {
      mutationBuffer = mutationBuffer.slice(-2000);
    }
  });

  /** Mutações dentro de uma janela [início, fim], sem consumir o buffer. */
  function mutationsBetween(startedAt, endedAt) {
    return mutationBuffer
      .filter((entry) => entry.at >= startedAt && entry.at <= endedAt)
      .map((entry) => entry.record);
  }

  /** Descarta o que já não interessa a nenhuma ação pendente. */
  function pruneMutations() {
    let oldest = Date.now();
    for (const entry of pending.values()) {
      if (entry.startedAt < oldest) oldest = entry.startedAt;
    }
    mutationBuffer = mutationBuffer.filter((entry) => entry.at >= oldest - 100);
  }

  function startObserving() {
    try {
      observer.observe(document.documentElement || document.body, {
        childList: true, subtree: true, attributes: true,
        attributeOldValue: true, characterData: true, characterDataOldValue: true,
        attributeFilter: ['class', 'aria-expanded', 'aria-selected', 'aria-checked',
                          'aria-invalid', 'disabled', 'hidden', 'style', 'value'],
      });
    } catch (e) { /* documento ainda não pronto */ }
  }

  if (document.documentElement) startObserving();
  else document.addEventListener('DOMContentLoaded', startObserving);

  /** Consome o buffer e resume o que mudou de forma consumível pelo Oracle. */
  function summarizeMutations(records) {
    const added = [];
    const removed = [];
    const attrChanged = [];
    const textChanged = [];
    const seenAdded = new Set();
    const seenRemoved = new Set();

    for (const r of records) {
      if (r.type === 'childList') {
        for (const node of r.addedNodes) {
          if (node.nodeType !== 1 || added.length >= MAX_NODES) continue;
          const key = nodeIdOf(node);
          if (seenAdded.has(key)) continue;
          seenAdded.add(key);
          added.push({
            tag: node.tagName.toLowerCase(),
            classList: classListOf(node),
            attributes: attrsOf(node),
            role: node.getAttribute ? (node.getAttribute('role') || '') : '',
            text: textOf(node),
          });
        }
        for (const node of r.removedNodes) {
          if (node.nodeType !== 1 || removed.length >= MAX_NODES) continue;
          const key = nodeIdOf(node);
          if (seenRemoved.has(key)) continue;
          seenRemoved.add(key);
          removed.push({
            tag: node.tagName.toLowerCase(),
            classList: classListOf(node),
            attributes: attrsOf(node),
            role: node.getAttribute ? (node.getAttribute('role') || '') : '',
            text: textOf(node),
          });
        }
      } else if (r.type === 'attributes') {
        const el = r.target;
        if (!el || el.nodeType !== 1 || attrChanged.length >= MAX_NODES) continue;
        const entry = {
          name: r.attributeName,
          value: el.getAttribute(r.attributeName),
          oldValue: r.oldValue,
          selector: bestSelectorFor(el),
        };
        if (r.attributeName === 'class') {
          const before = new Set((r.oldValue || '').split(/\s+/).filter(Boolean));
          const after = Array.from(el.classList || []);
          entry.added = after.filter((c) => !before.has(c));
          entry.removed = Array.from(before).filter((c) => !after.includes(c));
          if (!entry.added.length && !entry.removed.length) continue;
        }
        attrChanged.push(entry);
      } else if (r.type === 'characterData') {
        const parent = r.target.parentElement;
        if (!parent || textChanged.length >= MAX_NODES) continue;
        const after = (r.target.data || '').trim();
        const before = (r.oldValue || '').trim();
        if (!after || after === before) continue;
        textChanged.push({ before, after, selector: bestSelectorFor(parent) });
      }
    }

    return {
      added, removed, attrChanged, textChanged,
      listDelta: detectListDelta(added, removed),
    };
  }

  /**
   * Detecta o padrão "lista foi populada": vários irmãos com a mesma cara
   * entrando de uma vez. É o sinal de que uma tabela/grid carregou dados.
   */
  function detectListDelta(added, removed) {
    if (added.length < 2) return null;
    const groups = new Map();
    for (const node of added) {
      const key = node.tag + '|' + (node.classList[0] || '') + '|' +
                  (node.attributes['data-cy'] || '');
      groups.set(key, (groups.get(key) || 0) + 1);
    }
    let bestKey = null;
    let bestCount = 0;
    for (const [key, count] of groups) {
      if (count > bestCount) { bestKey = key; bestCount = count; }
    }
    if (bestCount < 2) return null;

    const [tag, cls, testAttr] = bestKey.split('|');
    let selector = tag;
    if (testAttr) selector = `[data-cy="${cssEscape(testAttr)}"]`;
    else if (cls) selector = `${tag}.${cssEscape(cls)}`;

    const countAfter = countMatches(selector);
    return {
      selector,
      countAfter,
      countBefore: Math.max(0, countAfter - bestCount + removed.length),
    };
  }

  function bestSelectorFor(el) {
    const cands = candidateSelectors(el);
    for (const sel of cands) {
      if (countMatches(sel) === 1) return sel;
    }
    return cands[0] || (el.tagName ? el.tagName.toLowerCase() : '');
  }

  // --- rede: o Playwright captura via CDP, aqui só marcamos o instante ----

  // --- localStorage -------------------------------------------------------

  function snapshotStorage() {
    const out = [];
    try {
      for (let i = 0; i < localStorage.length; i++) out.push(localStorage.key(i));
    } catch (e) { /* bloqueado por política */ }
    return out;
  }

  // --- erros de console ---------------------------------------------------

  const consoleErrors = [];
  const originalError = console.error;
  console.error = function (...args) {
    try {
      consoleErrors.push(args.map((a) => {
        if (a instanceof Error) return a.message;
        if (typeof a === 'object') { try { return JSON.stringify(a).slice(0, 200); } catch (e) { return '[objeto]'; } }
        return String(a).slice(0, 200);
      }).join(' '));
      if (consoleErrors.length > 50) consoleErrors.shift();
    } catch (e) { /* nunca quebrar o app hospedeiro */ }
    return originalError.apply(console, args);
  };
  window.addEventListener('error', (e) => {
    consoleErrors.push(`${e.message} (${e.filename}:${e.lineno})`);
    if (consoleErrors.length > 50) consoleErrors.shift();
  });
  window.addEventListener('unhandledrejection', (e) => {
    consoleErrors.push(`Promise rejeitada: ${e.reason}`);
    if (consoleErrors.length > 50) consoleErrors.shift();
  });

  // --- ciclo de vida de uma ação -----------------------------------------

  /**
   * Registra uma ação e agenda a coleta do seu efeito.
   *
   * A separação entre "o que o usuário fez" e "o que aconteceu depois" é o
   * que permite ao Oracle inferir pós-condições. Sem a janela de estabilização
   * o diff sairia vazio, porque a maioria dos apps reage de forma assíncrona.
   */
  function record(type, el, extra = {}) {
    if (window.__cygenPaused) return;

    const id = ++seq;
    const startedAt = Date.now();

    // Atribuição causal: o que a página fizer a partir de agora é reação a
    // ESTA ação, não à anterior. Fechamos a janela de tudo que ainda estava
    // aberto — sem isto, a digitação (cuja janela é mais longa por causa do
    // debounce) engoliria a reação ao clique que veio depois dela.
    for (const entry of pending.values()) {
      if (entry.closedAt === undefined) {
        entry.closedAt = startedAt;
        // O estado final da ação anterior é o estado AGORA, antes desta ação
        // mexer em qualquer coisa. Ler no settle traria a URL e o storage já
        // alterados por esta ação, e a assertion apontaria para o passo errado.
        entry.urlAtClose = location.href;
        entry.titleAtClose = document.title;
        entry.storageAtClose = snapshotStorage();
      }
    }

    const storageBefore = snapshotStorage();
    const errorsBefore = consoleErrors.length;

    const event = {
      seq: id,
      type,
      timestamp: startedAt,
      url: location.href,
      urlBefore: location.href,
      titleBefore: document.title,
      element: el ? describe(el) : {},
      ancestors: el ? ancestorsOf(el) : [],
      ...extra,
    };

    pending.set(id, { event, storageBefore, errorsBefore, startedAt });

    // Sinaliza imediatamente para a UI mostrar o passo aparecendo ao vivo,
    // ainda sem a evidência (que chega no `settle`).
    emit({ ...event, phase: 'start' });

    setTimeout(() => settle(id), SETTLE_MS);
  }

  function settle(id) {
    const entry = pending.get(id);
    if (!entry) return;
    pending.delete(id);

    const { event, storageBefore, errorsBefore, startedAt } = entry;
    // A janela vai do início da ação até o instante em que a ação seguinte
    // começou (ou até agora, se nenhuma outra veio). Não consumimos o buffer:
    // outra ação ainda em curso pode precisar das mesmas mutações.
    const endedAt = entry.closedAt ?? Date.now();
    const records = mutationsBetween(startedAt, endedAt);

    const storageAfter = entry.storageAtClose ?? snapshotStorage();
    const beforeSet = new Set(storageBefore);
    const afterSet = new Set(storageAfter);

    event.phase = 'settled';
    event.urlAfter = entry.urlAtClose ?? location.href;
    event.titleAfter = entry.titleAtClose ?? document.title;
    event.mutations = summarizeMutations(records);
    event.storageDelta = {
      localStorageAdded: storageAfter.filter((k) => !beforeSet.has(k)),
      localStorageRemoved: storageBefore.filter((k) => !afterSet.has(k)),
    };
    event.consoleErrors = consoleErrors.slice(errorsBefore);
    // A duração é a da janela efetiva, não o tempo até o settle. O lado
    // Python usa este valor para decidir quais requisições pertencem a este
    // passo; informar mais do que a janela real faria um passo reivindicar as
    // chamadas do passo seguinte.
    event.durationMs = Math.max(0, endedAt - startedAt);
    // Janela cortada por uma ação seguinte: o limite é exato, não estimado.
    // O lado Python não deve acrescentar folga aqui, senão este passo captura
    // as requisições que pertencem à ação que o interrompeu.
    event.truncated = entry.closedAt !== undefined;

    emit(event);
    pruneMutations();
  }

  // --- listeners ----------------------------------------------------------

  document.addEventListener('click', (e) => {
    const el = realTarget(e);
    if (!el || el.nodeType !== 1) return;
    const input = el.closest ? el.closest('input') : null;
    if (input && (input.type === 'checkbox' || input.type === 'radio')) {
      record('click', input, { checkedAfter: input.checked });
      return;
    }
    record('click', el, { beneath: beneathPoint(e.clientX, e.clientY) });
  }, true);

  document.addEventListener('dblclick', (e) => {
    record('dblclick', realTarget(e), { beneath: beneathPoint(e.clientX, e.clientY) });
  }, true);

  // Digitação: um evento por tecla seria ruído. Agrupamos por campo e só
  // registramos quando o usuário para de digitar — o compilador de intenção
  // ainda faz um segundo colapso, mas isso já reduz drasticamente o volume.
  const typingTimers = new WeakMap();
  document.addEventListener('input', (e) => {
    const el = realTarget(e);
    if (!el || !('value' in el)) return;
    if (el.tagName === 'SELECT') return;

    const existing = typingTimers.get(el);
    if (existing) clearTimeout(existing);

    const timer = setTimeout(() => {
      typingTimers.delete(el);
      const isSecret = el.type === 'password';
      record('type', el, {
        value: isSecret ? '' : el.value,
        valueAfter: isSecret ? '' : el.value,
        secret: isSecret,
      });
    }, 450);
    typingTimers.set(el, timer);
  }, true);

  document.addEventListener('change', (e) => {
    const el = realTarget(e);
    if (!el) return;
    if (el.tagName === 'SELECT') {
      const opt = el.options[el.selectedIndex];
      record('select', el, {
        value: el.value,
        selectedText: opt ? opt.text : '',
      });
    } else if (el.type === 'file') {
      const names = Array.from(el.files || []).map((f) => f.name);
      record('upload', el, { value: names });
    }
  }, true);

  document.addEventListener('keydown', (e) => {
    // Só teclas com significado de fluxo. Caracteres normais já viram `type`.
    if (!['Enter', 'Escape', 'Tab'].includes(e.key)) return;
    if (e.key === 'Tab') return;   // navegação por teclado não é intenção de teste
    record('keypress', realTarget(e), { value: e.key });
  }, true);

  // --- navegação de SPA ---------------------------------------------------
  // Rotas em hash e pushState não disparam `load`. Sem isto, uma SPA inteira
  // parece uma única página para o gravador.

  let lastUrl = location.href;
  function checkNavigation(source) {
    if (location.href === lastUrl) return;
    const from = lastUrl;
    lastUrl = location.href;
    emit({
      seq: ++seq,
      type: 'navigation',
      phase: 'settled',
      timestamp: Date.now(),
      url: location.href,
      urlBefore: from,
      urlAfter: location.href,
      titleBefore: document.title,
      titleAfter: document.title,
      element: {},
      ancestors: [],
      source,
      mutations: {}, network: [], storageDelta: {}, consoleErrors: [],
    });
  }

  for (const method of ['pushState', 'replaceState']) {
    const original = history[method];
    history[method] = function (...args) {
      const result = original.apply(this, args);
      setTimeout(() => checkNavigation(method), 0);
      return result;
    };
  }
  window.addEventListener('popstate', () => checkNavigation('popstate'));
  window.addEventListener('hashchange', () => checkNavigation('hashchange'));

  // --- modo seletor (o usuário aponta um elemento para criar assertion) ---

  let pickerActive = false;
  let highlighted = null;
  const overlay = document.createElement('div');
  overlay.style.cssText = [
    'position:fixed', 'pointer-events:none', 'z-index:2147483647',
    'border:2px solid #A8C7E8', 'background:rgba(168,199,232,.18)',
    'border-radius:6px', 'transition:all .09s ease-out', 'display:none',
    'box-shadow:0 0 0 9999px rgba(0,0,0,.04)',
  ].join(';');

  function ensureOverlay() {
    if (!overlay.parentNode && document.body) document.body.appendChild(overlay);
  }

  function moveOverlay(el) {
    ensureOverlay();
    const r = el.getBoundingClientRect();
    overlay.style.display = 'block';
    overlay.style.top = `${r.top}px`;
    overlay.style.left = `${r.left}px`;
    overlay.style.width = `${r.width}px`;
    overlay.style.height = `${r.height}px`;
  }

  window.__cygenSetPicker = (active) => {
    pickerActive = !!active;
    if (!pickerActive) {
      overlay.style.display = 'none';
      highlighted = null;
    }
  };

  document.addEventListener('mousemove', (e) => {
    if (!pickerActive) return;
    const el = realTarget(e);
    if (!el || el === highlighted || el.nodeType !== 1) return;
    highlighted = el;
    moveOverlay(el);
  }, true);

  document.addEventListener('click', (e) => {
    if (!pickerActive) return;
    e.preventDefault();
    e.stopPropagation();
    const el = realTarget(e);
    emit({
      seq: ++seq,
      type: 'pick',
      phase: 'settled',
      timestamp: Date.now(),
      url: location.href,
      element: describe(el),
      ancestors: ancestorsOf(el),
      snapshot: {
        text: textOf(el),
        value: 'value' in el ? String(el.value || '') : null,
        visible: !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length),
        checked: 'checked' in el ? !!el.checked : null,
        disabled: 'disabled' in el ? !!el.disabled : null,
        count: countMatches(bestSelectorFor(el)),
      },
      mutations: {}, network: [], storageDelta: {}, consoleErrors: [],
    });
  }, true);

  // --- controle externo ---------------------------------------------------

  window.__cygenPause = () => { window.__cygenPaused = true; };
  window.__cygenResume = () => { window.__cygenPaused = false; };
  window.__cygenStatus = () => ({
    installed: true,
    seq,
    pending: pending.size,
    url: location.href,
  });

  emit({
    seq: 0, type: 'ready', phase: 'settled', timestamp: Date.now(),
    url: location.href, element: {}, ancestors: [],
    mutations: {}, network: [], storageDelta: {}, consoleErrors: [],
  });
})();
