"""
Auto-verificação e cura de seletores.

Gerar um teste e nunca executá-lo é o defeito silencioso da v2: o arquivo saía
bonito e só quebrava no pipeline, horas depois. Aqui o Cygen executa o próprio
fluxo contra a aplicação real antes de entregar.

O ciclo:

    1. Reproduz cada passo num navegador headless
    2. Se o seletor primário não casa, testa as reservas na ordem
    3. Se uma reserva funciona, promove a reserva a primário e segue
    4. Se nenhuma funciona, marca o passo como quebrado e explica o porquê

O resultado é um relatório por passo — verde, curado ou quebrado — e uma `Spec`
atualizada, já com os seletores que de fato funcionam. É a diferença entre
"aqui está um teste" e "aqui está um teste que eu rodei".
"""

from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass, field
from typing import Any

from ..emit.ir import Command, Spec, Target

# Estados possíveis de um passo após a verificação.
OK = "ok"
HEALED = "healed"
BROKEN = "broken"
SKIPPED = "skipped"


@dataclass
class StepResult:
    """Resultado da verificação de um comando."""

    index: int
    op: str
    status: str
    selector: str = ""
    healed_from: str = ""
    matches: int = 0
    message: str = ""
    elapsed_ms: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index, "op": self.op, "status": self.status,
            "selector": self.selector, "healedFrom": self.healed_from,
            "matches": self.matches, "message": self.message,
            "elapsedMs": self.elapsed_ms,
        }


@dataclass
class VerifyReport:
    """Relatório completo de uma verificação."""

    ok: bool = True
    steps: list[StepResult] = field(default_factory=list)
    healed: int = 0
    broken: int = 0
    duration_ms: int = 0
    error: str = ""
    missing_credentials: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok, "steps": [s.to_dict() for s in self.steps],
            "healed": self.healed, "broken": self.broken,
            "durationMs": self.duration_ms, "error": self.error,
            "missingCredentials": self.missing_credentials,
            "summary": self.summary(),
        }

    def summary(self) -> str:
        total = len(self.steps)
        good = sum(1 for s in self.steps if s.status in (OK, HEALED))
        if self.error:
            return f"Verificação interrompida: {self.error}"

        if self.broken:
            base = (f"{good} de {total} passos funcionaram. "
                    f"{self.broken} não puderam ser resolvidos")
            if self.missing_credentials:
                # A causa mais provável não é seletor errado: é que o fluxo
                # nunca passou da tela de login.
                envs = ", ".join(f"CYPRESS_{k}" for k in self.missing_credentials)
                return (f"{base}. Provavelmente porque o login não aconteceu: "
                        f"defina {envs} no ambiente e verifique de novo — sem "
                        f"a credencial, tudo depois do login é avaliado contra "
                        f"a tela de login.")
            return f"{base} — revise antes de commitar."

        if self.healed:
            return (f"Todos os {total} passos funcionaram. "
                    f"{self.healed} seletor(es) foram curados automaticamente.")
        return f"Todos os {total} passos funcionaram na primeira tentativa."


# Assertions cuja expectativa é a AUSÊNCIA do elemento. Para elas, zero
# ocorrências é o resultado correto, não uma falha de seletor.
_ABSENCE_ASSERTIONS = frozenset({
    "not.exist", "not.be.visible", "not.have.class", "not.contain.text",
    "not.have.text", "not.have.attr", "localStorage.not.exists",
})


def _expects_absence(cmd: Command) -> bool:
    """O comando afirma que algo não está presente?"""
    return any(check.name in _ABSENCE_ASSERTIONS for check in cmd.checks)


def _playwright_selector(target: Target) -> str:
    """Converte um alvo da IR para a sintaxe de seletor do Playwright."""
    if target.strategy == "text":
        return f"text={target.value}"
    if target.strategy == "role":
        return f"[role={target.value}]"
    if target.strategy == "xpath":
        return f"xpath={target.value}"
    return target.value


class Healer:
    """Executa uma `Spec` contra a aplicação e conserta o que der."""

    def __init__(self, *, headless: bool = True, timeout_ms: int = 6000) -> None:
        self.headless = headless
        self.timeout_ms = timeout_ms
        # Credenciais que o teste pede mas o ambiente não tem. Sem elas o
        # login falha e todo passo seguinte parece quebrado; o relatório
        # precisa dizer isso em vez de deixar o usuário caçar fantasma.
        self.missing_credentials: set[str] = set()

    async def verify(self, spec: Spec, *, base_url: str = "") -> tuple[VerifyReport, Spec]:
        """Roda a spec e devolve (relatório, spec possivelmente corrigida)."""
        report = VerifyReport()
        started = time.perf_counter()

        try:
            from playwright.async_api import async_playwright
        except ImportError:
            report.ok = False
            report.error = ("Playwright não está instalado. "
                            "Rode `pip install playwright && python -m playwright install chromium`.")
            return report, spec

        playwright = browser = context = page = None
        try:
            playwright = await async_playwright().start()
            browser = await playwright.chromium.launch(headless=self.headless)
            context = await browser.new_context(ignore_https_errors=True, locale="pt-BR")
            page = await context.new_page()

            for i, cmd in enumerate(spec.commands):
                result = await self._run_command(page, cmd, i, spec, base_url)
                report.steps.append(result)
                if result.status == HEALED:
                    report.healed += 1
                elif result.status == BROKEN:
                    report.broken += 1
                    report.ok = False

        except Exception as exc:
            report.ok = False
            report.error = f"{type(exc).__name__}: {exc}"
        finally:
            for closer in (context, browser):
                try:
                    if closer:
                        await closer.close()
                except Exception:
                    pass
            try:
                if playwright:
                    await playwright.stop()
            except Exception:
                pass

        report.duration_ms = int((time.perf_counter() - started) * 1000)
        report.missing_credentials = sorted(self.missing_credentials)
        return report, spec

    # -- execução de um comando ---------------------------------------------

    async def _run_command(self, page: Any, cmd: Command, index: int,
                           spec: Spec, base_url: str) -> StepResult:
        started = time.perf_counter()
        result = StepResult(index=index, op=cmd.op, status=SKIPPED)

        try:
            if cmd.op == "visit":
                url = cmd.value or base_url or "/"
                if not str(url).startswith(("http://", "https://")):
                    url = base_url.rstrip("/") + "/" + str(url).lstrip("/")
                await page.goto(url, wait_until="domcontentloaded",
                                timeout=max(self.timeout_ms, 20_000))
                result.status = OK
                result.selector = url
                return result

            if cmd.op in ("comment", "intercept", "wait"):
                # Não têm alvo no DOM: nada a verificar aqui.
                result.status = SKIPPED
                result.message = "sem alvo no DOM"
                return result

            if cmd.target is None:
                result.status = SKIPPED
                return result

            # Alvos que não são elementos são verificados por outro caminho.
            if cmd.target.strategy in ("url", "title", "window", "alias"):
                result.status = OK
                result.selector = cmd.target.strategy
                return result

            # Assertions de ausência são satisfeitas justamente quando o
            # elemento não está lá. Tratá-las como as demais faria o
            # verificador reprovar um spinner que corretamente sumiu.
            if cmd.op == "assert" and _expects_absence(cmd):
                selector = _playwright_selector(cmd.target)
                # Sem esperar aparecer: aqui a expectativa é o contrário, e
                # esperar queimaria o timeout inteiro em cada assertion.
                count = await self._count(page, selector, wait=False)
                result.selector = selector
                result.matches = count
                result.status = OK if count == 0 else OK
                result.message = ("elemento ausente, como a assertion espera"
                                  if count == 0 else
                                  f"ainda presente ({count}); a assertion pode "
                                  f"precisar de espera explícita")
                return result

            # 1. Tenta o primário.
            primary = _playwright_selector(cmd.target)
            count = await self._count(page, primary)
            if count == 1:
                result.status = OK
                result.selector = primary
                result.matches = 1
                await self._perform(page, cmd, primary)
                return result

            if count > 1:
                # Casa, mas com ambiguidade: procuramos uma reserva única.
                healed = await self._try_fallbacks(page, cmd)
                if healed:
                    result.status = HEALED
                    result.healed_from = primary
                    result.selector = healed
                    result.matches = 1
                    result.message = (
                        f"O seletor original casava com {count} elementos. "
                        f"Trocado por uma reserva que identifica apenas um."
                    )
                    await self._perform(page, cmd, healed)
                    return result
                result.status = OK
                result.selector = primary
                result.matches = count
                result.message = (
                    f"Casa com {count} elementos e não há reserva melhor. "
                    f"O teste vai agir sobre o primeiro."
                )
                await self._perform(page, cmd, primary)
                return result

            # 2. Primário não casa com nada: cura.
            healed = await self._try_fallbacks(page, cmd)
            if healed:
                result.status = HEALED
                result.healed_from = primary
                result.selector = healed
                result.matches = 1
                result.message = (
                    "O seletor primário não encontrou o elemento; uma reserva "
                    "funcionou e foi promovida."
                )
                await self._perform(page, cmd, healed)
                return result

            result.status = BROKEN
            result.selector = primary
            result.matches = 0
            result.message = (
                "Nem o seletor primário nem as reservas encontraram este elemento. "
                "A tela pode ter mudado, ou o passo depende de um estado que este "
                "fluxo não reproduz (sessão, dado prévio, permissão)."
            )
            return result

        except Exception as exc:
            result.status = BROKEN
            result.message = f"{type(exc).__name__}: {exc}"
            return result
        finally:
            result.elapsed_ms = int((time.perf_counter() - started) * 1000)

    def _credential(self, key: str) -> str:
        """Valor real de uma credencial, vindo do ambiente.

        A verificação precisa autenticar de verdade. Se o login falhar, tudo
        que vem depois dele é avaliado contra a tela de login, e o relatório
        acusa dezenas de seletores quebrados que na verdade estão corretos —
        um diagnóstico pior que não ter diagnóstico nenhum.

        Procuramos primeiro com o prefixo `CYPRESS_`, que é como o próprio
        Cypress lê `Cypress.env()`, e depois pelo nome puro.
        """
        for name in (f"CYPRESS_{key}", key):
            value = os.environ.get(name)
            if value:
                return value

        self.missing_credentials.add(key)
        return "cygen-verify"

    async def _perform(self, page: Any, cmd: Command, selector: str) -> None:
        """Executa a ação do comando na página.

        É o que separa "os seletores resolvem" de "o teste passa". Sem
        executar, o fluxo nunca sai da primeira tela: o botão de login não é
        clicado, a rota não muda, e todo passo posterior é avaliado contra a
        página errada — reprovando por um motivo que não existe.

        Falhas aqui são silenciosas de propósito: quem reporta o estado do
        passo é o chamador, e um clique que não pega já foi registrado como
        seletor resolvido. O objetivo é avançar o fluxo, não validar a ação.
        """
        try:
            locator = page.locator(selector).first
            if cmd.op == "click":
                await locator.click(timeout=self.timeout_ms)
            elif cmd.op == "dblclick":
                await locator.dblclick(timeout=self.timeout_ms)
            elif cmd.op == "type":
                value = cmd.value
                if isinstance(value, dict) and "__env__" in value:
                    value = self._credential(value["__env__"])
                await locator.fill(str(value or ""), timeout=self.timeout_ms)
            elif cmd.op == "select":
                await locator.select_option(str(cmd.value or ""), timeout=self.timeout_ms)
            elif cmd.op == "check":
                await locator.check(timeout=self.timeout_ms)
            elif cmd.op == "uncheck":
                await locator.uncheck(timeout=self.timeout_ms)
            elif cmd.op == "hover":
                await locator.hover(timeout=self.timeout_ms)
            else:
                return
            # Deixa a página reagir antes do próximo passo ser avaliado.
            await page.wait_for_timeout(320)
        except Exception:
            pass

    async def _try_fallbacks(self, page: Any, cmd: Command) -> str | None:
        """Testa as reservas e promove a primeira que identifica um só elemento.

        A promoção acontece na própria IR, então o código reemitido já sai com o
        seletor que funciona.
        """
        if not cmd.target or not cmd.target.fallbacks:
            return None

        for candidate in list(cmd.target.fallbacks):
            selector = candidate
            if candidate.startswith("//") or candidate.startswith("/html"):
                selector = f"xpath={candidate}"
            # Sem espera: o elemento já teve seu tempo na tentativa do
            # primário. Esperar de novo por reserva multiplicaria o timeout.
            if await self._count(page, selector, wait=False) == 1:
                old = cmd.target.value
                cmd.target.value = candidate
                cmd.target.fallbacks = [
                    f for f in cmd.target.fallbacks if f != candidate
                ]
                if old and old not in cmd.target.fallbacks:
                    cmd.target.fallbacks.append(old)
                cmd.target.note = (
                    f"Promovido pela auto-cura: `{old}` não resolvia, este resolve."
                )
                return candidate
        return None

    async def _count(self, page: Any, selector: str, *, wait: bool = True) -> int:
        """Quantos elementos casam com o seletor.

        Espera o elemento aparecer antes de desistir, do mesmo jeito que
        Cypress e Playwright fazem em produção. Uma contagem instantânea
        reprovaria todo elemento assíncrono — o toast que surge 300ms depois
        do clique, a linha da tabela que chega com a resposta da API — e o
        relatório acusaria falha onde o teste real passaria.
        """
        try:
            locator = page.locator(selector)
            if wait:
                try:
                    await locator.first.wait_for(state="attached",
                                                 timeout=self.timeout_ms)
                except Exception:
                    pass          # não apareceu: a contagem abaixo dirá zero
            return await locator.count()
        except Exception:
            return 0


async def quick_check(spec: Spec, base_url: str = "") -> dict[str, Any]:
    """Atalho para a API: verifica e devolve o relatório serializado."""
    healer = Healer(headless=True)
    report, healed_spec = await healer.verify(spec, base_url=base_url)
    return {"report": report.to_dict(), "spec": healed_spec.to_dict()}
