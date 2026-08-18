"""
Cliente unificado de IA.

Um adaptador por dialeto. A interface pública é uma só — `complete()` — e o
chamador não precisa saber com quem está falando.

Duas garantias que a v2 não dava:

  parâmetros filtrados por capacidade
      `temperature` só é enviado a modelos que aceitam. Modelos Claude atuais
      respondem 400 se o parâmetro aparecer, então mandá-lo às cegas — como a
      v2 fazia — quebraria a chamada.

  custo real antes de gastar
      A v2 estimava tokens como `len(texto) / 4` e multiplicava pelo preço do
      gpt-3.5 de 2023. Aqui o custo sai do preço declarado por modelo no
      registry, e a contagem de tokens vem da própria API quando ela responde.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

import httpx

from . import registry
from .registry import Model, Provider

TIMEOUT = httpx.Timeout(120.0, connect=15.0)


@dataclass
class Usage:
    """Consumo de uma chamada."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost: float = 0.0

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    def to_dict(self) -> dict[str, Any]:
        return {
            "promptTokens": self.prompt_tokens,
            "completionTokens": self.completion_tokens,
            "totalTokens": self.total_tokens,
            "cost": round(self.cost, 6),
        }


@dataclass
class Completion:
    """Resposta de uma chamada de IA."""

    text: str = ""
    usage: Usage = field(default_factory=Usage)
    provider: str = ""
    model: str = ""
    ok: bool = True
    error: str = ""
    elapsed_ms: int = 0
    stop_reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text, "usage": self.usage.to_dict(),
            "provider": self.provider, "model": self.model,
            "ok": self.ok, "error": self.error,
            "elapsedMs": self.elapsed_ms, "stopReason": self.stop_reason,
        }


class AIClient:
    """Fala com qualquer provedor do registry."""

    def __init__(self, provider_id: str = "native", model_id: str | None = None,
                 *, max_tokens: int = 4096, temperature: float = 0.3) -> None:
        self.provider_id = provider_id
        self.model_id = model_id
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.history: list[dict[str, Any]] = []

    # -- interface pública ---------------------------------------------------

    async def complete(
        self,
        messages: list[dict[str, str]],
        *,
        system: str = "",
        max_tokens: int | None = None,
        code: str = "",
    ) -> Completion:
        """Uma chamada de conversa. Devolve texto, consumo e custo.

        `code` é o teste sob revisão. O provedor nativo o analisa localmente;
        os demais o recebem embutido na mensagem.
        """
        resolved = registry.resolve(self.provider_id, self.model_id)
        if not resolved:
            return Completion(ok=False, error=f"Provedor desconhecido: {self.provider_id}")
        provider, model = resolved

        if not provider.configured():
            names = " ou ".join(provider.env_keys) or "(nenhuma)"
            return Completion(
                ok=False, provider=provider.id, model=model.id,
                error=f"{provider.label} não está configurado. "
                      f"Defina a variável de ambiente {names}.",
            )

        started = time.perf_counter()
        limit = max_tokens or self.max_tokens

        try:
            if provider.dialect == registry.DIALECT_NATIVE:
                result = self._native(messages, code)
            elif provider.dialect == registry.DIALECT_ANTHROPIC:
                result = await self._anthropic(provider, model, messages, system, limit)
            elif provider.dialect == registry.DIALECT_GOOGLE:
                result = await self._google(provider, model, messages, system, limit)
            elif provider.dialect == registry.DIALECT_COHERE:
                result = await self._cohere(provider, model, messages, system, limit)
            else:
                result = await self._openai(provider, model, messages, system, limit)
        except httpx.TimeoutException:
            result = Completion(ok=False, error="A requisição excedeu o tempo limite.")
        except httpx.HTTPError as exc:
            result = Completion(ok=False, error=f"Falha de rede: {exc}")
        except Exception as exc:                      # nunca derrubar a UI
            result = Completion(ok=False, error=f"{type(exc).__name__}: {exc}")

        result.provider = provider.id
        result.model = model.id
        result.elapsed_ms = int((time.perf_counter() - started) * 1000)
        result.usage.cost = model.cost(result.usage.prompt_tokens,
                                       result.usage.completion_tokens)
        self.history.append(result.to_dict())
        return result

    def estimate(self, text: str) -> dict[str, Any]:
        """Estimativa de custo antes de gastar.

        A contagem por caracteres é aproximada e está declarada como tal — a v2
        apresentava o mesmo cálculo como se fosse exato.
        """
        resolved = registry.resolve(self.provider_id, self.model_id)
        if not resolved:
            return {"ok": False, "error": "provedor desconhecido"}
        provider, model = resolved

        approx_prompt = max(1, len(text) // 3)     # ~3 chars/token em pt-BR
        approx_completion = self.max_tokens // 2
        return {
            "ok": True,
            "provider": provider.label,
            "model": model.label,
            "approxPromptTokens": approx_prompt,
            "approxCompletionTokens": approx_completion,
            "approxCost": round(model.cost(approx_prompt, approx_completion), 5),
            "free": model.input_price == 0 and model.output_price == 0,
            "disclaimer": "Estimativa por caracteres; o valor real vem na resposta da API.",
        }

    # -- adaptadores ---------------------------------------------------------

    def _native(self, messages: list[dict[str, str]], code: str = "") -> Completion:
        """O Oracle revisando código.

        Quando há um teste em mãos, ele faz a análise estática na hora — sem
        rede, sem token, sem espera. Quando não há, explica o que sabe fazer em
        vez de devolver uma recusa genérica.
        """
        from ..intel import review as reviewer

        # A mensagem pode trazer o código em bloco cercado, quando o usuário
        # cola em vez de gerar pelo Estúdio.
        if not code.strip() and messages:
            last = messages[-1].get("content", "")
            fenced = re.search(r"```(?:javascript|js|ts|typescript)?\s*\n(.*?)```",
                               last, re.S)
            if fenced:
                code = fenced.group(1)

        if not code.strip():
            return Completion(
                text=(
                    "Não recebi nenhum código para revisar.\n\n"
                    "Gere um teste no Estúdio e clique em “Pedir revisão à IA”, "
                    "ou cole o código aqui dentro de um bloco ```js.\n\n"
                    f"O Oracle aplica {reviewer.rule_count()} regras de revisão "
                    "estática: espera por tempo fixo, seletor acoplado a "
                    "framework, credencial no arquivo, assertion que sempre "
                    "passa, valor volátil, ação forçada e outras. Tudo local, "
                    "sem custo.\n\n"
                    "Para conversar em texto livre sobre o teste, escolha um "
                    "provedor de IA em Configurações."
                ),
                usage=Usage(),
            )

        result = reviewer.analyze(code)
        return Completion(text=reviewer.to_text(result), usage=Usage())

    async def _openai(self, provider: Provider, model: Model,
                      messages: list[dict[str, str]], system: str,
                      limit: int) -> Completion:
        """Dialeto `/chat/completions` — cobre a maioria dos provedores."""
        payload: dict[str, Any] = {
            "model": model.id,
            "messages": ([{"role": "system", "content": system}] if system else []) + messages,
            "max_tokens": limit,
        }
        # Só enviamos o que o modelo aceita.
        if model.supports(registry.CAP_TEMPERATURE):
            payload["temperature"] = self.temperature

        headers = {"Content-Type": "application/json"}
        key = provider.key()
        if key:
            headers["Authorization"] = f"Bearer {key}"

        base = provider.base_url
        if provider.id == "azure":
            import os
            endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT", "").rstrip("/")
            if not endpoint:
                return Completion(ok=False, error="Defina AZURE_OPENAI_ENDPOINT.")
            version = os.environ.get("AZURE_OPENAI_API_VERSION", "2024-10-21")
            url = f"{endpoint}/openai/deployments/{model.id}/chat/completions?api-version={version}"
            headers = {"Content-Type": "application/json", "api-key": key or ""}
        else:
            url = f"{base}/chat/completions"

        async with httpx.AsyncClient(timeout=TIMEOUT) as http:
            response = await http.post(url, headers=headers, json=payload)

        if response.status_code != 200:
            return Completion(ok=False, error=_http_error(response))

        data = response.json()
        choice = (data.get("choices") or [{}])[0]
        usage_raw = data.get("usage") or {}
        return Completion(
            text=(choice.get("message") or {}).get("content", "") or "",
            stop_reason=choice.get("finish_reason", ""),
            usage=Usage(
                prompt_tokens=usage_raw.get("prompt_tokens", 0),
                completion_tokens=usage_raw.get("completion_tokens", 0),
            ),
        )

    async def _anthropic(self, provider: Provider, model: Model,
                         messages: list[dict[str, str]], system: str,
                         limit: int) -> Completion:
        """Dialeto `/v1/messages`.

        Modelos atuais rejeitam `temperature`; a profundidade se controla por
        `output_config.effort`. O pensamento adaptativo fica ligado, que é o
        recomendado para análise de código.
        """
        payload: dict[str, Any] = {
            "model": model.id,
            "max_tokens": limit,
            "messages": messages,
        }
        if system:
            payload["system"] = system
        if model.supports(registry.CAP_THINKING):
            payload["thinking"] = {"type": "adaptive"}
            payload["output_config"] = {"effort": "medium"}
        if model.supports(registry.CAP_TEMPERATURE):
            payload["temperature"] = self.temperature

        headers = {
            "Content-Type": "application/json",
            "x-api-key": provider.key() or "",
            "anthropic-version": "2023-06-01",
        }

        async with httpx.AsyncClient(timeout=TIMEOUT) as http:
            response = await http.post(f"{provider.base_url}/messages",
                                       headers=headers, json=payload)

        if response.status_code != 200:
            return Completion(ok=False, error=_http_error(response))

        data = response.json()
        stop = data.get("stop_reason", "")

        # Os classificadores podem recusar; nesse caso `content` vem vazio e
        # ler `content[0]` levantaria IndexError.
        if stop == "refusal":
            details = data.get("stop_details") or {}
            return Completion(
                ok=False, stop_reason=stop,
                error="O modelo recusou a solicitação"
                      + (f" (categoria: {details.get('category')})" if details.get("category") else "")
                      + ". Reformule o pedido ou escolha outro provedor.",
            )

        text = "".join(
            block.get("text", "")
            for block in (data.get("content") or [])
            if block.get("type") == "text"
        )
        usage_raw = data.get("usage") or {}
        return Completion(
            text=text, stop_reason=stop,
            usage=Usage(
                prompt_tokens=usage_raw.get("input_tokens", 0),
                completion_tokens=usage_raw.get("output_tokens", 0),
            ),
        )

    async def _google(self, provider: Provider, model: Model,
                      messages: list[dict[str, str]], system: str,
                      limit: int) -> Completion:
        """Dialeto `:generateContent` do Gemini."""
        contents = [
            {"role": "model" if m.get("role") == "assistant" else "user",
             "parts": [{"text": m.get("content", "")}]}
            for m in messages
        ]
        payload: dict[str, Any] = {
            "contents": contents,
            "generationConfig": {"maxOutputTokens": limit},
        }
        if model.supports(registry.CAP_TEMPERATURE):
            payload["generationConfig"]["temperature"] = self.temperature
        if system:
            payload["systemInstruction"] = {"parts": [{"text": system}]}

        url = f"{provider.base_url}/models/{model.id}:generateContent"
        async with httpx.AsyncClient(timeout=TIMEOUT) as http:
            response = await http.post(
                url, params={"key": provider.key() or ""},
                headers={"Content-Type": "application/json"}, json=payload,
            )

        if response.status_code != 200:
            return Completion(ok=False, error=_http_error(response))

        data = response.json()
        candidates = data.get("candidates") or []
        text = ""
        if candidates:
            parts = (candidates[0].get("content") or {}).get("parts") or []
            text = "".join(p.get("text", "") for p in parts)
        usage_raw = data.get("usageMetadata") or {}
        return Completion(
            text=text,
            stop_reason=(candidates[0].get("finishReason", "") if candidates else ""),
            usage=Usage(
                prompt_tokens=usage_raw.get("promptTokenCount", 0),
                completion_tokens=usage_raw.get("candidatesTokenCount", 0),
            ),
        )

    async def _cohere(self, provider: Provider, model: Model,
                      messages: list[dict[str, str]], system: str,
                      limit: int) -> Completion:
        """Dialeto `/v2/chat` da Cohere."""
        payload: dict[str, Any] = {
            "model": model.id,
            "messages": ([{"role": "system", "content": system}] if system else []) + messages,
            "max_tokens": limit,
        }
        if model.supports(registry.CAP_TEMPERATURE):
            payload["temperature"] = self.temperature

        async with httpx.AsyncClient(timeout=TIMEOUT) as http:
            response = await http.post(
                f"{provider.base_url}/chat",
                headers={"Content-Type": "application/json",
                         "Authorization": f"Bearer {provider.key() or ''}"},
                json=payload,
            )

        if response.status_code != 200:
            return Completion(ok=False, error=_http_error(response))

        data = response.json()
        content = (data.get("message") or {}).get("content") or []
        text = "".join(c.get("text", "") for c in content)
        usage_raw = ((data.get("usage") or {}).get("tokens") or {})
        return Completion(
            text=text, stop_reason=data.get("finish_reason", ""),
            usage=Usage(
                prompt_tokens=int(usage_raw.get("input_tokens", 0) or 0),
                completion_tokens=int(usage_raw.get("output_tokens", 0) or 0),
            ),
        )


def _http_error(response: httpx.Response) -> str:
    """Extrai a mensagem de erro mais útil que o provedor tiver devolvido."""
    try:
        data = response.json()
    except Exception:
        return f"HTTP {response.status_code}: {response.text[:300]}"

    for path in (("error", "message"), ("message",), ("detail",), ("error",)):
        node: Any = data
        for key in path:
            if isinstance(node, dict) and key in node:
                node = node[key]
            else:
                node = None
                break
        if isinstance(node, str) and node:
            return f"HTTP {response.status_code}: {node}"

    return f"HTTP {response.status_code}: {json.dumps(data)[:300]}"


# ---------------------------------------------------------------------------
# Prompts do domínio
# ---------------------------------------------------------------------------

SYSTEM_REVIEW = """Você é um especialista em testes automatizados Cypress e Playwright.

O usuário está usando o Cygen, que grava interações no navegador e gera testes
a partir do que observou. As assertions já foram deduzidas por um motor lógico
local a partir de evidência real (mutações de DOM, respostas HTTP, mudanças de
rota) — elas não são palpites.

Seu papel é o de revisor, não de autor:
- Aponte fragilidades concretas (seletores acoplados a layout, esperas por tempo)
- Sugira melhorias específicas, com o trecho de código corrigido
- Não invente assertions sobre coisas que não estão na evidência apresentada
- Responda em português do Brasil, direto ao ponto

Se o teste já estiver bom, diga isso em uma frase em vez de inventar críticas.

Não sugira que o usuário extraia comandos customizados manualmente, nem que
crie `cypress.config.js`, `package.json` ou a pasta `support/` na mão. O Cygen
gera tudo isso: o botão "Gerar projeto completo", na aba Código, monta um
projeto que roda com `npm install && npm test`, com os comandos repetidos já
extraídos e nomeados, `cy.session()` no login e caminhos relativos à baseUrl.

Termine sempre indicando o próximo passo concreto. Quando o teste estiver
pronto, esse passo é gerar o projeto completo — não uma lista de tarefas
manuais."""

SYSTEM_RULES = """Você é um analista de qualidade que ajuda a transformar
documentação de regras de negócio em critérios de teste verificáveis.

Dado um documento, extraia:
1. As regras objetivas e testáveis (o que deve acontecer, sob qual condição)
2. Para cada regra, como verificá-la numa interface web
3. Os casos de borda que a documentação sugere mas não declara

Responda em português do Brasil. Seja específico: "o campo CPF rejeita menos de
11 dígitos" vale mais que "validar o formulário"."""
