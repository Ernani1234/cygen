"""
Representação intermediária (IR) do teste.

O gerador da v2 concatenava strings direto do evento para o código Cypress.
Isso amarrava a saída a um único framework e produzia bugs de escape: um valor
com apóstrofo (`O'Brien`) gerava JavaScript inválido.

Aqui existe uma camada no meio. Os passos semânticos viram uma árvore de
comandos neutros; cada emissor traduz essa árvore para seu alvo. Adicionar um
novo alvo (Puppeteer, Selenium, Robot Framework) é escrever um emissor, sem
tocar em nada da inferência.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Target:
    """Como localizar um elemento, de forma independente de framework."""

    strategy: str                    # css | text | role | xpath | url | window | alias
    value: str = ""
    fallbacks: list[str] = field(default_factory=list)
    confidence: float = 1.0
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy": self.strategy, "value": self.value,
            "fallbacks": self.fallbacks, "confidence": self.confidence,
            "note": self.note,
        }


@dataclass
class Check:
    """Uma verificação a ser aplicada sobre um alvo."""

    name: str
    args: list[Any] = field(default_factory=list)
    why: str = ""
    confidence: float = 1.0
    target: Target | None = None     # None = herda o alvo do comando

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name, "args": self.args, "why": self.why,
            "confidence": self.confidence,
            "target": self.target.to_dict() if self.target else None,
        }


@dataclass
class Command:
    """Um comando executável do teste."""

    op: str                          # visit | click | type | select | check | wait | intercept | assert | comment
    target: Target | None = None
    value: Any = None
    checks: list[Check] = field(default_factory=list)
    comment: str = ""
    alias: str = ""
    options: dict[str, Any] = field(default_factory=dict)
    group: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "op": self.op,
            "target": self.target.to_dict() if self.target else None,
            "value": self.value,
            "checks": [c.to_dict() for c in self.checks],
            "comment": self.comment, "alias": self.alias,
            "options": self.options, "group": self.group,
        }


@dataclass
class Spec:
    """Um arquivo de teste completo."""

    name: str
    description: str = ""
    base_url: str = ""
    commands: list[Command] = field(default_factory=list)
    setup: list[Command] = field(default_factory=list)     # roda em beforeEach
    env_keys: list[str] = field(default_factory=list)      # credenciais externas
    warnings: list[str] = field(default_factory=list)
    suggestions: list[dict[str, Any]] = field(default_factory=list)
    groups: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name, "description": self.description,
            "baseUrl": self.base_url,
            "commands": [c.to_dict() for c in self.commands],
            "setup": [c.to_dict() for c in self.setup],
            "envKeys": self.env_keys, "warnings": self.warnings,
            "suggestions": self.suggestions, "groups": self.groups,
        }

    def stats(self) -> dict[str, int]:
        return {
            "commands": len(self.commands),
            "checks": sum(len(c.checks) for c in self.commands),
            "intercepts": sum(1 for c in self.commands if c.op == "intercept"),
            "groups": len(self.groups),
        }
