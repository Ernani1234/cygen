"""
Oracle — motor de inferência de assertions de custo zero.

Nenhuma chamada de API, nenhum token, nenhuma latência de rede. O Oracle olha
para o que *de fato aconteceu* na página quando o usuário agiu e deduz, por
regras explícitas, quais assertions do Cypress descrevem aquele acontecimento.

A intuição central é que um LLM não é necessário aqui. Quando o usuário clica
em "Entrar" e, logo depois, o `POST /api/login` retorna 200, o `localStorage`
ganha uma chave `token` e a URL vira `#/dashboard`, não há ambiguidade a
resolver: essas três coisas *são* o critério de aceite. O trabalho é observar
com precisão e traduzir sem inventar.

Cada regra declara:
    when()    -> a evidência dispara esta regra?
    emit()    -> quais assertions ela produz
    why       -> explicação em português exibida na UI

Toda assertion emitida carrega sua justificativa. O usuário sempre vê *por que*
o Cygen sugeriu aquilo, e pode recusar item a item.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable
from urllib.parse import urlparse

from . import catalog

# ---------------------------------------------------------------------------
# Análise de volatilidade de valores
# ---------------------------------------------------------------------------
# Um valor volátil não pode ser afirmado com igualdade exata. Afirmar
# `should('have.text', '23/05/2025 14:31')` garante que o teste passa hoje e
# falha amanhã. Detectamos essas formas e rebaixamos a assertion para um
# formato — `match(/\d{2}\/\d{2}\/\d{4}/)` — que continua verdadeiro sempre.

_VOLATILE_PATTERNS: list[tuple[str, re.Pattern[str], str]] = [
    ("uuid", re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I),
     r"/^[0-9a-f-]{36}$/i"),
    ("iso_datetime", re.compile(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}"),
     r"/^\d{4}-\d{2}-\d{2}/"),
    ("date_br", re.compile(r"^\d{2}/\d{2}/\d{4}$"), r"/^\d{2}\/\d{2}\/\d{4}$/"),
    ("datetime_br", re.compile(r"^\d{2}/\d{2}/\d{4}[\s,]+\d{2}:\d{2}"),
     r"/^\d{2}\/\d{2}\/\d{4}/"),
    ("time", re.compile(r"^\d{1,2}:\d{2}(:\d{2})?$"), r"/^\d{1,2}:\d{2}/"),
    ("currency_brl", re.compile(r"^R\$\s?[\d.,]+$"), r"/^R\$\s?[\d.,]+$/"),
    ("currency_usd", re.compile(r"^\$\s?[\d.,]+$"), r"/^\$\s?[\d.,]+$/"),
    ("percent", re.compile(r"^[\d.,]+\s?%$"), r"/^[\d.,]+\s?%$/"),
    ("long_number", re.compile(r"^\d{7,}$"), r"/^\d+$/"),
    ("token", re.compile(r"^[A-Za-z0-9_-]{24,}$"), r"/^[\w-]{24,}$/"),
    ("relative_time", re.compile(r"^(há|em)\s+\d+\s+\w+|^\d+\s+(minutos?|horas?|dias?)\s+atrás", re.I),
     r"/\d+/"),
]

# Formatos de dado reconhecíveis pelo *conteúdo digitado*. Servem para o Oracle
# entender a semântica do campo mesmo sem `type=email` no HTML.
_VALUE_SHAPES: list[tuple[str, re.Pattern[str], str]] = [
    ("email", re.compile(r"^[^@\s]+@[^@\s]+\.[a-z]{2,}$", re.I), "e-mail"),
    ("cpf", re.compile(r"^\d{3}\.?\d{3}\.?\d{3}-?\d{2}$"), "CPF"),
    ("cnpj", re.compile(r"^\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}$"), "CNPJ"),
    ("phone_br", re.compile(r"^\(?\d{2}\)?\s?9?\d{4}-?\d{4}$"), "telefone"),
    ("cep", re.compile(r"^\d{5}-?\d{3}$"), "CEP"),
    ("url", re.compile(r"^https?://", re.I), "URL"),
    ("number", re.compile(r"^-?[\d.,]+$"), "número"),
]

# Palavras que denunciam um campo de credencial. Nunca gravamos o valor.
_SECRET_HINTS = ("senha", "password", "passwd", "pwd", "secret", "token",
                 "pin", "cvv", "cartao", "card")

# Classes/atributos que sinalizam feedback ao usuário.
_ERROR_HINTS = ("error", "erro", "invalid", "invalido", "danger", "alert-danger",
                "is-invalid", "has-error", "field-error", "helper-text")
_SUCCESS_HINTS = ("success", "sucesso", "ok", "valid", "alert-success", "toast-success")
_LOADING_HINTS = ("loading", "carregando", "spinner", "skeleton", "shimmer",
                  "progress", "placeholder-glow", "q-loading")


def classify_volatility(value: str) -> tuple[str | None, str | None]:
    """Retorna (nome_do_padrão, regex_js) se o valor for volátil."""
    v = (value or "").strip()
    if not v:
        return None, None
    for label, pattern, js_regex in _VOLATILE_PATTERNS:
        if pattern.match(v):
            return label, js_regex
    return None, None


def classify_shape(value: str) -> tuple[str | None, str | None]:
    """Retorna (id_do_formato, rótulo_pt) do conteúdo, se reconhecido."""
    v = (value or "").strip()
    if not v:
        return None, None
    for shape_id, pattern, label in _VALUE_SHAPES:
        if pattern.match(v):
            return shape_id, label
    return None, None


def is_secret_field(el: dict[str, Any]) -> bool:
    """True se o campo carrega credencial — o valor não deve ir para o código."""
    attrs = el.get("attributes") or {}
    if (attrs.get("type") or "").lower() == "password":
        return True
    haystack = " ".join(str(x).lower() for x in (
        attrs.get("name", ""), attrs.get("id", ""), attrs.get("aria-label", ""),
        attrs.get("placeholder", ""), attrs.get("autocomplete", ""),
        " ".join(el.get("classList") or []),
    ))
    return any(hint in haystack for hint in _SECRET_HINTS)


def _js_string(value: str) -> str:
    """Serializa uma string Python como literal JS entre aspas simples."""
    return "'" + (value or "").replace("\\", "\\\\").replace("'", "\\'").replace("\n", "\\n") + "'"


# ---------------------------------------------------------------------------
# Estruturas
# ---------------------------------------------------------------------------

@dataclass
class Assertion:
    """Uma assertion inferida, pronta para virar código."""

    name: str                    # nome canônico no catálogo
    target: str                  # "self" | seletor | "url" | "@alias" | ...
    args: list[Any] = field(default_factory=list)
    confidence: float = 0.5
    why: str = ""
    rule: str = ""
    category: str = ""
    raw: str | None = None       # código pronto, quando não é um `.should()` simples
    phase: str = "after"         # before | after — antes ou depois da ação

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name, "target": self.target, "args": self.args,
            "confidence": round(self.confidence, 3), "why": self.why,
            "rule": self.rule, "category": self.category, "raw": self.raw,
            "phase": self.phase,
        }


@dataclass
class Evidence:
    """Tudo que o gravador observou em torno de uma ação.

    É o insumo do Oracle. Quanto mais rica, mais precisa a inferência — por isso
    o `injector.js` faz um diff de DOM antes/depois de cada ação em vez de
    apenas registrar o clique.
    """

    action: dict[str, Any]                              # a ação em si
    element: dict[str, Any] = field(default_factory=dict)
    url_before: str = ""
    url_after: str = ""
    title_before: str = ""
    title_after: str = ""
    mutations: dict[str, Any] = field(default_factory=dict)   # diff do DOM
    network: list[dict[str, Any]] = field(default_factory=list)
    storage_delta: dict[str, Any] = field(default_factory=dict)
    console_errors: list[str] = field(default_factory=list)
    duration_ms: int = 0

    # -- atalhos de leitura -------------------------------------------------

    @property
    def kind(self) -> str:
        return (self.action.get("type") or "").lower()

    @property
    def tag(self) -> str:
        return (self.element.get("tag") or "").lower()

    @property
    def attrs(self) -> dict[str, str]:
        return self.element.get("attributes") or {}

    @property
    def role(self) -> str:
        return (self.attrs.get("role") or "").lower()

    @property
    def classes(self) -> list[str]:
        return self.element.get("classList") or []

    def url_changed(self) -> bool:
        return bool(self.url_after) and self.url_after != self.url_before

    def added_nodes(self) -> list[dict[str, Any]]:
        return self.mutations.get("added") or []

    def removed_nodes(self) -> list[dict[str, Any]]:
        return self.mutations.get("removed") or []

    def text_changes(self) -> list[dict[str, Any]]:
        return self.mutations.get("textChanged") or []

    def attr_changes(self) -> list[dict[str, Any]]:
        return self.mutations.get("attrChanged") or []


# ---------------------------------------------------------------------------
# Regras
# ---------------------------------------------------------------------------

Rule = Callable[[Evidence], Iterable[Assertion]]
_RULES: list[tuple[str, str, Rule]] = []


def rule(rule_id: str, title: str):
    """Registra uma regra de inferência no motor."""
    def wrap(fn: Rule) -> Rule:
        _RULES.append((rule_id, title, fn))
        return fn
    return wrap


# --- Fase 1: pré-condições -------------------------------------------------
# Antes de agir sobre um elemento, o teste deve provar que o elemento estava
# em condição de receber a ação. Sem isso, uma falha de renderização vira um
# erro críptico de "elemento não encontrado" em vez de uma assertion clara.

@rule("pre.visible", "Elemento visível antes da interação")
def _pre_visible(ev: Evidence) -> Iterable[Assertion]:
    if ev.kind not in ("click", "dblclick", "type", "select", "check", "upload", "hover"):
        return
    yield Assertion(
        name="be.visible", target="self", confidence=0.95, phase="before",
        rule="pre.visible", category="Visibilidade",
        why="O usuário só conseguiu interagir porque o elemento estava visível. "
            "Afirmar isso transforma uma falha de renderização num erro legível.",
    )


@rule("pre.enabled", "Controle habilitado antes da interação")
def _pre_enabled(ev: Evidence) -> Iterable[Assertion]:
    if ev.kind not in ("click", "type", "select", "check"):
        return
    interactive = ev.tag in ("button", "input", "select", "textarea", "a") or \
        ev.role in ("button", "link", "textbox", "combobox", "checkbox")
    if not interactive:
        return
    # Se o elemento estava desabilitado no momento do clique, algo está errado
    # com a gravação — não afirmamos o contrário do observado.
    if ev.attrs.get("disabled") is not None:
        return
    yield Assertion(
        name="not.be.disabled", target="self", confidence=0.82, phase="before",
        rule="pre.enabled", category="Estado",
        why="Controle interativo aceitou a ação, logo não estava desabilitado. "
            "Protege contra regressões que travam o botão.",
    )


@rule("pre.field.type", "Tipo do campo de entrada")
def _pre_field_type(ev: Evidence) -> Iterable[Assertion]:
    if ev.kind != "type" or ev.tag != "input":
        return
    field_type = (ev.attrs.get("type") or "").lower()
    if field_type in ("password", "email", "tel", "number", "date", "url"):
        yield Assertion(
            name="have.attr", target="self", args=["type", field_type],
            confidence=0.7, phase="before", rule="pre.field.type",
            category="Atributos e Classes",
            why=f"Campo declarado como `{field_type}`. Se virar texto puro, "
                f"a validação nativa do navegador some silenciosamente.",
        )


# --- Fase 2: efeito sobre o valor do próprio campo -------------------------

@rule("post.value", "Valor efetivamente aceito pelo campo")
def _post_value(ev: Evidence) -> Iterable[Assertion]:
    if ev.kind != "type":
        return
    typed = ev.action.get("value") or ""
    settled = ev.action.get("valueAfter", typed) or ""

    if is_secret_field(ev.element):
        # Regra de segurança: credencial nunca vira literal no código. O
        # emissor troca por Cypress.env(), e a assertion afirma o formato.
        yield Assertion(
            name="not.have.value", target="self", args=[""],
            confidence=0.75, rule="post.value.secret", category="Texto e Valor",
            why="Campo de credencial: o Cygen afirma que ficou preenchido, mas "
                "nunca escreve a senha no arquivo de teste.",
        )
        return

    if not settled:
        return

    # Máscara detectada: o campo transformou o que foi digitado.
    if settled != typed:
        yield Assertion(
            name="have.value", target="self", args=[settled],
            confidence=0.9, rule="post.value.masked", category="Texto e Valor",
            why=f"O campo tem máscara: você digitou `{typed}` e o DOM guardou "
                f"`{settled}`. Afirmar o valor final é o que impede o teste de "
                f"falhar por um formato que na verdade está correto.",
        )
        return

    volatile, js_regex = classify_volatility(settled)
    if volatile:
        yield Assertion(
            name="match", target="self", args=[{"regex": js_regex}],
            confidence=0.72, rule="post.value.volatile", category="Comparações",
            why=f"Valor do tipo `{volatile}` muda entre execuções. O Cygen "
                f"afirma o formato em vez do conteúdo — assim o teste continua "
                f"válido amanhã.",
        )
        return

    shape, label = classify_shape(settled)
    yield Assertion(
        name="have.value", target="self", args=[settled], confidence=0.88,
        rule="post.value", category="Texto e Valor",
        why=(f"O campo recebeu um {label} e o reteve." if label
             else "O valor digitado foi aceito e permaneceu no campo."),
    )


@rule("post.checked", "Estado de marcação após o clique")
def _post_checked(ev: Evidence) -> Iterable[Assertion]:
    input_type = (ev.attrs.get("type") or "").lower()
    is_toggle = input_type in ("checkbox", "radio") or ev.role in ("checkbox", "switch", "radio")
    if not is_toggle or ev.kind not in ("click", "check"):
        return
    checked = ev.action.get("checkedAfter")
    if checked is None:
        checked = ev.action.get("checked")
    if checked is None:
        return
    if ev.role in ("switch", "checkbox") and ev.tag != "input":
        # Toggle customizado (div com role): o estado vive em aria-checked.
        yield Assertion(
            name="have.attr", target="self",
            args=["aria-checked", "true" if checked else "false"],
            confidence=0.85, rule="post.checked.aria", category="Acessibilidade",
            why="Toggle customizado expõe o estado em `aria-checked` — é o "
                "único lugar onde ele é observável.",
        )
    else:
        yield Assertion(
            name="be.checked" if checked else "not.be.checked", target="self",
            confidence=0.92, rule="post.checked", category="Estado",
            why=f"O clique deixou o controle {'marcado' if checked else 'desmarcado'}. "
                f"É o efeito observável da ação.",
        )


@rule("post.select", "Opção escolhida em um select")
def _post_select(ev: Evidence) -> Iterable[Assertion]:
    if ev.kind != "select":
        return
    value = ev.action.get("value")
    text = ev.action.get("selectedText")
    if value:
        yield Assertion(
            name="have.value", target="self", args=[value], confidence=0.9,
            rule="post.select", category="Texto e Valor",
            why="A opção escolhida define o valor do select — é o resultado direto da ação.",
        )
    if text and text != value:
        yield Assertion(
            name="contain.text", target="self", args=[text], confidence=0.7,
            rule="post.select.text", category="Texto e Valor",
            why="O rótulo visível confirma a escolha do ponto de vista do usuário.",
        )


# --- Fase 3: navegação -----------------------------------------------------

@rule("post.url", "Mudança de rota")
def _post_url(ev: Evidence) -> Iterable[Assertion]:
    if not ev.url_changed():
        return
    before = urlparse(ev.url_before)
    after = urlparse(ev.url_after)

    # Rotas SPA com hash (padrão em Vue/Angular legado, como o SGPMMS).
    if after.fragment and after.fragment != before.fragment:
        frag = "#" + after.fragment
        volatile, js_regex = classify_volatility(after.fragment.rsplit("/", 1)[-1])
        if volatile:
            yield Assertion(
                name="url.match", target="url", args=[{"regex": js_regex}],
                confidence=0.72, rule="post.url.hash.volatile", category="URL e Navegação",
                why=f"A rota termina num identificador `{volatile}`, que muda a cada "
                    f"execução. Afirmamos o padrão da rota, não o id.",
            )
        else:
            yield Assertion(
                name="location.hash", target="url", args=[frag], confidence=0.9,
                rule="post.url.hash", category="URL e Navegação",
                why="A ação navegou para outra rota da SPA. O hash é a prova de "
                    "que a navegação aconteceu de verdade.",
            )
        return

    if after.path != before.path:
        segments = [s for s in after.path.split("/") if s]
        stable = [s for s in segments if not classify_volatility(s)[0]]
        if stable and len(stable) < len(segments):
            # Há um id volátil na rota: afirmar só o trecho estável.
            yield Assertion(
                name="url.include", target="url", args=["/" + stable[-1]],
                confidence=0.85, rule="post.url.partial", category="URL e Navegação",
                why=f"A rota contém um identificador dinâmico. Afirmar apenas "
                    f"`/{stable[-1]}` mantém o teste válido para qualquer registro.",
            )
        else:
            yield Assertion(
                name="location.pathname", target="url", args=[after.path],
                confidence=0.88, rule="post.url.path", category="URL e Navegação",
                why="A ação levou o usuário a outra página — é o critério de "
                    "aceite mais objetivo que existe.",
            )
        return

    if after.query != before.query:
        yield Assertion(
            name="location.search", target="url", args=[after.query and f"?{after.query}"],
            confidence=0.6, rule="post.url.query", category="URL e Navegação",
            why="A ação alterou os parâmetros da URL (filtro, paginação ou busca).",
        )


@rule("post.title", "Mudança de título da página")
def _post_title(ev: Evidence) -> Iterable[Assertion]:
    if not ev.title_after or ev.title_after == ev.title_before:
        return
    yield Assertion(
        name="title.include", target="title", args=[ev.title_after],
        confidence=0.62, rule="post.title", category="URL e Navegação",
        why="O título mudou junto com a navegação. Vale como confirmação "
            "secundária, útil quando a URL é opaca.",
    )


# --- Fase 4: rede ----------------------------------------------------------

@rule("post.network", "Requisições disparadas pela ação")
def _post_network(ev: Evidence) -> Iterable[Assertion]:
    for req in ev.network:
        url = req.get("url") or ""
        method = (req.get("method") or "GET").upper()
        status = req.get("status")
        alias = req.get("alias") or _alias_for(url, method)

        if status is None:
            continue

        # Status exato quando é sucesso conhecido; faixa quando é variável.
        if status in (200, 201, 204):
            yield Assertion(
                name="response.status", target=f"@{alias}", args=[status],
                confidence=0.92, rule="post.network.status",
                category="Requisições e Respostas",
                why=f"`{method} {_short_path(url)}` respondeu {status}. Interceptar e "
                    f"esperar essa chamada elimina o `cy.wait(3000)` — o teste passa a "
                    f"aguardar o evento real, não o relógio.",
            )
        elif 200 <= status < 300:
            yield Assertion(
                name="response.status.range", target=f"@{alias}", args=[200, 299],
                confidence=0.85, rule="post.network.range",
                category="Requisições e Respostas",
                why=f"`{method} {_short_path(url)}` respondeu {status}; afirmamos a "
                    f"faixa 2xx para tolerar variação legítima.",
            )
        elif status >= 400:
            yield Assertion(
                name="response.status", target=f"@{alias}", args=[status],
                confidence=0.7, rule="post.network.error",
                category="Requisições e Respostas",
                why=f"A chamada falhou com {status} durante a gravação. Se isso foi "
                    f"intencional (teste de erro), mantenha; senão, regrave o fluxo.",
            )

        # Propriedades estáveis no corpo da resposta.
        body = req.get("bodyPreview")
        if isinstance(body, dict):
            for key in ("token", "id", "success", "status", "message", "data",
                        "access_token", "total"):
                if key not in body:
                    continue
                value = body[key]
                if isinstance(value, bool) or (isinstance(value, (int, float)) and key != "id"):
                    yield Assertion(
                        name="response.body.property", target=f"@{alias}",
                        args=[key, value], confidence=0.72,
                        rule="post.network.body", category="Requisições e Respostas",
                        why=f"O corpo da resposta trouxe `{key}: {value}` — um valor "
                            f"estável que descreve o resultado da operação.",
                    )
                else:
                    yield Assertion(
                        name="response.body.property", target=f"@{alias}", args=[key],
                        confidence=0.68, rule="post.network.body.exists",
                        category="Requisições e Respostas",
                        why=f"O corpo trouxe `{key}`, cujo conteúdo varia por execução. "
                            f"Afirmamos a presença da chave, não o valor.",
                    )
                break

        if isinstance(body, list):
            yield Assertion(
                name="response.body.length", target=f"@{alias}", args=[1],
                confidence=0.7, rule="post.network.list",
                category="Requisições e Respostas",
                why=f"A resposta é uma lista com {len(body)} item(ns). Afirmar "
                    f"'pelo menos 1' valida que veio dado sem travar na quantidade.",
            )


# --- Fase 5: reação visual da interface ------------------------------------

@rule("post.toast", "Notificação exibida ao usuário")
def _post_toast(ev: Evidence) -> Iterable[Assertion]:
    for node in ev.added_nodes():
        classes = " ".join(node.get("classList") or []).lower()
        role = (node.get("role") or "").lower()
        live = (node.get("attributes") or {}).get("aria-live")
        text = (node.get("text") or "").strip()

        is_notification = (
            role in ("alert", "status") or live in ("polite", "assertive")
            or any(h in classes for h in ("toast", "snackbar", "notification", "flash", "alert"))
        )
        if not is_notification or not text or len(text) > 200:
            continue

        tone = "erro" if any(h in classes for h in _ERROR_HINTS) else (
            "sucesso" if any(h in classes for h in _SUCCESS_HINTS) else "informação")

        volatile, js_regex = classify_volatility(text)
        if volatile:
            yield Assertion(
                name="match", target={"contains": text[:30]}, args=[{"regex": js_regex}],
                confidence=0.6, rule="post.toast.volatile", category="Comparações",
                why=f"A notificação de {tone} contém dado variável; afirmamos o formato.",
            )
        else:
            yield Assertion(
                name="be.visible", target={"contains": text}, confidence=0.86,
                rule="post.toast", category="Visibilidade",
                why=f"Apareceu uma notificação de {tone}: “{_truncate(text, 60)}”. "
                    f"É a confirmação que o próprio app dá de que a ação funcionou — "
                    f"a assertion mais fiel à experiência do usuário.",
            )


@rule("post.modal", "Diálogo aberto ou fechado")
def _post_modal(ev: Evidence) -> Iterable[Assertion]:
    for node in ev.added_nodes():
        role = (node.get("role") or "").lower()
        classes = " ".join(node.get("classList") or []).lower()
        if role in ("dialog", "alertdialog") or "modal" in classes or "dialog" in classes:
            yield Assertion(
                name="be.visible", target={"role": role or "dialog"}, confidence=0.84,
                rule="post.modal.open", category="Visibilidade",
                why="Um diálogo foi aberto pela ação. Afirmar sua visibilidade "
                    "impede que os passos seguintes rodem contra a tela errada.",
            )
            return
    for node in ev.removed_nodes():
        role = (node.get("role") or "").lower()
        classes = " ".join(node.get("classList") or []).lower()
        if role in ("dialog", "alertdialog") or "modal" in classes:
            yield Assertion(
                name="not.exist", target={"role": role or "dialog"}, confidence=0.82,
                rule="post.modal.close", category="Visibilidade",
                why="O diálogo foi fechado. Afirmar que sumiu evita que o teste "
                    "clique num elemento coberto por um overlay invisível.",
            )
            return


@rule("post.loading", "Indicador de carregamento resolvido")
def _post_loading(ev: Evidence) -> Iterable[Assertion]:
    for node in ev.removed_nodes():
        classes = " ".join(node.get("classList") or []).lower()
        if any(h in classes for h in _LOADING_HINTS):
            selector = _first_semantic_class(node.get("classList") or [], _LOADING_HINTS)
            yield Assertion(
                name="not.exist", target={"css": f".{selector}"} if selector else "self",
                confidence=0.88, rule="post.loading", category="Visibilidade",
                why="Havia um indicador de carregamento que desapareceu. Esperar "
                    "que ele suma é infinitamente melhor que `cy.wait(2000)`: "
                    "o teste sincroniza com o app, não com o cronômetro.",
            )
            return


@rule("post.validation", "Mensagem de validação de formulário")
def _post_validation(ev: Evidence) -> Iterable[Assertion]:
    # Via atributo ARIA — o caminho mais confiável.
    for change in ev.attr_changes():
        if change.get("name") == "aria-invalid" and change.get("value") == "true":
            yield Assertion(
                name="have.attr", target="self", args=["aria-invalid", "true"],
                confidence=0.85, rule="post.validation.aria", category="Acessibilidade",
                why="O campo foi marcado como inválido. Se o fluxo gravado testa "
                    "validação, esta é a assertion central dele.",
            )
            return
    # Via classe de erro adicionada.
    for node in ev.added_nodes():
        classes = " ".join(node.get("classList") or []).lower()
        text = (node.get("text") or "").strip()
        if any(h in classes for h in _ERROR_HINTS) and text and len(text) < 160:
            yield Assertion(
                name="be.visible", target={"contains": text}, confidence=0.8,
                rule="post.validation.text", category="Visibilidade",
                why=f"Mensagem de validação exibida: “{_truncate(text, 60)}”.",
            )
            return


@rule("post.aria.expanded", "Expansão de menu ou acordeão")
def _post_aria_expanded(ev: Evidence) -> Iterable[Assertion]:
    for change in ev.attr_changes():
        if change.get("name") != "aria-expanded":
            continue
        value = str(change.get("value")).lower()
        yield Assertion(
            name="have.attr", target="self", args=["aria-expanded", value],
            confidence=0.86, rule="post.aria.expanded", category="Acessibilidade",
            why=f"O controle {'abriu' if value == 'true' else 'fechou'} seu painel. "
                f"`aria-expanded` é onde esse estado é observável de forma confiável.",
        )
        return


@rule("post.class", "Mudança de estado sinalizada por classe")
def _post_class(ev: Evidence) -> Iterable[Assertion]:
    for change in ev.attr_changes():
        if change.get("name") != "class":
            continue
        added = set(change.get("added") or [])
        meaningful = {
            c for c in added
            if c.lower() in ("active", "selected", "current", "checked", "expanded", "open")
        }
        if not meaningful:
            continue
        cls = sorted(meaningful)[0]
        yield Assertion(
            name="have.class", target="self", args=[cls], confidence=0.68,
            rule="post.class", category="Atributos e Classes",
            why=f"A ação marcou o elemento com a classe `{cls}`. Assertion de "
                f"estado visual — útil para abas e menus, mas sensível a redesign.",
        )
        return


@rule("post.list", "Coleção populada ou alterada")
def _post_list(ev: Evidence) -> Iterable[Assertion]:
    delta = ev.mutations.get("listDelta") or {}
    selector = delta.get("selector")
    after = delta.get("countAfter")
    before = delta.get("countBefore")
    if not selector or after is None:
        return
    if before == 0 and after > 0:
        yield Assertion(
            name="have.length.at.least", target={"css": selector}, args=[1],
            confidence=0.84, rule="post.list.populated", category="Coleções e Listas",
            why=f"A lista saiu de vazia para {after} item(ns). Afirmar 'pelo menos 1' "
                f"valida que os dados chegaram sem prender o teste a um número que "
                f"muda conforme a massa de dados.",
        )
    elif before is not None and after != before:
        yield Assertion(
            name="have.length", target={"css": selector}, args=[after],
            confidence=0.6, rule="post.list.changed", category="Coleções e Listas",
            why=f"A quantidade de itens mudou de {before} para {after}. Revise: se o "
                f"ambiente tiver outra massa de dados, prefira uma comparação relativa.",
        )


@rule("post.text", "Texto atualizado na tela")
def _post_text(ev: Evidence) -> Iterable[Assertion]:
    for change in ev.text_changes():
        before = (change.get("before") or "").strip()
        after = (change.get("after") or "").strip()
        selector = change.get("selector")
        if not after or after == before or len(after) > 160 or not selector:
            continue

        volatile, js_regex = classify_volatility(after)
        if volatile:
            yield Assertion(
                name="match", target={"css": selector}, args=[{"regex": js_regex}],
                confidence=0.66, rule="post.text.volatile", category="Comparações",
                why=f"O texto virou um valor do tipo `{volatile}`. Afirmar o formato "
                    f"mantém o teste verde entre execuções.",
            )
            return

        # Números: comparar magnitude é mais robusto que igualdade.
        if re.fullmatch(r"-?[\d.,]+", after) and re.fullmatch(r"-?[\d.,]+", before or "0"):
            yield Assertion(
                name="have.text", target={"css": selector}, args=[after],
                confidence=0.62, rule="post.text.number", category="Texto e Valor",
                why=f"Contador foi de `{before}` para `{after}`. Se esse número "
                    f"depender de dados do ambiente, troque por `be.gt`.",
            )
            return

        yield Assertion(
            name="contain.text", target={"css": selector}, args=[after],
            confidence=0.74, rule="post.text", category="Texto e Valor",
            why=f"O conteúdo mudou para “{_truncate(after, 60)}” em resposta à ação. "
                f"Usamos `contain.text` em vez de `have.text` porque espaçamento e "
                f"nós irmãos costumam variar.",
        )
        return


@rule("post.storage", "Sessão persistida no navegador")
def _post_storage(ev: Evidence) -> Iterable[Assertion]:
    for key in (ev.storage_delta.get("localStorageAdded") or []):
        if any(hint in key.lower() for hint in ("token", "auth", "session", "user", "jwt")):
            yield Assertion(
                name="localStorage.exists", target="window", args=[key],
                confidence=0.8, rule="post.storage", category="Armazenamento e Janela",
                why=f"A ação gravou `{key}` no localStorage — evidência direta de que "
                    f"a sessão foi estabelecida, independente do que a tela mostra.",
            )
            return
    for key in (ev.storage_delta.get("localStorageRemoved") or []):
        if any(hint in key.lower() for hint in ("token", "auth", "session", "jwt")):
            yield Assertion(
                name="localStorage.not.exists", target="window", args=[key],
                confidence=0.78, rule="post.storage.cleared",
                category="Armazenamento e Janela",
                why=f"`{key}` foi removido do localStorage — a sessão foi encerrada.",
            )
            return


@rule("post.console", "Erros de JavaScript durante a ação")
def _post_console(ev: Evidence) -> Iterable[Assertion]:
    if not ev.console_errors:
        return
    yield Assertion(
        name="__console_clean__", target="window", confidence=0.4,
        rule="post.console", category="Outros",
        raw="// ⚠ O app registrou erro no console durante esta ação:\n"
            + "\n".join(f"    // {_truncate(e, 100)}" for e in ev.console_errors[:3]),
        why="Foram detectados erros de JavaScript enquanto a ação rodava. Não viram "
            "assertion automaticamente, mas ficam anotados: quase sempre indicam um "
            "bug real que o teste manual não percebeu.",
    )


# ---------------------------------------------------------------------------
# Utilidades internas
# ---------------------------------------------------------------------------

def _truncate(text: str, limit: int) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _short_path(url: str) -> str:
    try:
        parsed = urlparse(url)
        return parsed.path or url
    except Exception:
        return url


def _alias_for(url: str, method: str) -> str:
    """Deriva um alias de intercept legível a partir da URL."""
    path = _short_path(url).strip("/")
    segments = [s for s in path.split("/") if s and not classify_volatility(s)[0]]
    tail = segments[-1] if segments else "request"
    tail = re.sub(r"[^a-zA-Z0-9]+", "_", tail).strip("_") or "request"
    prefix = {"GET": "get", "POST": "post", "PUT": "put",
              "PATCH": "patch", "DELETE": "delete"}.get(method, "req")
    return f"{prefix}_{tail}".lower()


def _first_semantic_class(classes: list[str], hints: tuple[str, ...]) -> str | None:
    for c in classes:
        if any(h in c.lower() for h in hints):
            return c
    return None


# ---------------------------------------------------------------------------
# Motor
# ---------------------------------------------------------------------------

class Oracle:
    """Aplica todas as regras a uma evidência e devolve assertions ranqueadas."""

    def __init__(self, *, min_confidence: float = 0.55,
                 disabled_rules: set[str] | None = None) -> None:
        self.min_confidence = min_confidence
        self.disabled_rules = disabled_rules or set()

    def infer(self, ev: Evidence) -> list[Assertion]:
        """Assertions inferidas para uma ação, ordenadas por relevância."""
        produced: list[Assertion] = []
        for rule_id, _title, fn in _RULES:
            if rule_id in self.disabled_rules:
                continue
            try:
                produced.extend(fn(ev))
            except Exception as exc:  # uma regra ruim não pode derrubar a análise
                produced.append(Assertion(
                    name="__rule_error__", target="self", confidence=0.0,
                    rule=rule_id, raw=f"// regra {rule_id} falhou: {exc}",
                    why="Erro interno de regra — reporte este fluxo.",
                ))

        # A estabilidade catalogada modula a confiança da regra: uma regra
        # confiante que produz uma assertion frágil não deve dominar o ranking.
        for a in produced:
            if a.name in catalog.BY_NAME:
                a.confidence *= 0.6 + 0.4 * catalog.stability_of(a.name)
                a.category = a.category or catalog.BY_NAME[a.name]["category"]

        kept = [a for a in produced
                if a.confidence >= self.min_confidence or a.raw or a.confidence == 0.0]
        kept = self._dedupe(kept)
        kept.sort(key=lambda a: (a.phase != "before", -a.confidence))
        return kept

    @staticmethod
    def _dedupe(assertions: list[Assertion]) -> list[Assertion]:
        """Remove duplicatas mantendo a de maior confiança."""
        seen: dict[tuple, Assertion] = {}
        for a in assertions:
            key = (a.name, str(a.target), str(a.args), a.phase)
            prev = seen.get(key)
            if prev is None or a.confidence > prev.confidence:
                seen[key] = a
        return list(seen.values())

    # -- relatório ----------------------------------------------------------

    @staticmethod
    def rules() -> list[dict[str, str]]:
        """Todas as regras registradas — a UI exibe isso como 'o que eu sei'."""
        return [{"id": rid, "title": title} for rid, title, _ in _RULES]

    @staticmethod
    def rule_count() -> int:
        return len(_RULES)
