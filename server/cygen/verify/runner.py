"""
Execução do projeto Cypress gerado.

Mostrar ao usuário um bloco de comandos para copiar é devolver a ele o
trabalho que a ferramenta deveria fazer. Este módulo executa: instala as
dependências se faltarem, grava as credenciais onde o Cypress as procura, e
abre ou roda a suite.

Três detalhes do Windows que só aparecem na prática:

  npm e npx sao `.cmd`, nao executaveis. Chamar `npm` direto de um subprocesso
  falha com FileNotFoundError; e preciso resolver o `.cmd` no PATH.

  ELECTRON_RUN_AS_NODE derruba o Cypress com `bad option: --smoke-test`, pelo
  mesmo motivo que derruba qualquer app Electron. Limpamos no ambiente do
  filho.

  `cypress open` abre uma janela e nao termina. Precisa ser lancado desanexado,
  senao o backend fica preso esperando o usuario fechar.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import sys
from pathlib import Path
from typing import Any, Awaitable, Callable

IS_WINDOWS = os.name == "nt"

# Callback opcional para reportar progresso enquanto um comando roda.
Progress = Callable[[str, str], Awaitable[None]]


def _which(name: str) -> str | None:
    """Localiza um executável, cobrindo os wrappers `.cmd` do Windows.

    `shutil.which` já consulta PATHEXT no Windows, mas ser explícito aqui
    evita a armadilha de `npm` resolver para `npm.ps1` — que o PowerShell
    bloqueia por política de execução e um subprocesso não consegue rodar.
    """
    if IS_WINDOWS:
        for candidate in (f"{name}.cmd", f"{name}.exe", name):
            found = shutil.which(candidate)
            if found:
                return found
        return None
    return shutil.which(name)


def child_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    """Ambiente para o processo filho, saneado."""
    env = dict(os.environ)
    # Sem isto o Cypress nao inicia: ele e um app Electron, e a variavel o faz
    # rodar como Node puro, sem entender os proprios argumentos.
    env.pop("ELECTRON_RUN_AS_NODE", None)
    env.setdefault("CI", "1")          # desliga a telemetria interativa
    if extra:
        env.update({k: str(v) for k, v in extra.items()})
    return env


async def path_visible_to_children(path: Path) -> bool:
    """A pasta existe do ponto de vista de um processo externo?

    Não é a mesma pergunta que `path.exists()`. O Python da Microsoft Store
    roda em contêiner e virtualiza `AppData\\Local`: o interpretador enxerga um
    caminho que mais ninguém enxerga. Perguntamos ao `cmd.exe`, que é quem vai
    de fato rodar o npm.
    """
    if not IS_WINDOWS:
        return path.exists()
    try:
        # O teste precisa usar o caminho ABSOLUTO e rodar de fora da pasta.
        # Lançar o `cmd` com `cwd` apontando para ela não serve: o Windows
        # entrega o diretório por handle, e o `cmd` reporta o caminho sem
        # reclamar mesmo quando ele é virtual — foi assim que a primeira versão
        # desta checagem passou num caso que o npm depois rejeitou.
        process = await asyncio.create_subprocess_exec(
            "cmd.exe", "/c", "dir", "/b", str(path),
            env=child_env(),
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
        )
        await process.wait()
        return process.returncode == 0
    except Exception:
        return False


def node_available() -> dict[str, Any]:
    """Node e npm estão instalados?"""
    node = _which("node")
    npm = _which("npm")
    if not node or not npm:
        return {
            "ok": False,
            "error": "Node.js não encontrado. Instale em https://nodejs.org "
                     "para rodar o Cypress — o restante do Cygen funciona sem ele.",
        }
    return {"ok": True, "node": node, "npm": npm}


def write_env_file(project: Path, values: dict[str, str]) -> Path | None:
    """Grava as credenciais em `cypress.env.json`.

    É onde o Cypress procura por conta própria, então o usuário não precisa
    exportar variável nenhuma antes de rodar. O arquivo já está no
    `.gitignore` do projeto gerado.

    Valores vazios são descartados: gravar `""` faria o teste tentar logar com
    senha em branco e falhar de um jeito que parece bug da aplicação.
    """
    clean = {k: v for k, v in (values or {}).items() if str(v).strip()}
    if not clean:
        return None

    target = project / "cypress.env.json"
    existing: dict[str, Any] = {}
    if target.exists():
        try:
            existing = json.loads(target.read_text(encoding="utf-8"))
        except Exception:
            existing = {}

    existing.update(clean)
    target.write_text(json.dumps(existing, indent=2, ensure_ascii=False) + "\n",
                      encoding="utf-8")
    return target


def _spawn_args(cmd: list[str]) -> list[str]:
    """Ajusta a linha de comando para o que o sistema sabe executar.

    `npm` e `npx` no Windows são arquivos de lote, não executáveis. Passá-los
    direto ao `create_subprocess_exec` produz um erro que não menciona nada
    disso — "A pasta atual não é válida" —, e leva horas para associar à
    causa. Roteando por `cmd.exe /c` o lote executa normalmente.

    Usamos o nome curto e não o caminho completo justamente por causa do
    `cmd.exe`: ele reparte a linha nos espaços, e `C:\\Program Files\\nodejs\\
    npm.cmd` viraria dois argumentos.
    """
    if not IS_WINDOWS:
        return cmd

    head, *rest = cmd
    name = Path(head).name
    if name.lower().endswith((".cmd", ".bat")):
        return ["cmd.exe", "/c", Path(name).stem, *rest]
    return cmd


async def _stream(cmd: list[str], cwd: Path, env: dict[str, str],
                  on_progress: Progress | None, tag: str) -> tuple[int, str]:
    """Roda um comando reportando a saída linha a linha."""
    process = await asyncio.create_subprocess_exec(
        *_spawn_args(cmd), cwd=str(cwd), env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )

    captured: list[str] = []
    assert process.stdout is not None
    async for raw in process.stdout:
        line = raw.decode("utf-8", "replace").rstrip()
        if not line:
            continue
        captured.append(line)
        if on_progress:
            try:
                await on_progress(tag, line)
            except Exception:
                pass

    await process.wait()
    return process.returncode or 0, "\n".join(captured[-160:])


async def install(project: Path, *, on_progress: Progress | None = None,
                  force: bool = False) -> dict[str, Any]:
    """Instala as dependências, se ainda não estiverem lá."""
    check = node_available()
    if not check["ok"]:
        return check

    if not await path_visible_to_children(project):
        return {
            "ok": False,
            "error": (
                "A pasta do projeto não é visível para o npm. Isso acontece "
                "quando ela fica em AppData e o Python veio da Microsoft "
                "Store, que virtualiza esse diretório. Gere o projeto de novo "
                "— o Cygen agora grava em Documentos\\Cygen, que todo processo "
                "enxerga."
            ),
        }

    if not force and (project / "node_modules" / "cypress").exists():
        return {"ok": True, "skipped": True,
                "message": "Dependências já instaladas."}

    if on_progress:
        await on_progress("install", "Instalando o Cypress. Na primeira vez "
                                     "leva alguns minutos.")

    code, output = await _stream(
        [check["npm"], "install", "--no-audit", "--no-fund"],
        project, child_env(), on_progress, "install",
    )
    if code != 0:
        return {"ok": False, "error": "Falha no `npm install`.", "output": output}
    return {"ok": True, "message": "Dependências instaladas.", "output": output}


async def open_studio(project: Path, env_values: dict[str, str] | None = None
                      ) -> dict[str, Any]:
    """Abre a interface do Cypress na pasta do projeto.

    Lançado desanexado: `cypress open` só termina quando o usuário fecha a
    janela, e o backend não pode ficar bloqueado esperando isso.
    """
    check = node_available()
    if not check["ok"]:
        return check

    write_env_file(project, env_values or {})

    npx = _which("npx")
    if not npx:
        return {"ok": False, "error": "`npx` não encontrado junto ao Node."}

    kwargs: dict[str, Any] = {
        "cwd": str(project),
        "env": child_env(),
        "stdout": asyncio.subprocess.DEVNULL,
        "stderr": asyncio.subprocess.DEVNULL,
    }
    if IS_WINDOWS:
        # Console proprio: a janela do Cypress sobrevive ao backend.
        kwargs["creationflags"] = 0x00000010          # CREATE_NEW_CONSOLE
    else:
        kwargs["start_new_session"] = True

    try:
        await asyncio.create_subprocess_exec(
            *_spawn_args([npx, "cypress", "open"]), **kwargs
        )
    except Exception as exc:
        return {"ok": False, "error": f"Não consegui abrir o Cypress: {exc}"}

    return {
        "ok": True,
        "message": "Cypress abrindo. A janela pode levar alguns segundos para "
                   "aparecer na primeira vez.",
    }


async def run(project: Path, *, env_values: dict[str, str] | None = None,
              browser: str = "electron",
              on_progress: Progress | None = None) -> dict[str, Any]:
    """Roda a suite sem interface e devolve o resultado estruturado."""
    check = node_available()
    if not check["ok"]:
        return check

    write_env_file(project, env_values or {})

    npx = _which("npx")
    if not npx:
        return {"ok": False, "error": "`npx` não encontrado junto ao Node."}

    if on_progress:
        await on_progress("run", "Executando a suite...")

    code, output = await _stream(
        [npx, "cypress", "run", "--browser", browser],
        project, child_env(), on_progress, "run",
    )

    summary = _parse_output(output)
    summary.update({
        "ok": code == 0,
        "exitCode": code,
        "output": _strip_ansi(output)[-4000:],
        "browser": browser,
    })
    if code != 0 and not summary.get("tests"):
        # O Cypress nao chegou a rodar teste nenhum: o erro esta na saida.
        summary["error"] = _first_error(_strip_ansi(output))
    return summary


# O Cypress colore a saida mesmo sem terminal interativo.
_ANSI = __import__("re").compile(r"\x1b\[[0-9;]*[A-Za-z]")


def _strip_ansi(text: str) -> str:
    return _ANSI.sub("", text or "")


def _parse_output(raw: str) -> dict[str, Any]:
    """Extrai o resultado da saída do Cypress.

    Lemos o resumo que o Cypress sempre imprime, em vez de pedir o reporter
    `json`: o `--reporter-options output=` não produziu arquivo nenhum nas
    versões testadas, e uma dependência extra (mochawesome) só para contar
    testes seria peso desnecessário no projeto gerado.
    """
    text = _strip_ansi(raw)

    def count(label: str) -> int:
        match = re.search(rf"{label}:\s+(\d+)", text)
        return int(match.group(1)) if match else 0

    duration_ms = 0
    duration = re.search(r"Duration:\s+(?:(\d+)\s*minutes?,?\s*)?(\d+)\s*seconds?", text)
    if duration:
        minutes = int(duration.group(1) or 0)
        duration_ms = (minutes * 60 + int(duration.group(2))) * 1000

    # Os testes que falharam aparecem numerados, seguidos da mensagem.
    failures: list[dict[str, str]] = []
    for block in re.finditer(r"^\s+\d+\)\s+(.+?)\n(.*?)(?=\n\s*\d+\)|\n\s*\(|\Z)",
                             text, re.S | re.M):
        title = " ".join(block.group(1).split())
        message = " ".join(block.group(2).split())[:500]
        if title:
            failures.append({"title": title, "message": message})
        if len(failures) >= 8:
            break

    # Reservas que entraram em ação durante a execução. Um teste que passou
    # usando reserva passou hoje e é um alerta para amanhã: o seletor primário
    # já não encontra o elemento, e a reserva é a última linha de defesa.
    reservas: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for match in re.finditer(r"CYGEN_RESERVA (.+?) >> (.+)", text):
        pair = (match.group(1).strip(), match.group(2).strip())
        if pair in seen:
            continue
        seen.add(pair)
        reservas.append({"from": pair[0], "to": pair[1]})

    # As mensagens de encerramento que cada teste imprimiu. Voltam para a
    # interface porque são a leitura mais direta do que aconteceu: "Teste de
    # Login para o user ana concluído" diz mais que "1 passing".
    notas: list[str] = []
    for match in re.finditer(r"✓ (Teste de .+?concluído)", text):
        nota = match.group(1).strip()
        if nota not in notas:
            notas.append(nota)

    return {
        "notas": notas[:20],
        "tests": count("Tests"),
        "passing": count("Passing"),
        "failing": count("Failing"),
        "durationMs": duration_ms,
        "failures": failures,
        "reservas": reservas[:12],
    }


def _first_error(output: str) -> str:
    """Extrai da saída bruta a linha que explica a falha."""
    markers = ("Error:", "error:", "Cypress could not", "Cypress failed",
               "Cannot find module", "bad option")
    for line in output.splitlines():
        if any(marker in line for marker in markers):
            return line.strip()[:400]
    return output.splitlines()[-1][:400] if output.splitlines() else "Falha desconhecida."


def reveal(path: Path) -> dict[str, Any]:
    """Abre a pasta do projeto no explorador de arquivos do sistema."""
    try:
        if IS_WINDOWS:
            os.startfile(str(path))                        # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            os.system(f'open "{path}"')
        else:
            os.system(f'xdg-open "{path}"')
        return {"ok": True}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
