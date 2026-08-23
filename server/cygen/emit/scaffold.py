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
from . import fixtures
from .cypress import INDENT
from .ir import Command, Spec, Suite

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
    chain: list[str] = field(default_factory=list)


@dataclass
class Project:
    """Projeto Cypress completo, como um mapa caminho -> conteúdo."""

    files: dict[str, str] = field(default_factory=dict)
    commands: list[CustomCommand] = field(default_factory=list)
    env_keys: list[str] = field(default_factory=list)
    name: str = ""
    # nome legível -> cadeia de seletores, como foi para `elementos.json`
    fixtures: dict[str, list[str]] = field(default_factory=dict)

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
            "fixtures": self.fixtures,
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


def _resolver(target: Any) -> str:
    """Expressão que resolve um alvo: cadeia quando há reservas, `cy.get` senão."""
    chain = emit_cypress.runtime_chain(target)
    if chain:
        return emit_cypress.emit_chain(chain)
    return f"cy.get({emit_cypress.js_string(target.value)})"


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

    # O login é o passo que mais dói quando quebra: sem ele, todo teste da
    # suite falha por um motivo que não é o dele. Aqui as cadeias de reserva
    # valem mais que em qualquer outro lugar.
    user_at = _resolver(user_field.target)
    pass_at = _resolver(secret.target)
    submit_at = _resolver(submit.target)

    body = f"""Cypress.Commands.add('login', (usuario, senha) => {{
  const user = usuario ?? Cypress.env('USUARIO') ?? {user_value};
  const pass = senha ?? Cypress.env({emit_cypress.js_string(env_key)});

  cy.visit({emit_cypress.js_string(visit_path)});
  {user_at}.should('be.visible').clear().type(user);
  {pass_at}.should('be.visible').clear().type(pass, {{ log: false }});
  {submit_at}.should('be.visible').click();
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
    chains: dict[str, list[str]] = {}

    for cmd in spec.commands:
        if not cmd.target or cmd.target.strategy != "css":
            continue
        counts[cmd.target.value] += 1
        labels.setdefault(cmd.target.value, _element_label(cmd))
        # A cadeia do elemento entra no comando extraído: assim a reserva
        # continua valendo depois da abstração, e não só antes dela.
        if cmd.target.value not in chains:
            chains[cmd.target.value] = emit_cypress.runtime_chain(cmd.target)

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

        chain = chains.get(selector) or []
        resolver = (emit_cypress.emit_chain(chain) if chain
                    else f"cy.get({emit_cypress.js_string(selector)})")
        reservas = (f" {len(chain) - 1} reserva(s) embutida(s)." if chain else "")

        out.append(CustomCommand(
            name=name,
            body=(f"Cypress.Commands.add({emit_cypress.js_string(name)}, () =>\n"
                  f"  {resolver});"),
            doc=f"Atalho para `{selector}` — usado {count} vezes neste fluxo.{reservas}",
            replaces=[selector],
            chain=chain,
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


def _inject_before_each(code: str, chamada: str) -> str:
    """Insere um `beforeEach` logo depois da linha do `describe`.

    Ancorar no primeiro `it(` — como esta função fazia antes — colocava o
    bloco *entre* o comentário que descreve o teste e o teste em si, deixando
    a explicação de um `it()` pairando sobre o `beforeEach`.
    """
    linhas = code.splitlines()
    for i, linha in enumerate(linhas):
        if linha.startswith("describe("):
            linhas[i + 1:i + 1] = [
                f"{INDENT}beforeEach(() => {{",
                f"{INDENT * 2}{chamada}",
                f"{INDENT}}});",
                "",
            ]
            break
    return "\n".join(linhas) + "\n"


def _apply_commands(code: str, commands: list[CustomCommand]) -> str:
    """Substitui as sequências extraídas pelas chamadas dos novos comandos.

    O alvo pode ter sido emitido de duas formas — `cy.get('sel')` quando ele é
    único, `cy.alvo(['sel', ...reservas])` quando tem cadeia. As duas precisam
    ser reconhecidas: casar só a primeira deixava o spec com uma mistura de
    `cy.botaoEntrar()` e cadeias literais para o mesmo elemento.
    """
    for command in commands:
        if command.name == "login":
            continue          # o login é tratado à parte, no beforeEach
        for selector in command.replaces:
            literal = emit_cypress.js_string(selector)
            code = code.replace(f"cy.get({literal})", f"cy.{command.name}()")
            code = re.sub(
                rf"cy\.alvo\(\[{re.escape(literal)}(?:,[^\]]*)?\]\)",
                f"cy.{command.name}()",
                code,
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
      // `cy.alvo` avisa daqui quando precisou de uma reserva. O navegador nao
      // escreve no stdout da execucao; o processo Node escreve, e e essa saida
      // que o Cygen le para dizer quais seletores estao envelhecendo.
      on('task', {{
        cygenReserva({{ primario, usado }}) {{
          console.log(`CYGEN_RESERVA ${{primario}} >> ${{usado}}`);
          return null;
        }},
        // Encerramento de cada teste. O `cy.log` aparece so na interface do
        // Cypress; esta linha e a que sobra no stdout da execucao, que e onde
        // se olha depois que a suite terminou.
        cygenNota({{ teste, ator }}) {{
          console.log(ator
            ? `✓ Teste de ${{teste}} para o user ${{ator}} concluído`
            : `✓ Teste de ${{teste}} concluído`);
          return null;
        }},
      }});
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


def _alvo_file() -> str:
    """O comando `cy.alvo`: resolve um elemento tentando a cadeia de reservas.

    Sem isto, a cadeia de seletores só existia antes da entrega — a auto-cura
    rodava no Playwright, escolhia o melhor e congelava esse no arquivo. Na
    primeira mudança de tela depois disso, o teste dava timeout com uma única
    opção na mão e as outras a um comentário de distância.
    """
    return """/* Resolucao de elemento com cadeia de reservas.
 *
 * `cy.get` tem uma unica chance: o seletor casa ou o teste morre de timeout.
 * Mas o Cygen conhece varios seletores para cada elemento, ranqueados por
 * confiabilidade na hora da gravacao. `cy.alvo` usa essa lista: tenta todos em
 * ordem dentro da mesma janela de espera e segue com o primeiro que casar.
 *
 * O ganho nao e mascarar mudanca na aplicacao — e distinguir dois casos que o
 * timeout do `cy.get` confunde. Se uma reserva resolve, o elemento continua la
 * e so o gancho mudou: o teste passa e o relatorio avisa qual reserva salvou.
 * Se nenhuma resolve, o elemento sumiu de verdade, e a mensagem de erro lista
 * tudo que foi tentado em vez de mostrar um seletor solto.
 */

// Intervalo entre tentativas. Curto o bastante para nao somar atraso
// perceptivel, longo o bastante para nao ocupar a fila do Cypress a toa.
const INTERVALO = 100;

function candidatos(cadeia) {
  return (Array.isArray(cadeia) ? cadeia : [cadeia]).filter(Boolean);
}

function ehTexto(seletor) {
  return seletor.startsWith('text=');
}

function escaparAspas(valor) {
  return String(valor).replace(/\\\\/g, '\\\\\\\\').replace(/"/g, '\\\\"');
}

/**
 * Elementos que casam com um candidato, agora, sem esperar.
 *
 * `text=Entrar` nao vira `:contains("Entrar")` direto porque `:contains` casa
 * com todo ancestral que contem o texto — `html`, `body` e cada `div` do
 * caminho. Filtramos para os que nao tem descendente com o mesmo texto, que e
 * o mesmo criterio do `cy.contains`: o elemento mais profundo.
 */
function casam(seletor) {
  if (ehTexto(seletor)) {
    const alvo = `:contains("${escaparAspas(seletor.slice(5))}")`;
    return Cypress.$(alvo).filter((_, el) => Cypress.$(el).find(alvo).length === 0);
  }
  return Cypress.$(seletor);
}

/** Primeiro seletor da lista que casa com algo AGORA, sem esperar. */
function primeiroPresente(lista) {
  for (const seletor of lista) {
    try {
      if (casam(seletor).length > 0) return seletor;
    } catch (erro) {
      // Seletor invalido para o motor do jQuery (regex de i18n, sintaxe de
      // outro framework). Nao e motivo para derrubar a cadeia inteira.
    }
  }
  return null;
}

Cypress.Commands.add('alvo', (cadeia, opcoes = {}) => {
  const lista = candidatos(cadeia);
  const limite = opcoes.timeout || Cypress.config('defaultCommandTimeout');
  const primario = lista[0];

  const tentar = (restante) => {
    const achado = primeiroPresente(lista);

    if (achado) {
      if (achado !== primario) {
        // Reserva assumiu. Registrado no log do teste e no stdout da execucao,
        // porque um seletor que precisou de reserva hoje quebra de vez amanha.
        Cypress.log({
          name: 'alvo',
          message: `reserva: ${achado}`,
          consoleProps: () => ({ primario, usado: achado, cadeia: lista }),
        });
        cy.task('cygenReserva', { primario, usado: achado }, { log: false });
      }
      // Um seletor pode casar com mais de um elemento — `[data-cy="linha"] td`
      // pega todas as celulas da linha. Sem o `.first()`, o `.click()` seguinte
      // falha por ambiguidade, e o teste morre com um erro que fala de numero
      // de elementos em vez de falar do passo. Agir sobre o primeiro e o que o
      // Cygen ja avisa no aviso de geracao.
      const achados = casam(achado).length;
      if (achados > 1) {
        Cypress.log({ name: 'alvo',
                      message: `${achado} casa com ${achados}; usando o primeiro` });
      }
      return ehTexto(achado)
        ? cy.contains(achado.slice(5), { timeout: limite, log: false }).first()
        : cy.get(achado, { timeout: limite, log: false }).first();
    }

    if (restante <= 0) {
      const tentativas = lista.map((s, i) => `  ${i + 1}. ${s}`).join('\\n');
      throw new Error(
        `Nenhum dos ${lista.length} seletores encontrou o elemento em ` +
        `${limite}ms.\\n\\nTentados, em ordem de confiabilidade:\\n${tentativas}\\n\\n` +
        `Se o elemento existe na tela, o gancho mudou: regrave este passo. ` +
        `Se nao existe, o fluxo nao chegou ate aqui — veja o passo anterior.`
      );
    }

    return cy.wait(INTERVALO, { log: false })
      .then(() => tentar(restante - INTERVALO));
  };

  return tentar(limite);
});
"""


def _support_e2e() -> str:
    return """import './alvo';
import './commands';

// Erros de JavaScript da aplicacao nao devem derrubar o teste por si sos: o
// objetivo aqui e validar o fluxo, e um erro de terceiro (analytics, chat)
// nao significa que o fluxo quebrou. Eles continuam visiveis no log.
Cypress.on('uncaught:exception', (err) => {
  console.warn('Erro nao tratado na aplicacao:', err.message);
  return false;
});
"""


def _commands_file(commands: list[CustomCommand], flow_name: str,
                   *, header: str = "") -> str:
    out = []
    if header:
        # As fixtures são importadas aqui, e não no spec: é neste arquivo que
        # os seletores aparecem depois que cada fluxo virou um comando.
        out.append(header)
        out.append("")
    out += [
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
    alvo.js        cy.alvo: resolve elementos pela cadeia de reservas
    commands.js    comandos customizados extraidos do fluxo
    e2e.js         configuracao global
cypress.config.js  baseUrl, timeouts e retentativas
```

## Seletores com reserva

Onde o teste chama `cy.alvo([...])`, a lista vem ordenada por confiabilidade:
o primeiro item e o seletor escolhido na gravacao, os seguintes sao reservas
medidas no mesmo elemento. Em execucao, o Cypress tenta todos dentro da mesma
janela de espera e segue com o primeiro que casar.

Quando uma reserva assume, a saida traz uma linha `CYGEN_RESERVA` dizendo qual
seletor falhou e qual salvou — sinal de que aquele gancho esta envelhecendo e
vale um `data-cy` no elemento. Quando nenhuma casa, o erro lista tudo que foi
tentado, em vez de mostrar um seletor solto.

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
          extract_commands: bool = True, use_fixtures: bool = True) -> Project:
    """Monta o projeto Cypress completo a partir da `Spec`."""
    project = Project(name=spec.name, env_keys=list(spec.env_keys))

    login = _detect_login(spec) if extract_commands else None

    # Um fluxo que é só o login não pode ter o login extraído: sobraria um
    # `it()` sem nenhum comando, e um teste vazio passa sempre. Quando o fluxo
    # inteiro é entrar no sistema, entrar no sistema é o teste.
    if login and not _without_login(spec, login)[0].commands:
        login = None

    # Ver a nota em `build_suite`: com fixtures, o atalho por repetição vira
    # um comando sem chamador.
    repeats = ([] if use_fixtures
               else (_detect_repeats(spec) if extract_commands else []))
    # Seletores já cobertos pelo login não viram comando próprio também.
    if login:
        covered = set(login.replaces)
        repeats = [c for c in repeats
                   if not any(sel in covered for sel in c.replaces)]

    commands = ([login] if login else []) + repeats
    project.commands = commands

    emit_spec, landing = _without_login(spec, login)

    # As fixtures descrevem o que o spec usa. Extrair do fluxo original
    # incluiria os campos de login que foram para o `commands.js` — entradas
    # que ninguém referencia, e que dariam a impressão de que o teste toca
    # elementos que ele não toca.
    mapa = fixtures.extract([emit_spec]) if use_fixtures else None

    code = emit_cypress.emit(
        emit_spec, verbose=verbose,
        header=fixtures.imports_line() if mapa else "",
        closing=fixtures.closing_line(spec.name, mapa, INDENT * 2) if mapa else None,
    )
    code = _rewrite_visits(code, spec.base_url)
    if mapa:
        code = fixtures.rewrite(code, mapa["porCadeia"])

    if login:
        # O login vira pré-condição do teste. Ele já navega por dentro, então
        # nenhum `cy.visit` extra é necessário — nem correto: um visit depois
        # do login recarregaria a aplicação na rota de entrada.
        code = _inject_before_each(code, "cy.login();")

    code = _apply_commands(code, commands)
    code = re.sub(r"\n{3,}", "\n\n", code)

    filename = emit_cypress.spec_filename(spec.name)

    project.files = {
        f"cypress/e2e/{filename}": code,
        "cypress/support/alvo.js": _alvo_file(),
        "cypress/support/commands.js": _commands_file(commands, spec.name),
        "cypress/support/e2e.js": _support_e2e(),
        "cypress.config.js": _config(spec),
        "package.json": _package_json(spec.name),
        "cypress.env.example.json": _env_example(spec.env_keys, spec.base_url),
        ".gitignore": _gitignore(),
        "README.md": _readme(spec, commands, filename),
    }
    if mapa:
        project.files.update(fixtures.files(mapa))
        project.fixtures = mapa["elementos"]
    return project


def _flow_commands(suite: Suite, mapa: dict[str, Any] | None, *, verbose: bool,
                   base_url: str, extras: list[CustomCommand]) -> list[CustomCommand]:
    """Um comando nomeado por fluxo da sequência.

    O nome sai do nome do fluxo: `Entra no sistema` vira `cy.entraNoSistema()`.
    Nomes descritivos importam mais aqui do que em qualquer outro comando
    gerado — é o que o `it()` mostra, e é a única coisa que o arquivo da
    sequência diz sobre o que aquele teste faz.
    """
    usados = {c.name for c in extras} | {"login", "alvo"}
    out: list[CustomCommand] = []

    for spec in suite.specs:
        nome = camel(spec.name) or f"fluxo{len(out) + 1}"
        while nome in usados:
            nome = f"{nome}Fluxo"
        usados.add(nome)

        corpo = emit_cypress._emit_body(
            spec, INDENT, verbose=verbose,
            closing=fixtures.closing_line(spec.name, mapa, INDENT) if mapa else None,
        )
        texto = "\n".join(corpo)
        texto = _rewrite_visits(texto, base_url)
        if mapa:
            texto = fixtures.rewrite(texto, mapa["porCadeia"])
        texto = _apply_commands(texto, extras)
        texto = re.sub(r"\n{3,}", "\n\n", texto)

        out.append(CustomCommand(
            name=nome,
            body=(f"Cypress.Commands.add({emit_cypress.js_string(nome)}, () => {{\n"
                  f"{texto}\n}});"),
            doc=spec.description or f"executa o fluxo “{spec.name}”.",
        ))
    return out


def build_suite(suite: Suite, *, verbose: bool = True,
                extract_commands: bool = True,
                use_fixtures: bool = True) -> Project:
    """Projeto Cypress de uma sequência: um arquivo, um `it()` por fluxo.

    A detecção de login e de repetições roda sobre os fluxos **juntos**, não um
    a um. Numa sequência é normal que só o primeiro fluxo tenha a tela de login
    e que um mesmo seletor apareça duas vezes em fluxos diferentes — olhando
    cada fluxo isoladamente, nenhum dos dois padrões atingiria o limiar, e a
    sequência sairia repetindo o que um comando resolveria.
    """
    project = Project(name=suite.name, env_keys=list(suite.env_keys))

    # Spec de mentira, só para a detecção enxergar a sequência inteira de uma
    # vez. Não é emitida: serve de lente sobre os comandos de todos os fluxos.
    combined = Spec(
        name=suite.name, base_url=suite.base_url,
        commands=[c for s in suite.specs for c in s.commands],
        env_keys=list(suite.env_keys),
    )

    # Extrair o login para um `beforeEach` só faz sentido quando cada teste
    # começa com a sessão limpa. Numa sequência encadeada a sessão atravessa os
    # testes: relogar antes de cada um é trabalho jogado fora — e pior, esvazia
    # o primeiro teste, aquele cujo assunto é justamente entrar no sistema. Um
    # `it()` sem nenhum comando passa sempre, e passar sem testar nada é o pior
    # resultado possível para uma suíte.
    login = _detect_login(combined) if (extract_commands and suite.isolate) else None
    # Atalhos para seletor repetido (`cy.usuario()`) e fixtures resolvem o
    # mesmo problema: dar nome ao elemento. Com as duas ligadas, o arquivo
    # ganhava um comando que ninguém chamava, porque o corpo já falava
    # `elementos.usuario`. A fixture vence — ela guarda a cadeia inteira num
    # lugar só e serve aos dois arquivos.
    repeats = ([] if use_fixtures
               else (_detect_repeats(combined) if extract_commands else []))
    if login:
        covered = set(login.replaces)
        repeats = [c for c in repeats
                   if not any(sel in covered for sel in c.replaces)]

    commands = ([login] if login else []) + repeats
    project.commands = commands

    trimmed = Suite(name=suite.name, description=suite.description,
                    base_url=suite.base_url, isolate=suite.isolate)
    for spec in suite.specs:
        cut, _ = _without_login(spec, login)
        # Um fluxo que era só o login não sobrevive à extração. Ele não vira um
        # teste vazio: o `beforeEach` já faz o que ele fazia.
        if login and not cut.commands:
            continue
        trimmed.specs.append(cut)

    # As fixtures saem dos fluxos já sem o login: se ele virou `beforeEach`, os
    # campos de usuário e senha não aparecem mais no corpo dos testes, e um
    # `elementos.senha` que ninguém referencia é ruído no arquivo.
    mapa = fixtures.extract(trimmed.specs) if use_fixtures else None

    # Cada fluxo vira um comando nomeado. O `.cy.js` da sequência passa a ser o
    # índice do que roda e em que ordem — que é a pergunta que se faz a ele —
    # enquanto o passo a passo mora no `commands.js`, um bloco por fluxo. Com
    # os corpos inline, o arquivo da sequência crescia até a sequência sumir
    # dentro dele.
    fluxos = _flow_commands(trimmed, mapa, verbose=verbose,
                            base_url=suite.base_url, extras=commands)
    chamada = {s.name: f"cy.{c.name}();" for s, c in zip(trimmed.specs, fluxos)}

    code = emit_cypress.emit_suite(
        trimmed, verbose=verbose,
        body_for=lambda s: [f"{INDENT * 2}{chamada[s.name]}"],
    )

    if login:
        code = _inject_before_each(code, "cy.login();")

    code = re.sub(r"\n{3,}", "\n\n", code)
    project.commands = commands + fluxos

    filename = emit_cypress.spec_filename(suite.name)
    spec_for_config = Spec(name=suite.name, description=suite.description,
                           base_url=suite.base_url, env_keys=suite.env_keys)

    project.files = {
        f"cypress/e2e/{filename}": code,
        "cypress/support/alvo.js": _alvo_file(),
        "cypress/support/commands.js": _commands_file(
            project.commands, suite.name,
            header=fixtures.imports_line() if mapa else ""),
        "cypress/support/e2e.js": _support_e2e(),
        "cypress.config.js": _config(spec_for_config),
        "package.json": _package_json(suite.name),
        "cypress.env.example.json": _env_example(suite.env_keys, suite.base_url),
        ".gitignore": _gitignore(),
        # O README descreve o que foi de fato emitido: `trimmed` pode ter menos
        # testes que `suite`, quando um fluxo virou o `beforeEach` de todos.
        "README.md": _suite_readme(trimmed, project.commands, filename),
    }
    if mapa:
        project.files.update(fixtures.files(mapa))
        project.fixtures = mapa["elementos"]
    return project


def _suite_readme(suite: Suite, commands: list[CustomCommand],
                  filename: str) -> str:
    env_lines = "\n".join(
        f"$env:CYPRESS_{k} = \"seu-valor\"" for k in suite.env_keys
    ) or "# nenhuma credencial necessaria nesta sequencia"

    cmd_lines = "\n".join(
        f"| `cy.{c.name}()` | {c.doc} |" for c in commands
    ) or "| — | nenhum comando extraido |"

    testes = "\n".join(
        f"{i}. **{s.name}** — {s.description or 'fluxo gravado'}"
        for i, s in enumerate(suite.specs, 1)
    )

    isolamento = (
        "Cada teste comeca com sessao limpa (`testIsolation` ligado): eles sao\n"
        "independentes e podem rodar em qualquer ordem."
        if suite.isolate else
        "Os testes compartilham sessao, cookies e armazenamento\n"
        "(`testIsolation: false`) — e por isso que o segundo continua de onde o\n"
        "primeiro parou. A ordem importa, e uma falha no meio costuma derrubar\n"
        "os testes seguintes: ao investigar, comece pela primeira falha."
    )

    return f"""# {suite.name}

{suite.description or 'Sequencia de testes end-to-end gerada pelo Cygen.'}

## Os testes, na ordem

{testes}

{isolamento}

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

Para rodar um teste sozinho, use o filtro do Cypress:

```powershell
npx cypress run --spec "cypress/e2e/{filename}" --env grep="nome do teste"
```

## Estrutura

```
cypress/
  e2e/{filename}   todos os testes da sequencia
  support/
    alvo.js        cy.alvo: resolve elementos pela cadeia de reservas
    commands.js    comandos customizados extraidos dos fluxos
    e2e.js         configuracao global
cypress.config.js  baseUrl, timeouts e retentativas
```

## Comandos disponiveis

| Comando | O que faz |
|---|---|
{cmd_lines}
"""


def write_to_disk(project: Project, target: Any) -> list[str]:
    """Grava o projeto num diretório. Devolve os caminhos escritos.

    Specs antigos que não fazem mais parte do projeto são removidos. Sem isso,
    renomear um teste deixava o arquivo anterior em `cypress/e2e/` — e o
    Cypress, que roda tudo que casa com o padrão, executaria as duas versões:
    a nova e a que o usuário acabou de substituir.
    """
    from pathlib import Path

    root = Path(target)
    root.mkdir(parents=True, exist_ok=True)

    written: list[str] = []
    for relative, content in project.files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        written.append(str(path))

    atuais = {
        (root / relative).resolve()
        for relative in project.files
        if relative.startswith("cypress/e2e/")
    }
    e2e = root / "cypress" / "e2e"
    if e2e.is_dir():
        for antigo in e2e.glob("*.cy.js"):
            if antigo.resolve() not in atuais:
                try:
                    antigo.unlink()
                except OSError:
                    pass          # arquivo aberto no editor: fica para a próxima

    return sorted(written)
