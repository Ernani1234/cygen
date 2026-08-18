"""
Gerador de projeto Cypress completo.

Um arquivo `.cy.js` sozinho não roda. Falta a configuração, o `package.json`,
a pasta `support/`, e alguém precisa decidir onde as credenciais moram. Entregar
só o spec transfere esse trabalho de volta para quem pediu o teste.

Este módulo fecha a lacuna: recebe a `Spec` e devolve um projeto que roda com
`npm install && npx cypress run`, sem edição manual além das variáveis de
ambiente.

Também resolve um incômodo da revisão. Apontar "este seletor se repete, extraia
para um comando" é uma tarefa que o Cygen tem informação de sobra para executar
— o nome do elemento, o grupo semântico do passo, a sequência inteira. Então em
vez de sugerir, ele gera: `cy.login()`, `cy.campoUsuario()`, com `cy.session()`
onde faz sentido.
"""

from __future__ import annotations

import json
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from . import cypress as emit_cypress
from .ir import Command, Spec

# Quantas repetições justificam extrair um comando. Duas ainda é coincidência;
# a partir de três é padrão, e o custo de manutenção passa a valer a abstração.
_REPEAT_THRESHOLD = 3


def _ascii(text: str) -> str:
    return (unicodedata.normalize("NFKD", text or "")
            .encode("ascii", "ignore").decode("ascii"))


def slug(text: str, sep: str = "-") -> str:
    cleaned = re.sub(r"[^\w\s-]", "", _ascii(text)).strip()
    return re.sub(r"[\s_-]+", sep, cleaned).lower() or "teste"


def camel(text: str) -> str:
    """`campo usuario` -> `campoUsuario`. Nome de comando Cypress."""
    parts = [p for p in re.split(r"[^\w]+", _ascii(text)) if p]
    if not parts:
        return "acao"
    head, *tail = parts
    name = head.lower() + "".join(p.capitalize() for p in tail)
    # Um identificador JS não pode começar com dígito.
    return name if not name[:1].isdigit() else f"c{name}"


@dataclass
class CustomCommand:
    """Um comando customizado gerado a partir do fluxo."""

    name: str
    body: str
    doc: str
    replaces: list[str] = field(default_factory=list)


@dataclass
class Project:
    """Projeto Cypress completo, como um mapa caminho -> conteúdo."""

    files: dict[str, str] = field(default_factory=dict)
    commands: list[CustomCommand] = field(default_factory=list)
    env_keys: list[str] = field(default_factory=list)
    name: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "files": self.files,
            "fileList": sorted(self.files.keys()),
            "commands": [
                {"name": c.name, "doc": c.doc, "replaces": c.replaces}
                for c in self.commands
            ],
            "envKeys": self.env_keys,
        }


# ---------------------------------------------------------------------------
# Extração de comandos customizados
# ---------------------------------------------------------------------------

def _element_label(cmd: Command) -> str:
    """Nome legível do alvo, a partir do comentário do passo."""
    comment = cmd.comment or ""
    # Os rótulos vêm no formato: Preenche "usuário *" com "ana"
    quoted = re.search(r"[“\"']([^”\"']{2,40})[”\"']", comment)
    if quoted:
        return quoted.group(1)
    if cmd.target and cmd.target.value:
        attr = re.search(r'\[[\w-]+=["\']?([\w-]+)', cmd.target.value)
        if attr:
            return attr.group(1)
    return "elemento"


def _detect_login(spec: Spec) -> CustomCommand | None:
    """Reconhece a sequência de login e a transforma em `cy.login()`.

    Login é o candidato óbvio: aparece em praticamente todo fluxo, é sempre a
    mesma sequência e é o maior desperdício de tempo quando repetido. O comando
    gerado usa `cy.session()`, que faz o Cypress reaproveitar a sessão entre
    testes em vez de reautenticar a cada um.
    """
    typed = [c for c in spec.commands if c.op == "type" and c.target]
    if len(typed) < 2:
        return None

    secret = next(
        (c for c in typed if isinstance(c.value, dict) and "__env__" in c.value),
        None,
    )
    if secret is None:
        return None

    # O identificador é o último campo preenchido antes da senha.
    idx = spec.commands.index(secret)
    user_field = next(
        (c for c in reversed(spec.commands[:idx])
         if c.op == "type" and c.target and not isinstance(c.value, dict)),
        None,
    )
    if user_field is None:
        return None

    submit = next(
        (c for c in spec.commands[idx + 1:]
         if c.op == "click" and c.target),
        None,
    )
    if submit is None:
        return None

    env_key = secret.value["__env__"]
    visit = next((c for c in spec.commands if c.op == "visit"), None)
    visit_path = _relative(visit.value, spec.base_url) if visit else "/"

    user_sel = emit_cypress.js_string(user_field.target.value)
    pass_sel = emit_cypress.js_string(secret.target.value)
    submit_sel = emit_cypress.js_string(submit.target.value)
    user_value = emit_cypress.js_value(user_field.value)

    body = f"""Cypress.Commands.add('login', (usuario, senha) => {{
  const user = usuario ?? Cypress.env('USUARIO') ?? {user_value};
  const pass = senha ?? Cypress.env({emit_cypress.js_string(env_key)});

  cy.visit({emit_cypress.js_string(visit_path)});
  cy.get({user_sel}).should('be.visible').clear().type(user);
  cy.get({pass_sel}).should('be.visible').clear().type(pass, {{ log: false }});
  cy.get({submit_sel}).should('be.visible').click();
}});

// Otimizacao opcional: `cy.session` guarda cookies e localStorage entre os
// testes, evitando refazer o login a cada `it`. Numa suite grande a diferenca
// e enorme.
//
// Nao ativamos por padrao porque depende de como a aplicacao trata quem ja
// esta autenticado. `cy.session` restaura o armazenamento, mas nao a pagina:
// e preciso um `cy.visit` depois, e a aplicacao tem que reconhecer a sessao
// nessa rota. Muitas SPAs comecam sempre na tela de login e ignoram o storage
// ate o formulario ser enviado — nesses casos o teste quebra de um jeito
// confuso, reclamando de rota errada.
//
// Teste na sua aplicacao: faca login manualmente, va para a rota de destino e
// recarregue. Se continuar logado, pode usar a versao abaixo.
//
// Cypress.Commands.add('login', (usuario, senha) => {{
//   const user = usuario ?? Cypress.env('USUARIO') ?? {user_value};
//   const pass = senha ?? Cypress.env({emit_cypress.js_string(env_key)});
//   cy.session([user, pass], () => {{
//     cy.visit({emit_cypress.js_string(visit_path)});
//     cy.get({user_sel}).clear().type(user);
//     cy.get({pass_sel}).clear().type(pass, {{ log: false }});
//     cy.get({submit_sel}).click();
//     cy.location('pathname', {{ timeout: 10000 }}).should('not.include', 'login');
//   }});
//   cy.visit('<rota-que-reconhece-a-sessao>');
// }});"""

    return CustomCommand(
        name="login",
        body=body,
        doc="Autentica pelo formulário. Chame no `beforeEach`.",
        replaces=[user_field.target.value, secret.target.value, submit.target.value],
    )


def _detect_repeats(spec: Spec) -> list[CustomCommand]:
    """Seletores repetidos viram comandos nomeados.

    Em vez de avisar que há repetição e deixar o trabalho para depois, geramos
    o comando com um nome derivado do próprio elemento.
    """
    counts: Counter[str] = Counter()
    labels: dict[str, str] = {}

    for cmd in spec.commands:
        if not cmd.target or cmd.target.strategy != "css":
            continue
        counts[cmd.target.value] += 1
        labels.setdefault(cmd.target.value, _element_label(cmd))

    out: list[CustomCommand] = []
    used: set[str] = {"login"}

    for selector, count in counts.most_common():
        if count < _REPEAT_THRESHOLD:
            continue
        base = camel(labels.get(selector, "elemento"))
        name = base
        suffix = 2
        while name in used:
            name = f"{base}{suffix}"
            suffix += 1
        used.add(name)

        out.append(CustomCommand(
            name=name,
            body=(f"Cypress.Commands.add({emit_cypress.js_string(name)}, () =>\n"
                  f"  cy.get({emit_cypress.js_string(selector)}));"),
            doc=f"Atalho para `{selector}` — usado {count} vezes neste fluxo.",
            replaces=[selector],
        ))

    return out[:6]      # além disso vira poluição, não conveniência


# ---------------------------------------------------------------------------
# Arquivos do projeto
# ---------------------------------------------------------------------------

def _relative(url: str, base_url: str) -> str:
    """Converte uma URL absoluta em caminho relativo à baseUrl."""
    if not url:
        return "/"
    if base_url and url.startswith(base_url):
        rest = url[len(base_url):]
        return rest or "/"
    return url


def _rewrite_visits(code: str, base_url: str) -> str:
    """Troca `cy.visit('https://app/x')` por `cy.visit('/x')`.

    Com a `baseUrl` no config, caminhos relativos deixam o mesmo spec rodar
    em desenvolvimento, homologação e produção trocando uma variável — que é
    o ponto inteiro de ter uma `baseUrl`.
    """
    if not base_url:
        return code
    escaped = re.escape(base_url.rstrip("/"))
    return re.sub(
        rf"cy\.visit\((['\"]){escaped}([^'\"]*)\1\)",
        lambda m: f"cy.visit({m.group(1)}{m.group(2) or '/'}{m.group(1)})",
        code,
    )


def _apply_commands(code: str, commands: list[CustomCommand]) -> str:
    """Substitui as sequências extraídas pelas chamadas dos novos comandos."""
    for command in commands:
        if command.name == "login":
            continue          # o login é tratado à parte, no beforeEach
        for selector in command.replaces:
            code = code.replace(
                f"cy.get({emit_cypress.js_string(selector)})",
                f"cy.{command.name}()",
            )
    return code


def _without_login(spec: Spec, login: CustomCommand | None) -> tuple[Spec, str]:
    """Spec sem os comandos de login, e o caminho onde o fluxo continua.

    A remoção acontece na IR, não no texto emitido. Cortar linhas do código
    pronto deixava para trás os comentários que descreviam as ações removidas
    — o spec ficava narrando passos que não estavam mais lá.

    Devolve também o caminho a visitar depois, porque `cy.session()` restaura
    a sessão mas não carrega página nenhuma.

    Esse caminho é a URL de entrada original, não a rota onde o login
    aterrissou. Parece contraintuitivo, mas a rota pós-login costuma ser
    client-side: o servidor devolve 404 se você a pedir diretamente. Foi o que
    aconteceu ao testar contra o saucedemo — `cy.visit('/inventory.html')`
    quebrou com 404, enquanto `/` funciona e deixa a aplicação decidir para
    onde levar quem já está autenticado.
    """
    if not login:
        return spec, ""

    targets = set(login.replaces)
    kept: list[Command] = []
    entry = ""

    for cmd in spec.commands:
        # A ação de login em si e as verificações sobre os seus campos.
        if cmd.target and cmd.target.value in targets:
            continue
        # A navegação inicial vira parte do `beforeEach`.
        if cmd.op == "visit":
            if not entry:
                entry = _relative(cmd.value or "", spec.base_url)
            continue
        kept.append(cmd)

    landing = entry or "/"

    trimmed = Spec(
        name=spec.name, description=spec.description, base_url=spec.base_url,
        commands=kept, setup=spec.setup, env_keys=spec.env_keys,
        warnings=spec.warnings, suggestions=spec.suggestions, groups=spec.groups,
    )
    return trimmed, landing or "/"


def _config(spec: Spec) -> str:
    base = spec.base_url or "http://localhost:3000"
    return f"""const {{ defineConfig }} = require('cypress');

module.exports = defineConfig({{
  e2e: {{
    baseUrl: process.env.CYPRESS_BASE_URL || {emit_cypress.js_string(base)},
    supportFile: 'cypress/support/e2e.js',
    specPattern: 'cypress/e2e/**/*.cy.js',

    // Tempos generosos o bastante para uma CI carregada, sem esconder
    // lentidao real da aplicacao.
    defaultCommandTimeout: 8000,
    requestTimeout: 12000,
    responseTimeout: 20000,
    pageLoadTimeout: 40000,

    viewportWidth: 1440,
    viewportHeight: 900,

    video: false,
    screenshotOnRunFailure: true,

    // Uma nova tentativa em CI cobre instabilidade de rede sem mascarar bug:
    // um teste que so passa na segunda vez continua aparecendo no relatorio.
    retries: {{ runMode: 1, openMode: 0 }},

    setupNodeEvents(on, config) {{
      return config;
    }},
  }},
}});
"""


def _package_json(name: str) -> str:
    return json.dumps({
        "name": slug(name),
        "version": "1.0.0",
        "private": True,
        "description": f"Testes end-to-end: {name}",
        "scripts": {
            "test": "cypress run",
            "test:open": "cypress open",
            "test:chrome": "cypress run --browser chrome",
            "test:headed": "cypress run --headed",
        },
        "devDependencies": {"cypress": "^13.15.0"},
    }, indent=2, ensure_ascii=False) + "\n"


def _support_e2e() -> str:
    return """import './commands';

// Erros de JavaScript da aplicacao nao devem derrubar o teste por si sos: o
// objetivo aqui e validar o fluxo, e um erro de terceiro (analytics, chat)
// nao significa que o fluxo quebrou. Eles continuam visiveis no log.
Cypress.on('uncaught:exception', (err) => {
  console.warn('Erro nao tratado na aplicacao:', err.message);
  return false;
});
"""


def _commands_file(commands: list[CustomCommand], flow_name: str) -> str:
    out = [
        "// Comandos customizados gerados pelo Cygen a partir do fluxo",
        f"// \"{flow_name}\".",
        "//",
        "// Cada um substitui uma sequencia que se repetia no teste. Quando o",
        "// elemento mudar na aplicacao, o conserto acontece aqui, num lugar so.",
        "",
    ]
    if not commands:
        out.append("// Nenhuma repeticao suficiente para justificar um comando.")
        out.append("// Adicione os seus abaixo conforme a suite crescer.")
        return "\n".join(out) + "\n"

    for command in commands:
        out.append(f"// {command.doc}")
        out.append(command.body)
        out.append("")
    return "\n".join(out)


def _env_example(env_keys: list[str], base_url: str) -> str:
    lines = [
        "# Credenciais e configuracao do ambiente.",
        "#",
        "# Copie para `cypress.env.json` (que o .gitignore ja ignora) ou",
        "# exporte como variaveis de ambiente com o prefixo CYPRESS_.",
        "",
        "{",
        f'  "BASE_URL": {json.dumps(base_url or "http://localhost:3000")},',
    ]
    for key in env_keys:
        lines.append(f'  "{key}": "troque-por-um-valor-real",')
    if lines[-1].endswith(","):
        lines[-1] = lines[-1][:-1]
    lines.append("}")
    return "\n".join(lines) + "\n"


def _gitignore() -> str:
    return """node_modules/
cypress/videos/
cypress/screenshots/
cypress/downloads/

# Contem credenciais reais. Nunca versione.
cypress.env.json
.env
"""


def _readme(spec: Spec, commands: list[CustomCommand], filename: str) -> str:
    env_lines = "\n".join(
        f"$env:CYPRESS_{k} = \"seu-valor\"" for k in spec.env_keys
    ) or "# nenhuma credencial necessaria neste fluxo"

    cmd_lines = "\n".join(
        f"| `cy.{c.name}()` | {c.doc} |" for c in commands
    ) or "| — | nenhum comando extraido |"

    return f"""# {spec.name}

{spec.description or 'Teste end-to-end gerado pelo Cygen.'}

Projeto pronto para rodar. As assertions foram deduzidas do que a aplicacao
realmente fez durante a gravacao — nao de um palpite.

## Rodar

```powershell
npm install
```

Configure as credenciais (elas nunca ficam no codigo):

```powershell
{env_lines}
```

Ou copie `cypress.env.example.json` para `cypress.env.json` e preencha os
valores — esse arquivo ja esta no `.gitignore`.

Depois:

```powershell
npm test          # sem interface, como em CI
npm run test:open # abre o Cypress para acompanhar passo a passo
```

## Estrutura

```
cypress/
  e2e/{filename}
  support/
    commands.js    comandos customizados extraidos do fluxo
    e2e.js         configuracao global
cypress.config.js  baseUrl, timeouts e retentativas
```

## Comandos disponiveis

| Comando | O que faz |
|---|---|
{cmd_lines}

## Ambiente

A `baseUrl` esta em `cypress.config.js` e pode ser trocada sem editar o teste:

```powershell
$env:CYPRESS_BASE_URL = "https://homologacao.exemplo.com"
npm test
```

Os caminhos no spec sao relativos, entao o mesmo arquivo roda em qualquer
ambiente.
"""


# ---------------------------------------------------------------------------
# Montagem
# ---------------------------------------------------------------------------

def build(spec: Spec, *, verbose: bool = True,
          extract_commands: bool = True) -> Project:
    """Monta o projeto Cypress completo a partir da `Spec`."""
    project = Project(name=spec.name, env_keys=list(spec.env_keys))

    login = _detect_login(spec) if extract_commands else None
    repeats = _detect_repeats(spec) if extract_commands else []
    # Seletores já cobertos pelo login não viram comando próprio também.
    if login:
        covered = set(login.replaces)
        repeats = [c for c in repeats
                   if not any(sel in covered for sel in c.replaces)]

    commands = ([login] if login else []) + repeats
    project.commands = commands

    emit_spec, landing = _without_login(spec, login)
    code = emit_cypress.emit(emit_spec, verbose=verbose)
    code = _rewrite_visits(code, spec.base_url)

    if login:
        # O login vira pré-condição do teste. Ele já navega por dentro, então
        # nenhum `cy.visit` extra é necessário — nem correto: um visit depois
        # do login recarregaria a aplicação na rota de entrada.
        code = code.replace(
            "  it(",
            "  beforeEach(() => {\n    cy.login();\n  });\n\n  it(",
            1,
        )

    code = _apply_commands(code, commands)
    code = re.sub(r"\n{3,}", "\n\n", code)

    filename = emit_cypress.spec_filename(spec.name)

    project.files = {
        f"cypress/e2e/{filename}": code,
        "cypress/support/commands.js": _commands_file(commands, spec.name),
        "cypress/support/e2e.js": _support_e2e(),
        "cypress.config.js": _config(spec),
        "package.json": _package_json(spec.name),
        "cypress.env.example.json": _env_example(spec.env_keys, spec.base_url),
        ".gitignore": _gitignore(),
        "README.md": _readme(spec, commands, filename),
    }
    return project


def write_to_disk(project: Project, target: Any) -> list[str]:
    """Grava o projeto num diretório. Devolve os caminhos escritos."""
    from pathlib import Path

    root = Path(target)
    root.mkdir(parents=True, exist_ok=True)

    written: list[str] = []
    for relative, content in project.files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        written.append(str(path))
    return sorted(written)
