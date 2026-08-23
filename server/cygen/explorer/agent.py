"""
O auto-teste: a IA explora o sistema e os fluxos saem prontos.

A ideia é trocar quem produz os eventos. O gravador do Cygen já observa cliques
e digitação no navegador e transforma isso em passos com evidência — mutações,
rede, armazenamento. Quem clicava era uma pessoa. Aqui quem clica é o agente,
pelo Playwright, e o mesmo injetor registra os eventos do mesmo jeito: são
eventos de DOM de verdade, indistinguíveis dos de um humano.

O resultado é que tudo depois disso continua valendo — Oracle deduz as
assertions, o emissor escreve o código, o healer valida. O agente não gera
código: ele gera *jornadas*, e o resto do Cygen faz o que já fazia.

Cada marco declarado pelo agente vira um fluxo salvo, com nome próprio. Uma
execução costuma render vários — que é o que a sequência espera receber.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Awaitable, Callable

from ..intel.intent import compile_steps
from ..recorder.engine import RecordingSession
from . import dados, perception, safety
from .planner import Planner

Progress = Callable[[dict[str, Any]], Awaitable[None]]


class AutoTest:
    """Uma execução do auto-teste, do briefing aos fluxos salvos."""

    def __init__(self, *, briefing: str, base_url: str, provider: str,
                 model: str | None = None, max_passos: int = 40,
                 headless: bool = False, permitir_destrutivo: bool = False,
                 valores: dict[str, str] | None = None,
                 on_progress: Progress | None = None) -> None:
        self.briefing = briefing
        self.base_url = base_url
        self.max_passos = max_passos
        self.headless = headless
        self.permitir_destrutivo = permitir_destrutivo
        self.valores = valores or {}
        self.on_progress = on_progress

        self.planner = Planner(provider, model)
        self.session: RecordingSession | None = None

        self.passos: list[dict[str, Any]] = []      # o que o agente fez
        self.marcos: list[dict[str, Any]] = []      # fluxos delimitados
        self.telas: set[str] = set()
        self.parar = False
        self.erro = ""
        self._ultimo_evento = 0                     # corte do marco anterior
        # Repetição é o jeito mais comum de uma exploração autônoma travar: o
        # modelo escolhe a mesma ação, a tela não muda, e ele escolhe de novo
        # até o orçamento acabar. Guardamos o suficiente para perceber.
        self._ultima_assinatura = ""
        self._repeticoes = 0
        self._esgotados: set[str] = set()

    # -- comunicação ---------------------------------------------------------

    async def _aviso(self, tipo: str, **dados_extra: Any) -> None:
        if self.on_progress:
            try:
                await self.on_progress({"tipo": tipo, **dados_extra})
            except Exception:
                pass

    # -- execução ------------------------------------------------------------

    async def run(self) -> dict[str, Any]:
        inicio = time.perf_counter()

        # O gravador é quem abre o navegador e injeta o observador. O agente
        # dirige a mesma página: os cliques dele entram na gravação.
        self.session = RecordingSession(on_event=self._on_event,
                                        headless=self.headless)
        try:
            await self.session.start(self.base_url)
        except Exception as exc:
            return {"ok": False, "error": f"não consegui abrir o navegador: {exc}"}

        await self._aviso("inicio", url=self.base_url)

        try:
            await self._loop()
        except Exception as exc:
            self.erro = f"{type(exc).__name__}: {exc}"

        # O que sobrou depois do último marco ainda é uma jornada — fechada
        # antes de encerrar a sessão, enquanto a página ainda existe para
        # esperar os eventos pendentes.
        try:
            await self._fechar_marco("Exploração final", forcado=True)
        except Exception:
            pass

        try:
            await self.session.stop()
        except Exception:
            pass

        return {
            "ok": not self.erro,
            "error": self.erro,
            "passos": self.passos,
            "marcos": [m["nome"] for m in self.marcos],
            "fluxos": self._montar_fluxos(),
            "telas": len(self.telas),
            "chamadas": self.planner.chamadas,
            "tokens": self.planner.tokens,
            "custo": round(self.planner.custo, 5),
            "duracao": int(time.perf_counter() - inicio),
        }

    async def _on_event(self, event: dict[str, Any]) -> None:
        """O gravador avisa; o agente não precisa fazer nada com isso."""
        return None

    async def _loop(self) -> None:
        page = self.session.page
        historico: list[str] = []

        for passo in range(1, self.max_passos + 1):
            if self.parar:
                break

            estado = await perception.observe(page)
            tela = perception.fingerprint(estado)
            self.telas.add(tela)

            # Elementos que já se provaram inúteis saem da lista antes de o
            # modelo vê-los: é mais eficaz do que pedir para ele não insistir.
            estado = self._sem_esgotados(estado)

            acao = await self.planner.decide(
                briefing=self.briefing, estado=estado, historico=historico,
                passo=passo, limite=self.max_passos,
            )

            travado = self._detectar_repeticao(acao, tela)
            if travado:
                historico.append(travado)
                await self._aviso("passo", passo=passo, descricao=travado,
                                  porque="evitando repetir a mesma ação",
                                  url=estado.get("url", ""))
                self.passos.append({"passo": passo, "acao": "repetida",
                                    "descricao": travado, "porque": "",
                                    "url": estado.get("url", "")})
                continue

            antes = len(self.session.collected())
            url_antes = estado.get("url", "")

            descricao = await self._executar(page, estado, acao)
            historico.append(descricao)

            # Deixa o observador fechar a janela dele antes de seguir.
            await self._respirar(page)
            self._completar_evento(acao, estado, antes, url_antes, page)

            self.passos.append({
                "passo": passo,
                "acao": acao.get("acao", "?"),
                "descricao": descricao,
                "porque": acao.get("porque", ""),
                "url": estado.get("url", ""),
            })
            await self._aviso("passo", passo=passo, descricao=descricao,
                              porque=acao.get("porque", ""),
                              url=estado.get("url", ""))

            if acao.get("acao") == "concluir":
                break

    async def _respirar(self, page: Any) -> None:
        """Espera a janela de observação do injetor fechar.

        O observador emite a evidência 700ms depois da ação. Agir antes disso
        faz a próxima ação fechar a janela da anterior, e o passo chega ao
        Oracle sem as mutações que justificariam uma assertion.
        """
        try:
            await page.wait_for_timeout(900)
        except Exception:
            pass

    def _completar_evento(self, acao: dict[str, Any], estado: dict[str, Any],
                          antes: int, url_antes: str, page: Any) -> None:
        """Registra o passo quando o observador não conseguiu registrar.

        Um clique que navega derruba a página antes de a mensagem chegar ao
        backend: a chamada morre em voo junto com o documento. Para um humano
        isso quase nunca acontece — ele leva segundos entre um clique e outro —
        mas o agente clica no instante seguinte, e era o passo mais importante
        que se perdia: o “Entrar” do login.

        O agente sabe o que fez e em qual elemento. O evento sintetizado tem
        menos evidência que o original (sem mutações), mas preserva a ação e a
        troca de URL, que é o que o Oracle precisa para um clique de navegação.
        """
        if acao.get("acao") not in ("clicar", "digitar", "selecionar"):
            return
        if not self.session or len(self.session.collected()) > antes:
            return          # o observador deu conta

        indice = acao.get("indice")
        elementos = estado.get("elementos", [])
        if not isinstance(indice, int) or not (0 <= indice < len(elementos)):
            return
        el = elementos[indice]

        tipo = {"clicar": "click", "digitar": "type", "selecionar": "select"}[acao["acao"]]
        seletor = el.get("seletor") or ""
        atributos: dict[str, Any] = {}
        if seletor.startswith("#"):
            atributos["id"] = seletor[1:]
        elif "[name=" in seletor:
            atributos["name"] = seletor.split('[name="')[-1].rstrip('"]')
        elif seletor.startswith("["):
            chave, _, valor = seletor[1:-1].partition("=")
            atributos[chave] = valor.strip('"')

        try:
            url_depois = page.url
        except Exception:
            url_depois = url_antes

        self.session.events.append({
            "seq": 10_000 + len(self.session.events),
            "type": tipo,
            "phase": "settled",
            "timestamp": time.time() * 1000,
            "url": url_antes,
            "value": acao.get("valor"),
            "element": {
                "tag": "button" if el.get("tipo") == "botao" else "input",
                "text": el.get("nome", ""),
                "classList": [],
                "attributes": atributos,
                "matchCounts": {seletor: 1} if seletor else {},
            },
            "ancestors": [],
            "urlBefore": url_antes,
            "urlAfter": url_depois,
            "mutations": {"added": [], "removed": []},
            "network": [],
            "consoleErrors": [],
            "sintetico": True,
        })

    def _assinatura(self, acao: dict[str, Any], tela: str) -> str:
        """Identidade de uma ação, para reconhecer a mesma coisa de novo."""
        return "|".join(str(acao.get(k, "")) for k in
                        ("acao", "indice", "valor", "url")) + "@" + tela

    def _detectar_repeticao(self, acao: dict[str, Any], tela: str) -> str:
        """Devolve uma explicação quando a ação é repetição inútil.

        A mesma ação na mesma tela duas vezes seguidas já é suspeita: se a
        primeira tivesse funcionado, a tela teria mudado. Na terceira o
        elemento é aposentado — insistir nele consumiria o orçamento inteiro,
        que é como esta função nasceu, depois de o agente preencher o mesmo
        campo doze vezes.
        """
        if acao.get("acao") in ("marco", "concluir", "esperar"):
            return ""

        assinatura = self._assinatura(acao, tela)
        if assinatura != self._ultima_assinatura:
            self._ultima_assinatura = assinatura
            self._repeticoes = 0
            return ""

        self._repeticoes += 1
        alvo = acao.get("indice")

        if self._repeticoes >= 2 and alvo is not None:
            self._esgotados.add(f"{tela}:{alvo}")
            self._repeticoes = 0
            self._ultima_assinatura = ""
            return (f"a mesma ação foi escolhida três vezes sem mudar a tela; "
                    f"o elemento {alvo} foi descartado para o agente tentar outro caminho")

        return ("essa ação acabou de ser feita e a tela não mudou — "
                "escolha outra")

    def _sem_esgotados(self, estado: dict[str, Any]) -> dict[str, Any]:
        """A tela sem os elementos que já se mostraram sem efeito."""
        tela = perception.fingerprint(estado)
        sobrando = [e for i, e in enumerate(estado.get("elementos", []))
                    if f"{tela}:{i}" not in self._esgotados]
        if len(sobrando) == len(estado.get("elementos", [])):
            return estado
        return {**estado, "elementos": sobrando}

    async def _executar(self, page: Any, estado: dict[str, Any],
                        acao: dict[str, Any]) -> str:
        """Realiza a ação escolhida e devolve o que foi feito, em português."""
        tipo = acao.get("acao", "")

        if tipo == "concluir":
            return f"concluiu: {acao.get('porque', '')}"

        if tipo == "marco":
            nome = acao.get("nome") or f"Fluxo {len(self.marcos) + 1}"
            await self._fechar_marco(nome)
            await self._aviso("marco", nome=nome)
            return f"marcou o fim do fluxo “{nome}”"

        if tipo == "esperar":
            await page.wait_for_timeout(900)
            return f"esperou ({acao.get('porque', '')})"

        if tipo == "navegar":
            destino = acao.get("url") or "/"
            if not destino.startswith("http"):
                destino = self.base_url.rstrip("/") + "/" + destino.lstrip("/")
            try:
                await page.goto(destino, wait_until="domcontentloaded", timeout=20000)
                return f"navegou para {destino}"
            except Exception as exc:
                return f"não consegui navegar para {destino}: {exc}"

        elementos = estado.get("elementos", [])
        indice = acao.get("indice")
        if not isinstance(indice, int) or not (0 <= indice < len(elementos)):
            return f"índice inválido ({indice}); nada foi feito"

        elemento = elementos[indice]
        pode, motivo = safety.allowed(
            elemento, permitir_destrutivo=self.permitir_destrutivo)
        if not pode:
            await self._aviso("bloqueado", motivo=motivo)
            return f"ação recusada: {motivo}"

        alvo = self._localizar(page, elemento, indice)
        rotulo = elemento.get("nome") or elemento.get("seletor") or f"elemento {indice}"

        try:
            if tipo == "digitar":
                valor = acao.get("valor") or dados.guess(elemento, self.valores)
                # O usuário mandou; a heurística só cobre o que ele não disse.
                combinado = dados.guess(elemento, self.valores)
                if any(chave.lower() in (elemento.get("nome") or "").lower()
                       for chave in self.valores):
                    valor = combinado
                await alvo.fill(str(valor), timeout=8000)
                mostrado = "•••" if elemento.get("tipo") == "senha" else valor
                return f'preencheu “{rotulo}” com “{mostrado}”'

            if tipo == "selecionar":
                await alvo.select_option(str(acao.get("valor") or ""), timeout=8000)
                return f'selecionou “{acao.get("valor")}” em “{rotulo}”'

            if tipo == "clicar":
                await alvo.click(timeout=8000)
                return f'clicou em “{rotulo}”'

            return f"ação desconhecida: {tipo}"

        except Exception as exc:
            # Falha de ação não derruba a execução: o agente vê o resultado na
            # próxima observação e tenta outro caminho.
            return f'não consegui {tipo} em “{rotulo}”: {type(exc).__name__}'

    def _localizar(self, page: Any, elemento: dict[str, Any], indice: int) -> Any:
        """Locator do elemento, pelo seletor quando existe e pelo rótulo quando não."""
        seletor = elemento.get("seletor")
        if seletor:
            return page.locator(seletor).first
        nome = elemento.get("nome") or ""
        if nome:
            return page.get_by_text(nome, exact=False).first
        return page.locator("body")

    # -- fluxos --------------------------------------------------------------

    async def _fechar_marco(self, nome: str, *, forcado: bool = False) -> None:
        """Registra o fim de uma jornada. O corte real acontece no final.

        A primeira versão fatiava os eventos aqui, e perdia os últimos: o
        evento de um clique chega pela ponte do Playwright de forma assíncrona,
        e um clique que navega chega ainda mais tarde. O resultado era um teste
        de login sem o botão “Entrar” — e o teste seguinte falhando por não
        estar autenticado.

        Guardar só o instante e particionar depois elimina a corrida: quando a
        exploração termina, todos os eventos já chegaram, e cada um vai para a
        jornada em que de fato aconteceu.
        """
        if self.session and self.session.page:
            try:
                await self.session.page.wait_for_timeout(700)
            except Exception:
                pass
        self.marcos.append({"nome": nome, "ate": time.time() * 1000})

    def _montar_fluxos(self) -> list[dict[str, Any]]:
        """Cada marco vira um fluxo, com os eventos que aconteceram até ele.

        A compilação é a mesma de uma gravação humana — `compile_steps` não
        sabe (nem precisa saber) que quem clicou foi um agente.
        """
        eventos = self.session.collected() if self.session else []
        if not eventos:
            return []

        # O `visit` inicial não tem timestamp do navegador; ele abre a primeira
        # jornada e por isso recebe o instante mais antigo possível.
        def quando(evento: dict[str, Any]) -> float:
            return float(evento.get("timestamp") or 0)

        out: list[dict[str, Any]] = []
        anterior = 0.0
        for marco in self.marcos:
            fatia = [e for e in eventos if anterior <= quando(e) < marco["ate"]]
            anterior = marco["ate"]
            if not fatia:
                continue

            steps, sugestoes = compile_steps(fatia)
            if not steps:
                continue
            out.append({
                "name": marco["nome"],
                "description": "gerado pelo auto-teste do Cygen",
                "baseUrl": self.base_url,
                "steps": [s.to_dict() for s in steps],
                "suggestions": sugestoes,
                "rawEventCount": len(fatia),
                "auto": True,
            })
        return out
