"""
Compilador de intenção: eventos brutos → passos semânticos.

O gravador captura tudo que acontece. A maior parte disso não é intenção do
usuário — é ruído da implementação. Quando alguém clica em "Entrar" num app
Quasar, o navegador registra um clique no `.q-focus-helper` (a camada de ripple),
outro no `<span>` interno e outro no `<button>` real. O Cygen v2 gravava os três
e gerava três `cy.get(...).click()`, dos quais dois falham em qualquer deploy.

Este módulo resolve isso em quatro passagens:

    1. Retarget  — sobe/desce na árvore até o elemento que carrega a intenção
    2. Colapso   — funde eventos que descrevem um único ato do usuário
    3. Segmentação — agrupa passos em blocos com significado (login, formulário)
    4. Enriquecimento — anexa evidência (rede, mutações) a cada passo

O que sai daqui já é a história que o teste deve contar.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from .selectors import is_framework_class, looks_generated

# Elementos que carregam intenção por si sós.
_SEMANTIC_TAGS = {"button", "a", "input", "select", "textarea", "label",
                  "summary", "option"}
_SEMANTIC_ROLES = {"button", "link", "checkbox", "radio", "tab", "menuitem",
                   "option", "switch", "textbox", "combobox", "searchbox"}

# Wrappers puramente visuais que nunca devem virar alvo de um passo.
_GHOST_CLASS_HINTS = ("focus-helper", "ripple", "overlay", "backdrop", "touch",
                      "highlight", "shadow", "blur")

# Palavras que sinalizam envio de formulário.
_SUBMIT_HINTS = ("entrar", "login", "acessar", "salvar", "enviar", "confirmar",
                 "cadastrar", "criar", "buscar", "pesquisar", "submit", "save",
                 "continuar", "avançar", "finalizar", "aplicar")


@dataclass
class Step:
    """Um passo semântico do fluxo — a unidade que vira uma linha de teste."""

    index: int
    kind: str                                   # visit | click | type | select | ...
    element: dict[str, Any] = field(default_factory=dict)
    value: Any = None
    label: str = ""                             # descrição legível em português
    url: str = ""
    evidence: dict[str, Any] = field(default_factory=dict)
    assertions: list[dict[str, Any]] = field(default_factory=list)
    selector: dict[str, Any] | None = None
    # Seletor fixado pelo usuário para este passo: `{"value", "engine",
    # "source"}`. Vive fora de `selector` porque `selector` é recalculado a
    # cada geração — guardar a escolha lá dentro a apagaria no primeiro
    # "Gerar código" seguinte.
    selector_override: dict[str, Any] | None = None
    group: str = ""                             # nome do bloco semântico
    notes: list[str] = field(default_factory=list)
    source_events: list[int] = field(default_factory=list)
    enabled: bool = True
    # Detalhes da ação além do valor: `valueAfter` (o que o campo guardou, que
    # difere do digitado quando há máscara), `checkedAfter`, `selectedText`.
    # Sem isto o Oracle não consegue detectar máscara nem estado de toggle.
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index, "kind": self.kind, "element": self.element,
            "value": self.value, "label": self.label, "url": self.url,
            "evidence": self.evidence, "assertions": self.assertions,
            "selector": self.selector, "selectorOverride": self.selector_override,
            "group": self.group, "notes": self.notes,
            "sourceEvents": self.source_events, "enabled": self.enabled,
            "meta": self.meta,
        }


# ---------------------------------------------------------------------------
# Passagem 1 — retarget
# ---------------------------------------------------------------------------

def is_ghost_element(el: dict[str, Any]) -> bool:
    """True para elementos que existem só para efeito visual.

    Estes são a causa raiz dos seletores inúteis nos testes da v2.
    """
    classes = [c.lower() for c in (el.get("classList") or [])]
    if any(hint in c for c in classes for hint in _GHOST_CLASS_HINTS):
        return True
    tag = (el.get("tag") or "").lower()
    text = (el.get("text") or "").strip()
    role = (el.get("attributes") or {}).get("role", "")
    # Div/span sem texto, sem papel e sem atributo de teste não tem identidade.
    if tag in ("div", "span", "i") and not text and not role:
        attrs = el.get("attributes") or {}
        has_hook = any(k.startswith("data-") for k in attrs)
        if not has_hook:
            return True
    return False


def _carries_intent(candidate: dict[str, Any]) -> bool:
    """O elemento representa uma ação de verdade?"""
    tag = (candidate.get("tag") or "").lower()
    attrs = candidate.get("attributes") or {}
    role = (attrs.get("role") or "").lower()
    if any(k in attrs for k in ("data-cy", "data-testid", "data-test", "data-qa")):
        return True
    return tag in _SEMANTIC_TAGS or role in _SEMANTIC_ROLES


def retarget(
    el: dict[str, Any],
    ancestors: list[dict[str, Any]],
    beneath: list[dict[str, Any]] | None = None,
) -> tuple[dict[str, Any], str | None]:
    """Encontra o elemento que representa a intenção por trás do clique.

    Duas buscas, porque frameworks escondem o controle de duas formas:

      ancestrais — o ripple é filho do botão (Quasar, Material)
      por baixo  — o overlay é irmão do botão, empilhado por cima (CSS absoluto)

    A segunda depende de `elementsFromPoint`, coletado no navegador no momento
    do clique: quando o alvo real está *atrás* e não *acima*, subir pela árvore
    nunca chega nele.

    Devolve (elemento_escolhido, nota_explicativa).
    """
    if not is_ghost_element(el):
        return el, None

    original = _describe(el)

    for ancestor in ancestors:
        if _carries_intent(ancestor):
            tag = (ancestor.get("tag") or "elemento").lower()
            return ancestor, (
                f"Clique original caiu em `{original}`, um elemento decorativo do "
                f"framework. O Cygen redirecionou para o `<{tag}>` que realmente "
                f"carrega a ação — é isso que impede o teste de quebrar."
            )

    for under in (beneath or []):
        if _carries_intent(under):
            tag = (under.get("tag") or "elemento").lower()
            return under, (
                f"Clique original caiu em `{original}`, uma camada sobreposta sem "
                f"função própria. O Cygen olhou o que estava sob o cursor e achou "
                f"o `<{tag}>` que recebe a ação de fato."
            )

    return el, (
        "Este elemento não tem identidade semântica. O seletor gerado será frágil; "
        "considere pedir um `data-cy` ao time."
    )


def _describe(el: dict[str, Any]) -> str:
    tag = (el.get("tag") or "?").lower()
    classes = el.get("classList") or []
    if classes:
        return f"{tag}.{classes[0]}"
    return tag


# ---------------------------------------------------------------------------
# Passagem 2 — colapso de eventos
# ---------------------------------------------------------------------------

def collapse(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Funde sequências de eventos que representam um único ato do usuário."""
    out: list[dict[str, Any]] = []

    for pos, ev in enumerate(events):
        kind = (ev.get("type") or "").lower()

        # a) Digitação: o gravador emite um evento por tecla. Um `cy.type()`
        #    com a frase inteira é o equivalente correto.
        if kind == "type" and out:
            prev = out[-1]
            if (prev.get("type") == "type"
                    and _same_element(prev, ev)
                    and _gap_ms(prev, ev) < 3000):
                prev["value"] = ev.get("value")
                prev["valueAfter"] = ev.get("valueAfter", ev.get("value"))
                prev["_events"] = prev.get("_events", []) + [ev.get("seq")]
                prev["timestamp"] = ev.get("timestamp", prev.get("timestamp"))
                continue

        # b) Clique duplicado no mesmo alvo em menos de 250ms: é ripple/bubbling,
        #    não um duplo-clique intencional (que o gravador marca como dblclick).
        if kind == "click" and out:
            prev = out[-1]
            if (prev.get("type") == "click"
                    and _same_element(prev, ev)
                    and _gap_ms(prev, ev) < 250):
                prev["_events"] = prev.get("_events", []) + [ev.get("seq")]
                continue

        # c) Clique num campo imediatamente seguido de digitação nele: o
        #    `cy.type()` já faz o foco. O clique é redundante.
        if kind == "click":
            nxt = _next_meaningful(events, pos)
            if (nxt and nxt.get("type") == "type"
                    and _same_element(ev, nxt)
                    and _gap_ms(ev, nxt) < 2500):
                continue

        # d) Foco/blur puros não descrevem intenção testável.
        if kind in ("focus", "blur"):
            continue

        # d2) Navegação disparada por uma ação anterior. O clique que a causou
        #     já registra `urlBefore`/`urlAfter`, e o Oracle já deduz a
        #     assertion de rota a partir dele. Mantê-la separada produziria um
        #     passo órfão sem elemento e uma assertion duplicada.
        if kind == "navigation" and out:
            prev = out[-1]
            caused_by_action = (
                prev.get("type") in ("click", "dblclick", "keypress", "select")
                and _gap_ms(prev, ev) < 2000
            )
            if caused_by_action:
                prev["urlAfter"] = ev.get("urlAfter") or prev.get("urlAfter")
                continue

        # e) Scroll sem consequência: só mantemos se algo entrou em cena depois.
        if kind == "scroll" and not (ev.get("mutations") or {}).get("added"):
            continue

        out.append(dict(ev))

    return out


def _same_element(a: dict[str, Any], b: dict[str, Any]) -> bool:
    """Dois eventos apontam para o mesmo elemento?

    A comparação desce por ordem de confiabilidade. O nodeId é definitivo, mas
    some quando o retarget troca o alvo por um ancestral; nesse caso um atributo
    de teste identifica o elemento igualmente bem.
    """
    ea, eb = a.get("element") or {}, b.get("element") or {}
    if not ea or not eb:
        return False

    if ea.get("nodeId") and ea.get("nodeId") == eb.get("nodeId"):
        return True

    # Atributos de identidade: se ambos declaram o mesmo, é o mesmo elemento.
    attrs_a = ea.get("attributes") or {}
    attrs_b = eb.get("attributes") or {}
    for key in ("data-cy", "data-testid", "data-test", "data-qa", "name", "id"):
        va, vb = attrs_a.get(key), attrs_b.get(key)
        if va and vb:
            return va == vb

    if ea.get("xpath") and ea.get("xpath") == eb.get("xpath"):
        return True

    return False


def _gap_ms(a: dict[str, Any], b: dict[str, Any]) -> float:
    return abs(float(b.get("timestamp", 0)) - float(a.get("timestamp", 0)))


def _next_meaningful(events: list[dict[str, Any]], pos: int) -> dict[str, Any] | None:
    """Próximo evento que representa intenção, ignorando foco/blur/scroll."""
    for nxt in events[pos + 1:]:
        if (nxt.get("type") or "").lower() not in ("focus", "blur", "scroll"):
            return nxt
    return None


# ---------------------------------------------------------------------------
# Passagem 3 — segmentação em blocos
# ---------------------------------------------------------------------------

def segment(steps: list[Step]) -> list[Step]:
    """Atribui um nome de bloco a cada passo (login, formulário, navegação...).

    Os blocos viram comentários e, opcionalmente, `it()` separados no código —
    é o que faz o teste gerado parecer escrito por uma pessoa.
    """
    if not steps:
        return steps

    # Detecção de login: campo de senha + um envio logo depois.
    password_idx = next(
        (s.index for s in steps
         if s.kind == "type"
         and (s.element.get("attributes") or {}).get("type") == "password"),
        None,
    )
    if password_idx is not None:
        for step in steps:
            if step.index <= password_idx + 1:
                step.group = "Autenticação"

    current = ""
    for step in steps:
        if step.group:
            current = step.group
            continue

        if step.kind == "visit":
            current = "Navegação"
        elif step.kind == "type":
            current = current if current == "Preenchimento" else "Preenchimento"
        elif step.kind == "select":
            current = "Preenchimento"
        elif step.kind == "click":
            text = (step.element.get("text") or "").strip().lower()
            if any(hint in text for hint in _SUBMIT_HINTS):
                current = "Envio"
            elif step.evidence.get("urlChanged"):
                current = "Navegação"
            elif current not in ("Preenchimento", "Envio"):
                current = "Interação"
        step.group = current or "Fluxo"

    return steps


def detect_repeats(steps: list[Step]) -> list[dict[str, Any]]:
    """Encontra sequências repetidas — candidatas a virar comando customizado.

    Se o usuário faz login em três fluxos diferentes, aquilo deveria ser
    `cy.login()` em `support/commands.js`, não 6 linhas duplicadas.
    """
    signatures = [f"{s.kind}:{_signature(s.element)}" for s in steps]
    suggestions: list[dict[str, Any]] = []
    n = len(signatures)

    for size in range(3, min(9, n // 2 + 1)):
        for start in range(n - size * 2 + 1):
            block = signatures[start:start + size]
            rest = signatures[start + size:]
            for offset in range(len(rest) - size + 1):
                if rest[offset:offset + size] == block:
                    suggestions.append({
                        "size": size,
                        "firstAt": start,
                        "secondAt": start + size + offset,
                        "steps": [steps[i].label for i in range(start, start + size)],
                        "suggestion": (
                            f"Esta sequência de {size} passos se repete no fluxo. "
                            f"Extraia para um comando customizado em "
                            f"`cypress/support/commands.js` e chame duas vezes."
                        ),
                    })
                    break
            if suggestions:
                break
        if suggestions:
            break
    return suggestions


def _signature(el: dict[str, Any]) -> str:
    attrs = el.get("attributes") or {}
    for key in ("data-cy", "data-testid", "name", "id"):
        if attrs.get(key):
            return f"{key}={attrs[key]}"
    return f"{el.get('tag')}:{(el.get('text') or '')[:20]}"


# ---------------------------------------------------------------------------
# Rotulagem em português
# ---------------------------------------------------------------------------

def _em(name: str) -> str:
    """Contrai a preposição `em` com o artigo do nome.

    Sem isto a timeline diz "Clica em o botão". A contração só se aplica quando
    o nome começa por artigo — nomes entre aspas ficam como estão.
    """
    for article, contracted in (("o ", "no "), ("a ", "na "),
                                ("os ", "nos "), ("as ", "nas ")):
        if name.startswith(article):
            return contracted + name[len(article):]
    return f"em {name}"


def label_for(kind: str, el: dict[str, Any], value: Any = None, url: str = "") -> str:
    """Frase legível para o passo — é o que aparece na timeline da UI."""
    name = human_name(el)

    if kind == "visit":
        return f"Abre {_pretty_url(url)}"
    if kind == "navigation":
        # Navegação que sobreviveu ao colapso: veio do usuário (voltar, digitar
        # a URL) e não de um clique já registrado.
        return f"Navega para {_pretty_url(url)}"
    if kind == "click":
        return f"Clica {_em(name)}"
    if kind == "dblclick":
        return f"Clica duas vezes {_em(name)}"
    if kind == "type":
        attrs = el.get("attributes") or {}
        if (attrs.get("type") or "").lower() == "password":
            return f"Digita a senha {_em(name)}"
        shown = str(value or "")
        if len(shown) > 24:
            shown = shown[:21] + "…"
        return f"Preenche {name} com “{shown}”"
    if kind == "select":
        return f"Escolhe “{value}” {_em(name)}"
    if kind == "check":
        return f"Marca {name}"
    if kind == "uncheck":
        return f"Desmarca {name}"
    if kind == "hover":
        return f"Passa o mouse sobre {name}"
    if kind == "upload":
        return f"Envia arquivo {_em(name)}"
    if kind == "keypress":
        return f"Pressiona {value} {_em(name)}"
    if kind == "scroll":
        return "Rola a página"
    if kind == "assert":
        return f"Verifica {name}"
    return f"{kind} {_em(name)}"


def human_name(el: dict[str, Any]) -> str:
    """Melhor nome humano disponível para um elemento."""
    attrs = el.get("attributes") or {}
    text = (el.get("text") or "").strip()

    for source in (text, attrs.get("aria-label"), attrs.get("placeholder"),
                   attrs.get("title"), attrs.get("alt"), attrs.get("name")):
        if source and not looks_generated(str(source)):
            clean = " ".join(str(source).split())
            if 0 < len(clean) <= 40:
                return f"“{clean}”"

    tag = (el.get("tag") or "elemento").lower()
    role = (attrs.get("role") or "").lower()
    pretty = {
        "button": "o botão", "a": "o link", "input": "o campo",
        "select": "a lista", "textarea": "a área de texto", "img": "a imagem",
        "label": "o rótulo", "table": "a tabela",
    }.get(role or tag, f"o elemento <{tag}>")

    classes = [c for c in (el.get("classList") or [])
               if not is_framework_class(c) and not looks_generated(c)]
    if classes:
        return f"{pretty} `.{classes[0]}`"
    return pretty


def _pretty_url(url: str) -> str:
    clean = re.sub(r"^https?://", "", url or "")
    return clean[:60] + ("…" if len(clean) > 60 else "")


# ---------------------------------------------------------------------------
# Pipeline completo
# ---------------------------------------------------------------------------

def compile_steps(events: list[dict[str, Any]]) -> tuple[list[Step], list[dict[str, Any]]]:
    """Executa as quatro passagens. Devolve (passos, sugestões de refatoração)."""
    # Ordem causal, não ordem de chegada. Um evento só é emitido depois da sua
    # janela de estabilização, então um clique lento chega DEPOIS da navegação
    # que ele próprio causou. Ordenar pelo instante em que a ação começou
    # devolve a sequência real — sem isso, o colapso compara cada evento com o
    # vizinho errado.
    events = sorted(events, key=lambda e: float(e.get("timestamp") or 0))

    # O retarget precisa vir ANTES do colapso: enquanto o clique ainda aponta
    # para o `.q-focus-helper`, ele parece um elemento diferente do input que
    # recebe a digitação logo depois, e a regra de redundância não dispara.
    retargeted: list[dict[str, Any]] = []
    for ev in events:
        ev = dict(ev)
        if (ev.get("type") or "").lower() in ("click", "dblclick"):
            el, note = retarget(
                ev.get("element") or {},
                ev.get("ancestors") or [],
                ev.get("beneath") or [],
            )
            ev["element"] = el
            if note:
                ev["_note"] = note
        retargeted.append(ev)

    collapsed = collapse(retargeted)
    steps: list[Step] = []

    for i, ev in enumerate(collapsed):
        el = ev.get("element") or {}
        notes: list[str] = [ev["_note"]] if ev.get("_note") else []
        kind = (ev.get("type") or "unknown").lower()
        value = ev.get("value")
        url = ev.get("url") or ""

        steps.append(Step(
            index=i,
            kind=kind,
            element=el,
            value=value,
            url=url,
            label=label_for(kind, el, value, url),
            evidence={
                "urlBefore": ev.get("urlBefore", ""),
                "urlAfter": ev.get("urlAfter", ""),
                "urlChanged": bool(ev.get("urlAfter")) and ev.get("urlAfter") != ev.get("urlBefore"),
                "titleBefore": ev.get("titleBefore", ""),
                "titleAfter": ev.get("titleAfter", ""),
                "mutations": ev.get("mutations") or {},
                "network": ev.get("network") or [],
                "storageDelta": ev.get("storageDelta") or {},
                "consoleErrors": ev.get("consoleErrors") or [],
                "durationMs": ev.get("durationMs", 0),
            },
            notes=notes,
            source_events=ev.get("_events") or ([ev.get("seq")] if ev.get("seq") is not None else []),
            meta={
                key: ev[key] for key in
                ("valueAfter", "checkedAfter", "checked", "selectedText", "secret")
                if key in ev
            },
        ))

    steps = segment(steps)
    return steps, detect_repeats(steps)
