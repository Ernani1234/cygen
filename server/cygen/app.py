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
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .ai import registry
from .ai.client import SYSTEM_REVIEW, SYSTEM_RULES, AIClient
from .emit import cypress as emit_cypress
from .emit import playwright_ts as emit_playwright
from .emit.build import build_spec
from .intel import catalog
from .intel.intent import Step, compile_steps
from .intel.oracle import Oracle
from .intel.selectors import SelectorEngine
from .recorder.engine import RecordingSession, ensure_browser
from .store import FlowStore, Settings
from .verify.healer import Healer

UI_DIR = Path(__file__).resolve().parent.parent.parent / "ui"

app = FastAPI(title="Cygen", version="3.0.0")
store = FlowStore()
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
    if not store.delete(flow_id):
        raise HTTPException(404, "Fluxo não encontrado.")
    return {"ok": True}


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

    outputs: dict[str, Any] = {
        "cypress": {
            "filename": emit_cypress.spec_filename(spec.name),
            "code": emit_cypress.emit(spec, verbose=body.verbose,
                                      split_groups=body.splitGroups),
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
    store.save(flow)

    return {
        "outputs": outputs,
        "stats": spec.stats(),
        "warnings": spec.warnings,
        "envKeys": spec.env_keys,
        "suggestions": spec.suggestions,
        "steps": flow["steps"],
    }


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
    project = scaffolder.build(spec, verbose=body.verbose)

    target = store.project_dir(spec.name)
    written = scaffolder.write_to_disk(project, target)

    flow["steps"] = [s.to_dict() for s in steps]
    flow["projectPath"] = str(target)
    store.save(flow)

    return {
        **project.to_dict(),
        "path": str(target),
        "written": written,
        "warnings": spec.warnings,
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
    """O projeto já tem dependências instaladas? O Node existe?"""
    from .verify import runner

    target = _project_path(path)
    node = runner.node_available()
    return {
        "node": node,
        "installed": (target / "node_modules" / "cypress").exists(),
        "path": str(target),
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
# Metadados
# ---------------------------------------------------------------------------

@app.get("/api/meta")
async def meta() -> dict[str, Any]:
    return {
        "version": app.version,
        "oracle": {"rules": Oracle.rules(), "count": Oracle.rule_count()},
        "assertions": {"total": catalog.total(), "categories": catalog.categories()},
        "providers": registry.stats(),
        "settings": settings.values,
    }


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
