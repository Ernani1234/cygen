"""
Motor de gravação sobre Playwright.

Substitui o par Selenium + chromedriver.exe da v2. Três ganhos estruturais:

    add_init_script  — o gravador é reinstalado a cada navegação, iframe e
                       recarga. A v2 injetava uma vez e perdia tudo na
                       primeira troca de rota.
    route/response   — a rede é capturada pelo próprio browser, sem precisar
                       ler performance logs por polling.
    install          — o navegador é baixado sob demanda; nada de versionar
                       um .exe de driver dentro do repositório.

A correlação rede↔ação acontece aqui: uma requisição disparada dentro da
janela de estabilização de um passo é anexada àquele passo, e é o que permite
ao Oracle trocar `cy.wait(3000)` por `cy.wait('@alias')`.
"""

from __future__ import annotations

import asyncio
import json
import re
import time
from pathlib import Path
from typing import Any, Awaitable, Callable
from urllib.parse import urlparse

INJECTOR = Path(__file__).with_name("injector.js")

# Recursos que nunca interessam a um teste funcional.
_IGNORED_RESOURCES = {"image", "font", "stylesheet", "media", "manifest", "other"}
_IGNORED_EXTENSIONS = re.compile(
    r"\.(png|jpe?g|gif|svg|webp|ico|woff2?|ttf|eot|css|map)(\?|$)", re.I
)
_ANALYTICS = re.compile(
    r"(google-analytics|googletagmanager|hotjar|segment|mixpanel|sentry|"
    r"doubleclick|facebook\.net|clarity\.ms|newrelic|datadoghq)", re.I
)


def _volatile_segment(segment: str) -> bool:
    """True se o trecho de caminho parece um id gerado."""
    if re.fullmatch(r"\d+", segment) and len(segment) >= 2:
        return True
    if re.fullmatch(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", segment, re.I):
        return True
    if len(segment) > 16 and re.fullmatch(r"[0-9a-zA-Z_-]+", segment) and any(c.isdigit() for c in segment):
        return True
    return False


def url_pattern(url: str) -> str:
    """Transforma uma URL concreta num glob estável para `cy.intercept`.

    `/api/orcamento/8814/itens` vira `**/api/orcamento/*/itens*`, para o teste
    não depender do registro que existia no dia da gravação.
    """
    parsed = urlparse(url)
    segments = [s for s in parsed.path.split("/") if s]
    generalized = ["*" if _volatile_segment(s) else s for s in segments]
    if not generalized:
        return "**/*"
    return "**/" + "/".join(generalized) + "*"


def alias_for(url: str, method: str) -> str:
    """Alias legível e válido como identificador JS."""
    parsed = urlparse(url)
    segments = [s for s in parsed.path.split("/") if s and not _volatile_segment(s)]
    tail = segments[-1] if segments else "request"
    tail = re.sub(r"[^a-zA-Z0-9]+", "_", tail).strip("_").lower() or "request"
    prefix = {"GET": "get", "POST": "post", "PUT": "put",
              "PATCH": "patch", "DELETE": "delete"}.get(method.upper(), "req")
    return f"{prefix}_{tail}"


class RecordingSession:
    """Uma sessão de gravação viva.

    Mantém a lista de eventos observados e a fila de requisições recentes,
    correlacionando-as no momento em que cada passo estabiliza.
    """

    def __init__(
        self,
        *,
        on_event: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
        browser_name: str = "chromium",
        headless: bool = False,
        viewport: tuple[int, int] = (1440, 900),
    ) -> None:
        self.on_event = on_event
        self.browser_name = browser_name
        self.headless = headless
        self.viewport = viewport

        self.events: list[dict[str, Any]] = []
        self.network: list[dict[str, Any]] = []
        self.started_at: float | None = None
        self.base_url = ""
        self.recording = False
        self.picker = False

        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None
        self._alias_counts: dict[str, int] = {}
        self._lock = asyncio.Lock()

    # -- ciclo de vida ------------------------------------------------------

    @property
    def page(self):
        """A página em uso, para quem precisa dirigi-la de fora.

        O auto-teste age nesta mesma página: os cliques dele são eventos de DOM
        reais, capturados pelo injetor como qualquer outro. É o que permite a
        exploração automática reaproveitar o pipeline inteiro da gravação.
        """
        return self._page

    async def start(self, url: str) -> dict[str, Any]:
        """Abre o navegador, instala o gravador e navega para a URL."""
        from playwright.async_api import async_playwright

        self._playwright = await async_playwright().start()
        launcher = getattr(self._playwright, self.browser_name)

        self._browser = await launcher.launch(
            headless=self.headless,
            args=["--disable-blink-features=AutomationControlled",
                  "--disable-popup-blocking"] if self.browser_name == "chromium" else [],
        )
        self._context = await self._browser.new_context(
            viewport={"width": self.viewport[0], "height": self.viewport[1]},
            ignore_https_errors=True,
            locale="pt-BR",
        )

        # O binding precisa existir antes do init script rodar.
        await self._context.expose_binding("cygenEmit", self._on_page_event)
        await self._context.add_init_script(INJECTOR.read_text(encoding="utf-8"))

        self._context.on("response", self._on_response)
        self._context.on("page", self._on_new_page)

        self._page = await self._context.new_page()

        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        self.base_url = f"{urlparse(url).scheme}://{urlparse(url).netloc}"

        self.started_at = time.time()
        self.recording = True

        await self._page.goto(url, wait_until="domcontentloaded", timeout=60_000)

        await self._push({
            "seq": 0, "type": "visit", "phase": "settled",
            "timestamp": self.started_at * 1000, "url": url,
            "element": {}, "ancestors": [], "mutations": {}, "network": [],
            "storageDelta": {}, "consoleErrors": [],
        })
        return {"ok": True, "url": url, "baseUrl": self.base_url}

    async def stop(self) -> dict[str, Any]:
        """Encerra a gravação e libera o navegador."""
        self.recording = False
        try:
            if self._context:
                await self._context.close()
            if self._browser:
                await self._browser.close()
            if self._playwright:
                await self._playwright.stop()
        except Exception:
            pass
        finally:
            self._page = self._context = self._browser = self._playwright = None

        return {
            "ok": True,
            "events": len(self.events),
            "duration": round(time.time() - self.started_at) if self.started_at else 0,
        }

    async def pause(self) -> None:
        if self._page:
            await self._page.evaluate("window.__cygenPause && window.__cygenPause()")

    async def resume(self) -> None:
        if self._page:
            await self._page.evaluate("window.__cygenResume && window.__cygenResume()")

    async def set_picker(self, active: bool) -> None:
        """Liga/desliga o modo 'apontar elemento para criar assertion'."""
        self.picker = active
        if self._page:
            await self._page.evaluate(
                "(a) => window.__cygenSetPicker && window.__cygenSetPicker(a)", active
            )

    async def navigate(self, url: str) -> None:
        if self._page:
            if not url.startswith(("http://", "https://")):
                url = "https://" + url
            await self._page.goto(url, wait_until="domcontentloaded")

    async def screenshot(self) -> bytes | None:
        """Captura a tela atual — usada pelo preview ao vivo da UI."""
        if not self._page:
            return None
        try:
            return await self._page.screenshot(type="jpeg", quality=62, scale="css")
        except Exception:
            return None

    # -- captura ------------------------------------------------------------

    async def _on_new_page(self, page: Any) -> None:
        """Abas abertas pelo app também são gravadas."""
        self._page = page

    async def _on_page_event(self, source: Any, event: dict[str, Any]) -> None:
        """Recebe um evento vindo do script injetado."""
        if not self.recording:
            return
        if event.get("type") == "ready":
            return

        if event.get("phase") == "start":
            # Passo apareceu: a UI mostra na hora, evidência chega depois.
            await self._emit({**event, "_provisional": True})
            return

        event["network"] = self._network_for(event)
        await self._push(event)

    async def _push(self, event: dict[str, Any]) -> None:
        async with self._lock:
            self.events.append(event)
        await self._emit(event)

    async def _emit(self, event: dict[str, Any]) -> None:
        if self.on_event:
            try:
                await self.on_event(event)
            except Exception:
                pass

    async def _on_response(self, response: Any) -> None:
        """Registra respostas relevantes para correlação posterior."""
        if not self.recording:
            return
        try:
            request = response.request
            if request.resource_type in _IGNORED_RESOURCES:
                return
            url = response.url
            if _IGNORED_EXTENSIONS.search(url) or _ANALYTICS.search(url):
                return

            method = request.method.upper()
            alias = self._unique_alias(alias_for(url, method))

            entry: dict[str, Any] = {
                "url": url,
                "method": method,
                "status": response.status,
                "alias": alias,
                "pattern": url_pattern(url),
                "at": time.time() * 1000,
                "resourceType": request.resource_type,
            }

            # Só lemos o corpo de respostas JSON pequenas: o Oracle usa isso
            # para inferir assertions sobre o payload.
            content_type = (response.headers or {}).get("content-type", "")
            if "json" in content_type.lower():
                try:
                    body = await response.json()
                    entry["bodyPreview"] = _shrink(body)
                except Exception:
                    pass

            self.network.append(entry)
            if len(self.network) > 400:
                self.network = self.network[-200:]
        except Exception:
            pass

    def _unique_alias(self, base: str) -> str:
        """Garante alias único: dois POSTs no mesmo endpoint não colidem."""
        count = self._alias_counts.get(base, 0)
        self._alias_counts[base] = count + 1
        return base if count == 0 else f"{base}_{count + 1}"

    # Folga sobre a janela do passo. Existe porque a resposta HTTP chega alguns
    # milissegundos depois do evento que a disparou. Curta de propósito: uma
    # folga generosa faz um passo reivindicar as chamadas do passo seguinte, e
    # a assertion de rede aparece no lugar errado do teste.
    NETWORK_SLACK_MS = 180

    def _network_for(self, event: dict[str, Any]) -> list[dict[str, Any]]:
        """Requisições disparadas dentro da janela efetiva do passo."""
        start = float(event.get("timestamp") or 0)
        duration = float(event.get("durationMs") or 0)
        # Janela cortada por outra ação tem limite exato; só a que terminou
        # naturalmente merece folga para a resposta atrasada.
        slack = 0 if event.get("truncated") else self.NETWORK_SLACK_MS
        end = start + duration + slack

        matched = [r for r in self.network if start <= r["at"] <= end]
        # Limpa o que já foi consumido para não anexar a mesma chamada duas vezes.
        consumed = {id(r) for r in matched}
        self.network = [r for r in self.network if id(r) not in consumed]
        return matched[:8]

    # -- consulta -----------------------------------------------------------

    def snapshot(self) -> dict[str, Any]:
        """Estado atual da sessão, para a UI."""
        settled = [e for e in self.events if e.get("phase") != "start"]
        return {
            "recording": self.recording,
            "picker": self.picker,
            "eventCount": len(settled),
            "baseUrl": self.base_url,
            "duration": round(time.time() - self.started_at) if self.started_at else 0,
            "networkCount": len(self.network),
        }

    def collected(self) -> list[dict[str, Any]]:
        """Eventos estabilizados, prontos para o compilador de intenção."""
        return [e for e in self.events
                if e.get("phase") != "start" and e.get("type") != "ready"]


def _shrink(value: Any, depth: int = 0) -> Any:
    """Reduz um payload JSON ao que cabe numa evidência."""
    if depth > 2:
        return "…"
    if isinstance(value, dict):
        return {k: _shrink(v, depth + 1) for k, v in list(value.items())[:12]}
    if isinstance(value, list):
        return [_shrink(v, depth + 1) for v in value[:5]]
    if isinstance(value, str):
        return value[:120]
    return value


async def ensure_browser(browser_name: str = "chromium") -> dict[str, Any]:
    """Verifica se o navegador do Playwright está instalado; instala se não.

    Substitui o ritual de baixar o chromedriver certo para a versão certa do
    Chrome — a maior fonte de 'não abre aqui' na v2.
    """
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return {"ok": False, "error": "playwright não instalado",
                "fix": "pip install playwright"}

    try:
        async with async_playwright() as p:
            launcher = getattr(p, browser_name)
            browser = await launcher.launch(headless=True)
            version = browser.version
            await browser.close()
            return {"ok": True, "browser": browser_name, "version": version}
    except Exception as exc:
        message = str(exc)
        if "Executable doesn't exist" in message or "playwright install" in message:
            proc = await asyncio.create_subprocess_exec(
                "python", "-m", "playwright", "install", browser_name,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
            )
            out, _ = await proc.communicate()
            if proc.returncode == 0:
                return {"ok": True, "browser": browser_name, "installed": True}
            return {"ok": False, "error": (out or b"").decode("utf-8", "replace")[-500:]}
        return {"ok": False, "error": message[:500]}
