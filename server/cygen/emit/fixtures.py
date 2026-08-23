"""
Extração de seletores e valores para fixtures.

Um spec cheio de `cy.alvo(['#f_5b7d19', 'input[name="usr"]'])` é executável e
ilegível: quem lê precisa decifrar o seletor para descobrir de que campo se
trata, e quem mantém tem de caçar a mesma string em vinte linhas quando a tela
muda. O Cygen já sabe o nome de cada elemento — ele veio do rótulo, do
`aria-label` ou do texto do botão na hora da gravação. Aqui esse nome sai do
comentário e vira código.

O resultado é um par de fixtures:

    cypress/fixtures/elementos.json   nome legível -> cadeia de seletores
    cypress/fixtures/dados.json       nome legível -> valor digitado

e um spec que diz `cy.alvo(elementos.usuario)` em vez de repetir a cadeia. A
cadeia inteira sobrevive: trocar o literal por uma referência não custa as
reservas, que continuam no JSON, na mesma ordem.

Senhas nunca entram em `dados.json`. Elas já vivem em variáveis de ambiente, e
uma fixture é um arquivo comum, versionado com o resto do projeto — é
exatamente o lugar onde uma credencial não pode estar.
"""

from __future__ import annotations

import json
import re
import unicodedata
from typing import Any

from ..intel.selectors import looks_generated
from . import cypress as emit_cypress
from .ir import Command, Spec

# Palavras que descrevem a ação, não o elemento. Saem do nome: `botaoClicaEm`
# não diz mais do que `botaoEntrar`.
_RUIDO = {
    "clica", "clique", "clicar", "em", "no", "na", "o", "a", "de", "do", "da",
    "preenche", "preencher", "com", "seleciona", "selecionar", "marca",
    "marcar", "digita", "digitar", "campo", "botao", "abre", "abrir",
}

# Sufixos comuns de rótulo que não ajudam a identificar: "Usuário *" e
# "Usuário:" são o mesmo campo.
_ENFEITE = re.compile(r"[\s*:•·]+$")

# Trecho hexadecimal longo o bastante para ser hash, não palavra.
_HEX = re.compile(r"[0-9a-f]{6,}", re.I)


def _ascii(text: str) -> str:
    return (unicodedata.normalize("NFKD", text or "")
            .encode("ascii", "ignore").decode("ascii"))


def camel(text: str) -> str:
    """`Usuário *` -> `usuario`; `Nome do cliente` -> `nomeDoCliente`."""
    limpo = _ENFEITE.sub("", text or "")
    partes = [p for p in re.split(r"[^\w]+", _ascii(limpo)) if p]
    if not partes:
        return ""
    # Uma palavra só de ruído vira nome vazio; várias, tiramos só as de ruído
    # do começo, que é onde o verbo aparece.
    while len(partes) > 1 and partes[0].lower() in _RUIDO:
        partes.pop(0)
    cabeca, *resto = partes
    nome = cabeca.lower() + "".join(p.capitalize() for p in resto)
    return nome if not nome[:1].isdigit() else f"e{nome}"


def legivel(texto: str) -> bool:
    """O texto serve como nome de fixture?

    `looks_generated` cobre o que é obviamente de máquina, mas passa por pouco
    em casos como `f_5b7d19ae` — quatro dígitos em dez caracteres fica logo
    abaixo do limiar dela. Aqui o critério é outro e mais exigente, porque o
    propósito é diferente: não basta o valor ser estável, ele tem de ser *lido*
    por uma pessoa no meio de uma linha de teste.
    """
    if not texto or looks_generated(texto):
        return False
    if _HEX.search(_ascii(texto).replace("-", "").replace("_", "")):
        return False
    letras = sum(c.isalpha() for c in texto)
    digitos = sum(c.isdigit() for c in texto)
    # Precisa de palavra de verdade, e de poucos números no meio dela.
    return letras >= 3 and (digitos / max(len(texto), 1)) < 0.3


def label_of(cmd: Command) -> str:
    """O nome mais legível disponível para o alvo deste comando.

    A ordem é a da confiança: o rótulo que o usuário vê na tela vence o
    atributo técnico, que vence o seletor cru. É o mesmo critério que fez o
    elemento ser reconhecível durante a gravação.

    Valores que parecem gerados por máquina são recusados. `elementos.f_5b7d19`
    não é mais legível do que o seletor que ele substituiu — só mais longo — e
    o ponto de nomear era justamente parar de ler hash.
    """
    comment = cmd.comment or ""
    for candidato in re.findall(r"[“\"']([^”\"']{2,40})[”\"']", comment):
        if legivel(candidato):
            return candidato

    target = cmd.target
    if target and target.strategy == "text" and legivel(target.value):
        return target.value
    if target and target.value:
        attr = re.search(r'\[[\w-]+=["\']?([\w-]+)', target.value)
        if attr and legivel(attr.group(1)):
            return attr.group(1)
        ident = re.match(r"^#([\w-]+)$", target.value)
        if ident and legivel(ident.group(1)):
            return ident.group(1)
    return ""


def _unico(nome: str, usados: set[str], fallback: str) -> str:
    """Garante um nome livre, sem inventar sufixo quando não precisa."""
    base = nome or fallback
    if base not in usados:
        usados.add(base)
        return base
    i = 2
    while f"{base}{i}" in usados:
        i += 1
    usados.add(f"{base}{i}")
    return f"{base}{i}"


def extract(specs: list[Spec]) -> dict[str, Any]:
    """Percorre os fluxos e devolve os mapas de elementos e dados.

    Recebe uma lista porque numa sequência o mesmo campo aparece em vários
    fluxos: extraindo tudo junto, o elemento ganha um nome só e uma entrada só.

    Os **dados** seguem o caminho oposto quando há mais de um fluxo. O campo é
    o mesmo, o valor não: dois logins usam `#usuario`, um com `adm` e outro com
    `op`. Achatar os dois num `dados.usuario` faria o segundo teste anunciar o
    nome do primeiro — e a mensagem de encerramento passaria a mentir. Por isso
    numa sequência `dados` é agrupado por fluxo.
    """
    elementos: dict[str, list[str]] = {}
    dados: dict[str, Any] = {}
    por_cadeia: dict[str, str] = {}     # cadeia serializada -> nome já dado
    usados: set[str] = set()
    por_fluxo = len(specs) > 1

    for spec in specs:
        escopo = camel(spec.name) or "fluxo"
        if por_fluxo:
            dados.setdefault(escopo, {})
        alvo_dados = dados[escopo] if por_fluxo else dados
        for cmd in spec.commands:
            if cmd.op in ("comment", "intercept", "wait", "visit"):
                continue
            target = cmd.target
            if not target or target.strategy not in ("css", "text"):
                continue

            cadeia = emit_cypress.runtime_chain(target)
            if not cadeia:
                cadeia = [f"text={target.value}" if target.strategy == "text"
                          else target.value]

            assinatura = json.dumps(cadeia, ensure_ascii=False)
            nome = por_cadeia.get(assinatura)
            if nome is None:
                nome = _unico(camel(label_of(cmd)), usados,
                              f"elemento{len(elementos) + 1}")
                por_cadeia[assinatura] = nome
                elementos[nome] = cadeia

            # O valor digitado acompanha o campo, com o mesmo nome — assim
            # `dados.usuario` e `elementos.usuario` são o par óbvio.
            if cmd.op in ("type", "select") and cmd.value is not None:
                if isinstance(cmd.value, dict):
                    continue          # `__env__`: segredo, não vai para arquivo
                alvo_dados.setdefault(nome, cmd.value)

    return {"elementos": elementos, "dados": dados, "porCadeia": por_cadeia,
            "porFluxo": por_fluxo}


def rewrite(code: str, por_cadeia: dict[str, str]) -> str:
    """Troca as cadeias literais do código por referências à fixture.

    A substituição casa a cadeia inteira, não pedaços dela: um seletor pode ser
    prefixo de outro (`#user` e `#username`), e casar por trecho trocaria a
    referência errada.
    """
    for assinatura, nome in por_cadeia.items():
        cadeia = json.loads(assinatura)
        code = code.replace(emit_cypress.emit_chain(cadeia),
                            f"cy.alvo(elementos.{nome})")

        # Alvos sem reservas saem como `cy.get('sel')` ou `cy.contains('txt')`.
        if len(cadeia) == 1:
            unico = cadeia[0]
            alvo = (f"cy.contains({emit_cypress.js_string(unico[5:])})"
                    if unico.startswith("text=")
                    else f"cy.get({emit_cypress.js_string(unico)})")
            code = code.replace(alvo, f"cy.alvo(elementos.{nome})")
    return code


def imports_line() -> str:
    """O `import` que o spec precisa para enxergar as fixtures.

    Import estático, não `cy.fixture()`. As duas formas leem o mesmo arquivo,
    mas `cy.fixture` é assíncrona: o valor só existe dentro de um `.then`, e o
    spec inteiro teria de ser aninhado para usar um seletor. O import deixa
    `elementos.usuario` legível na linha onde ele é usado — que é o ponto de
    extrair os nomes.
    """
    return ("import elementos from '../fixtures/elementos.json';\n"
            "import dados from '../fixtures/dados.json';")


def files(mapa: dict[str, Any]) -> dict[str, str]:
    """Os arquivos de fixture, prontos para gravar."""
    return {
        "cypress/fixtures/elementos.json":
            json.dumps(mapa["elementos"], ensure_ascii=False, indent=2) + "\n",
        "cypress/fixtures/dados.json":
            json.dumps(mapa["dados"], ensure_ascii=False, indent=2) + "\n",
    }


# ---------------------------------------------------------------------------
# Mensagem de encerramento
# ---------------------------------------------------------------------------

# Campos cujo valor identifica quem está usando o sistema. Serve para dizer
# "para o user ana" em vez de só "concluído", que não distingue uma execução da
# outra quando a suíte roda com várias contas.
_ATOR = re.compile(r"usuario|usuário|user|login|email|e-mail|conta|cpf|matricula",
                   re.I)


def actor_key(mapa: dict[str, Any], spec_name: str = "") -> str | None:
    """Caminho, dentro de `dados`, do valor que identifica o ator do teste.

    Numa sequência os dados são agrupados por fluxo, então o caminho tem dois
    níveis: `loginDoOperador.usuario`. É o que garante que cada teste anuncie a
    conta que ele de fato usou.
    """
    if mapa.get("porFluxo"):
        escopo = camel(spec_name) or "fluxo"
        for nome in mapa["dados"].get(escopo, {}):
            if _ATOR.search(nome):
                return f"{escopo}.{nome}"
        return None
    for nome in mapa["dados"]:
        if _ATOR.search(nome):
            return nome
    return None


def closing_line(spec_name: str, mapa: dict[str, Any], indent: str) -> list[str]:
    """A linha que fecha o teste, dizendo o que terminou e para quem.

    Vai para o log do Cypress e para a saída do terminal. A segunda parte
    importa: numa suíte com vários testes, o stdout é o único lugar onde dá
    para ver, depois do fato, o que rodou e com qual conta.
    """
    ator = actor_key(mapa, spec_name)
    titulo = emit_cypress.js_string(spec_name)
    # O nome do teste entra num template literal; crase e `${` dentro dele
    # quebrariam a string.
    seguro = spec_name.replace("\\", "\\\\").replace("`", "\\`").replace("${", "\\${")

    if ator:
        texto = f"`Teste de {seguro} para o user ${{dados.{ator}}} concluído`"
        nota = f"{{ teste: {titulo}, ator: dados.{ator} }}"
    else:
        texto = f"`Teste de {seguro} concluído`"
        nota = f"{{ teste: {titulo} }}"

    return [
        "",
        f"{indent}// Fecha o teste dizendo o que terminou — e para quem.",
        f"{indent}cy.log({texto});",
        f"{indent}cy.task('cygenNota', {nota}, {{ log: false }});",
    ]
