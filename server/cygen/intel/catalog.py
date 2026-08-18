"""
Catálogo de assertions Cypress.

Portado e expandido a partir de `modules/cypress_assertions.py` do Cygen v2.
A diferença estrutural: cada assertion agora carrega *metadados de máquina* além
da documentação humana. O Oracle usa esses metadados para decidir, por lógica
pura, quais assertions fazem sentido para um evento observado.

Metadados por assertion:
    arity      -> quantos argumentos o `.should()` consome (0, 1 ou 2)
    subject    -> em que tipo de sujeito a assertion pode ser aplicada
    applies_to -> tags/roles HTML compatíveis ("*" = qualquer)
    negatable  -> se existe a forma negativa correspondente
    stability  -> quão resistente a assertion é a mudanças cosméticas (0..1)
                  usado para ranquear: preferimos assertions estáveis.
"""

from __future__ import annotations

from typing import Any

# Tipos de sujeito sobre os quais uma assertion pode operar.
SUBJECT_ELEMENT = "element"
SUBJECT_COLLECTION = "collection"
SUBJECT_URL = "url"
SUBJECT_TITLE = "title"
SUBJECT_RESPONSE = "response"
SUBJECT_VALUE = "value"
SUBJECT_WINDOW = "window"


def _a(
    name: str,
    description: str,
    syntax: str,
    example: str,
    *,
    arity: int = 0,
    subject: str = SUBJECT_ELEMENT,
    applies_to: tuple[str, ...] = ("*",),
    negatable: bool = True,
    stability: float = 0.5,
) -> dict[str, Any]:
    return {
        "name": name,
        "description": description,
        "syntax": syntax,
        "example": example,
        "arity": arity,
        "subject": subject,
        "applies_to": applies_to,
        "negatable": negatable,
        "stability": stability,
    }


CATALOG: dict[str, list[dict[str, Any]]] = {
    "Visibilidade": [
        _a("exist", "Verifica se o elemento existe no DOM",
           ".should('exist')", "cy.get('.item').should('exist')",
           stability=0.95),
        _a("not.exist", "Verifica se o elemento não existe no DOM",
           ".should('not.exist')", "cy.get('.spinner').should('not.exist')",
           stability=0.95),
        _a("be.visible", "Verifica se o elemento está visível",
           ".should('be.visible')", "cy.get('button').should('be.visible')",
           stability=0.9),
        _a("not.be.visible", "Verifica se o elemento não está visível",
           ".should('not.be.visible')", "cy.get('.dropdown').should('not.be.visible')",
           stability=0.85),
    ],
    "Estado": [
        _a("be.checked", "Verifica se o checkbox/radio está marcado",
           ".should('be.checked')", "cy.get('#termos').should('be.checked')",
           applies_to=("input[type=checkbox]", "input[type=radio]"), stability=0.9),
        _a("not.be.checked", "Verifica se o checkbox/radio não está marcado",
           ".should('not.be.checked')", "cy.get('#termos').should('not.be.checked')",
           applies_to=("input[type=checkbox]", "input[type=radio]"), stability=0.9),
        _a("be.disabled", "Verifica se o elemento está desabilitado",
           ".should('be.disabled')", "cy.get('button').should('be.disabled')",
           applies_to=("button", "input", "select", "textarea", "fieldset"), stability=0.85),
        _a("not.be.disabled", "Verifica se o elemento não está desabilitado",
           ".should('not.be.disabled')", "cy.get('button').should('not.be.disabled')",
           applies_to=("button", "input", "select", "textarea", "fieldset"), stability=0.85),
        _a("be.enabled", "Verifica se o elemento está habilitado",
           ".should('be.enabled')", "cy.get('button').should('be.enabled')",
           applies_to=("button", "input", "select", "textarea"), stability=0.85),
        _a("be.focused", "Verifica se o elemento está com foco",
           ".should('be.focused')", "cy.get('input').should('be.focused')",
           stability=0.6),
        _a("not.be.focused", "Verifica se o elemento não está com foco",
           ".should('not.be.focused')", "cy.get('input').should('not.be.focused')",
           stability=0.6),
        _a("be.selected", "Verifica se a opção está selecionada",
           ".should('be.selected')", "cy.get('option').should('be.selected')",
           applies_to=("option",), stability=0.85),
        _a("not.be.selected", "Verifica se a opção não está selecionada",
           ".should('not.be.selected')", "cy.get('option').should('not.be.selected')",
           applies_to=("option",), stability=0.85),
    ],
    "Texto e Valor": [
        _a("have.text", "Verifica se o elemento tem exatamente o texto",
           ".should('have.text', 'texto')", "cy.get('h1').should('have.text', 'Bem-vindo')",
           arity=1, stability=0.45),
        _a("contain.text", "Verifica se o elemento contém o texto",
           ".should('contain.text', 'texto')", "cy.get('p').should('contain.text', 'salvo')",
           arity=1, stability=0.75),
        _a("not.have.text", "Verifica se o elemento não tem exatamente o texto",
           ".should('not.have.text', 'texto')", "cy.get('h1').should('not.have.text', 'Erro')",
           arity=1, stability=0.45),
        _a("not.contain.text", "Verifica se o elemento não contém o texto",
           ".should('not.contain.text', 'texto')", "cy.get('p').should('not.contain.text', 'erro')",
           arity=1, stability=0.7),
        _a("have.value", "Verifica se o campo tem exatamente o valor",
           ".should('have.value', 'valor')", "cy.get('input').should('have.value', 'ana@x.com')",
           arity=1, applies_to=("input", "textarea", "select"), stability=0.8),
        _a("not.have.value", "Verifica se o campo não tem o valor",
           ".should('not.have.value', 'valor')", "cy.get('input').should('not.have.value', '')",
           arity=1, applies_to=("input", "textarea", "select"), stability=0.8),
        _a("contain.value", "Verifica se o valor do campo contém o texto",
           ".should('contain.value', 'texto')", "cy.get('input').should('contain.value', '@')",
           arity=1, applies_to=("input", "textarea"), stability=0.7),
        _a("have.html", "Verifica o HTML interno exato",
           ".should('have.html', 'html')", "cy.get('div').should('have.html', '<b>Oi</b>')",
           arity=1, stability=0.2),
        _a("contain.html", "Verifica se o HTML interno contém o trecho",
           ".should('contain.html', 'html')", "cy.get('div').should('contain.html', '<b>')",
           arity=1, stability=0.35),
        _a("be.empty", "Verifica se o elemento está vazio",
           ".should('be.empty')", "cy.get('ul').should('be.empty')", stability=0.8),
        _a("not.be.empty", "Verifica se o elemento não está vazio",
           ".should('not.be.empty')", "cy.get('ul').should('not.be.empty')", stability=0.85),
    ],
    "Atributos e Classes": [
        _a("have.attr", "Verifica atributo com valor específico",
           ".should('have.attr', 'attr', 'valor')",
           "cy.get('a').should('have.attr', 'href', '/home')",
           arity=2, stability=0.7),
        _a("have.attr.exists", "Verifica a existência do atributo",
           ".should('have.attr', 'attr')", "cy.get('img').should('have.attr', 'alt')",
           arity=1, stability=0.8),
        _a("not.have.attr", "Verifica que o elemento não tem o atributo",
           ".should('not.have.attr', 'attr')", "cy.get('button').should('not.have.attr', 'disabled')",
           arity=1, stability=0.75),
        _a("have.class", "Verifica se o elemento tem a classe CSS",
           ".should('have.class', 'classe')", "cy.get('li').should('have.class', 'active')",
           arity=1, stability=0.55),
        _a("not.have.class", "Verifica se o elemento não tem a classe CSS",
           ".should('not.have.class', 'classe')", "cy.get('li').should('not.have.class', 'error')",
           arity=1, stability=0.55),
        _a("have.css", "Verifica propriedade CSS computada",
           ".should('have.css', 'prop', 'valor')",
           "cy.get('div').should('have.css', 'color', 'rgb(255, 0, 0)')",
           arity=2, stability=0.25),
        _a("have.prop", "Verifica propriedade DOM",
           ".should('have.prop', 'prop', valor)",
           "cy.get('input').should('have.prop', 'checked', true)",
           arity=2, stability=0.7),
        _a("have.id", "Verifica o id do elemento",
           ".should('have.id', 'id')", "cy.get('div').should('have.id', 'main')",
           arity=1, stability=0.6),
        _a("have.data", "Verifica atributo data-* com valor",
           ".should('have.data', 'chave', 'valor')",
           "cy.get('div').should('have.data', 'state', 'open')",
           arity=2, stability=0.8),
        _a("have.focus", "Verifica se o elemento detém o foco",
           ".should('have.focus')", "cy.get('input').should('have.focus')", stability=0.6),
    ],
    "Coleções e Listas": [
        _a("have.length", "Verifica o número exato de elementos",
           ".should('have.length', n)", "cy.get('li').should('have.length', 5)",
           arity=1, subject=SUBJECT_COLLECTION, stability=0.5),
        _a("have.length.greaterThan", "Verifica se há mais que N elementos",
           ".should('have.length.greaterThan', n)", "cy.get('tr').should('have.length.greaterThan', 0)",
           arity=1, subject=SUBJECT_COLLECTION, stability=0.85),
        _a("have.length.lessThan", "Verifica se há menos que N elementos",
           ".should('have.length.lessThan', n)", "cy.get('.erro').should('have.length.lessThan', 3)",
           arity=1, subject=SUBJECT_COLLECTION, stability=0.7),
        _a("have.length.at.least", "Verifica se há pelo menos N elementos",
           ".should('have.length.at.least', n)", "cy.get('.item').should('have.length.at.least', 1)",
           arity=1, subject=SUBJECT_COLLECTION, stability=0.85),
        _a("have.length.at.most", "Verifica se há no máximo N elementos",
           ".should('have.length.at.most', n)", "cy.get('.toast').should('have.length.at.most', 1)",
           arity=1, subject=SUBJECT_COLLECTION, stability=0.7),
    ],
    "URL e Navegação": [
        _a("url.include", "Verifica se a URL contém o trecho",
           "cy.url().should('include', 'trecho')", "cy.url().should('include', '/dashboard')",
           arity=1, subject=SUBJECT_URL, stability=0.9),
        _a("url.not.include", "Verifica se a URL não contém o trecho",
           "cy.url().should('not.include', 'trecho')", "cy.url().should('not.include', '/login')",
           arity=1, subject=SUBJECT_URL, stability=0.9),
        _a("url.eq", "Verifica a URL exata",
           "cy.url().should('eq', 'url')", "cy.url().should('eq', 'https://app.com/home')",
           arity=1, subject=SUBJECT_URL, stability=0.35),
        _a("url.match", "Verifica a URL contra um regex",
           "cy.url().should('match', /re/)", "cy.url().should('match', /\\/user\\/\\d+/)",
           arity=1, subject=SUBJECT_URL, stability=0.8),
        _a("location.pathname", "Verifica o pathname",
           "cy.location('pathname').should('eq', '/x')",
           "cy.location('pathname').should('eq', '/dashboard')",
           arity=1, subject=SUBJECT_URL, stability=0.85),
        _a("location.hash", "Verifica o hash da URL (rotas SPA com #)",
           "cy.location('hash').should('eq', '#/x')",
           "cy.location('hash').should('eq', '#/orcamento')",
           arity=1, subject=SUBJECT_URL, stability=0.85),
        _a("location.search", "Verifica a query string",
           "cy.location('search').should('eq', '?a=1')",
           "cy.location('search').should('include', 'id=')",
           arity=1, subject=SUBJECT_URL, stability=0.6),
        _a("title.include", "Verifica se o título contém o texto",
           "cy.title().should('include', 'texto')", "cy.title().should('include', 'Painel')",
           arity=1, subject=SUBJECT_TITLE, stability=0.75),
        _a("title.eq", "Verifica o título exato",
           "cy.title().should('eq', 'texto')", "cy.title().should('eq', 'Painel')",
           arity=1, subject=SUBJECT_TITLE, stability=0.6),
    ],
    "Requisições e Respostas": [
        _a("response.status", "Verifica o status HTTP da resposta interceptada",
           ".its('response.statusCode').should('eq', 200)",
           "cy.wait('@login').its('response.statusCode').should('eq', 200)",
           arity=1, subject=SUBJECT_RESPONSE, stability=0.9),
        _a("response.status.range", "Verifica faixa de status HTTP",
           ".its('response.statusCode').should('be.within', 200, 299)",
           "cy.wait('@api').its('response.statusCode').should('be.within', 200, 299)",
           arity=2, subject=SUBJECT_RESPONSE, stability=0.95),
        _a("response.body.property", "Verifica propriedade no corpo da resposta",
           ".its('response.body').should('have.property', 'k', v)",
           "cy.wait('@login').its('response.body').should('have.property', 'token')",
           arity=2, subject=SUBJECT_RESPONSE, stability=0.8),
        _a("response.body.length", "Verifica o tamanho de um array na resposta",
           ".its('response.body').should('have.length.at.least', n)",
           "cy.wait('@lista').its('response.body').should('have.length.at.least', 1)",
           arity=1, subject=SUBJECT_RESPONSE, stability=0.8),
        _a("request.method", "Verifica o método HTTP da requisição",
           ".its('request.method').should('eq', 'POST')",
           "cy.wait('@salvar').its('request.method').should('eq', 'POST')",
           arity=1, subject=SUBJECT_RESPONSE, stability=0.95),
        _a("response.headers", "Verifica um cabeçalho da resposta",
           ".its('response.headers').should('have.property', 'h', v)",
           "cy.wait('@api').its('response.headers').should('have.property', 'content-type')",
           arity=2, subject=SUBJECT_RESPONSE, stability=0.7),
    ],
    "Comparações": [
        _a("eq", "Verifica igualdade", ".should('eq', v)",
           "cy.get('span').invoke('text').should('eq', '100')",
           arity=1, subject=SUBJECT_VALUE, stability=0.5),
        _a("not.eq", "Verifica desigualdade", ".should('not.eq', v)",
           "cy.get('span').invoke('text').should('not.eq', '0')",
           arity=1, subject=SUBJECT_VALUE, stability=0.6),
        _a("include", "Verifica inclusão", ".should('include', v)",
           "cy.get('div').invoke('text').should('include', 'ok')",
           arity=1, subject=SUBJECT_VALUE, stability=0.7),
        _a("not.include", "Verifica não-inclusão", ".should('not.include', v)",
           "cy.get('div').invoke('text').should('not.include', 'erro')",
           arity=1, subject=SUBJECT_VALUE, stability=0.7),
        _a("match", "Verifica contra regex", ".should('match', /re/)",
           "cy.get('span').invoke('text').should('match', /R\\$\\s?\\d+/)",
           arity=1, subject=SUBJECT_VALUE, stability=0.85),
        _a("not.match", "Verifica que não casa com o regex", ".should('not.match', /re/)",
           "cy.get('div').invoke('text').should('not.match', /erro/i)",
           arity=1, subject=SUBJECT_VALUE, stability=0.8),
        _a("contain", "Verifica se contém o valor", ".should('contain', v)",
           "cy.get('li').should('contain', 'Item 3')", arity=1, stability=0.7),
        _a("not.contain", "Verifica se não contém o valor", ".should('not.contain', v)",
           "cy.get('ul').should('not.contain', 'Removido')", arity=1, stability=0.7),
        _a("deep.equal", "Igualdade profunda de objetos", ".should('deep.equal', obj)",
           "cy.window().its('state').should('deep.equal', { ok: true })",
           arity=1, subject=SUBJECT_VALUE, stability=0.3),
    ],
    "Numéricos": [
        _a("be.gt", "Maior que", ".should('be.gt', n)",
           "cy.get('.total').invoke('text').then(parseFloat).should('be.gt', 0)",
           arity=1, subject=SUBJECT_VALUE, stability=0.85),
        _a("be.gte", "Maior ou igual a", ".should('be.gte', n)",
           "cy.get('.qtd').invoke('text').then(parseInt).should('be.gte', 1)",
           arity=1, subject=SUBJECT_VALUE, stability=0.85),
        _a("be.lt", "Menor que", ".should('be.lt', n)",
           "cy.get('.erros').invoke('text').then(parseInt).should('be.lt', 1)",
           arity=1, subject=SUBJECT_VALUE, stability=0.8),
        _a("be.lte", "Menor ou igual a", ".should('be.lte', n)",
           "cy.get('.qtd').invoke('text').then(parseInt).should('be.lte', 10)",
           arity=1, subject=SUBJECT_VALUE, stability=0.8),
        _a("be.within", "Dentro de um intervalo", ".should('be.within', min, max)",
           "cy.get('.pct').invoke('text').then(parseFloat).should('be.within', 0, 100)",
           arity=2, subject=SUBJECT_VALUE, stability=0.9),
        _a("be.closeTo", "Próximo de um valor com margem", ".should('be.closeTo', n, delta)",
           "cy.get('.v').invoke('text').then(parseFloat).should('be.closeTo', 100.5, 0.1)",
           arity=2, subject=SUBJECT_VALUE, stability=0.8),
    ],
    "Acessibilidade": [
        _a("have.attr.aria-expanded", "Verifica estado de expansão ARIA",
           ".should('have.attr', 'aria-expanded', 'true')",
           "cy.get('[role=button]').should('have.attr', 'aria-expanded', 'true')",
           arity=2, stability=0.85),
        _a("have.attr.aria-selected", "Verifica seleção ARIA",
           ".should('have.attr', 'aria-selected', 'true')",
           "cy.get('[role=tab]').should('have.attr', 'aria-selected', 'true')",
           arity=2, stability=0.85),
        _a("have.attr.aria-invalid", "Verifica estado de erro ARIA",
           ".should('have.attr', 'aria-invalid', 'true')",
           "cy.get('input').should('have.attr', 'aria-invalid', 'true')",
           arity=2, stability=0.85),
        _a("have.attr.aria-checked", "Verifica marcação ARIA",
           ".should('have.attr', 'aria-checked', 'true')",
           "cy.get('[role=switch]').should('have.attr', 'aria-checked', 'true')",
           arity=2, stability=0.85),
        _a("have.attr.role", "Verifica o papel ARIA do elemento",
           ".should('have.attr', 'role', 'dialog')",
           "cy.get('.modal').should('have.attr', 'role', 'dialog')",
           arity=2, stability=0.8),
    ],
    "Armazenamento e Janela": [
        _a("localStorage.exists", "Verifica se uma chave existe no localStorage",
           "cy.window().its('localStorage').invoke('getItem', 'k').should('exist')",
           "cy.window().its('localStorage').invoke('getItem', 'token').should('exist')",
           arity=1, subject=SUBJECT_WINDOW, stability=0.85),
        _a("localStorage.not.exists", "Verifica se uma chave não existe no localStorage",
           "cy.window().its('localStorage').invoke('getItem', 'k').should('be.null')",
           "cy.window().its('localStorage').invoke('getItem', 'token').should('be.null')",
           arity=1, subject=SUBJECT_WINDOW, stability=0.85),
        _a("cookie.exists", "Verifica a existência de um cookie",
           "cy.getCookie('nome').should('exist')", "cy.getCookie('session').should('exist')",
           arity=1, subject=SUBJECT_WINDOW, stability=0.85),
    ],
    "Outros": [
        _a("be.true", "Verifica se o valor é verdadeiro", ".should('be.true')",
           "cy.get('input').invoke('prop', 'checked').should('be.true')",
           subject=SUBJECT_VALUE, stability=0.8),
        _a("be.false", "Verifica se o valor é falso", ".should('be.false')",
           "cy.get('input').invoke('prop', 'disabled').should('be.false')",
           subject=SUBJECT_VALUE, stability=0.8),
        _a("be.null", "Verifica se o valor é nulo", ".should('be.null')",
           "cy.window().its('app.user').should('be.null')",
           subject=SUBJECT_VALUE, stability=0.7),
        _a("not.be.null", "Verifica se o valor não é nulo", ".should('not.be.null')",
           "cy.window().its('app.config').should('not.be.null')",
           subject=SUBJECT_VALUE, stability=0.75),
        _a("be.undefined", "Verifica se o valor é indefinido", ".should('be.undefined')",
           "cy.window().its('app.tmp').should('be.undefined')",
           subject=SUBJECT_VALUE, stability=0.7),
        _a("not.be.undefined", "Verifica se o valor não é indefinido", ".should('not.be.undefined')",
           "cy.window().its('app.init').should('not.be.undefined')",
           subject=SUBJECT_VALUE, stability=0.75),
        _a("be.a", "Verifica o tipo do valor", ".should('be.a', 'tipo')",
           "cy.window().its('app.items').should('be.an', 'array')",
           arity=1, subject=SUBJECT_VALUE, stability=0.8),
    ],
}


# Índice plano nome -> metadados, construído uma vez na importação.
BY_NAME: dict[str, dict[str, Any]] = {}
for _category, _items in CATALOG.items():
    for _item in _items:
        BY_NAME[_item["name"]] = {**_item, "category": _category}


def categories() -> list[str]:
    """Nomes das categorias do catálogo."""
    return list(CATALOG.keys())


def get(name: str) -> dict[str, Any] | None:
    """Metadados de uma assertion pelo nome canônico."""
    return BY_NAME.get(name)


def stability_of(name: str) -> float:
    """Estabilidade da assertion (0..1). Desconhecidas recebem 0.5 (neutro)."""
    meta = BY_NAME.get(name)
    return float(meta["stability"]) if meta else 0.5


def search(query: str) -> list[dict[str, Any]]:
    """Busca textual em nome, descrição e exemplo."""
    q = query.strip().lower()
    if not q:
        return []
    hits = []
    for meta in BY_NAME.values():
        haystack = f"{meta['name']} {meta['description']} {meta['example']}".lower()
        if q in haystack:
            hits.append(meta)
    return hits


def total() -> int:
    """Quantidade de assertions catalogadas."""
    return len(BY_NAME)
