"""
Revisão estática de testes — o Oracle lendo código em vez de eventos.

O `oracle.py` observa o que a página fez e propõe assertions. Este módulo faz o
caminho inverso: recebe um arquivo de teste pronto e aponta o que vai doer
depois. São os mesmos princípios, aplicados a texto.

Vale a pena existir porque as falhas que derrubam suíte em produção são quase
sempre as mesmas meia dúzia — espera por tempo, seletor acoplado a layout,
senha no arquivo, assertion que não afirma nada. Reconhecer isso não precisa
de um modelo de linguagem; precisa de uma lista honesta e da disciplina de
apontar a linha exata.

Cada achado traz a linha, o motivo e o conserto. E o relatório também diz o que
está certo: uma revisão que só reclama ensina menos do que uma que mostra o
padrão bom ao lado do ruim.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

# Severidades, da mais grave para a mais leve.
ERRO = "erro"        # quebra ou vai quebrar
AVISO = "aviso"      # frágil, quebra no próximo redesign
DICA = "dica"        # funciona, dá para melhorar
ELOGIO = "elogio"    # está certo e merece ser notado

_ORDER = {ERRO: 0, AVISO: 1, DICA: 2, ELOGIO: 3}


@dataclass
class Finding:
    """Um achado da revisão."""

    severity: str
    title: str
    detail: str
    line: int = 0
    snippet: str = ""
    fix: str = ""
    rule: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "severity": self.severity, "title": self.title, "detail": self.detail,
            "line": self.line, "snippet": self.snippet, "fix": self.fix,
            "rule": self.rule,
        }


@dataclass
class Review:
    """Resultado completo da revisão."""

    findings: list[Finding] = field(default_factory=list)
    lines: int = 0
    framework: str = "cypress"

    @property
    def errors(self) -> int:
        return sum(1 for f in self.findings if f.severity == ERRO)

    @property
    def warnings(self) -> int:
        return sum(1 for f in self.findings if f.severity == AVISO)

    @property
    def hints(self) -> int:
        return sum(1 for f in self.findings if f.severity == DICA)

    @property
    def praise(self) -> int:
        return sum(1 for f in self.findings if f.severity == ELOGIO)

    def score(self) -> int:
        """Nota de 0 a 100. Erros pesam muito mais que dicas.

        Cem só quando não há nada a apontar. Um relatório que lista um ponto
        frágil e mesmo assim dá nota máxima se contradiz, e o leitor passa a
        desconfiar da nota inteira.
        """
        penalty = self.errors * 22 + self.warnings * 9 + self.hints * 3
        bonus = min(self.praise * 3, 12)
        score = max(0, min(100, 100 - penalty + bonus))
        if penalty and score >= 100:
            return 99
        return score

    def to_dict(self) -> dict[str, Any]:
        return {
            "findings": [f.to_dict() for f in self.findings],
            "lines": self.lines, "framework": self.framework,
            "errors": self.errors, "warnings": self.warnings,
            "hints": self.hints, "praise": self.praise, "score": self.score(),
        }


# ---------------------------------------------------------------------------
# Padrões
# ---------------------------------------------------------------------------

# Classes que pertencem ao framework de UI, não ao domínio da aplicação.
_FRAMEWORK_CLASS = re.compile(
    r"\.(q-[\w-]+|Mui[\w-]+|ant-[\w-]+|el-[\w-]+|v-[\w-]+|ng-[\w-]+|chakra-[\w-]+"
    r"|rc-[\w-]+|p-[\w-]+|css-[0-9a-z]{6,}|sc-[0-9a-z]{6,})"
)
# Utilitários de espaçamento/cor: mudam a cada ajuste de design.
_UTILITY_CLASS = re.compile(
    r"\.(m[trblxy]?-\d|p[trblxy]?-\d|w-\d|h-\d|text-\w+|bg-\w+|flex|grid|"
    r"items-\w+|justify-\w+|rounded\w*|shadow\w*)\b"
)
_GENERATED_ID = re.compile(
    r"#[\w-]*(?:[0-9a-f]{8}-[0-9a-f]{4}|[0-9a-f]{12,}|\d{5,})"
)
_VOLATILE_LITERAL = re.compile(
    r"'(?:\d{2}/\d{2}/\d{4}|\d{4}-\d{2}-\d{2}[T ]?\d{0,2}:?\d{0,2}"
    r"|R\$\s?[\d.,]+|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})'"
)
_SECRET_HINT = re.compile(
    r"(senha|password|passwd|pwd|secret|token|api[_-]?key|cvv|pin)", re.I
)

Rule = Callable[[list[str], str], Iterable[Finding]]
_RULES: list[Rule] = []


def rule(fn: Rule) -> Rule:
    _RULES.append(fn)
    return fn


def _lines_matching(lines: list[str], pattern: re.Pattern[str]):
    """Itera (nº da linha 1-based, texto) das linhas que casam, fora de comentário."""
    for i, raw in enumerate(lines, start=1):
        text = raw.strip()
        if text.startswith("//") or text.startswith("*") or text.startswith("/*"):
            continue
        if pattern.search(raw):
            yield i, text


# ---------------------------------------------------------------------------
# Regras
# ---------------------------------------------------------------------------

@rule
def _arbitrary_wait(lines: list[str], code: str) -> Iterable[Finding]:
    """`cy.wait(3000)` — a causa nº 1 de suíte instável."""
    pattern = re.compile(r"cy\.wait\(\s*(\d+)\s*\)")
    for line_no, text in _lines_matching(lines, pattern):
        ms = pattern.search(text).group(1)
        yield Finding(
            severity=ERRO, line=line_no, snippet=text, rule="wait.fixo",
            title=f"Espera por tempo fixo ({ms}ms)",
            detail=(
                "Esta linha aposta que a aplicação responde em menos de "
                f"{ms}ms. Numa máquina de CI carregada ela falha; num dia bom "
                "ela desperdiça o tempo todo. É a origem mais comum de teste "
                "que passa na sua máquina e falha no pipeline."
            ),
            fix=(
                "Espere pelo evento, não pelo relógio:\n"
                "  cy.intercept('POST', '**/api/recurso*').as('salvar');\n"
                "  // ... a ação que dispara a chamada\n"
                "  cy.wait('@salvar');\n"
                "Se não houver requisição, espere pelo efeito visível:\n"
                "  cy.get('.spinner').should('not.exist');"
            ),
        )


@rule
def _framework_selector(lines: list[str], code: str) -> Iterable[Finding]:
    """Seletor preso a classe de framework de UI."""
    for line_no, text in _lines_matching(lines, _FRAMEWORK_CLASS):
        match = _FRAMEWORK_CLASS.search(text)
        yield Finding(
            severity=AVISO, line=line_no, snippet=text, rule="seletor.framework",
            title=f"Seletor depende de classe de framework ({match.group(0)})",
            detail=(
                "Essa classe é gerada pelo framework de UI para estilo e "
                "comportamento, não para identificar o elemento. Ela some ou "
                "muda quando o time atualiza a versão da biblioteca — e o "
                "teste quebra sem que ninguém tenha mexido na regra de negócio."
            ),
            fix=(
                "Peça um atributo de teste no elemento:\n"
                '  <button data-cy=\"salvar-pedido\">\n'
                "e use:\n"
                "  cy.get('[data-cy=\"salvar-pedido\"]')\n"
                "Sem acesso ao código-fonte, prefira o texto visível ou o "
                "papel ARIA: cy.contains('Salvar') / cy.get('[role=dialog]')."
            ),
        )


@rule
def _utility_selector(lines: list[str], code: str) -> Iterable[Finding]:
    """Seletor preso a classe utilitária (Tailwind e afins)."""
    for line_no, text in _lines_matching(lines, _UTILITY_CLASS):
        if not re.search(r"cy\.get\(|locator\(", text):
            continue
        yield Finding(
            severity=AVISO, line=line_no, snippet=text, rule="seletor.utilitario",
            title="Seletor depende de classe utilitária de estilo",
            detail=(
                "Classes como `.mt-4` ou `.text-sm` descrevem aparência. "
                "Qualquer ajuste de espaçamento renomeia a classe e derruba o "
                "teste, mesmo com a funcionalidade intacta."
            ),
            fix="Troque por um atributo de teste, texto visível ou papel ARIA.",
        )


@rule
def _generated_id(lines: list[str], code: str) -> Iterable[Finding]:
    """id gerado em runtime."""
    for line_no, text in _lines_matching(lines, _GENERATED_ID):
        yield Finding(
            severity=ERRO, line=line_no, snippet=text, rule="seletor.id-gerado",
            title="Seletor usa id gerado em runtime",
            detail=(
                "Este id tem cara de gerado pelo framework a cada renderização "
                "(hash ou contador). Ele será diferente na próxima execução, "
                "então o teste falha já na segunda rodada."
            ),
            fix="Use um atributo de teste estável, `name`, ou o texto visível.",
        )


@rule
def _xpath_selector(lines: list[str], code: str) -> Iterable[Finding]:
    """XPath posicional."""
    pattern = re.compile(r"(cy\.xpath\(|['\"]xpath=|/html/body)")
    for line_no, text in _lines_matching(lines, pattern):
        yield Finding(
            severity=AVISO, line=line_no, snippet=text, rule="seletor.xpath",
            title="Seletor por posição na árvore (XPath)",
            detail=(
                "Um caminho como `/html/body/div[1]/div[3]` descreve onde o "
                "elemento estava, não o que ele é. Basta alguém envolver a "
                "seção numa `<div>` para o teste apontar para o lugar errado — "
                "e o pior: às vezes ele acha *outro* elemento e falha com uma "
                "mensagem que não faz sentido."
            ),
            fix="Prefira atributo de teste, texto ou papel ARIA.",
        )


@rule
def _index_selector(lines: list[str], code: str) -> Iterable[Finding]:
    """Seleção por índice."""
    pattern = re.compile(r"\.(eq\(\s*\d+\s*\)|first\(\)|last\(\)|nth-child\()")
    for line_no, text in _lines_matching(lines, pattern):
        yield Finding(
            severity=DICA, line=line_no, snippet=text, rule="seletor.indice",
            title="Elemento escolhido por posição",
            detail=(
                "Pegar o item pelo índice amarra o teste à ordem atual dos "
                "dados. Quando a ordenação mudar, ou a massa de teste ganhar "
                "um registro, o teste passa a agir sobre a linha errada — e "
                "pode até continuar verde, verificando a coisa errada."
            ),
            fix=(
                "Escolha pelo conteúdo:\n"
                "  cy.contains('[data-cy=linha]', 'Pedido 1234').click();"
            ),
        )


@rule
def _hardcoded_secret(lines: list[str], code: str) -> Iterable[Finding]:
    """Credencial escrita no arquivo."""
    pattern = re.compile(r"\.(type|fill)\(\s*['\"]([^'\"]{3,})['\"]")
    for i, raw in enumerate(lines, start=1):
        text = raw.strip()
        if text.startswith("//"):
            continue
        match = pattern.search(raw)
        if not match:
            continue
        # Só acusamos se o contexto sugerir credencial.
        if not _SECRET_HINT.search(raw):
            continue
        if "Cypress.env" in raw or "process.env" in raw:
            continue
        yield Finding(
            severity=ERRO, line=i, snippet=text, rule="segredo.no-codigo",
            title="Credencial escrita no arquivo de teste",
            detail=(
                "Este valor vai para o repositório e para o histórico do Git, "
                "onde não sai mais. Qualquer pessoa com acesso ao código passa "
                "a ter a senha — e revogá-la depois não apaga o commit."
            ),
            fix=(
                "Leia do ambiente:\n"
                "  cy.get('[data-cy=senha]').type(Cypress.env('SENHA'));\n"
                "e defina antes de rodar:\n"
                "  CYPRESS_SENHA=... npx cypress run"
            ),
        )


@rule
def _empty_assertion(lines: list[str], code: str) -> Iterable[Finding]:
    """Assertion que não afirma nada de útil."""
    pattern = re.compile(
        r"cy\.get\(\s*['\"](?:body|html)['\"]\s*\)\s*\.should\(\s*['\"](?:exist|be\.visible)"
    )
    for line_no, text in _lines_matching(lines, pattern):
        yield Finding(
            severity=AVISO, line=line_no, snippet=text, rule="assertion.vazia",
            title="Assertion que sempre passa",
            detail=(
                "`body` existe em toda página carregada, inclusive numa tela de "
                "erro 500. Esta linha dá a sensação de estar verificando algo, "
                "mas passaria mesmo se a funcionalidade estivesse quebrada — o "
                "que é pior que não ter verificação nenhuma, porque esconde a "
                "ausência dela."
            ),
            fix=(
                "Afirme o que a ação deveria ter produzido:\n"
                "  cy.location('pathname').should('eq', '/painel');\n"
                "  cy.contains('Bem-vindo').should('be.visible');"
            ),
        )


@rule
def _volatile_literal(lines: list[str], code: str) -> Iterable[Finding]:
    """Assertion sobre valor que muda sozinho."""
    for line_no, text in _lines_matching(lines, _VOLATILE_LITERAL):
        if "should" not in text and "expect" not in text:
            continue
        value = _VOLATILE_LITERAL.search(text).group(0)
        yield Finding(
            severity=AVISO, line=line_no, snippet=text, rule="assertion.volatil",
            title=f"Assertion sobre valor que muda entre execuções ({value})",
            detail=(
                "Datas, horários, identificadores e valores monetários mudam "
                "sozinhos. Este teste passa hoje e falha amanhã sem que nada "
                "no sistema tenha mudado — e o time aprende a ignorar a falha, "
                "que é como uma suíte morre."
            ),
            fix=(
                "Afirme o formato, não o conteúdo:\n"
                "  cy.get('[data-cy=data]').invoke('text')\n"
                "    .should('match', /^\\d{2}\\/\\d{2}\\/\\d{4}$/);"
            ),
        )


@rule
def _force_click(lines: list[str], code: str) -> Iterable[Finding]:
    """`{ force: true }` escondendo um problema."""
    pattern = re.compile(r"force\s*:\s*true")
    for line_no, text in _lines_matching(lines, pattern):
        yield Finding(
            severity=AVISO, line=line_no, snippet=text, rule="acao.forcada",
            title="Ação forçada com `force: true`",
            detail=(
                "O `force` desliga as verificações que o Cypress faz antes de "
                "clicar — visível, habilitado, não coberto. Se o elemento "
                "estava coberto por um overlay, o usuário real também não "
                "conseguiria clicar. O teste passa a validar algo que ninguém "
                "consegue fazer."
            ),
            fix=(
                "Descubra o que está cobrindo e espere sumir:\n"
                "  cy.get('.overlay').should('not.exist');\n"
                "  cy.get('[data-cy=salvar]').click();"
            ),
        )


@rule
def _action_without_assertion(lines: list[str], code: str) -> Iterable[Finding]:
    """Bloco `it` sem nenhuma verificação."""
    blocks = re.finditer(r"\bit\(\s*['\"`]([^'\"`]*)['\"`]", code)
    for match in blocks:
        start = match.end()
        # Fatia grosseira até o próximo `it(` ou o fim.
        nxt = code.find("it(", start)
        body = code[start:nxt if nxt > 0 else len(code)]
        has_action = re.search(r"\.(click|type|fill|select|check)\(", body)
        has_assert = re.search(r"\.should\(|expect\(|\.to\.", body)
        if has_action and not has_assert:
            line_no = code[:match.start()].count("\n") + 1
            yield Finding(
                severity=ERRO, line=line_no, snippet=match.group(0),
                rule="teste.sem-assertion",
                title=f"O teste “{match.group(1)[:44]}” não verifica nada",
                detail=(
                    "Há ações, mas nenhuma afirmação sobre o resultado. Este "
                    "teste só falha se um seletor sumir; se a funcionalidade "
                    "parar de funcionar mantendo a tela igual, ele continua "
                    "verde. É um teste que dá falsa segurança."
                ),
                fix=(
                    "Afirme o efeito esperado ao final:\n"
                    "  cy.contains('Salvo com sucesso').should('be.visible');"
                ),
            )


@rule
def _vague_name(lines: list[str], code: str) -> Iterable[Finding]:
    """Nome de teste que não diz o que ele valida."""
    vague = re.compile(
        r"\b(it|describe)\(\s*['\"`]\s*(teste?\s*\d*|test\s*\d*|deve funcionar"
        r"|funciona|ok|caso\s*\d*|cen[áa]rio\s*\d*)\s*['\"`]", re.I
    )
    for match in vague.finditer(code):
        line_no = code[:match.start()].count("\n") + 1
        yield Finding(
            severity=DICA, line=line_no, snippet=match.group(0).strip(),
            rule="nome.vago",
            title="Nome de teste não descreve o comportamento",
            detail=(
                "Quando este teste falhar no pipeline às três da manhã, o nome "
                "é a primeira e às vezes única informação que a pessoa de "
                "plantão terá. “teste 3” não ajuda ninguém."
            ),
            fix=(
                "Descreva o comportamento esperado:\n"
                "  it('bloqueia o login com senha errada e mostra o erro')"
            ),
        )


@rule
def _duplicate_chain(lines: list[str], code: str) -> Iterable[Finding]:
    """O mesmo seletor repetido — candidato a comando customizado.

    A captura usa retrovisor para a aspa de abertura. Sem isso, o seletor
    `'[data-cy="login_id"]'` (aspas simples por fora, duplas por dentro) seria
    truncado em `[data-cy=` — e quatro seletores distintos apareceriam como
    quatro repetições do mesmo.
    """
    signature = re.compile(r"cy\.get\(\s*(['\"])(.+?)\1")
    seen: dict[str, list[int]] = {}
    for i, raw in enumerate(lines, start=1):
        if raw.strip().startswith("//"):
            continue
        for match in signature.finditer(raw):
            seen.setdefault(match.group(2), []).append(i)

    # Um achado por seletor repetido vira uma parede de avisos idênticos, e o
    # conselho é sempre o mesmo. Consolidamos num único item que diz o que
    # fazer — e aponta para quem faz.
    repeated = {sel: hits for sel, hits in seen.items() if len(hits) >= 3}
    if not repeated:
        return

    ordered = sorted(repeated.items(), key=lambda kv: -len(kv[1]))
    listing = "\n".join(
        f"      {sel}  ({len(hits)}x — linhas "
        f"{', '.join(str(n) for n in hits[:5])}{'…' if len(hits) > 5 else ''})"
        for sel, hits in ordered[:6]
    )
    first_line = min(hits[0] for hits in repeated.values())

    yield Finding(
        severity=DICA, line=first_line, rule="repeticao",
        title=(f"{len(repeated)} seletor(es) se repetem — vale extrair comandos"
               if len(repeated) > 1 else
               "Um seletor se repete — vale extrair um comando"),
        detail=(
            "Quando esses elementos mudarem na aplicação, o conserto precisa "
            "acontecer em cada ocorrência — e é fácil esquecer uma.\n\n"
            f"{listing}"
        ),
        fix=(
            "O Cygen faz isso por você: use “Gerar projeto completo” na aba "
            "Código.\n"
            "Ele cria `cypress/support/commands.js` com os comandos já "
            "nomeados a partir dos elementos, reescreve o spec para usá-los, "
            "e monta a configuração, o package.json e o README.\n"
            "O resultado roda com `npm install && npm test`, sem edição manual "
            "além das credenciais."
        ),
    )


@rule
def _missing_visit(lines: list[str], code: str) -> Iterable[Finding]:
    """Teste que age sem ter aberto página nenhuma."""
    if not re.search(r"cy\.(visit|session)\(|page\.goto\(", code):
        if re.search(r"cy\.get\(|page\.locator\(", code):
            yield Finding(
                severity=AVISO, line=1, rule="fluxo.sem-visit",
                title="Nenhuma navegação inicial",
                detail=(
                    "O teste interage com elementos mas nunca abre uma página. "
                    "Isso funciona se houver um `beforeEach` em outro arquivo, "
                    "mas torna o teste impossível de rodar isolado — e ler."
                ),
                fix="Adicione `cy.visit('/rota')` no início ou num `beforeEach`.",
            )


# --- Reconhecimento do que está certo -------------------------------------

@rule
def _praise_intercept(lines: list[str], code: str) -> Iterable[Finding]:
    if re.search(r"cy\.intercept\(", code) and re.search(r"cy\.wait\(\s*['\"]@", code):
        yield Finding(
            severity=ELOGIO, rule="bom.intercept",
            title="Espera sincronizada com a rede",
            detail=(
                "O teste intercepta a chamada e espera por ela em vez de "
                "cronometrar. É o que separa uma suíte confiável de uma que o "
                "time aprende a re-executar até passar."
            ),
        )


@rule
def _praise_test_attrs(lines: list[str], code: str) -> Iterable[Finding]:
    count = len(re.findall(r"\[data-(?:cy|test|testid|qa)[=\]]", code))
    if count >= 3:
        yield Finding(
            severity=ELOGIO, rule="bom.data-cy",
            title=f"{count} seletores usam atributo dedicado a teste",
            detail=(
                "Atributos como `data-cy` existem só para automação, então "
                "nenhum ajuste de estilo os quebra. É a base de um teste que "
                "sobrevive a refatoração."
            ),
        )


@rule
def _praise_env_secret(lines: list[str], code: str) -> Iterable[Finding]:
    if re.search(r"Cypress\.env\(|process\.env\.", code):
        yield Finding(
            severity=ELOGIO, rule="bom.segredo",
            title="Credenciais vêm do ambiente",
            detail="Nenhuma senha no repositório. É como deve ser.",
        )


@rule
def _praise_semantic_wait(lines: list[str], code: str) -> Iterable[Finding]:
    if re.search(r"should\(\s*['\"]not\.exist", code):
        yield Finding(
            severity=ELOGIO, rule="bom.espera-semantica",
            title="Espera pelo desaparecimento de um elemento",
            detail=(
                "Aguardar um spinner sumir sincroniza o teste com a aplicação, "
                "não com o relógio."
            ),
        )


# ---------------------------------------------------------------------------
# Motor
# ---------------------------------------------------------------------------

def analyze(code: str) -> Review:
    """Roda todas as regras sobre o código e devolve a revisão ordenada."""
    lines = code.splitlines()
    framework = "playwright" if re.search(r"@playwright/test|page\.goto\(", code) else "cypress"
    review = Review(lines=len(lines), framework=framework)

    for fn in _RULES:
        try:
            review.findings.extend(fn(lines, code))
        except Exception:
            continue          # uma regra ruim não derruba a revisão inteira

    # Um mesmo problema na mesma linha não precisa ser dito duas vezes.
    seen: set[tuple] = set()
    unique: list[Finding] = []
    for finding in review.findings:
        key = (finding.rule, finding.line)
        if key in seen:
            continue
        seen.add(key)
        unique.append(finding)

    unique.sort(key=lambda f: (_ORDER.get(f.severity, 9), f.line))
    review.findings = unique
    return review


def rule_count() -> int:
    return len(_RULES)


# ---------------------------------------------------------------------------
# Apresentação
# ---------------------------------------------------------------------------

_LABEL = {
    ERRO: "✕ ERRO",
    AVISO: "▲ ATENÇÃO",
    DICA: "○ SUGESTÃO",
    ELOGIO: "✓ BOM",
}


def to_text(review: Review, *, title: str = "") -> str:
    """Formata a revisão como texto legível para o chat."""
    out: list[str] = []

    if review.errors == 0 and review.warnings == 0:
        veredito = "Este teste está sólido."
    elif review.errors:
        veredito = (f"Encontrei {review.errors} problema(s) que vão quebrar "
                    f"este teste, e {review.warnings} ponto(s) frágeis.")
    else:
        veredito = (f"Nada quebrado, mas há {review.warnings} ponto(s) que "
                    f"tendem a quebrar num redesign.")

    out.append(f"{veredito}  ·  nota {review.score()}/100")
    out.append(f"{review.lines} linhas · {review.framework} · "
               f"{rule_count()} regras aplicadas · custo R$ 0")
    out.append("")

    if not review.findings:
        out.append("Nenhuma observação — o que também é raro o bastante para "
                   "merecer nota.")
    else:
        for finding in review.findings:
            head = _LABEL.get(finding.severity, finding.severity)
            where = f"  linha {finding.line}" if finding.line else ""
            out.append(f"{head}{where} — {finding.title}")
            if finding.snippet:
                out.append(f"    {finding.snippet[:110]}")
            out.append(f"    {finding.detail}")
            if finding.fix:
                out.append("")
                for fix_line in finding.fix.splitlines():
                    out.append(f"    {fix_line}")
            out.append("")

    out.append(next_step(review))
    return "\n".join(out).rstrip()


def next_step(review: Review) -> str:
    """O que fazer agora.

    Uma revisão que termina em diagnóstico deixa o trabalho de decidir com quem
    já não sabia o que fazer. O último parágrafo sempre aponta uma ação, e a
    ação preferida é a que o Cygen consegue executar sozinho.
    """
    lines = ["─" * 62, "PRÓXIMO PASSO"]

    if review.errors:
        lines.append(
            "Resolva primeiro os itens marcados como ERRO — eles não são risco "
            "futuro, são falha certa. Depois gere o projeto completo."
        )
    else:
        lines.append(
            "Este teste está pronto para virar um projeto que roda."
        )

    lines.append("")
    lines.append(
        "Na aba Código, use “Gerar projeto completo”. O Cygen monta:"
    )
    lines.append("")
    lines.append("  cypress.config.js        baseUrl, timeouts, retentativas")
    lines.append("  package.json             dependência e scripts")
    lines.append("  cypress/e2e/*.cy.js      o teste, com caminhos relativos")
    lines.append("  cypress/support/         comandos extraídos das repetições")
    lines.append("  cypress.env.example.json onde as credenciais entram")
    lines.append("  README.md                como rodar")
    lines.append("")
    lines.append(
        "Você só preenche as credenciais e roda `npm install && npm test`."
    )
    return "\n".join(lines)
