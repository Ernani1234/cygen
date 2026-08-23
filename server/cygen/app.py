"""
Backend do Cygen.

FastAPI servindo a UI e a API, mais um WebSocket que empurra cada passo
capturado para a interface no instante em que acontece. É o que substitui o
screenshot redimensionado a 10fps da v2: em vez de a UI ficar perguntando "e
agora?", o gravador avisa.
"""

from __future__ import annotations

import asyncio
import base64
import json
import re
import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .ai import registry
from .ai.client import SYSTEM_REVIEW, SYSTEM_RULES, AIClient
from .emit import cypress as emit_cypress
from .emit import fixtures as emit_fixtures
from .emit import playwright_ts as emit_playwright
from .emit.build import build_spec
from .intel import catalog
from .intel.intent import Step, compile_steps
from .intel.oracle import Oracle
from .intel.selectors import SelectorEngine
from .recorder.engine import RecordingSession, ensure_browser
from .store import FlowStore, Settings, SuiteStore
from .verify.healer import Healer

UI_DIR = Path(__file__).resolve().parent.parent.parent / "ui"

app = FastAPI(title="Cygen", version="3.0.0")
store = FlowStore()
suites = SuiteStore()
settings = Settings()

# Estado vivo da aplicação. Uma sessão de gravação por vez — gravar dois fluxos
# ao mesmo tempo confundiria a correlação de rede entre eles.
session: RecordingSession | None = None
sockets: set[WebSocket] = set()


# ---------------------------------------------------------------------------
# WebSocket
# ---------------------------------------------------------------------------

async def broadcast(kind: str, payload: Any) -> None:
    """Envia uma mensagem a todos os clientes conectados."""
    if not sockets:
        return
    message = json.dumps({"type": kind, "data": payload}, ensure_ascii=False, default=str)
    dead: list[WebSocket] = []
    for socket in list(sockets):
        try:
            await socket.send_text(message)
        except Exception:
            dead.append(socket)
    for socket in dead:
        sockets.discard(socket)


@app.websocket("/ws")
async def websocket_endpoint(socket: WebSocket) -> None:
    await socket.accept()
    sockets.add(socket)
    try:
        await socket.send_text(json.dumps({
            "type": "hello",
            "data": {
                "recording": bool(session and session.recording),
                "oracleRules": Oracle.rule_count(),
                "assertions": catalog.total(),
                "providers": registry.stats(),
            },
        }))
        while True:
            # O cliente não envia comandos por aqui — o WS é só de saída. Este
            # receive mantém a conexão viva e detecta a desconexão.
            await socket.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        sockets.discard(socket)


async def on_recorder_event(event: dict[str, Any]) -> None:
    """Repassa um evento do gravador para a UI, já traduzido em passo."""
    from .intel.intent import human_name, label_for

    element = event.get("element") or {}
    kind = (event.get("type") or "").lower()
    await broadcast("event", {
        "seq": event.get("seq"),
        "type": kind,
        "label": label_for(kind, element, event.get("value"), event.get("url", "")),
        "provisional": bool(event.get("_provisional")),
        "url": event.get("url", ""),
        "networkCount": len(event.get("network") or []),
        "hasMutations": bool((event.get("mutations") or {}).get("added")
                             or (event.get("mutations") or {}).get("removed")),
        "consoleErrors": len(event.get("consoleErrors") or []),
    })


# ---------------------------------------------------------------------------
# Modelos de requisição
# ---------------------------------------------------------------------------

class StartBody(BaseModel):
    url: str
    browser: str = "chromium"
    headless: bool = False


class NavigateBody(BaseModel):
    url: str


class PickerBody(BaseModel):
    active: bool


class GenerateBody(BaseModel):
    name: str = "Fluxo gravado"
    description: str = ""
    baseUrl: str = ""
    flowId: str | None = None
    disabledSteps: list[int] = []
    # O que o usuário recusou, por passo. Ausente = nada recusado.
    rejectedRules: dict[str, list[str]] | None = None
    splitGroups: bool = False
    verbose: bool = True
    minConfidence: float = 0.55
    # Extrair seletores e valores para `cypress/fixtures/`, deixando o spec
    # falar em nomes (`elementos.usuario`) em vez de cadeias de seletor.
    fixtures: bool = True


class SelectorBody(BaseModel):
    """Escolha de seletor para um passo. `value` vazio volta ao automático."""

    value: str = ""
    engine: str = "css"


class CodeEditBody(BaseModel):
    """Código editado à mão. `code` nulo desfaz a edição daquela aba."""

    tab: str
    code: str | None = None


class SuiteBody(BaseModel):
    """Criação ou edição de uma sequência."""

    name: str = "Nova sequência"
    description: str = ""
    baseUrl: str = ""
    flowIds: list[str] = []
    # Ligado, cada teste começa com sessão limpa. Desligado (o padrão para uma
    # sequência), eles continuam de onde o anterior parou.
    isolate: bool = False


class SuiteRunBody(BaseModel):
    verbose: bool = True
    fixtures: bool = True


class AutoTestBody(BaseModel):
    """Briefing do auto-teste: o que testar, onde, e sob quais regras."""

    baseUrl: str
    objetivo: str = ""            # o que a IA deve fazer no sistema
    regras: str = ""              # regras de negócio e restrições
    escopo: str = "objetivo"      # objetivo | modulo | rotas | completo
    login: dict[str, str] = {}    # usuário, senha e como entrar
    valores: dict[str, str] = {}  # valores ditados para campos específicos
    provider: str = ""
    model: str | None = None
    maxPassos: int = 40
    headless: bool = False
    permitirDestrutivo: bool = False
    confirmoAmbiente: bool = False


class ChatBody(BaseModel):
    message: str
    code: str = ""
    provider: str | None = None
    model: str | None = None
    mode: str = "review"


class VerifyBody(BaseModel):
    flowId: str
    baseUrl: str = ""


class SettingsBody(BaseModel):
    values: dict[str, Any]


# ---------------------------------------------------------------------------
# Gravação
# ---------------------------------------------------------------------------

@app.post("/api/record/start")
async def record_start(body: StartBody) -> dict[str, Any]:
    global session
    if session and session.recording:
        raise HTTPException(409, "Já existe uma gravação em andamento.")

    session = RecordingSession(
        on_event=on_recorder_event,
        browser_name=body.browser or "chromium",
        headless=body.headless,
    )
    try:
        result = await session.start(body.url)
    except Exception as exc:
        session = None
        message = str(exc)
        if "Executable doesn't exist" in message or "playwright install" in message:
            raise HTTPException(
                503,
                "O navegador do Playwright ainda não foi baixado. "
                "Rode `python -m playwright install chromium` e tente de novo.",
            ) from exc
        raise HTTPException(500, f"Não foi possível iniciar o navegador: {message}") from exc

    await broadcast("recording", {"active": True, "url": result["url"]})
    return result


@app.post("/api/record/stop")
async def record_stop() -> dict[str, Any]:
    global session
    if not session:
        raise HTTPException(400, "Nenhuma gravação em andamento.")

    events = session.collected()
    result = await session.stop()
    steps, suggestions = compile_steps(events)

    flow = store.save({
        "name": "Gravação sem nome",
        "baseUrl": session.base_url,
        "steps": [s.to_dict() for s in steps],
        "suggestions": suggestions,
        "rawEventCount": len(events),
        "duration": result.get("duration", 0),
    })
    session = None

    await broadcast("recording", {"active": False})
    return {
        **result,
        "flowId": flow["id"],
        "steps": flow["steps"],
        "suggestions": suggestions,
        "collapsed": len(events) - len(steps),
    }


@app.get("/api/record/status")
async def record_status() -> dict[str, Any]:
    if not session:
        return {"recording": False}
    return session.snapshot()


@app.post("/api/record/pause")
async def record_pause() -> dict[str, Any]:
    if not session:
        raise HTTPException(400, "Nenhuma gravação em andamento.")
    await session.pause()
    return {"ok": True, "paused": True}


@app.post("/api/record/resume")
async def record_resume() -> dict[str, Any]:
    if not session:
        raise HTTPException(400, "Nenhuma gravação em andamento.")
    await session.resume()
    return {"ok": True, "paused": False}


@app.post("/api/record/navigate")
async def record_navigate(body: NavigateBody) -> dict[str, Any]:
    if not session:
        raise HTTPException(400, "Nenhuma gravação em andamento.")
    await session.navigate(body.url)
    return {"ok": True}


@app.post("/api/record/picker")
async def record_picker(body: PickerBody) -> dict[str, Any]:
    if not session:
        raise HTTPException(400, "Nenhuma gravação em andamento.")
    await session.set_picker(body.active)
    return {"ok": True, "picker": body.active}


@app.get("/api/record/screenshot")
async def record_screenshot() -> dict[str, Any]:
    """Quadro atual do navegador, para o preview ao vivo."""
    if not session:
        return {"ok": False}
    shot = await session.screenshot()
    if not shot:
        return {"ok": False}
    return {"ok": True, "image": base64.b64encode(shot).decode("ascii")}


# ---------------------------------------------------------------------------
# Fluxos
# ---------------------------------------------------------------------------

@app.get("/api/flows")
async def list_flows() -> dict[str, Any]:
    return {"flows": store.list()}


@app.get("/api/flows/{flow_id}")
async def get_flow(flow_id: str) -> dict[str, Any]:
    flow = store.load(flow_id)
    if not flow:
        raise HTTPException(404, "Fluxo não encontrado.")
    return flow


@app.delete("/api/flows/{flow_id}")
async def delete_flow(flow_id: str) -> dict[str, Any]:
    # Sequências que usavam o fluxo perdem um teste. Avisamos quais foram
    # afetadas em vez de deixar a descoberta para a próxima execução.
    affected = [s["name"] for s in suites.using_flow(flow_id)]
    if not store.delete(flow_id):
        raise HTTPException(404, "Fluxo não encontrado.")

    for summary in suites.list():
        data = suites.load(summary["id"])
        if not data or flow_id not in (data.get("flowIds") or []):
            continue
        data["flowIds"] = [f for f in data["flowIds"] if f != flow_id]
        suites.save(data)

    return {"ok": True, "affectedSuites": affected}


@app.post("/api/flows/{flow_id}/duplicate")
async def duplicate_flow(flow_id: str) -> dict[str, Any]:
    """Copia um fluxo para servir de ponto de partida a outro.

    O caso é o segundo teste de uma sequência: quase o mesmo caminho, com um
    passo a mais ou um valor diferente. Regravar tudo para mudar uma linha é
    trabalho que o Cygen não deveria pedir.

    A cópia leva os passos e as escolhas de seletor, mas não o veredito da
    verificação nem o projeto em disco: nada disso foi comprovado para o fluxo
    novo, e herdar um selo de "verificado" que ninguém verificou é pior do que
    não ter selo nenhum.
    """
    flow = store.load(flow_id)
    if not flow:
        raise HTTPException(404, "Fluxo não encontrado.")

    copy = dict(flow)
    for key in ("id", "createdAt", "updatedAt", "verification", "projectPath"):
        copy.pop(key, None)
    copy["name"] = f"{flow.get('name', 'Fluxo')} (cópia)"
    return store.save(copy)


@app.put("/api/flows/{flow_id}/steps/{index}/selector")
async def set_step_selector(flow_id: str, index: int,
                            body: SelectorBody) -> dict[str, Any]:
    """Fixa (ou solta) o seletor de um passo.

    Gravar no fluxo, e não só no estado da tela, é o que faz a escolha
    sobreviver ao "Gerar código" seguinte — que recalcula todos os planos do
    zero — e à reabertura do fluxo amanhã.
    """
    flow = store.load(flow_id)
    if not flow:
        raise HTTPException(404, "Fluxo não encontrado.")

    value = body.value.strip()
    engine = body.engine if body.engine in ("css", "text", "xpath") else "css"

    target = next((s for s in flow.get("steps", []) if s.get("index") == index), None)
    if target is None:
        raise HTTPException(404, "Passo não encontrado neste fluxo.")

    target["selectorOverride"] = (
        {"value": value, "engine": engine, "source": "manual"} if value else None
    )
    store.save(flow)
    return {"ok": True, "index": index, "override": target["selectorOverride"]}


"""Abas que o usuário pode editar, e onde cada uma cai no projeto gerado.

`None` significa que a aba não faz parte do projeto Cypress — o spec do
Playwright é entregue à parte, e escrevê-lo dentro do projeto faria o Cypress
tentar rodar um arquivo que não é dele.
"""
EDITABLE_TABS = {
    "cypress": "spec",
    "commands": "cypress/support/commands.js",
    "playwright": None,
}

# Um spec com 5 MB não veio de alguém digitando; veio de um erro ou de um
# abuso. O limite protege o JSON do fluxo de virar um arquivo intratável.
MAX_CODE_BYTES = 2_000_000


@app.put("/api/flows/{flow_id}/code")
async def set_flow_code(flow_id: str, body: CodeEditBody) -> dict[str, Any]:
    """Guarda (ou descarta) o código que o usuário editou à mão.

    A edição vive no fluxo, não na tela: fechar a janela não pode desfazer o
    que a pessoa escreveu. Ela também vence o código gerado na hora de montar
    o projeto — do contrário, editar seria um exercício de escrita sem efeito.
    """
    flow = store.load(flow_id)
    if not flow:
        raise HTTPException(404, "Fluxo não encontrado.")
    if body.tab not in EDITABLE_TABS:
        raise HTTPException(400, f"Aba desconhecida: {body.tab}")

    edits = dict(flow.get("edits") or {})
    if body.code is None:
        edits.pop(body.tab, None)
    else:
        if len(body.code.encode("utf-8")) > MAX_CODE_BYTES:
            raise HTTPException(413, "Código grande demais para ser guardado.")
        edits[body.tab] = body.code

    flow["edits"] = edits
    store.save(flow)
    return {"ok": True, "tab": body.tab, "edited": sorted(edits)}


@app.patch("/api/flows/{flow_id}")
async def update_flow(flow_id: str, patch: dict[str, Any]) -> dict[str, Any]:
    flow = store.load(flow_id)
    if not flow:
        raise HTTPException(404, "Fluxo não encontrado.")
    # Só campos editáveis pelo usuário; `steps` e `id` não vêm por aqui.
    for key in ("name", "description", "baseUrl"):
        if key in patch:
            flow[key] = patch[key]
    return store.save(flow)


# ---------------------------------------------------------------------------
# Geração de código
# ---------------------------------------------------------------------------

def _rebuild(flow: dict[str, Any], body: GenerateBody):
    """Reconstrói os passos e a spec a partir do fluxo salvo."""
    steps = [Step(**_step_kwargs(raw)) for raw in flow.get("steps", [])]
    for step in steps:
        if step.index in body.disabledSteps:
            step.enabled = False

    rejected = None
    if body.rejectedRules:
        rejected = {int(k): set(v) for k, v in body.rejectedRules.items()}

    return build_spec(
        steps,
        name=body.name or flow.get("name", "Fluxo"),
        description=body.description or flow.get("description", ""),
        base_url=body.baseUrl or flow.get("baseUrl", ""),
        suggestions=flow.get("suggestions") or [],
        oracle=Oracle(min_confidence=body.minConfidence,
                      disabled_rules=set(settings.get("disabledRules") or [])),
        engine=SelectorEngine(preferred_attrs=settings.get("preferredAttrs")),
        rejected=rejected,
    ), steps


def _step_kwargs(raw: dict[str, Any]) -> dict[str, Any]:
    """Mapeia o JSON do passo para os campos do dataclass `Step`."""
    return {
        "index": raw.get("index", 0),
        "kind": raw.get("kind", "unknown"),
        "element": raw.get("element") or {},
        "value": raw.get("value"),
        "label": raw.get("label", ""),
        "url": raw.get("url", ""),
        "evidence": raw.get("evidence") or {},
        "assertions": raw.get("assertions") or [],
        "selector": raw.get("selector"),
        "selector_override": raw.get("selectorOverride"),
        "group": raw.get("group", ""),
        "notes": raw.get("notes") or [],
        "source_events": raw.get("sourceEvents") or [],
        "enabled": raw.get("enabled", True),
        # `meta` carrega o valor pós-máscara e o estado de toggles. Perdê-lo
        # aqui faria o Oracle deixar de detectar máscara ao reabrir o fluxo.
        "meta": raw.get("meta") or {},
    }


@app.post("/api/generate")
async def generate(body: GenerateBody) -> dict[str, Any]:
    flow = store.load(body.flowId) if body.flowId else None
    if not flow:
        raise HTTPException(404, "Fluxo não encontrado.")

    spec, steps = _rebuild(flow, body)

    # As fixtures entram já na pré-visualização. Mostrar o spec com cadeias
    # literais e gravar no disco outro com `elementos.usuario` deixaria a tela
    # discordando do arquivo — e é a tela que a pessoa edita.
    mapa = emit_fixtures.extract([spec]) if body.fixtures else None
    code = emit_cypress.emit(
        spec, verbose=body.verbose, split_groups=body.splitGroups,
        header=emit_fixtures.imports_line() if mapa else "",
        closing=(emit_fixtures.closing_line(spec.name, mapa, "    ")
                 if mapa and not body.splitGroups else None),
    )
    if mapa:
        code = emit_fixtures.rewrite(code, mapa["porCadeia"])

    outputs: dict[str, Any] = {
        "cypress": {
            "filename": emit_cypress.spec_filename(spec.name),
            "code": code,
        }
    }
    if settings.get("emitPlaywright"):
        outputs["playwright"] = {
            "filename": emit_playwright.spec_filename(spec.name),
            "code": emit_playwright.emit(spec, verbose=body.verbose),
        }

    commands = emit_cypress.emit_commands_file(spec)
    if commands:
        outputs["commands"] = {"filename": "commands.js", "code": commands}

    # Guarda os passos reanalisados: as assertions do Oracle e os planos de
    # seletor foram recalculados agora e valem para a próxima abertura.
    flow["steps"] = [s.to_dict() for s in steps]
    flow["name"] = spec.name
    flow["description"] = spec.description
    flow["baseUrl"] = spec.base_url
    flow["spec"] = spec.to_dict()
    # E guarda o código em si. Sem isto, reabrir um fluxo mostrava uma tela
    # vazia pedindo para gerar de novo — mesmo que nada tivesse mudado desde a
    # última vez. O arquivo existe; a interface é que o esquecia.
    flow["outputs"] = outputs
    flow["generatedAt"] = time.time()
    store.save(flow)

    return {
        "outputs": outputs,
        "stats": spec.stats(),
        "warnings": spec.warnings,
        "envKeys": spec.env_keys,
        "suggestions": spec.suggestions,
        "steps": flow["steps"],
    }


def _apply_edits(project: Any, edits: dict[str, str]) -> list[str]:
    """Substitui, no projeto montado, os arquivos que o usuário editou.

    Sem isto, editar o código seria decorativo: o projeto em disco continuaria
    saindo do gerador, e a suíte rodaria o texto que a pessoa acabou de
    reescrever — sem nenhum aviso de que a edição foi ignorada.

    O caminho do spec não é fixo: ele carrega o nome do fluxo. Procuramos o
    arquivo em `cypress/e2e/` em vez de recalculá-lo, para não depender de a
    regra de nomes ser a mesma nos dois lugares.
    """
    applied: list[str] = []
    for tab, code in (edits or {}).items():
        destino = EDITABLE_TABS.get(tab)
        if not destino or not code:
            continue
        if destino == "spec":
            destino = next((p for p in project.files if p.startswith("cypress/e2e/")), "")
            if not destino:
                continue
        project.files[destino] = code
        applied.append(destino)
    return applied


@app.post("/api/scaffold")
async def scaffold(body: GenerateBody) -> dict[str, Any]:
    """Monta o projeto Cypress completo e grava em disco.

    A diferença para `/api/generate` é o escopo: lá sai o spec, aqui sai algo
    que roda com `npm install && npm test`.
    """
    from .emit import scaffold as scaffolder

    flow = store.load(body.flowId) if body.flowId else None
    if not flow:
        raise HTTPException(404, "Fluxo não encontrado.")

    spec, steps = _rebuild(flow, body)
    project = scaffolder.build(spec, verbose=body.verbose,
                               use_fixtures=body.fixtures)
    edited = _apply_edits(project, flow.get("edits") or {})

    # Renomear o teste muda o nome da pasta e do arquivo. A pasta anterior é
    # movida para o novo nome, não abandonada com as dependências dentro.
    target = store.project_dir(spec.name, previous=flow.get("projectPath"))
    written = scaffolder.write_to_disk(project, target)

    flow["steps"] = [s.to_dict() for s in steps]
    flow["projectPath"] = str(target)
    store.save(flow)

    return {
        **project.to_dict(),
        "path": str(target),
        "written": written,
        "warnings": spec.warnings,
        # Regerar depois de trocar um seletor é o caminho normal, não a
        # exceção. Saber que as dependências continuam lá deixa a interface
        # prometer o certo: rodar de novo é imediato, não "alguns minutos".
        "installed": (target / "node_modules" / "cypress").exists(),
        # Quais arquivos saíram da edição manual em vez do gerador.
        "edited": edited,
    }


# ---------------------------------------------------------------------------
# Sequências
# ---------------------------------------------------------------------------

@app.get("/api/suites")
async def list_suites() -> dict[str, Any]:
    return {"suites": suites.list()}


@app.post("/api/suites")
async def create_suite(body: SuiteBody) -> dict[str, Any]:
    return suites.save({
        "name": body.name, "description": body.description,
        "baseUrl": body.baseUrl, "flowIds": body.flowIds,
        "isolate": body.isolate,
    })


@app.get("/api/suites/{suite_id}")
async def get_suite(suite_id: str) -> dict[str, Any]:
    suite = suites.load(suite_id)
    if not suite:
        raise HTTPException(404, "Sequência não encontrada.")

    # Os fluxos vão junto, resumidos: a tela precisa mostrar nome e tamanho de
    # cada teste sem fazer uma requisição por item da lista.
    resumo = []
    for flow_id in suite.get("flowIds") or []:
        flow = store.load(flow_id)
        if not flow:
            continue                       # fluxo excluído: some da sequência
        resumo.append({
            "id": flow_id,
            "name": flow.get("name", "Fluxo"),
            "description": flow.get("description", ""),
            "baseUrl": flow.get("baseUrl", ""),
            "stepCount": len(flow.get("steps") or []),
            "edited": sorted((flow.get("edits") or {}).keys()),
        })
    return {**suite, "flows": resumo}


@app.patch("/api/suites/{suite_id}")
async def update_suite(suite_id: str, body: SuiteBody) -> dict[str, Any]:
    suite = suites.load(suite_id)
    if not suite:
        raise HTTPException(404, "Sequência não encontrada.")
    suite.update({
        "name": body.name, "description": body.description,
        "baseUrl": body.baseUrl, "flowIds": body.flowIds,
        "isolate": body.isolate,
    })
    return suites.save(suite)


@app.delete("/api/suites/{suite_id}")
async def delete_suite(suite_id: str) -> dict[str, Any]:
    """Apaga a sequência. Os fluxos continuam existindo por conta própria."""
    if not suites.delete(suite_id):
        raise HTTPException(404, "Sequência não encontrada.")
    return {"ok": True}


def _qualify_env_keys(spec, prefixo: str) -> None:
    """Dá a cada credencial um nome próprio do fluxo, dentro da sequência.

    Dois fluxos que passam pela mesma tela de login produzem a mesma chave
    (`SENHA`), porque ela é derivada do campo. Isoladamente está certo; juntos
    numa sequência, vira um valor só para duas contas diferentes — e o segundo
    teste entra com a credencial do primeiro sem que nada acuse o problema.

    Aqui a chave passa a carregar o nome do fluxo: `ENTRA_NO_SISTEMA_SENHA`,
    `APROVA_PEDIDO_SENHA`. Cada `it()` recebe a sua.
    """
    if not spec.env_keys:
        return

    renomeadas = {k: f"{prefixo}_{k}" for k in spec.env_keys}
    spec.env_keys = [renomeadas[k] for k in spec.env_keys]

    for cmd in spec.commands:
        if isinstance(cmd.value, dict) and cmd.value.get("__env__") in renomeadas:
            cmd.value = {"__env__": renomeadas[cmd.value["__env__"]]}


def _env_prefix(name: str) -> str:
    """Nome do fluxo → prefixo de variável de ambiente."""
    base = "".join(c if c.isalnum() else "_"
                   for c in _slugify_ascii(name).upper()).strip("_")
    return re.sub(r"_+", "_", base)[:40] or "FLUXO"


def _slugify_ascii(text: str) -> str:
    import unicodedata
    return (unicodedata.normalize("NFKD", text or "")
            .encode("ascii", "ignore").decode("ascii"))


def _build_suite_ir(suite: dict[str, Any], *, verbose: bool):
    """Monta a `Suite` da IR a partir dos fluxos que ela referencia."""
    from .emit.ir import Suite as SuiteIR

    base_url = suite.get("baseUrl") or ""
    ir = SuiteIR(name=suite.get("name", "Sequência"),
                 description=suite.get("description", ""),
                 base_url=base_url,
                 isolate=bool(suite.get("isolate")))

    faltando: list[str] = []
    for flow_id in suite.get("flowIds") or []:
        flow = store.load(flow_id)
        if not flow:
            faltando.append(flow_id)
            continue
        spec, _ = _rebuild(flow, GenerateBody(
            name=flow.get("name", "Teste"),
            description=flow.get("description", ""),
            # A `baseUrl` da sequência manda: os fluxos podem ter sido gravados
            # em ambientes diferentes, e um `cy.visit` absoluto para outro
            # domínio no meio da sequência derruba a sessão compartilhada.
            baseUrl=base_url or flow.get("baseUrl", ""),
            flowId=flow_id,
            verbose=verbose,
        ))
        _qualify_env_keys(spec, _env_prefix(spec.name))
        ir.specs.append(spec)

    if not ir.base_url and ir.specs:
        ir.base_url = ir.specs[0].base_url
    return ir, faltando


@app.post("/api/suites/{suite_id}/generate")
async def generate_suite(suite_id: str, body: SuiteRunBody) -> dict[str, Any]:
    """Código da sequência: um arquivo, um `it()` por fluxo."""
    suite = suites.load(suite_id)
    if not suite:
        raise HTTPException(404, "Sequência não encontrada.")

    ir, faltando = _build_suite_ir(suite, verbose=body.verbose)
    if not ir.specs:
        raise HTTPException(400, "A sequência não tem nenhum fluxo utilizável.")

    # Preview e disco saem do mesmo lugar. A sequência distribui o código por
    # dois arquivos — o `.cy.js` com a ordem dos testes e o `commands.js` com
    # os fluxos —, e mostrar só um deles esconderia metade do que roda.
    from .emit import scaffold as scaffolder

    project = scaffolder.build_suite(ir, verbose=body.verbose,
                                     use_fixtures=body.fixtures)
    spec_path = next(p for p in project.files if p.startswith("cypress/e2e/"))

    outputs = {
        "cypress": {
            "filename": spec_path.split("/")[-1],
            "code": project.files[spec_path],
        },
        "commands": {
            "filename": "commands.js",
            "code": project.files["cypress/support/commands.js"],
        },
    }
    if "cypress/fixtures/elementos.json" in project.files:
        outputs["elementos"] = {
            "filename": "elementos.json",
            "code": project.files["cypress/fixtures/elementos.json"],
        }

    suite["outputs"] = outputs
    suite["generatedAt"] = time.time()
    suites.save(suite)

    return {
        "outputs": outputs,
        "stats": ir.stats(),
        "warnings": ir.warnings,
        "envKeys": ir.env_keys,
        "missingFlows": faltando,
    }


@app.post("/api/suites/{suite_id}/scaffold")
async def scaffold_suite(suite_id: str, body: SuiteRunBody) -> dict[str, Any]:
    """Projeto Cypress completo da sequência."""
    from .emit import scaffold as scaffolder

    suite = suites.load(suite_id)
    if not suite:
        raise HTTPException(404, "Sequência não encontrada.")

    ir, faltando = _build_suite_ir(suite, verbose=body.verbose)
    if not ir.specs:
        raise HTTPException(400, "A sequência não tem nenhum fluxo utilizável.")

    project = scaffolder.build_suite(ir, verbose=body.verbose,
                                     use_fixtures=body.fixtures)

    # Edição manual do spec de um fluxo não vale aqui: o arquivo da sequência
    # tem outra forma — um `describe` com vários `it()`. Aplicar o texto de um
    # fluxo sozinho apagaria os outros testes.
    target = store.project_dir(f"seq-{ir.name}", previous=suite.get("projectPath"))
    written = scaffolder.write_to_disk(project, target)

    suite["projectPath"] = str(target)
    suites.save(suite)

    return {
        **project.to_dict(),
        "path": str(target),
        "written": written,
        "warnings": ir.warnings,
        "installed": (target / "node_modules" / "cypress").exists(),
        "missingFlows": faltando,
    }


class ProjectBody(BaseModel):
    path: str
    env: dict[str, str] = {}
    browser: str = "electron"


def _project_path(raw: str) -> Path:
    """Valida que o caminho pertence à área de projetos do Cygen.

    O endpoint recebe um caminho do cliente e vai executar comandos nele. Sem
    essa checagem, um caminho arbitrário viraria execução arbitrária — o
    servidor escuta só em localhost, mas qualquer página aberta no navegador
    poderia chamá-lo.
    """
    from .store import projects_dir

    target = Path(raw).resolve()
    root = projects_dir().resolve()
    if not target.is_relative_to(root):
        raise HTTPException(400, "Caminho fora da pasta de projetos do Cygen.")
    if not target.exists():
        raise HTTPException(404, "Projeto não encontrado. Gere-o novamente.")
    return target


async def _progress(stage: str, line: str) -> None:
    await broadcast("project", {"stage": stage, "line": line})


@app.get("/api/project/status")
async def project_status(path: str) -> dict[str, Any]:
    """Tudo que a tela precisa para mostrar um projeto que já existe.

    Antes devolvia só se as dependências estavam instaladas, e a interface não
    tinha como redesenhar o painel de um projeto gerado numa sessão anterior —
    ela mostrava "nenhum projeto gerado ainda" e pedia para gerar de novo, com
    o projeto ali no disco. Agora responde o suficiente para o painel voltar
    inteiro: arquivos, credenciais que o teste pede e quais já estão salvas.
    """
    from .verify import runner

    target = _project_path(path)
    arquivos = sorted(
        f.relative_to(target).as_posix()
        for f in target.rglob("*")
        if f.is_file() and "node_modules" not in f.parts
    )

    return {
        "ok": True,
        "node": runner.node_available(),
        "installed": (target / "node_modules" / "cypress").exists(),
        "path": str(target),
        "fileList": arquivos,
        "envKeys": _project_env_keys(target),
        "savedKeys": sorted(_saved_env(target)),
    }


def _project_env_keys(target: Path) -> list[str]:
    """Credenciais que este projeto pede, lidas do exemplo que ele mesmo traz.

    A alternativa seria recalcular a partir do fluxo, o que só funciona
    enquanto fluxo e projeto estiverem em sincronia. O `cypress.env.example.json`
    faz parte do projeto gerado e descreve exatamente o que aquele código lê.
    """
    exemplo = target / "cypress.env.example.json"
    if not exemplo.exists():
        return []
    try:
        # O arquivo começa com comentários `#`, que JSON não aceita.
        corpo = "\n".join(l for l in exemplo.read_text(encoding="utf-8").splitlines()
                          if not l.strip().startswith("#"))
        dados = json.loads(corpo or "{}")
    except Exception:
        return []
    return [k for k in dados if k != "BASE_URL"]


def _saved_env(target: Path) -> set[str]:
    """Quais credenciais já estão gravadas no `cypress.env.json`."""
    arquivo = target / "cypress.env.json"
    if not arquivo.exists():
        return set()
    try:
        dados = json.loads(arquivo.read_text(encoding="utf-8"))
    except Exception:
        return set()
    return {k for k, v in dados.items() if str(v).strip()}


@app.post("/api/project/env")
async def project_env(body: ProjectBody) -> dict[str, Any]:
    """Grava as credenciais no projeto, de uma vez por todas.

    Elas iam para o `cypress.env.json` só na hora de rodar, e o campo voltava
    vazio na visita seguinte — dando a impressão de que o Cygen perguntava a
    mesma coisa sempre. Salvas aqui, valem para toda execução: pelo botão, pelo
    Cypress aberto à mão ou por `npm test` no terminal.

    O arquivo está no `.gitignore` do projeto gerado desde o começo, que é o
    que torna seguro guardá-las em disco: elas ficam na máquina de quem rodou,
    fora do controle de versão.
    """
    from .verify import runner

    target = _project_path(body.path)
    gravado = runner.write_env_file(target, body.env)
    return {
        "ok": True,
        "file": str(gravado) if gravado else "",
        "savedKeys": sorted(_saved_env(target)),
    }


@app.post("/api/project/open")
async def project_open(body: ProjectBody) -> dict[str, Any]:
    """Instala o que faltar e abre a interface do Cypress."""
    from .verify import runner

    target = _project_path(body.path)

    installed = await runner.install(target, on_progress=_progress)
    if not installed.get("ok"):
        return installed

    await broadcast("project", {"stage": "open", "line": "Abrindo o Cypress..."})
    return await runner.open_studio(target, body.env)


@app.post("/api/project/run")
async def project_run(body: ProjectBody) -> dict[str, Any]:
    """Instala o que faltar e roda a suite sem interface."""
    from .verify import runner

    target = _project_path(body.path)

    installed = await runner.install(target, on_progress=_progress)
    if not installed.get("ok"):
        return installed

    result = await runner.run(target, env_values=body.env,
                              browser=body.browser, on_progress=_progress)
    await broadcast("project", {"stage": "done", "line": ""})
    return result


@app.post("/api/project/reveal")
async def project_reveal(body: ProjectBody) -> dict[str, Any]:
    """Abre a pasta do projeto no explorador de arquivos."""
    from .verify import runner

    return runner.reveal(_project_path(body.path))


@app.post("/api/export")
async def export(payload: dict[str, Any]) -> dict[str, Any]:
    name = payload.get("name") or "teste"
    code = payload.get("code") or ""
    extension = payload.get("extension") or ".cy.js"
    if not code.strip():
        raise HTTPException(400, "Não há código para exportar.")
    path = store.export(name, code, extension)
    return {"ok": True, "path": str(path)}


# ---------------------------------------------------------------------------
# Verificação
# ---------------------------------------------------------------------------

@app.post("/api/verify")
async def verify(body: VerifyBody) -> dict[str, Any]:
    flow = store.load(body.flowId)
    if not flow:
        raise HTTPException(404, "Fluxo não encontrado.")

    spec_data = flow.get("spec")
    if not spec_data:
        raise HTTPException(400, "Gere o código antes de verificar.")

    spec, _ = _rebuild(flow, GenerateBody(
        name=flow.get("name", "Fluxo"),
        description=flow.get("description", ""),
        baseUrl=body.baseUrl or flow.get("baseUrl", ""),
        flowId=body.flowId,
    ))

    await broadcast("verify", {"status": "running"})
    healer = Healer(headless=True)
    report, healed = await healer.verify(spec, base_url=body.baseUrl or flow.get("baseUrl", ""))

    flow["verification"] = report.to_dict()
    flow["spec"] = healed.to_dict()
    store.save(flow)

    # Reemite com os seletores curados: o usuário recebe o código que passou.
    code = emit_cypress.emit(healed, verbose=True)
    await broadcast("verify", {"status": "done", "ok": report.ok})

    return {"report": report.to_dict(), "code": code}


# ---------------------------------------------------------------------------
# IA
# ---------------------------------------------------------------------------

@app.get("/api/ai/providers")
async def ai_providers() -> dict[str, Any]:
    return {"providers": registry.catalog(), "stats": registry.stats()}


class AIKeyBody(BaseModel):
    provider: str
    key: str = ""


@app.post("/api/ai/key")
async def ai_key(body: AIKeyBody) -> dict[str, Any]:
    """Define a chave de um provedor para esta sessão.

    Nada vai para o disco: a chave vive na memória do processo e morre quando
    o Cygen fecha. É o que permite experimentar um provedor gratuito sem
    aprender a mexer em variável de ambiente — e sem que o app passe a guardar
    credencial, que era justamente o que a v2 fazia de errado.
    """
    if not registry.set_key(body.provider, body.key):
        raise HTTPException(400, "Provedor desconhecido ou sem chave a definir.")

    provider = registry.get(body.provider)
    return {
        "ok": True,
        "provider": body.provider,
        "configured": bool(provider and provider.configured()),
        "envKey": provider.env_keys[0] if provider and provider.env_keys else "",
    }


@app.post("/api/ai/chat")
async def ai_chat(body: ChatBody) -> dict[str, Any]:
    client = AIClient(
        provider_id=body.provider or settings.get("provider", "native"),
        model_id=body.model or settings.get("model"),
    )
    system = SYSTEM_RULES if body.mode == "rules" else SYSTEM_REVIEW
    content = body.message
    if body.code:
        content = f"{body.message}\n\nCódigo atual:\n```javascript\n{body.code}\n```"

    result = await client.complete(
        [{"role": "user", "content": content}],
        system=system,
        code=body.code,          # o Oracle analisa localmente; os demais leem da mensagem
    )
    return result.to_dict()


@app.post("/api/review")
async def review_code(payload: dict[str, Any]) -> dict[str, Any]:
    """Revisão estática de um teste, estruturada.

    Mesmo motor do modo nativo do chat, mas devolvendo os achados como dados
    em vez de texto — é o que permite à interface destacar linha por linha.
    """
    from .intel import review as reviewer

    code = payload.get("code") or ""
    if not code.strip():
        raise HTTPException(400, "Nenhum código enviado para revisão.")
    return reviewer.analyze(code).to_dict()


@app.post("/api/ai/estimate")
async def ai_estimate(payload: dict[str, Any]) -> dict[str, Any]:
    client = AIClient(
        provider_id=payload.get("provider") or settings.get("provider", "native"),
        model_id=payload.get("model") or settings.get("model"),
    )
    return client.estimate(payload.get("text", ""))


# ---------------------------------------------------------------------------
# Auto-teste
# ---------------------------------------------------------------------------

# Uma execução por vez. Dois agentes clicando no mesmo sistema ao mesmo tempo
# produzem fluxos que se atrapalham — um cria o registro que o outro apaga.
autoteste: dict[str, Any] = {"rodando": False, "passos": [], "resultado": None}


def _briefing(body: AutoTestBody) -> str:
    """O texto que o agente recebe, montado a partir do formulário."""
    escopos = {
        "objetivo": "Cumpra o objetivo descrito e pare quando ele estiver feito.",
        "modulo": "Explore a fundo o módulo indicado no objetivo, cobrindo suas "
                  "telas e ações principais. Ignore o resto do sistema.",
        "rotas": "Percorra as rotas alcançáveis pelo menu, entrando em cada uma "
                 "e conferindo que ela carrega. Não preencha formulários longos.",
        "completo": "Cubra o máximo do sistema: menus, listagens e cadastros. "
                    "Declare um marco a cada jornada concluída.",
    }

    partes = [f"Sistema: {body.baseUrl}", "",
              f"Tipo de teste: {escopos.get(body.escopo, escopos['objetivo'])}"]
    if body.objetivo.strip():
        partes += ["", f"O que testar:\n{body.objetivo.strip()}"]
    if body.regras.strip():
        partes += ["", f"Regras de negócio e restrições:\n{body.regras.strip()}"]

    login = body.login or {}
    if login.get("usuario"):
        # A senha não entra no texto: ela é digitada pelo agente na hora, e um
        # briefing vira log, vira histórico de conversa, vira arquivo.
        entrada = login.get("instrucoes") or "faça login na tela inicial"
        partes += ["", "Acesso ao sistema:",
                   f"  usuário: {login['usuario']}",
                   "  senha: já fornecida — preencha o campo de senha com ela",
                   f"  como entrar: {entrada}"]
    if body.valores:
        partes += ["", "Valores obrigatórios em campos específicos:"]
        partes += [f"  {k}: {v}" for k, v in body.valores.items()]

    partes += ["", "Ao terminar cada jornada com sentido próprio, emita um "
                   "marco com um nome curto e descritivo — ele vira o nome do teste."]
    return "\n".join(partes)


@app.get("/api/autotest/status")
async def autotest_status() -> dict[str, Any]:
    return {
        "rodando": autoteste["rodando"],
        "passos": autoteste["passos"][-60:],
        "resultado": autoteste["resultado"],
    }


@app.post("/api/autotest/stop")
async def autotest_stop() -> dict[str, Any]:
    agente = autoteste.get("agente")
    if agente:
        agente.parar = True
    return {"ok": True}


@app.post("/api/autotest/start")
async def autotest_start(body: AutoTestBody) -> dict[str, Any]:
    """Roda o auto-teste e salva os fluxos que ele produzir.

    Exige um provedor de IA configurado. Não é uma limitação artificial: o
    agente decide cada passo consultando o modelo, e sem chave não há decisão
    — o Oracle nativo deduz assertions do que aconteceu, mas não escolhe o que
    fazer em seguida.
    """
    from .explorer import safety
    from .explorer.agent import AutoTest

    if autoteste["rodando"]:
        raise HTTPException(409, "Já existe um auto-teste em andamento.")
    if not body.baseUrl.strip():
        raise HTTPException(400, "Informe o endereço do sistema.")

    provider_id = body.provider or settings.get("provider", "")
    provider = registry.get(provider_id) if provider_id else None
    if not provider or provider.dialect == registry.DIALECT_NATIVE:
        raise HTTPException(
            400,
            "O auto-teste precisa de um provedor de IA. O Oracle nativo deduz "
            "as verificações, mas não decide o que clicar. Escolha um provedor "
            "em Configurações — vários têm camada gratuita.",
        )
    if not provider.configured():
        raise HTTPException(
            400,
            f"{provider.label} está sem chave. Informe a chave em Configurações; "
            f"ela fica guardada nesta máquina e não é pedida de novo.",
        )

    aviso = safety.check_target(body.baseUrl, confirmado=body.confirmoAmbiente)
    if aviso:
        raise HTTPException(400, aviso)

    autoteste.update({"rodando": True, "passos": [], "resultado": None})

    async def progresso(evento: dict[str, Any]) -> None:
        autoteste["passos"].append(evento)
        await broadcast("autotest", evento)

    agente = AutoTest(
        briefing=_briefing(body),
        base_url=body.baseUrl.strip(),
        provider=provider_id,
        model=body.model,
        max_passos=max(5, min(body.maxPassos, 200)),
        headless=body.headless,
        permitir_destrutivo=body.permitirDestrutivo,
        valores={**body.valores,
                 **({"senha": body.login["senha"]} if body.login.get("senha") else {})},
        on_progress=progresso,
    )
    autoteste["agente"] = agente

    try:
        resultado = await agente.run()
    finally:
        autoteste["rodando"] = False
        autoteste["agente"] = None

    # Cada jornada vira um fluxo salvo, pronto para abrir, revisar e gerar.
    salvos = []
    for fluxo in resultado.get("fluxos", []):
        gravado = store.save(fluxo)
        salvos.append({"id": gravado["id"], "name": gravado["name"],
                       "stepCount": len(gravado.get("steps") or [])})

    resultado["salvos"] = salvos
    autoteste["resultado"] = resultado
    await broadcast("autotest", {"tipo": "fim", "salvos": salvos})
    return resultado


# ---------------------------------------------------------------------------
# Metadados
# ---------------------------------------------------------------------------

@app.get("/api/meta")
async def meta() -> dict[str, Any]:
    from .store import data_dir, exports_dir, projects_dir, suites_dir

    return {
        "version": app.version,
        "oracle": {"rules": Oracle.rules(), "count": Oracle.rule_count()},
        "assertions": {"total": catalog.total(), "categories": catalog.categories()},
        "providers": registry.stats(),
        "settings": settings.values,
        # Onde cada coisa mora. A interface precisa disso para responder
        # "onde ficam meus testes?" sem que ninguém tenha de adivinhar — e
        # para mostrar o caminho de um projeto antes mesmo de ele existir.
        "paths": {
            "data": str(data_dir()),
            "suites": str(suites_dir()),
            "projects": str(projects_dir()),
            "exports": str(exports_dir()),
        },
    }


class RevealBody(BaseModel):
    """Qual pasta conhecida abrir. Nada de caminho livre vindo do cliente."""

    what: str


@app.post("/api/reveal")
async def reveal_dir(body: RevealBody) -> dict[str, Any]:
    """Abre uma das pastas do Cygen no explorador de arquivos.

    Recebe um nome, não um caminho: o endpoint executa uma ação do sistema
    operacional, e aceitar caminho livre transformaria isso num abre-qualquer
    coisa para qualquer página aberta no navegador.
    """
    from .store import data_dir, exports_dir, projects_dir, suites_dir
    from .verify import runner

    conhecidas = {
        "data": data_dir,
        "suites": suites_dir,
        "projects": projects_dir,
        "exports": exports_dir,
    }
    alvo = conhecidas.get(body.what)
    if not alvo:
        raise HTTPException(400, f"Pasta desconhecida: {body.what}")
    return runner.reveal(alvo())


@app.get("/api/assertions")
async def assertions(q: str = "") -> dict[str, Any]:
    if q:
        return {"results": catalog.search(q)}
    return {"catalog": {k: v for k, v in catalog.CATALOG.items()}}


@app.get("/api/settings")
async def get_settings() -> dict[str, Any]:
    return settings.load()


@app.post("/api/settings")
async def set_settings(body: SettingsBody) -> dict[str, Any]:
    return settings.save(body.values)


@app.get("/api/health")
async def health() -> dict[str, Any]:
    browser = await ensure_browser(settings.get("browser", "chromium"))
    return {"ok": True, "browser": browser, "providers": registry.stats()}


# ---------------------------------------------------------------------------
# UI estática
# ---------------------------------------------------------------------------

def _asset_token() -> str:
    """Identificador que muda sempre que o CSS ou o JS mudam.

    Sem isto, o navegador reaproveita a folha de estilo antiga e a interface
    aparece meio quebrada — regras novas não aplicadas, elementos com tamanho
    natural. Em Electron o efeito é pior, porque a janela não tem como o
    usuário forçar uma recarga sem cache.

    O token entra como query string nos links: o arquivo continua cacheável,
    mas uma versão nova tem URL nova.
    """
    marks: list[str] = []
    for relative in ("css/app.css", "js/app.js"):
        path = UI_DIR / relative
        try:
            marks.append(str(int(path.stat().st_mtime)))
        except OSError:
            marks.append("0")
    return "-".join(marks)


if UI_DIR.exists():
    app.mount("/assets", StaticFiles(directory=str(UI_DIR)), name="assets")

    @app.get("/")
    async def index() -> Response:
        html = (UI_DIR / "index.html").read_text(encoding="utf-8")
        token = _asset_token()
        html = (html
                .replace("/assets/css/app.css", f"/assets/css/app.css?v={token}")
                .replace("/assets/js/app.js", f"/assets/js/app.js?v={token}"))
        # O próprio index nunca é cacheado: é ele que carrega o token novo.
        return Response(
            content=html, media_type="text/html; charset=utf-8",
            headers={"Cache-Control": "no-store"},
        )


@app.exception_handler(Exception)
async def unhandled(request: Any, exc: Exception) -> JSONResponse:
    """Nenhum erro de backend deve derrubar a janela do app."""
    return JSONResponse(
        status_code=500,
        content={"error": f"{type(exc).__name__}: {exc}"},
    )
