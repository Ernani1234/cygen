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


@dataclass
class Suite:
    """Vários fluxos num arquivo só, cada um virando um `it()`.

    Existe porque uma jornada real raramente cabe numa gravação: cadastrar,
    aprovar e depois consultar são três fluxos que só fazem sentido em
    sequência, e na ordem certa. Reunidos aqui, viram um único `.cy.js` que o
    Cypress roda de cima para baixo.

    A ordem de `specs` é a ordem de execução, e não é decorativa — ver
    `emit_cypress.emit_suite` sobre isolamento entre testes.
    """

    name: str
    description: str = ""
    base_url: str = ""
    specs: list[Spec] = field(default_factory=list)
    # Quando ligado, cada teste começa com cookies e armazenamento limpos. É o
    # padrão do Cypress e o certo para testes independentes — mas é justamente
    # o que impede uma sequência de continuar de onde a anterior parou.
    isolate: bool = False

    @property
    def env_keys(self) -> list[str]:
        """União das credenciais pedidas pelos fluxos, sem repetir."""
        out: list[str] = []
        for spec in self.specs:
            for key in spec.env_keys:
                if key not in out:
                    out.append(key)
        return out

    @property
    def warnings(self) -> list[str]:
        """Avisos de todos os fluxos, cada um dizendo de onde veio."""
        out: list[str] = []
        for spec in self.specs:
            for warning in spec.warnings:
                marked = f"{spec.name}: {warning}"
                if marked not in out:
                    out.append(marked)
        return out

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name, "description": self.description,
            "baseUrl": self.base_url, "isolate": self.isolate,
            "specs": [s.to_dict() for s in self.specs],
            "envKeys": self.env_keys, "warnings": self.warnings,
        }

    def stats(self) -> dict[str, int]:
        return {
            "tests": len(self.specs),
            "commands": sum(len(s.commands) for s in self.specs),
            "checks": sum(len(c.checks) for s in self.specs for c in s.commands),
        }
