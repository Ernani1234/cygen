"""
Motor de seletores.

O Cygen v2 usava uma lista fixa de prioridade (data-cy > id > name > ...) e
pegava o primeiro que existisse. Isso produzia seletores como
`.q-focus-helper` e `#f_5b7d19ae-c3fa-4c3a-ab4f-b0084876d3b9` — ambos presentes
nos testes gerados pela versão antiga, ambos quebram no próximo deploy.

Aqui a abordagem é outra: geramos *todos* os candidatos plausíveis, damos uma
nota a cada um combinando

    intenção  -> o autor do app criou este atributo para ser um gancho de teste?
    unicidade -> quantos elementos casam com ele na página, agora?
    entropia  -> o valor parece gerado por máquina (hash, uuid, contador)?
    coesão    -> o seletor sobrevive a mudanças de layout/estilo?

e devolvemos uma cadeia ordenada: primário + reservas. A cadeia inteira vai
para o teste gerado, o que permite a auto-cura (`verify/healer.py`) trocar o
primário por uma reserva quando ele deixar de casar.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

# --- Detecção de valores gerados por máquina -------------------------------
# Se o valor bate com um destes padrões, ele muda a cada build/sessão e não
# serve como âncora de teste.

_UUID = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I
)
_LONG_HEX = re.compile(r"^[0-9a-f]{12,}$", re.I)
_CSS_MODULE_HASH = re.compile(r"^[\w-]+__[\w-]+___[\w-]{5,}$")
_EMOTION_HASH = re.compile(r"^(css|sc)-[0-9a-z]{6,}$", re.I)
_TRAILING_DIGITS = re.compile(r"[-_]?\d{3,}$")
_MIXED_NOISE = re.compile(r"^[a-z]{1,3}[0-9]{4,}$", re.I)

# Prefixos de classe de frameworks de UI: são de estilo, nunca de identidade.
_FRAMEWORK_CLASS_PREFIXES = (
    "q-",          # Quasar (o app SGPMMS do usuário usa Quasar)
    "mui", "Mui",  # Material UI
    "ant-",        # Ant Design
    "el-",         # Element UI
    "v-",          # Vuetify
    "ng-",         # Angular
    "chakra-",     # Chakra
    "bp3-", "bp4-",  # Blueprint
    "rc-",         # rc-components
    "ui-",         # jQuery UI
    "p-",          # PrimeNG/PrimeVue
)

# Classes de comportamento puro — nunca identificam um elemento de negócio.
_JUNK_CLASSES = {
    "active", "focus", "hover", "open", "closed", "show", "hide", "hidden",
    "visible", "selected", "disabled", "row", "col", "column", "flex",
    "container", "wrapper", "inner", "outer", "content", "block", "inline",
    "clearfix", "no-wrap", "items-start", "items-center", "justify-center",
    "text-center", "relative", "absolute", "fixed", "sticky",
    "q-focus-helper", "q-ripple", "MuiTouchRipple-root",
}

# Utilitários Tailwind: `px-4`, `mt-2`, `text-sm`, `bg-blue-500`, `w-1/2`...
_TAILWIND = re.compile(
    r"^-?(m|p)[trblxy]?-\d|^(w|h)-|^text-|^bg-|^border-|^flex-|^grid-|^gap-|"
    r"^rounded|^shadow|^opacity-|^z-|^top-|^left-|^right-|^bottom-"
)

# Atributos explicitamente criados para automação de teste.
_TEST_ATTRS = (
    "data-cy", "data-test", "data-testid", "data-test-id",
    "data-qa", "data-automation-id", "data-e2e",
)

# Atributos de acessibilidade: estáveis porque são contratos com o usuário.
_A11Y_ATTRS = ("aria-label", "aria-labelledby", "role", "title", "alt", "placeholder")


def looks_generated(value: str) -> bool:
    """True se o valor parece emitido por máquina e não escrito por humano."""
    if not value:
        return False
    v = value.strip()
    if _UUID.search(v) or _LONG_HEX.match(v):
        return True
    if _CSS_MODULE_HASH.match(v) or _EMOTION_HASH.match(v):
        return True
    if _MIXED_NOISE.match(v):
        return True
    # `campo_12345` — sufixo numérico longo indica índice/contador gerado.
    if _TRAILING_DIGITS.search(v) and len(v) > 6:
        return True
    # Alta densidade de dígitos num identificador curto.
    digits = sum(c.isdigit() for c in v)
    if len(v) >= 6 and digits / len(v) > 0.45:
        return True
    return False


def is_framework_class(name: str) -> bool:
    """True para classes de estilo de frameworks de UI."""
    if name in _JUNK_CLASSES:
        return True
    if _TAILWIND.match(name):
        return True
    return any(name.startswith(p) for p in _FRAMEWORK_CLASS_PREFIXES)


def _css_escape(value: str) -> str:
    """Escapa um valor para uso dentro de aspas duplas num seletor CSS."""
    return value.replace("\\", "\\\\").replace('"', '\\"')


@dataclass
class Candidate:
    """Um seletor possível para um elemento, com sua nota e justificativa."""

    value: str
    kind: str                    # test-attr | a11y | id | name | text | css | xpath
    score: float = 0.0
    matches: int | None = None   # nº de elementos que casam (None = não medido)
    why: str = ""
    engine: str = "css"          # css | xpath | text

    def to_dict(self) -> dict[str, Any]:
        return {
            "value": self.value,
            "kind": self.kind,
            "score": round(self.score, 3),
            "matches": self.matches,
            "why": self.why,
            "engine": self.engine,
        }


@dataclass
class SelectorPlan:
    """Cadeia final: um primário e reservas ordenadas por nota."""

    primary: Candidate | None
    fallbacks: list[Candidate] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def confidence(self) -> float:
        return self.primary.score if self.primary else 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "primary": self.primary.to_dict() if self.primary else None,
            "fallbacks": [c.to_dict() for c in self.fallbacks],
            "warnings": self.warnings,
            "confidence": round(self.confidence, 3),
        }


class SelectorEngine:
    """Gera e ranqueia seletores a partir do descritor de um elemento.

    O descritor é o dicionário que o gravador injetado produz no navegador
    (ver `recorder/injector.js`), contendo tag, atributos, texto, ancestrais e
    a contagem de elementos que casam com cada candidato na página real.
    """

    # Peso base por tipo de seletor. Reflete a *intenção* por trás do atributo.
    BASE_SCORE = {
        "test-attr": 1.00,
        "a11y": 0.78,
        "id": 0.72,
        "name": 0.70,
        "text": 0.62,
        "css": 0.40,
        "xpath": 0.15,
    }

    def __init__(self, preferred_attrs: list[str] | None = None) -> None:
        # Permite ao usuário registrar convenções próprias do projeto dele.
        self.preferred_attrs = preferred_attrs or list(_TEST_ATTRS)

    # -- geração ------------------------------------------------------------

    def candidates(self, el: dict[str, Any]) -> list[Candidate]:
        """Todos os candidatos plausíveis para o elemento, já pontuados."""
        attrs: dict[str, str] = {
            k: v for k, v in (el.get("attributes") or {}).items() if v is not None
        }
        tag = (el.get("tag") or "").lower()
        out: list[Candidate] = []

        # 1. Atributos dedicados a teste — a intenção é inequívoca.
        for attr in self.preferred_attrs:
            val = attrs.get(attr)
            if val and not looks_generated(val):
                out.append(Candidate(
                    value=f'[{attr}="{_css_escape(val)}"]',
                    kind="test-attr",
                    why=f"`{attr}` existe para automação — é o gancho mais estável possível.",
                ))

        # 2. Acessibilidade — contrato com o usuário final, muda pouco.
        for attr in _A11Y_ATTRS:
            val = attrs.get(attr)
            if not val or looks_generated(val):
                continue
            if attr == "role" and val in ("presentation", "none"):
                continue
            sel = f'[{attr}="{_css_escape(val)}"]'
            # Ancorar no tag reduz colisão sem perder estabilidade.
            if tag and attr in ("role", "placeholder", "title"):
                sel = f"{tag}{sel}"
            out.append(Candidate(
                value=sel, kind="a11y",
                why=f"`{attr}` é um contrato de acessibilidade — some só se a UX mudar.",
            ))

        # 3. id — bom quando escrito por humano, péssimo quando gerado.
        el_id = attrs.get("id") or el.get("id")
        if el_id:
            if looks_generated(el_id):
                out.append(Candidate(
                    value=f'[id="{_css_escape(el_id)}"]', kind="id", score=0.05,
                    why="id gerado em runtime — muda a cada carga da página.",
                ))
            else:
                out.append(Candidate(
                    value=f"#{el_id}", kind="id",
                    why="id escrito por humano — estável e único por definição.",
                ))

        # 4. name — o clássico dos formulários.
        name = attrs.get("name")
        if name and not looks_generated(name):
            sel = f'[name="{_css_escape(name)}"]'
            out.append(Candidate(
                value=f"{tag}{sel}" if tag in ("input", "select", "textarea") else sel,
                kind="name",
                why="`name` faz parte do contrato do formulário com o backend.",
            ))

        # 5. Texto visível — resiliente a refatoração de CSS, frágil a i18n.
        text = (el.get("text") or "").strip()
        if text and 1 < len(text) <= 60 and "\n" not in text:
            if not looks_generated(text):
                # Valor cru, sem aspas: quem escapa é o emissor, que sabe a
                # sintaxe do alvo. Aspas aqui produziriam cy.contains("'Entrar'").
                out.append(Candidate(
                    value=text, kind="text", engine="text",
                    why="texto visível — sobrevive a qualquer refatoração de CSS.",
                ))

        # 6. Classes — só as que parecem semânticas.
        classes = [
            c for c in (el.get("classList") or [])
            if c and not is_framework_class(c) and not looks_generated(c)
        ]
        if classes:
            # Usar até 2 classes: mais que isso vira acoplamento com o layout.
            chain = "".join(f".{c}" for c in classes[:2])
            out.append(Candidate(
                value=f"{tag}{chain}" if tag else chain, kind="css",
                why="classes com aparência semântica (não são utilitárias nem de framework).",
            ))

        # 7. Ancoragem estrutural: pai com atributo de teste + tag do filho.
        anchor = el.get("testAnchor")
        if anchor and anchor.get("selector"):
            rel = anchor.get("relative") or tag
            out.append(Candidate(
                value=f"{anchor['selector']} {rel}", kind="test-attr", score=0.88,
                why="ancorado num container marcado para teste — escopo estreito e estável.",
            ))

        # 8. XPath — último recurso, e sinalizado como tal.
        xpath = el.get("xpath")
        if xpath:
            out.append(Candidate(
                value=xpath, kind="xpath", engine="xpath",
                why="posição absoluta na árvore — quebra a qualquer mudança de layout.",
            ))

        # Aplicar as notas e a contagem de casamentos medida no navegador.
        match_counts: dict[str, int] = el.get("matchCounts") or {}
        for cand in out:
            cand.matches = match_counts.get(cand.value)
            cand.score = self.score(cand, el)

        # Desduplicar preservando o de maior nota.
        best: dict[str, Candidate] = {}
        for cand in out:
            prev = best.get(cand.value)
            if prev is None or cand.score > prev.score:
                best[cand.value] = cand

        return sorted(best.values(), key=lambda c: c.score, reverse=True)

    # -- pontuação ----------------------------------------------------------

    def score(self, cand: Candidate, el: dict[str, Any]) -> float:
        """Nota final 0..1 combinando intenção, unicidade e entropia."""
        # Notas fixadas na geração (âncora estrutural, id gerado) são mantidas.
        base = cand.score if cand.score else self.BASE_SCORE.get(cand.kind, 0.3)

        # Unicidade: o fator decisivo. Um seletor que casa com 8 elementos é
        # inútil por mais bem-intencionado que seja o atributo.
        if cand.matches is not None:
            if cand.matches == 0:
                return 0.0           # não casa com nada: descartar.
            if cand.matches == 1:
                base *= 1.15         # único: o ideal.
            elif cand.matches <= 3:
                base *= 0.55
            else:
                base *= 0.20

        # Comprimento: seletores longos são acoplados demais ao DOM atual.
        length = len(cand.value)
        if length > 120:
            base *= 0.5
        elif length > 70:
            base *= 0.8

        # Profundidade: cada `>` ou espaço é uma dependência de hierarquia.
        depth = cand.value.count(">") + cand.value.count(" ")
        if depth >= 3:
            base *= 0.7

        # Elementos interativos com seletor de texto: preferir o papel também.
        if cand.kind == "text" and (el.get("tag") or "").lower() in ("button", "a"):
            base *= 1.08

        return max(0.0, min(1.0, base))

    # -- plano final --------------------------------------------------------

    def plan(self, el: dict[str, Any], *, max_fallbacks: int = 3) -> SelectorPlan:
        """Cadeia primário + reservas, com avisos sobre riscos detectados."""
        cands = [c for c in self.candidates(el) if c.score > 0]
        if not cands:
            return SelectorPlan(
                primary=None,
                warnings=["Nenhum seletor confiável pôde ser derivado deste elemento."],
            )

        primary = cands[0]
        # Reservas devem usar *estratégias diferentes* do primário: se o
        # primário morrer por causa de um redesign de CSS, outra classe CSS
        # provavelmente morre junto.
        fallbacks: list[Candidate] = []
        used_kinds = {primary.kind}
        for cand in cands[1:]:
            if len(fallbacks) >= max_fallbacks:
                break
            if cand.kind in used_kinds and cand.kind != "test-attr":
                continue
            fallbacks.append(cand)
            used_kinds.add(cand.kind)

        warnings: list[str] = []
        if primary.score < 0.45:
            warnings.append(
                "Seletor primário fraco. Peça ao time para adicionar `data-cy` "
                "neste elemento — é a diferença entre um teste que dura e um "
                "que quebra no próximo deploy."
            )
        if primary.kind == "xpath":
            warnings.append("Só sobrou XPath: este passo vai quebrar com qualquer refatoração.")
        if primary.matches is not None and primary.matches > 1:
            warnings.append(
                f"O seletor primário casa com {primary.matches} elementos; "
                "Cypress vai agir sobre o primeiro."
            )
        return SelectorPlan(primary=primary, fallbacks=fallbacks, warnings=warnings)


def suggest_test_attr(el: dict[str, Any]) -> str:
    """Sugere um `data-cy` legível para um elemento que não tem gancho de teste.

    Usada pela UI para oferecer ao usuário um trecho pronto para pedir ao time
    de desenvolvimento — transformando um teste frágil numa melhoria do app.
    """
    text = (el.get("text") or "").strip().lower()
    attrs = el.get("attributes") or {}
    label = (
        text
        or attrs.get("aria-label", "")
        or attrs.get("placeholder", "")
        or attrs.get("name", "")
        or (el.get("tag") or "el")
    )
    slug = re.sub(r"[^a-z0-9]+", "-", str(label).lower()).strip("-")[:40]
    return slug or "elemento"
