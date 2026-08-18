"""
Emissor Playwright (TypeScript).

Prova o valor da IR: o mesmo fluxo gravado vira um `.spec.ts` sem que nada da
inferência precise saber que Playwright existe. As diferenças de idioma entre
os dois frameworks ficam contidas aqui — `getByText` no lugar de `contains`,
`expect()` no lugar de `.should()`, `waitForResponse` no lugar de alias.
"""

from __future__ import annotations

import json
import re
import unicodedata
from typing import Any

from .ir import Check, Command, Spec, Target

INDENT = "  "


# Metacaracteres de regex em JavaScript. `re.escape` do Python escapa demais
# (`#`, `-`, espaço) e polui o padrão gerado sem necessidade.
_JS_REGEX_META = set(r".^$*+?()[]{}|\/")


def js_regex_escape(value: str) -> str:
    """Escapa apenas o que é metacaractere de regex em JavaScript."""
    return "".join(f"\\{c}" if c in _JS_REGEX_META else c for c in value)


def ts_string(value: str) -> str:
    if value is None:
        return "''"
    escaped = (
        str(value).replace("\\", "\\\\").replace("'", "\\'")
        .replace("\n", "\\n").replace("\r", "\\r")
    )
    return f"'{escaped}'"


def ts_value(value: Any) -> str:
    if isinstance(value, dict):
        if "__env__" in value:
            return f"process.env.{value['__env__']}!"
        if "regex" in value:
            return value["regex"]
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list):
        return "[" + ", ".join(ts_value(v) for v in value) + "]"
    return ts_string(str(value))


def locator(target: Target | None) -> str:
    """Alvo da IR → locator do Playwright."""
    if target is None:
        return "page.locator('body')"
    if target.strategy == "text":
        return f"page.getByText({ts_string(target.value)})"
    if target.strategy == "role":
        return f"page.getByRole({ts_string(target.value)})"
    if target.strategy == "xpath":
        return f"page.locator({ts_string('xpath=' + target.value)})"
    return f"page.locator({ts_string(target.value)})"


# Mapa assertion do catálogo → matcher do Playwright.
_MATCHERS: dict[str, tuple[str, int]] = {
    "be.visible": ("toBeVisible", 0),
    "not.be.visible": ("not.toBeVisible", 0),
    "exist": ("toBeAttached", 0),
    "not.exist": ("not.toBeAttached", 0),
    "be.checked": ("toBeChecked", 0),
    "not.be.checked": ("not.toBeChecked", 0),
    "be.disabled": ("toBeDisabled", 0),
    "not.be.disabled": ("toBeEnabled", 0),
    "be.enabled": ("toBeEnabled", 0),
    "be.focused": ("toBeFocused", 0),
    "have.focus": ("toBeFocused", 0),
    "be.empty": ("toBeEmpty", 0),
    "not.be.empty": ("not.toBeEmpty", 0),
    "have.text": ("toHaveText", 1),
    "contain.text": ("toContainText", 1),
    "not.contain.text": ("not.toContainText", 1),
    "have.value": ("toHaveValue", 1),
    "not.have.value": ("not.toHaveValue", 1),
    "have.class": ("toHaveClass", 1),
    "not.have.class": ("not.toHaveClass", 1),
    "have.id": ("toHaveId", 1),
    "have.attr": ("toHaveAttribute", 2),
    "have.attr.exists": ("toHaveAttribute", 1),
    "have.length": ("toHaveCount", 1),
    "match": ("toHaveText", 1),
    "contain": ("toContainText", 1),
}


def emit_check(check: Check, target: Target | None, indent: str) -> list[str]:
    name, args = check.name, check.args or []

    if name.startswith("have.attr.aria-"):
        attr = name.replace("have.attr.", "")
        value = ts_value(args[-1]) if args else "'true'"
        return [f"{indent}await expect({locator(target)})"
                f".toHaveAttribute({ts_string(attr)}, {value});"]

    if name in ("url.include", "location.pathname", "location.hash", "url.eq"):
        if name == "url.eq":
            return [f"{indent}await expect(page).toHaveURL({ts_value(args[0])});"]
        pattern = js_regex_escape(str(args[0])) if args else ""
        return [f"{indent}await expect(page).toHaveURL(new RegExp({ts_string(pattern)}));"]

    if name in ("title.include", "title.eq"):
        if name == "title.eq":
            return [f"{indent}await expect(page).toHaveTitle({ts_value(args[0])});"]
        return [f"{indent}await expect(page)"
                f".toHaveTitle(new RegExp({ts_string(js_regex_escape(str(args[0])))}));"]

    if name.startswith("have.length."):
        # Playwright não tem comparadores relativos de contagem; usamos count().
        op = {"have.length.at.least": ">=", "have.length.greaterThan": ">",
              "have.length.lessThan": "<", "have.length.at.most": "<="}.get(name, ">=")
        return [f"{indent}expect(await {locator(target)}.count())"
                f".toBeGreaterThanOrEqual({ts_value(args[0])});"
                if op in (">=", ">")
                else f"{indent}expect(await {locator(target)}.count())"
                     f".toBeLessThanOrEqual({ts_value(args[0])});"]

    if name.startswith("localStorage."):
        key = ts_value(args[0]) if args else "''"
        negate = ".not" if name.endswith("not.exists") else ""
        return [f"{indent}expect(await page.evaluate("
                f"(k) => localStorage.getItem(k), {key})){negate}.toBeTruthy();"]

    matcher = _MATCHERS.get(name)
    if not matcher:
        return [f"{indent}// assertion sem equivalente direto em Playwright: {name}"]

    fn, arity = matcher
    if arity == 0:
        return [f"{indent}await expect({locator(target)}).{fn}();"]
    rendered = ", ".join(ts_value(a) for a in args[:arity])
    return [f"{indent}await expect({locator(target)}).{fn}({rendered});"]


def emit_command(cmd: Command, indent: str, *, verbose: bool) -> list[str]:
    lines: list[str] = []

    if cmd.op == "comment":
        for line in (cmd.comment or "").splitlines():
            lines.append(f"{indent}{line}" if line.startswith("//") else f"{indent}// {line}")
        return lines

    if verbose and cmd.comment and cmd.op not in ("assert", "wait"):
        lines.append(f"{indent}// {cmd.comment}")

    if cmd.op == "intercept":
        # A promessa precisa ser criada ANTES da ação que dispara a chamada.
        # Se `waitForResponse` só for chamado depois do clique, a resposta já
        # passou e a espera trava até o timeout. Aqui criamos sem `await`.
        var = _ident(cmd.alias)
        fragment = cmd.alias.split("_", 1)[-1]
        lines.append(f"{indent}const {var}Promise = page.waitForResponse("
                     f"r => r.url().includes({ts_string(fragment)}));")
        return lines

    if cmd.op == "wait":
        # Uma única const por alias — redeclarar o mesmo identificador não
        # compila em TypeScript.
        var = _ident(cmd.alias)
        lines.append(f"{indent}const {var} = await {var}Promise;")
        needs_body = any(c.name.startswith("response.body") for c in cmd.checks)
        if needs_body:
            lines.append(f"{indent}const {var}Body = await {var}.json();")
        for check in cmd.checks:
            args = check.args or []
            if check.name == "response.status":
                lines.append(f"{indent}expect({var}.status()).toBe({ts_value(args[0])});")
            elif check.name == "response.status.range":
                lines.append(f"{indent}expect({var}.status())"
                             f".toBeGreaterThanOrEqual({ts_value(args[0])});")
                lines.append(f"{indent}expect({var}.status())"
                             f".toBeLessThanOrEqual({ts_value(args[1])});")
            elif check.name == "request.method":
                lines.append(f"{indent}expect({var}.request().method())"
                             f".toBe({ts_value(args[0])});")
            elif check.name == "response.body.property":
                if len(args) >= 2:
                    lines.append(f"{indent}expect({var}Body)"
                                 f".toHaveProperty({ts_value(args[0])}, {ts_value(args[1])});")
                else:
                    lines.append(f"{indent}expect({var}Body)"
                                 f".toHaveProperty({ts_value(args[0])});")
            elif check.name == "response.body.length":
                lines.append(f"{indent}expect({var}Body.length)"
                             f".toBeGreaterThanOrEqual({ts_value(args[0])});")
        return lines

    if cmd.op == "assert":
        for check in cmd.checks:
            lines.extend(emit_check(check, cmd.target, indent))
        return lines

    if cmd.op == "visit":
        lines.append(f"{indent}await page.goto({ts_string(cmd.value or '/')});")
        return lines

    for check in cmd.checks:
        lines.extend(emit_check(check, cmd.target, indent))

    loc = locator(cmd.target)
    action = {
        "click": "click()",
        "dblclick": "dblclick()",
        "check": "check()",
        "uncheck": "uncheck()",
        "hover": "hover()",
        "focus": "focus()",
        "clear": "clear()",
        "scroll": "scrollIntoViewIfNeeded()",
    }.get(cmd.op)

    if cmd.op == "type":
        action = f"fill({ts_value(cmd.value)})"
    elif cmd.op == "select":
        action = f"selectOption({ts_value(cmd.value)})"
    elif cmd.op == "keypress":
        action = f"press({ts_string(str(cmd.value).title())})"
    elif cmd.op == "upload":
        action = f"setInputFiles({ts_value(cmd.value)})"

    if action is None:
        lines.append(f"{indent}// operação não suportada no emissor Playwright: {cmd.op}")
        return lines

    lines.append(f"{indent}await {loc}.{action};")
    return lines


def _ident(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_]", "_", value)
    return f"res_{cleaned}"


def emit(spec: Spec, *, verbose: bool = True) -> str:
    out: list[str] = []
    a = out.append

    a("import { test, expect } from '@playwright/test';")
    a("")
    a("/**")
    a(f" * {spec.name}")
    if spec.description:
        a(f" * {spec.description}")
    a(" *")
    a(" * Gerado pelo Cygen a partir do mesmo fluxo gravado que originou o")
    a(" * spec Cypress — mesma inferência, alvo diferente.")
    a(" */")
    a("")

    if spec.env_keys:
        for key in spec.env_keys:
            a(f"// requer process.env.{key}")
        a("")

    a(f"test({ts_string(spec.name)}, async ({{ page }}) => {{")
    current_group = None
    for cmd in spec.commands:
        if verbose and cmd.group and cmd.group != current_group:
            if current_group is not None:
                a("")
            a(f"{INDENT}// ── {cmd.group} ──")
            current_group = cmd.group
        out.extend(emit_command(cmd, INDENT, verbose=verbose))
    a("});")
    a("")
    return "\n".join(out)


def spec_filename(name: str) -> str:
    """Nome de arquivo ASCII, pelas mesmas razoes do emissor Cypress."""
    ascii_name = (
        unicodedata.normalize("NFKD", name or "")
        .encode("ascii", "ignore").decode("ascii")
    )
    slug = re.sub(r"[^\w\s-]", "", ascii_name).strip()
    slug = re.sub(r"[\s_-]+", "-", slug).lower()
    return f"{slug or 'teste'}.spec.ts"
