"""
O que o agente enxerga da tela.

O DOM inteiro não cabe no contexto de um modelo — uma tela comum de sistema
tem 50 mil tokens de HTML, e mandar isso a cada passo custaria caro para
devolver uma decisão que depende de vinte elementos. Aqui a página vira uma
lista curta de *coisas em que dá para agir*, cada uma com um rótulo que uma
pessoa reconheceria.

O resultado fica na casa de algumas centenas de tokens por tela. É o mesmo
princípio do resto do Cygen: o modelo recebe o que foi observado, não a
página crua para adivinhar sozinho.
"""

from __future__ import annotations

from typing import Any

# Quantos elementos descrever por tela. Acima disso a lista deixa de caber na
# decisão e passa a diluir o que importa — e uma tela com mais de 60 controles
# visíveis quase sempre é uma tabela, onde as linhas se repetem.
MAX_ELEMENTOS = 60

# O script roda no navegador: percorre o que está visível e devolve os
# controles com um nome legível. A ordem é a de leitura, que é a ordem em que
# uma pessoa tentaria.
SCAN = """() => {
  const visivel = (el) => {
    const r = el.getBoundingClientRect();
    if (r.width < 2 || r.height < 2) return false;
    const s = getComputedStyle(el);
    return s.visibility !== 'hidden' && s.display !== 'none' && s.opacity !== '0';
  };

  const rotulo = (el) => {
    const attrs = ['aria-label', 'placeholder', 'title', 'name', 'value'];
    for (const a of attrs) {
      const v = el.getAttribute && el.getAttribute(a);
      if (v && v.trim()) return v.trim().slice(0, 60);
    }
    if (el.id) {
      const lab = document.querySelector(`label[for="${CSS.escape(el.id)}"]`);
      if (lab && lab.textContent.trim()) return lab.textContent.trim().slice(0, 60);
    }
    const proprio = (el.innerText || el.textContent || '').trim();
    if (proprio) return proprio.replace(/\\s+/g, ' ').slice(0, 60);
    const pai = el.closest('label');
    if (pai && pai.textContent.trim()) return pai.textContent.trim().slice(0, 60);
    return '';
  };

  const tipo = (el) => {
    const tag = el.tagName.toLowerCase();
    if (tag === 'a') return 'link';
    if (tag === 'select') return 'select';
    if (tag === 'textarea') return 'texto';
    if (tag === 'input') {
      const t = (el.type || 'text').toLowerCase();
      if (['checkbox', 'radio'].includes(t)) return t;
      if (['submit', 'button', 'reset'].includes(t)) return 'botao';
      return t === 'password' ? 'senha' : 'texto';
    }
    return 'botao';
  };

  const seletor = (el) => {
    for (const a of ['data-cy', 'data-testid', 'data-test', 'data-qa']) {
      const v = el.getAttribute(a);
      if (v) return `[${a}="${v.replace(/"/g, '\\\\"')}"]`;
    }
    if (el.id && !/^[0-9]/.test(el.id) && !/[0-9a-f]{8}/i.test(el.id)) {
      return `#${el.id}`;
    }
    const nome = el.getAttribute('name');
    if (nome) return `${el.tagName.toLowerCase()}[name="${nome}"]`;
    const aria = el.getAttribute('aria-label');
    if (aria) return `[aria-label="${aria.replace(/"/g, '\\\\"')}"]`;
    return '';
  };

  // Um `tr` com addEventListener não tem `onclick`, `role` nem `href` — e é
  // exatamente assim que linhas de tabela funcionam na maioria das SPAs. Sem
  // as duas últimas famílias abaixo, o agente não enxerga metade dos alvos de
  // um sistema real e conclui que não há nada a fazer na tela.
  const seletores = [
    'a[href]', 'button', 'input', 'select', 'textarea',
    '[role="button"]', '[role="link"]', '[role="tab"]', '[role="menuitem"]',
    '[role="option"]', '[role="checkbox"]', '[role="switch"]',
    '[onclick]', '[tabindex]:not([tabindex="-1"])',
    '[data-cy]', '[data-testid]', '[data-test]', '[data-qa]',
  ];
  const alvos = [...document.querySelectorAll(seletores.join(','))];

  // Cursor de mão é a pista que sobra quando não há atributo nenhum. Só
  // olhamos os candidatos plausíveis: varrer o documento inteiro pedindo
  // estilo computado trava páginas grandes.
  for (const el of document.querySelectorAll('tr, li, .card, [class*="item"], [class*="row"]')) {
    if (alvos.includes(el)) continue;
    if (getComputedStyle(el).cursor === 'pointer') alvos.push(el);
    if (alvos.length > LIMITE * 4) break;
  }

  const out = [];
  const vistos = new Set();
  for (const el of alvos) {
    if (!visivel(el)) continue;
    const nome = rotulo(el);
    const sel = seletor(el);
    // Sem nome nem seletor, o elemento é indescritível para o modelo: ele não
    // saberia o que está clicando nem como pedir de volta.
    if (!nome && !sel) continue;

    const chave = `${tipo(el)}|${nome}|${sel}`;
    if (vistos.has(chave)) continue;      // linhas repetidas de tabela
    vistos.add(chave);

    out.push({
      tipo: tipo(el),
      nome,
      seletor: sel,
      valor: (el.value || '').toString().slice(0, 40),
      desabilitado: !!el.disabled,
      obrigatorio: !!el.required,
      padrao: el.getAttribute && el.getAttribute('pattern') || '',
      maximo: el.getAttribute && el.getAttribute('maxlength') || '',
    });
    if (out.length >= LIMITE) break;
  }

  // Mensagens de erro e avisos: é assim que o agente descobre que o valor que
  // ele inventou não serviu, em vez de repetir o mesmo erro para sempre.
  const avisos = [...document.querySelectorAll(
    '[role="alert"], .error, .invalid-feedback, .is-invalid, .q-field__messages,'
    + ' .Mui-error, .ant-form-item-explain-error, .text-danger, .erro')]
    .filter(visivel)
    .map((el) => (el.innerText || '').trim().replace(/\\s+/g, ' ').slice(0, 120))
    .filter(Boolean)
    .slice(0, 6);

  return {
    url: location.href,
    titulo: document.title,
    cabecalho: (document.querySelector('h1, h2, [role="heading"]') || {}).innerText || '',
    elementos: out,
    avisos,
  };
}"""


async def observe(page: Any) -> dict[str, Any]:
    """Estado atual da página, no formato que o planejador consome."""
    script = SCAN.replace("LIMITE", str(MAX_ELEMENTOS))
    try:
        estado = await page.evaluate(script)
    except Exception as exc:
        return {"url": "", "titulo": "", "elementos": [], "avisos": [],
                "erro": f"{type(exc).__name__}: {exc}"}

    estado["cabecalho"] = (estado.get("cabecalho") or "").strip()[:80]
    return estado


def fingerprint(estado: dict[str, Any]) -> str:
    """Assinatura da tela, para reconhecer que já estivemos aqui.

    Não usa a URL sozinha: `/clientes/1` e `/clientes/2` são a mesma tela com
    dados diferentes, e tratá-las como estados distintos faz o agente achar que
    descobriu trezentas páginas ao percorrer uma listagem. Também não usa o DOM
    inteiro, que muda a cada render. O meio-termo é o conjunto de controles —
    o que dá para *fazer* ali é o que define a tela.
    """
    import hashlib
    import re

    url = re.sub(r"/\d+", "/:id", (estado.get("url") or "").split("?")[0])
    controles = sorted(
        f"{e['tipo']}:{e['nome'] or e['seletor']}"
        for e in estado.get("elementos", [])
    )
    bruto = url + "|" + "|".join(controles)
    return hashlib.sha1(bruto.encode("utf-8")).hexdigest()[:12]


def describe(estado: dict[str, Any]) -> str:
    """A tela em texto, para entrar no prompt."""
    linhas = [
        f"URL: {estado.get('url', '')}",
        f"Título: {estado.get('titulo', '')}",
    ]
    if estado.get("cabecalho"):
        linhas.append(f"Cabeçalho: {estado['cabecalho']}")
    if estado.get("avisos"):
        linhas.append("Mensagens na tela: " + " | ".join(estado["avisos"]))

    linhas.append("")
    linhas.append("Elementos disponíveis (use o índice para agir):")
    for i, el in enumerate(estado.get("elementos", [])):
        partes = [f"  [{i}] {el['tipo']}", f"“{el['nome']}”" if el["nome"] else ""]
        if el.get("valor"):
            partes.append(f"(valor atual: {el['valor']})")
        if el.get("obrigatorio"):
            partes.append("(obrigatório)")
        if el.get("desabilitado"):
            partes.append("(desabilitado)")
        if el.get("padrao"):
            partes.append(f"(formato: {el['padrao']})")
        linhas.append(" ".join(p for p in partes if p))

    return "\n".join(linhas)
