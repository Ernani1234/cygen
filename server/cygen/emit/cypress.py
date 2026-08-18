"""
Emissor Cypress.

Traduz a IR para um spec `.cy.js` idiomático. Três coisas que a v2 não fazia:

    1. Escape correto — `O'Brien` não quebra mais o arquivo gerado.
    2. Cadeia de reserva — cada seletor primário carrega suas alternativas num
       comentário, e a auto-cura sabe usá-las.
    3. Espera determinística — `cy.wait('@alias')` em vez de `cy.wait(3000)`.
"""

from __future__ import annotations

import json
import re
import unicodedata
from typing import Any

from .ir import Check, Command, Spec, Target

INDENT = "  "


# ---------------------------------------------------------------------------
# Serialização segura de literais
# ---------------------------------------------------------------------------

def js_string(value: str) -> str:
    """String Python → literal JS entre aspas simples, com escape completo."""
    if value is None:
        return "''"
    escaped = (
        str(value)
        .replace("\\", "\\\\")
        .replace("'", "\\'")
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace("\t", "\\t")
    )
    return f"'{escaped}'"


def js_value(value: Any) -> str:
    """Qualquer valor Python → literal JS."""
    if isinstance(value, dict):
        if "__env__" in value:
            return f"Cypress.env({js_string(value['__env__'])})"
        if "regex" in value:
            return value["regex"]          # já é um literal de regex JS
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list):
        return "[" + ", ".join(js_value(v) for v in value) + "]"
    return js_string(str(value))


# ---------------------------------------------------------------------------
# Alvos
# ---------------------------------------------------------------------------

def emit_target(target: Target | None) -> str:
    """Alvo da IR → expressão Cypress que o resolve."""
    if target is None:
        return "cy.get('body')"
    if target.strategy == "url":
        return "cy.url()"
    if target.strategy == "title":
        return "cy.title()"
    if target.strategy == "window":
        return "cy.window()"
    if target.strategy == "text":
        return f"cy.contains({js_string(target.value)})"
    if target.strategy == "role":
        return f"cy.get({js_string(f'[role={target.value}]')})"
    if target.strategy == "xpath":
        # Cypress não tem XPath nativo; emitimos o plugin com um aviso.
        return f"cy.xpath({js_string(target.value)})"
    return f"cy.get({js_string(target.value)})"


def emit_checks(checks: list[Check]) -> str:
    """Lista de verificações → cadeia `.should(...)`."""
    parts = []
    for check in checks:
        parts.append(emit_check(check))
    return "".join(parts)


def emit_check(check: Check) -> str:
    """Uma verificação → um `.should(...)` (ou equivalente)."""
    name = check.name
    args = check.args or []

    # Assertions de URL/título já vêm com o sujeito embutido no alvo.
    alias_map = {
        "url.include": ("include", 1),
        "url.not.include": ("not.include", 1),
        "url.eq": ("eq", 1),
        "url.match": ("match", 1),
        "title.include": ("include", 1),
        "title.eq": ("eq", 1),
        "have.attr.exists": ("have.attr", 1),
    }
    if name in alias_map:
        mapped, _ = alias_map[name]
        rendered = ", ".join(js_value(a) for a in args)
        return f".should({js_string(mapped)}, {rendered})" if args else f".should({js_string(mapped)})"

    if name == "location.pathname":
        return ""      # tratado como comando próprio em emit_command
    if name == "location.hash":
        return ""
    if name == "location.search":
        return ""
    if name.startswith("response.") or name.startswith("request."):
        return ""      # idem — precisa de `.its()` antes
    if name.startswith("localStorage.") or name.startswith("cookie."):
        return ""

    if name.startswith("have.attr.aria-"):
        attr = name.replace("have.attr.", "")
        rendered = ", ".join(js_value(a) for a in args) if args else js_string("true")
        return f".should('have.attr', {js_string(attr)}, {rendered})"

    if not args:
        return f".should({js_string(name)})"
    rendered = ", ".join(js_value(a) for a in args)
    return f".should({js_string(name)}, {rendered})"


def _emit_special_assert(cmd: Command, indent: str) -> list[str] | None:
    """Assertions que exigem uma forma sintática própria em Cypress."""
    if not cmd.checks:
        return None
    check = cmd.checks[0]
    name = check.name
    args = check.args or []

    if name == "location.pathname":
        return [f"{indent}cy.location('pathname').should('eq', {js_value(args[0])});"]
    if name == "location.hash":
        return [f"{indent}cy.location('hash').should('eq', {js_value(args[0])});"]
    if name == "location.search":
        return [f"{indent}cy.location('search').should('include', {js_value(args[0])});"]
    if name == "localStorage.exists":
        return [f"{indent}cy.window().its('localStorage')"
                f".invoke('getItem', {js_value(args[0])}).should('exist');"]
    if name == "localStorage.not.exists":
        return [f"{indent}cy.window().its('localStorage')"
                f".invoke('getItem', {js_value(args[0])}).should('be.null');"]
    if name == "cookie.exists":
        return [f"{indent}cy.getCookie({js_value(args[0])}).should('exist');"]
    return None


def _response_expectation(check: Check) -> str | None:
    """Uma verificação de resposta → uma linha de `expect(...)` do Chai."""
    name, args = check.name, check.args or []
    if name == "response.status":
        return f"expect(response.statusCode).to.eq({js_value(args[0])});"
    if name == "response.status.range":
        return (f"expect(response.statusCode)"
                f".to.be.within({js_value(args[0])}, {js_value(args[1])});")
    if name == "request.method":
        return f"expect(request.method).to.eq({js_value(args[0])});"
    if name == "response.body.property":
        if len(args) >= 2:
            return (f"expect(response.body)"
                    f".to.have.property({js_value(args[0])}, {js_value(args[1])});")
        return f"expect(response.body).to.have.property({js_value(args[0])});"
    if name == "response.body.length":
        return f"expect(response.body).to.have.length.of.at.least({js_value(args[0])});"
    if name == "response.headers":
        return f"expect(response.headers).to.have.property({js_value(args[0])});"
    return None


def _emit_wait(alias: str, checks: list[Check], indent: str, *, verbose: bool) -> list[str]:
    """Uma espera por alias com todas as suas verificações.

    Um único `cy.wait` por alias: esperar duas vezes pelo mesmo intercept
    trava o teste, porque a segunda espera nunca é satisfeita.
    """
    if not checks:
        return [f"{indent}cy.wait('@{alias}');"]

    # Verificação única: a forma encadeada `.its()` é mais legível.
    if len(checks) == 1:
        check = checks[0]
        name, args = check.name, check.args or []
        base = f"{indent}cy.wait('@{alias}')"
        if name == "response.status":
            return [f"{base}.its('response.statusCode').should('eq', {js_value(args[0])});"]
        if name == "response.status.range":
            return [f"{base}.its('response.statusCode')"
                    f".should('be.within', {js_value(args[0])}, {js_value(args[1])});"]
        if name == "request.method":
            return [f"{base}.its('request.method').should('eq', {js_value(args[0])});"]
        if name == "response.body.property":
            if len(args) >= 2:
                return [f"{base}.its('response.body')"
                        f".should('have.property', {js_value(args[0])}, {js_value(args[1])});"]
            return [f"{base}.its('response.body')"
                    f".should('have.property', {js_value(args[0])});"]
        if name == "response.body.length":
            return [f"{base}.its('response.body')"
                    f".should('have.length.at.least', {js_value(args[0])});"]
        if name == "response.headers":
            return [f"{base}.its('response.headers')"
                    f".should('have.property', {js_value(args[0])});"]
        return [f"{base};"]

    # Várias verificações: desestruturar a interceptação num único bloco.
    lines = [f"{indent}cy.wait('@{alias}').then(({{ request, response }}) => {{"]
    for check in checks:
        expectation = _response_expectation(check)
        if not expectation:
            continue
        if verbose and check.why:
            for wrapped in _wrap(check.why, 76):
                lines.append(f"{indent}{INDENT}// {wrapped}")
        lines.append(f"{indent}{INDENT}{expectation}")
    lines.append(f"{indent}}});")
    return lines


# ---------------------------------------------------------------------------
# Comandos
# ---------------------------------------------------------------------------

def emit_command(cmd: Command, indent: str, *, verbose: bool) -> list[str]:
    """Um comando da IR → linhas de código Cypress."""
    lines: list[str] = []

    if cmd.op == "comment":
        for line in (cmd.comment or "").splitlines():
            lines.append(f"{indent}{line}" if line.startswith("//") else f"{indent}// {line}")
        return lines

    # Comentário explicativo acima do comando. `intercept` traz o seu próprio
    # logo antes da chamada, e `assert`/`wait` já embutem a justificativa.
    if verbose and cmd.comment and cmd.op not in ("assert", "wait", "intercept"):
        lines.append(f"{indent}// {cmd.comment}")
    for note in (cmd.options.get("notes") or []):
        for wrapped in _wrap(note, 84):
            lines.append(f"{indent}// ⓘ {wrapped}")

    # Cadeia de reserva documentada no código: é o que a auto-cura consome.
    if cmd.target and cmd.target.fallbacks and cmd.op in ("click", "type", "select", "check"):
        alts = " | ".join(cmd.target.fallbacks[:3])
        lines.append(f"{indent}// reservas: {alts}")

    if cmd.op == "intercept":
        method = js_string(cmd.value.get("method", "GET"))
        pattern = js_string(cmd.value.get("pattern", ""))
        if verbose and cmd.comment:
            lines.append(f"{indent}// {cmd.comment}")
        lines.append(f"{indent}cy.intercept({method}, {pattern}).as({js_string(cmd.alias)});")
        return lines

    if cmd.op == "wait":
        return lines + _emit_wait(cmd.alias, cmd.checks, indent, verbose=verbose)

    if cmd.op == "assert":
        special = _emit_special_assert(cmd, indent)
        if special:
            return lines + special
        subject = emit_target(cmd.target)
        chain = emit_checks(cmd.checks)
        if not chain:
            return lines
        lines.append(f"{indent}{subject}{chain};")
        return lines

    if cmd.op == "visit":
        lines.append(f"{indent}cy.visit({js_string(cmd.value or '/')});")
        return lines

    subject = emit_target(cmd.target)
    pre = emit_checks(cmd.checks)

    action = {
        "click": "click()",
        "dblclick": "dblclick()",
        "check": "check()",
        "uncheck": "uncheck()",
        "hover": "trigger('mouseover')",
        "scroll": "scrollIntoView()",
        "focus": "focus()",
        "clear": "clear()",
    }.get(cmd.op)

    if cmd.op == "type":
        rendered = js_value(cmd.value)
        action = f"clear().type({rendered})"
    elif cmd.op == "select":
        action = f"select({js_value(cmd.value)})"
    elif cmd.op == "keypress":
        action = f"type({js_string('{' + str(cmd.value).lower() + '}')})"
    elif cmd.op == "upload":
        action = f"selectFile({js_value(cmd.value)})"

    if action is None:
        lines.append(f"{indent}// operação não suportada no emissor Cypress: {cmd.op}")
        return lines

    lines.append(f"{indent}{subject}{pre}.{action};")
    return lines


def _wrap(text: str, width: int) -> list[str]:
    words = str(text).split()
    out, line = [], ""
    for word in words:
        if len(line) + len(word) + 1 > width:
            out.append(line)
            line = word
        else:
            line = f"{line} {word}".strip()
    if line:
        out.append(line)
    return out


# ---------------------------------------------------------------------------
# Documento completo
# ---------------------------------------------------------------------------

def emit(spec: Spec, *, verbose: bool = True, split_groups: bool = False) -> str:
    """Spec da IR → conteúdo completo de um arquivo `.cy.js`."""
    out: list[str] = []
    a = out.append

    a("/// <reference types=\"cypress\" />")
    a("")
    a("/**")
    a(f" * {spec.name}")
    if spec.description:
        for line in _wrap(spec.description, 76):
            a(f" * {line}")
    a(" *")
    a(" * Gerado pelo Cygen — cada assertion abaixo foi deduzida do que o app")
    a(" * realmente fez durante a gravação, não de um palpite.")
    if spec.env_keys:
        a(" *")
        a(" * Credenciais vêm de variáveis de ambiente (nunca do código):")
        for key in spec.env_keys:
            a(f" *   CYPRESS_{key}=...")
    a(" */")
    a("")

    if spec.warnings:
        a("// ─── Pontos de atenção ───────────────────────────────────────────")
        for warning in spec.warnings:
            for line in _wrap(warning, 74):
                a(f"//  {line}")
        a("")

    for suggestion in spec.suggestions:
        for line in _wrap(suggestion.get("suggestion", ""), 74):
            a(f"// ⟳ {line}")
    if spec.suggestions:
        a("")

    a(f"describe({js_string(spec.name)}, () => {{")

    if spec.setup:
        a(f"{INDENT}beforeEach(() => {{")
        for cmd in spec.setup:
            out.extend(emit_command(cmd, INDENT * 2, verbose=verbose))
        a(f"{INDENT}}});")
        a("")

    if split_groups and spec.groups:
        for group in spec.groups:
            group_cmds = [c for c in spec.commands if c.group == group]
            if not group_cmds:
                continue
            a(f"{INDENT}it({js_string(group)}, () => {{")
            for cmd in group_cmds:
                out.extend(emit_command(cmd, INDENT * 2, verbose=verbose))
            a(f"{INDENT}}});")
            a("")
    else:
        title = spec.description or f"executa o fluxo: {spec.name}"
        a(f"{INDENT}it({js_string(title)}, () => {{")
        current_group = None
        for cmd in spec.commands:
            if verbose and cmd.group and cmd.group != current_group:
                if current_group is not None:
                    a("")
                a(f"{INDENT * 2}// ── {cmd.group} ──")
                current_group = cmd.group
            out.extend(emit_command(cmd, INDENT * 2, verbose=verbose))
        a(f"{INDENT}}});")

    a("});")
    a("")
    return "\n".join(out)


def emit_commands_file(spec: Spec) -> str | None:
    """Gera `support/commands.js` quando há sequências repetidas."""
    if not spec.suggestions:
        return None
    out = [
        "// Comandos customizados sugeridos pelo Cygen.",
        "// Estas sequências apareceram mais de uma vez no fluxo gravado.",
        "",
    ]
    for i, suggestion in enumerate(spec.suggestions, 1):
        name = f"fluxo{i}"
        out.append(f"Cypress.Commands.add('{name}', () => {{")
        for label in suggestion.get("steps", []):
            out.append(f"  // {label}")
        out.append("  // TODO: mova para cá os comandos correspondentes do spec.")
        out.append("});")
        out.append("")
    return "\n".join(out)


# Nomeação de arquivo -------------------------------------------------------

def spec_filename(name: str) -> str:
    """Nome de arquivo seguro a partir do nome do fluxo.

    Acentos viram ASCII: nomes de spec atravessam Docker, CI e sistemas de
    arquivos com codificações diferentes, e `orçamento` já quebrou pipeline.
    """
    ascii_name = (
        unicodedata.normalize("NFKD", name or "")
        .encode("ascii", "ignore")
        .decode("ascii")
    )
    slug = re.sub(r"[^\w\s-]", "", ascii_name).strip()
    slug = re.sub(r"[\s_-]+", "_", slug).lower()
    return f"{slug or 'teste'}.cy.js"
