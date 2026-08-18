"""
Persistência de fluxos.

A v2 espalhava estado por `logs/`, `data/usage_stats.json`, `conversations/` e
um `config.json` que guardava a chave da API em texto puro no repositório. Aqui
tudo vive num diretório de dados do usuário, e segredo nenhum é gravado: chaves
de API só existem como variável de ambiente.
"""

from __future__ import annotations

import json
import os
import re
import time
import uuid
from pathlib import Path
from typing import Any


def data_dir() -> Path:
    """Diretório de dados do usuário, por plataforma."""
    override = os.environ.get("CYGEN_DATA_DIR")
    if override:
        path = Path(override)
    elif os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        path = Path(base) / "Cygen"
    elif os.uname().sysname == "Darwin":                       # type: ignore[attr-defined]
        path = Path.home() / "Library" / "Application Support" / "Cygen"
    else:
        base = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
        path = Path(base) / "cygen"
    path.mkdir(parents=True, exist_ok=True)
    return path


def flows_dir() -> Path:
    path = data_dir() / "flows"
    path.mkdir(parents=True, exist_ok=True)
    return path


def exports_dir() -> Path:
    path = data_dir() / "exports"
    path.mkdir(parents=True, exist_ok=True)
    return path


def documents_dir() -> Path:
    """Pasta de documentos do usuário, cobrindo redirecionamento do OneDrive."""
    home = Path.home()
    for candidate in ("Documents", "Documentos",
                      "OneDrive/Documents", "OneDrive/Documentos"):
        path = home / candidate
        if path.is_dir():
            return path
    return home


def projects_dir() -> Path:
    """Onde os projetos Cypress gerados são gravados.

    Fica em Documentos, não em AppData, por dois motivos.

    O primeiro é decisivo: o Python distribuído pela Microsoft Store roda em
    contêiner e **virtualiza escritas em AppData\\Local**. O Python enxerga
    `AppData\\Local\\Cygen`, mas o caminho real é
    `AppData\\Local\\Packages\\<pacote>\\LocalCache\\Local\\Cygen`. Qualquer
    outro processo — `cmd.exe`, `node`, o Cypress, o editor do usuário — não
    encontra nada ali. Rodar o projeto de dentro do AppData falhava com "A
    pasta atual não é válida", um erro que não menciona virtualização alguma.

    O segundo é de bom senso: um projeto Cypress é artefato do usuário, não
    cache do aplicativo. Ele vai ser aberto no editor, versionado, rodado na
    mão. Esconder isso em AppData seria o lugar errado mesmo sem o bug.
    """
    override = os.environ.get("CYGEN_PROJECTS_DIR")
    path = Path(override) if override else documents_dir() / "Cygen"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _slug(value: str) -> str:
    cleaned = re.sub(r"[^\w\s-]", "", value or "", flags=re.UNICODE).strip()
    cleaned = re.sub(r"[\s_-]+", "-", cleaned).lower()
    return cleaned[:60] or "fluxo"


class FlowStore:
    """Fluxos gravados, em JSON, um arquivo por fluxo."""

    def save(self, flow: dict[str, Any]) -> dict[str, Any]:
        """Grava um fluxo. Cria id e timestamps se ainda não existirem."""
        flow = dict(flow)
        flow.setdefault("id", f"{int(time.time())}-{uuid.uuid4().hex[:6]}")
        flow.setdefault("createdAt", time.time())
        flow["updatedAt"] = time.time()
        flow.setdefault("name", "Fluxo sem nome")

        path = flows_dir() / f"{flow['id']}.json"
        tmp = path.with_suffix(".json.tmp")
        # Escrita atômica: um crash no meio não deixa um JSON truncado no lugar
        # do fluxo anterior.
        tmp.write_text(json.dumps(flow, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)
        return flow

    def load(self, flow_id: str) -> dict[str, Any] | None:
        path = flows_dir() / f"{flow_id}.json"
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None

    def delete(self, flow_id: str) -> bool:
        path = flows_dir() / f"{flow_id}.json"
        if path.exists():
            path.unlink()
            return True
        return False

    def list(self) -> list[dict[str, Any]]:
        """Resumo de todos os fluxos, do mais recente para o mais antigo."""
        out: list[dict[str, Any]] = []
        for path in flows_dir().glob("*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            steps = data.get("steps") or []
            out.append({
                "id": data.get("id", path.stem),
                "name": data.get("name", path.stem),
                "description": data.get("description", ""),
                "baseUrl": data.get("baseUrl", ""),
                "stepCount": len(steps),
                "assertionCount": sum(len(s.get("assertions") or []) for s in steps),
                "createdAt": data.get("createdAt", 0),
                "updatedAt": data.get("updatedAt", 0),
                "verified": bool((data.get("verification") or {}).get("ok")),
            })
        out.sort(key=lambda f: f.get("updatedAt", 0), reverse=True)
        return out

    def export(self, name: str, content: str, extension: str) -> Path:
        """Grava um arquivo de teste no diretório de exportações."""
        target = exports_dir() / f"{_slug(name)}{extension}"
        target.write_text(content, encoding="utf-8")
        return target

    def project_dir(self, name: str) -> Path:
        """Pasta para um projeto Cypress completo.

        Regerar o mesmo fluxo sobrescreve os arquivos gerados, o que é o
        esperado. Mas `cypress.env.json` e `node_modules` ficam de fora do
        conjunto gerado justamente para sobreviverem a isso — o usuário não
        perde as credenciais que digitou ao regerar.
        """
        target = projects_dir() / _slug(name)
        target.mkdir(parents=True, exist_ok=True)
        return target


class Settings:
    """Preferências da aplicação.

    Nunca guarda segredos — só o *nome* do provedor escolhido. As chaves ficam
    em variáveis de ambiente, onde o sistema operacional já sabe protegê-las.
    """

    DEFAULTS: dict[str, Any] = {
        "provider": "native",
        "model": None,
        "theme": "auto",
        "browser": "chromium",
        "headless": False,
        "emitCypress": True,
        "emitPlaywright": False,
        "splitGroups": False,
        "verbose": True,
        "minConfidence": 0.55,
        "autoVerify": True,
        "preferredAttrs": ["data-cy", "data-test", "data-testid", "data-qa"],
        "disabledRules": [],
    }

    def __init__(self) -> None:
        self.path = data_dir() / "settings.json"
        self.values = dict(self.DEFAULTS)
        self.load()

    def load(self) -> dict[str, Any]:
        if self.path.exists():
            try:
                stored = json.loads(self.path.read_text(encoding="utf-8"))
                # Chaves desconhecidas são descartadas: um settings.json de uma
                # versão futura não deve injetar campos arbitrários.
                self.values.update({
                    k: v for k, v in stored.items() if k in self.DEFAULTS
                })
            except Exception:
                pass
        return self.values

    def save(self, patch: dict[str, Any] | None = None) -> dict[str, Any]:
        if patch:
            self.values.update({k: v for k, v in patch.items() if k in self.DEFAULTS})
        self.path.write_text(
            json.dumps(self.values, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return self.values

    def get(self, key: str, default: Any = None) -> Any:
        return self.values.get(key, default)
