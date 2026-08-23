"""
Construção da IR a partir dos passos semânticos + inferências do Oracle.

Este é o ponto onde tudo se encontra: passos vindos do `intent`, seletores
ranqueados pelo `SelectorEngine` e assertions deduzidas pelo `Oracle` viram
uma única árvore de comandos pronta para ser emitida em qualquer framework.
"""

from __future__ import annotations

from typing import Any

from ..intel.intent import Step
from ..intel.oracle import Assertion, Evidence, Oracle, is_secret_field
from ..intel.selectors import SelectorEngine, suggest_test_attr
from .ir import Check, Command, Spec, Target


def _fallback_value(cand: dict[str, Any]) -> str:
    """Seletor de reserva numa forma que diga por si só como ser resolvido.

    A reserva é só uma string quando chega na IR, e a estratégia dela se perde
    aí. Um candidato de texto (`Entrar`) entregue cru era interpretado como CSS
    tanto pelo Playwright quanto pelo Cypress e nunca casava com nada — a
    reserva existia no arquivo e era inútil na prática.

    Marcamos com o prefixo `text=`, que é a sintaxe nativa do Playwright e
    que o emissor traduz para o equivalente jQuery. XPath continua reconhecível
    pela própria forma (`//...`).
    """
    if cand.get("engine") == "text":
        return f"text={cand['value']}"
    return cand["value"]


def _target_from_plan(plan: dict[str, Any]) -> Target | None:
    primary = plan.get("primary")
    if not primary:
        return None
    engine = primary.get("engine", "css")
    strategy = {"css": "css", "text": "text", "xpath": "xpath"}.get(engine, "css")
    return Target(
        strategy=strategy,
        value=primary["value"],
        fallbacks=[_fallback_value(f) for f in plan.get("fallbacks", [])],
        confidence=primary.get("score", 0.0),
        note=primary.get("why", ""),
    )


def _target_from_assertion(a: Assertion, own: Target | None) -> Target | None:
    """Resolve o alvo declarado por uma assertion do Oracle."""
    t = a.target
    if t == "self":
        return own
    if t == "url":
        return Target(strategy="url")
    if t == "title":
        return Target(strategy="title")
    if t == "window":
        return Target(strategy="window")
    if isinstance(t, str) and t.startswith("@"):
        return Target(strategy="alias", value=t[1:])
    if isinstance(t, dict):
        if "css" in t:
            return Target(strategy="css", value=t["css"])
        if "contains" in t:
            return Target(strategy="text", value=t["contains"])
        if "role" in t:
            return Target(strategy="role", value=t["role"])
    return own


def build_spec(
    steps: list[Step],
    *,
    name: str,
    description: str = "",
    base_url: str = "",
    suggestions: list[dict[str, Any]] | None = None,
    oracle: Oracle | None = None,
    engine: SelectorEngine | None = None,
    rejected: dict[int, set[str]] | None = None,
) -> Spec:
    """Monta a `Spec` completa.

    `rejected` lista o que o usuário recusou: `{índice_do_passo: {"rule.id"}}`.

    O filtro é por recusa, não por aceite, e a diferença não é cosmética. Com
    uma lista de aceites, a ausência de informação significa "não aceite nada"
    — e na primeira geração a interface ainda não tem as assertions para
    montar essa lista, porque elas nascem justamente aqui. O resultado era um
    teste sem verificação nenhuma, silenciosamente. Filtrando por recusa, não
    saber nada significa aceitar tudo, que é o comportamento correto.
    """
    oracle = oracle or Oracle()
    engine = engine or SelectorEngine()

    spec = Spec(name=name, description=description, base_url=base_url,
                suggestions=suggestions or [])
    seen_aliases: set[str] = set()
    groups: list[str] = []

    for step in steps:
        if not step.enabled:
            continue
        if step.group and step.group not in groups:
            groups.append(step.group)

        # --- seletor -------------------------------------------------------
        target: Target | None = None
        if step.kind != "visit" and step.element:
            plan = engine.plan(step.element, override=step.selector_override).to_dict()
            step.selector = plan
            target = _target_from_plan(plan)
            for warning in plan.get("warnings", []):
                if warning not in spec.warnings:
                    spec.warnings.append(f"Passo {step.index + 1}: {warning}")
            if plan.get("confidence", 1.0) < 0.45:
                slug = suggest_test_attr(step.element)
                spec.warnings.append(
                    f"Passo {step.index + 1}: sugestão de melhoria no app — "
                    f'adicionar `data-cy="{slug}"` neste elemento.'
                )

        # --- evidência e inferência ---------------------------------------
        ev_data = step.evidence
        evidence = Evidence(
            action={"type": step.kind, "value": step.value, **(step.meta or {})},
            element=step.element,
            url_before=ev_data.get("urlBefore", ""),
            url_after=ev_data.get("urlAfter", ""),
            title_before=ev_data.get("titleBefore", ""),
            title_after=ev_data.get("titleAfter", ""),
            mutations=ev_data.get("mutations") or {},
            network=ev_data.get("network") or [],
            storage_delta=ev_data.get("storageDelta") or {},
            console_errors=ev_data.get("consoleErrors") or [],
            duration_ms=ev_data.get("durationMs", 0),
        )
        inferred = oracle.infer(evidence)
        step.assertions = [a.to_dict() for a in inferred]

        deny = (rejected or {}).get(step.index) or set()

        # --- intercepts precisam existir ANTES da ação que os dispara ------
        for req in evidence.network:
            alias = req.get("alias")
            if not alias or alias in seen_aliases:
                continue
            seen_aliases.add(alias)
            spec.commands.append(Command(
                op="intercept",
                alias=alias,
                value={"method": (req.get("method") or "GET").upper(),
                       "pattern": req.get("pattern") or req.get("url", "")},
                comment="Intercepta a chamada para poder esperá-la de forma determinística",
                group=step.group,
            ))

        # --- pré-condições -------------------------------------------------
        pre_checks = [
            Check(name=a.name, args=a.args, why=a.why, confidence=a.confidence)
            for a in inferred
            if a.phase == "before" and not a.raw and a.rule not in deny
        ]

        # --- o comando em si ----------------------------------------------
        value = step.value
        if step.kind == "type" and is_secret_field(step.element):
            key = _env_key(step.element)
            if key not in spec.env_keys:
                spec.env_keys.append(key)
            value = {"__env__": key}

        cmd = Command(
            op=step.kind,
            target=target,
            value=value,
            checks=pre_checks,
            comment=step.label,
            group=step.group,
            options={"notes": step.notes} if step.notes else {},
        )
        if step.kind == "visit":
            cmd.value = step.url
        spec.commands.append(cmd)

        # --- pós-condições -------------------------------------------------
        # Verificações sobre a mesma resposta interceptada precisam sair num
        # único `cy.wait`. Esperar duas vezes pelo mesmo alias trava o teste
        # (a segunda espera nunca resolve) e, em Playwright, declarar a mesma
        # const duas vezes nem compila.
        waits: dict[str, list[Check]] = {}
        pending: list[Command] = []

        for a in inferred:
            if a.phase == "before":
                continue
            if a.rule in deny:
                continue
            if a.raw:
                pending.append(Command(op="comment", comment=a.raw, group=step.group))
                continue
            a_target = _target_from_assertion(a, target)
            check = Check(name=a.name, args=a.args, why=a.why, confidence=a.confidence)
            if a_target and a_target.strategy == "alias":
                waits.setdefault(a_target.value, []).append(check)
            else:
                pending.append(Command(
                    op="assert", target=a_target, group=step.group,
                    checks=[check], comment=a.why,
                ))

        # A espera pela rede vem primeiro: as demais assertions só fazem
        # sentido depois que a resposta chegou e a tela reagiu.
        for alias, checks in waits.items():
            spec.commands.append(Command(
                op="wait", alias=alias, group=step.group, checks=checks,
                comment=checks[0].why,
            ))
        spec.commands.extend(pending)

    spec.groups = groups
    return spec


def _env_key(el: dict[str, Any]) -> str:
    """Nome da variável de ambiente para um campo de credencial."""
    attrs = el.get("attributes") or {}
    base = (attrs.get("name") or attrs.get("id") or "senha").upper()
    cleaned = "".join(c if c.isalnum() else "_" for c in base).strip("_")
    return cleaned or "SENHA"
