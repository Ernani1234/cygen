"""
Quem decide o próximo passo.

O modelo recebe três coisas: o que o usuário pediu, o que está na tela agora e
o que já foi feito. Devolve **uma** ação. Não um plano de vinte passos — um
plano longo feito sem ver as telas envelhece no segundo clique, e o agente
passaria a executar um roteiro que não corresponde mais ao sistema.

Uma ação por vez custa uma chamada por passo. Em troca, cada decisão é tomada
olhando a tela de verdade.
"""

from __future__ import annotations

import json
import re
from typing import Any

from ..ai.client import AIClient
from . import perception

SYSTEM = """Você é um explorador de sistemas web que produz testes automatizados.

A cada passo você recebe o estado da tela e responde com UMA ação, em JSON puro,
sem cercas de código e sem texto fora do JSON.

Ações possíveis:
  {"acao": "clicar",   "indice": N, "porque": "..."}
  {"acao": "digitar",  "indice": N, "valor": "...", "porque": "..."}
  {"acao": "selecionar","indice": N, "valor": "...", "porque": "..."}
  {"acao": "navegar",  "url": "/rota", "porque": "..."}
  {"acao": "esperar",  "porque": "..."}
  {"acao": "marco",    "nome": "Nome do fluxo concluído", "porque": "..."}
  {"acao": "concluir", "porque": "..."}

Regras:
- `indice` é o número entre colchetes na lista de elementos da tela.
- Use "marco" quando terminar uma jornada com sentido próprio (por exemplo,
  "Cadastro de cliente"). Cada marco vira um teste separado. Emita o marco
  DEPOIS de concluir a jornada e antes de começar a próxima.
- Use "concluir" quando o objetivo do usuário estiver cumprido, ou quando não
  houver mais nada relevante a explorar.
- Se houver mensagem de erro na tela, corrija o campo apontado antes de seguir.
- Não repita a ação anterior se a tela não mudou; tente outro caminho.
- Prefira caminhos que cumpram o objetivo do usuário a explorar ao acaso.
- Responda em português no campo "porque", em uma frase curta."""


class Planner:
    """Traduz estado da tela em ação, usando o provedor escolhido."""

    def __init__(self, provider: str, model: str | None = None) -> None:
        self.client = AIClient(provider_id=provider, model_id=model)
        self.provider = provider
        self.model = model
        self.tokens = 0
        self.custo = 0.0
        self.chamadas = 0

    async def decide(self, *, briefing: str, estado: dict[str, Any],
                     historico: list[str], passo: int, limite: int) -> dict[str, Any]:
        """A próxima ação. Nunca lança: falha vira uma ação `esperar`."""
        contexto = [
            f"OBJETIVO E REGRAS DO USUÁRIO:\n{briefing}",
            "",
            f"PASSO {passo} de no máximo {limite}.",
            "",
            "TELA ATUAL:",
            perception.describe(estado),
        ]
        if historico:
            contexto += ["", "JÁ FEITO (mais recente por último):"]
            contexto += [f"  - {h}" for h in historico[-12:]]

        try:
            resposta = await self.client.complete(
                [{"role": "user", "content": "\n".join(contexto)}],
                system=SYSTEM,
            )
        except Exception as exc:
            return {"acao": "esperar", "porque": f"falha ao consultar a IA: {exc}"}

        if not resposta.ok:
            return {"acao": "esperar", "porque": f"a IA respondeu com erro: {resposta.error}"}

        self.chamadas += 1
        uso = getattr(resposta, "usage", None)
        if uso:
            self.tokens += getattr(uso, "total_tokens", 0) or 0
            self.custo += getattr(uso, "cost", 0.0) or 0.0

        return _parse(resposta.text)


def _parse(texto: str) -> dict[str, Any]:
    """Extrai a ação da resposta.

    Modelos teimam em embrulhar JSON em cercas de código ou em explicar antes
    de responder, mesmo instruídos a não fazer. Recusar essas respostas
    gastaria uma chamada por teimosia; achar o objeto no meio do texto custa
    três linhas.
    """
    bruto = (texto or "").strip()
    bruto = re.sub(r"^```(?:json)?|```$", "", bruto, flags=re.M).strip()

    try:
        return json.loads(bruto)
    except Exception:
        pass

    inicio, fim = bruto.find("{"), bruto.rfind("}")
    if inicio >= 0 and fim > inicio:
        try:
            return json.loads(bruto[inicio:fim + 1])
        except Exception:
            pass

    return {"acao": "esperar", "porque": f"resposta ilegível da IA: {bruto[:120]}"}
