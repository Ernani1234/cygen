"""
Registry de provedores de IA.

O Cygen v2 falava com um único endpoint (`api.openai.com`) e um único modelo
(`gpt-3.5-turbo`), com o preço de 2023 chumbado no código. Aqui o objetivo é o
oposto: qualquer provedor do mercado, mais um modo nativo que não usa provedor
nenhum.

Dois pontos de projeto que só ficam óbvios depois de errar:

  1. Nem todo provedor aceita os mesmos parâmetros. `temperature` é rejeitado
     com HTTP 400 pelos modelos Claude mais recentes (Opus 5, Sonnet 5, Fable 5)
     — mandar 0.7 para todo mundo, como a v2 fazia, quebraria a integração.
     Por isso cada modelo declara o que aceita, e o cliente filtra.

  2. A maioria dos provedores fala o dialeto OpenAI. Um adaptador cobre quase
     todos; Anthropic e Google, que têm formatos próprios, ganham adaptadores
     dedicados. Assim adicionar um provedor novo costuma ser uma entrada de
     dicionário, não um módulo.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

# Dialetos de API. Determina qual adaptador em `providers.py` atende o provedor.
DIALECT_OPENAI = "openai"        # /chat/completions — o padrão de fato
DIALECT_ANTHROPIC = "anthropic"  # /v1/messages
DIALECT_GOOGLE = "google"        # :generateContent
DIALECT_COHERE = "cohere"        # /v2/chat
DIALECT_NATIVE = "native"        # o Oracle — roda local, custo zero

# Capacidades declaráveis por modelo.
CAP_TEMPERATURE = "temperature"
CAP_STREAMING = "streaming"
CAP_JSON = "json_mode"
CAP_THINKING = "thinking"
CAP_TOOLS = "tools"
CAP_VISION = "vision"

_COMMON = frozenset({CAP_TEMPERATURE, CAP_STREAMING, CAP_JSON, CAP_TOOLS})


@dataclass(frozen=True)
class Model:
    """Um modelo concreto, com preço e capacidades."""

    id: str
    label: str
    context: int                       # janela de contexto em tokens
    input_price: float                 # USD por 1M tokens de entrada
    output_price: float                # USD por 1M tokens de saída
    caps: frozenset[str] = _COMMON

    def supports(self, cap: str) -> bool:
        return cap in self.caps

    def cost(self, prompt_tokens: int, completion_tokens: int) -> float:
        """Custo estimado em USD desta chamada."""
        return (prompt_tokens * self.input_price
                + completion_tokens * self.output_price) / 1_000_000

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "label": self.label, "context": self.context,
            "inputPrice": self.input_price, "outputPrice": self.output_price,
            "caps": sorted(self.caps),
        }


@dataclass(frozen=True)
class Provider:
    """Um provedor de IA e como falar com ele."""

    id: str
    label: str
    dialect: str
    base_url: str
    env_keys: tuple[str, ...]          # variáveis de ambiente aceitas, em ordem
    models: tuple[Model, ...]
    docs: str = ""
    local: bool = False                # roda na máquina do usuário
    note: str = ""
    # O que o provedor oferece sem cartão de crédito. Vazio = só pago.
    # Existe porque "qual eu uso sem pagar?" é a primeira pergunta de quem
    # abre a lista, e ela não se responde olhando preço por token: um preço
    # baixo ainda exige cadastrar cartão.
    free_tier: str = ""
    signup: str = ""                   # onde se pega a chave, direto

    def key(self) -> str | None:
        """A chave deste provedor, do ambiente ou do arquivo do usuário.

        O ambiente vence. Quem já mantém a chave numa variável — em CI, num
        gerenciador de segredos — não deve ser sobreposto por algo que digitou
        na tela meses atrás e esqueceu.
        """
        for name in self.env_keys:
            value = os.environ.get(name)
            if value:
                return value.strip()

        from ..store import Keys
        guardadas = Keys().all()
        for name in self.env_keys:
            value = guardadas.get(name)
            if value:
                return value.strip()
        return None

    def configured(self) -> bool:
        return self.local or bool(self.key())

    def model(self, model_id: str) -> Model | None:
        for m in self.models:
            if m.id == model_id:
                return m
        return None

    def default_model(self) -> Model | None:
        return self.models[0] if self.models else None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "label": self.label, "dialect": self.dialect,
            "baseUrl": self.base_url, "envKeys": list(self.env_keys),
            "models": [m.to_dict() for m in self.models],
            "docs": self.docs, "local": self.local, "note": self.note,
            "configured": self.configured(),
            "freeTier": self.free_tier, "signup": self.signup,
            "free": bool(self.free_tier),
        }


def _m(model_id: str, label: str, context: int, inp: float, out: float,
       *, caps: frozenset[str] = _COMMON) -> Model:
    return Model(model_id, label, context, inp, out, caps)


# ---------------------------------------------------------------------------
# O provedor nativo — o diferencial do Cygen
# ---------------------------------------------------------------------------

NATIVE = Provider(
    id="native",
    label="Cygen Oracle (nativo, custo zero)",
    dialect=DIALECT_NATIVE,
    base_url="",
    env_keys=(),
    local=True,
    models=(
        Model("oracle", "Oracle — inferência lógica de assertions",
              context=0, input_price=0.0, output_price=0.0,
              caps=frozenset({CAP_JSON})),
    ),
    free_tier="Já vem pronto: roda local, sem chave, sem rede e sem custo.",
    note="Deduz assertions a partir do que a página fez, por regras explícitas. "
         "Sem chave, sem rede, sem latência, sem custo — e sem alucinar, porque "
         "não gera texto: só reconhece padrões no que foi observado.",
)


# ---------------------------------------------------------------------------
# Anthropic
# ---------------------------------------------------------------------------
# Os modelos atuais rejeitam `temperature`, `top_p` e `top_k` com HTTP 400 —
# por isso CAP_TEMPERATURE está ausente deles. A profundidade de raciocínio se
# controla por `output_config.effort`, não por amostragem.

_CLAUDE_CAPS = frozenset({CAP_STREAMING, CAP_JSON, CAP_TOOLS, CAP_THINKING, CAP_VISION})

ANTHROPIC = Provider(
    id="anthropic",
    label="Anthropic (Claude)",
    dialect=DIALECT_ANTHROPIC,
    base_url="https://api.anthropic.com/v1",
    env_keys=("ANTHROPIC_API_KEY", "CYGEN_ANTHROPIC_KEY"),
    docs="https://platform.claude.com/docs",
    models=(
        _m("claude-opus-5", "Claude Opus 5", 1_000_000, 5.0, 25.0, caps=_CLAUDE_CAPS),
        _m("claude-sonnet-5", "Claude Sonnet 5", 1_000_000, 3.0, 15.0, caps=_CLAUDE_CAPS),
        _m("claude-opus-4-8", "Claude Opus 4.8", 1_000_000, 5.0, 25.0, caps=_CLAUDE_CAPS),
        _m("claude-haiku-4-5", "Claude Haiku 4.5", 200_000, 1.0, 5.0, caps=_CLAUDE_CAPS),
        _m("claude-fable-5", "Claude Fable 5", 1_000_000, 10.0, 50.0, caps=_CLAUDE_CAPS),
    ),
    note="Modelos atuais não aceitam `temperature` — a profundidade se ajusta "
         "por `effort`. O Cygen respeita isso automaticamente.",
)


# ---------------------------------------------------------------------------
# Provedores de dialeto OpenAI
# ---------------------------------------------------------------------------

OPENAI = Provider(
    id="openai", label="OpenAI", dialect=DIALECT_OPENAI,
    base_url="https://api.openai.com/v1",
    env_keys=("OPENAI_API_KEY", "CYGEN_OPENAI_KEY"),
    docs="https://platform.openai.com/docs",
    models=(
        _m("gpt-4o", "GPT-4o", 128_000, 2.5, 10.0,
           caps=_COMMON | {CAP_VISION}),
        _m("gpt-4o-mini", "GPT-4o mini", 128_000, 0.15, 0.6,
           caps=_COMMON | {CAP_VISION}),
        _m("gpt-4.1", "GPT-4.1", 1_000_000, 2.0, 8.0,
           caps=_COMMON | {CAP_VISION}),
        _m("gpt-4.1-mini", "GPT-4.1 mini", 1_000_000, 0.4, 1.6),
        _m("o3-mini", "o3-mini (raciocínio)", 200_000, 1.1, 4.4,
           caps=frozenset({CAP_STREAMING, CAP_JSON, CAP_TOOLS, CAP_THINKING})),
    ),
)

GOOGLE = Provider(
    id="google", label="Google (Gemini)", dialect=DIALECT_GOOGLE,
    base_url="https://generativelanguage.googleapis.com/v1beta",
    env_keys=("GEMINI_API_KEY", "GOOGLE_API_KEY", "CYGEN_GEMINI_KEY"),
    docs="https://ai.google.dev/docs",
    signup="https://aistudio.google.com/apikey",
    free_tier="Camada gratuita no AI Studio, com limite por minuto e por dia. "
              "Chave em dois cliques, sem cartão.",
    models=(
        _m("gemini-2.0-flash", "Gemini 2.0 Flash", 1_000_000, 0.1, 0.4,
           caps=_COMMON | {CAP_VISION}),
        _m("gemini-1.5-pro", "Gemini 1.5 Pro", 2_000_000, 1.25, 5.0,
           caps=_COMMON | {CAP_VISION}),
        _m("gemini-1.5-flash", "Gemini 1.5 Flash", 1_000_000, 0.075, 0.3,
           caps=_COMMON | {CAP_VISION}),
    ),
)

MISTRAL = Provider(
    id="mistral", label="Mistral AI", dialect=DIALECT_OPENAI,
    base_url="https://api.mistral.ai/v1",
    env_keys=("MISTRAL_API_KEY",),
    docs="https://docs.mistral.ai",
    signup="https://console.mistral.ai/api-keys",
    free_tier="Camada experimental gratuita, com limite por minuto.",
    models=(
        _m("mistral-large-latest", "Mistral Large", 128_000, 2.0, 6.0),
        _m("codestral-latest", "Codestral (código)", 256_000, 0.3, 0.9),
        _m("mistral-small-latest", "Mistral Small", 128_000, 0.2, 0.6),
    ),
)

GROQ = Provider(
    id="groq", label="Groq (inferência rápida)", dialect=DIALECT_OPENAI,
    base_url="https://api.groq.com/openai/v1",
    env_keys=("GROQ_API_KEY",),
    docs="https://console.groq.com/docs",
    signup="https://console.groq.com/keys",
    free_tier="Gratuito com limite por minuto. É o mais rápido da lista — "
              "boa escolha para revisar um teste sem esperar.",
    models=(
        _m("llama-3.3-70b-versatile", "Llama 3.3 70B", 128_000, 0.59, 0.79),
        _m("llama-3.1-8b-instant", "Llama 3.1 8B", 128_000, 0.05, 0.08),
        _m("mixtral-8x7b-32768", "Mixtral 8x7B", 32_768, 0.24, 0.24),
    ),
)

DEEPSEEK = Provider(
    id="deepseek", label="DeepSeek", dialect=DIALECT_OPENAI,
    base_url="https://api.deepseek.com/v1",
    env_keys=("DEEPSEEK_API_KEY",),
    docs="https://api-docs.deepseek.com",
    models=(
        _m("deepseek-chat", "DeepSeek V3", 64_000, 0.27, 1.1),
        _m("deepseek-reasoner", "DeepSeek R1 (raciocínio)", 64_000, 0.55, 2.19,
           caps=_COMMON | {CAP_THINKING}),
    ),
)

XAI = Provider(
    id="xai", label="xAI (Grok)", dialect=DIALECT_OPENAI,
    base_url="https://api.x.ai/v1",
    env_keys=("XAI_API_KEY", "GROK_API_KEY"),
    docs="https://docs.x.ai",
    models=(
        _m("grok-2-latest", "Grok 2", 131_072, 2.0, 10.0),
        _m("grok-2-vision-latest", "Grok 2 Vision", 32_768, 2.0, 10.0,
           caps=_COMMON | {CAP_VISION}),
    ),
)

COHERE = Provider(
    id="cohere", label="Cohere", dialect=DIALECT_COHERE,
    base_url="https://api.cohere.com/v2",
    env_keys=("COHERE_API_KEY", "CO_API_KEY"),
    docs="https://docs.cohere.com",
    models=(
        _m("command-r-plus", "Command R+", 128_000, 2.5, 10.0),
        _m("command-r", "Command R", 128_000, 0.15, 0.6),
    ),
)

TOGETHER = Provider(
    id="together", label="Together AI", dialect=DIALECT_OPENAI,
    base_url="https://api.together.xyz/v1",
    env_keys=("TOGETHER_API_KEY",),
    docs="https://docs.together.ai",
    models=(
        _m("meta-llama/Llama-3.3-70B-Instruct-Turbo", "Llama 3.3 70B Turbo",
           131_072, 0.88, 0.88),
        _m("Qwen/Qwen2.5-Coder-32B-Instruct", "Qwen 2.5 Coder 32B",
           32_768, 0.8, 0.8),
    ),
)

FIREWORKS = Provider(
    id="fireworks", label="Fireworks AI", dialect=DIALECT_OPENAI,
    base_url="https://api.fireworks.ai/inference/v1",
    env_keys=("FIREWORKS_API_KEY",),
    docs="https://docs.fireworks.ai",
    models=(
        _m("accounts/fireworks/models/llama-v3p3-70b-instruct",
           "Llama 3.3 70B", 131_072, 0.9, 0.9),
    ),
)

PERPLEXITY = Provider(
    id="perplexity", label="Perplexity", dialect=DIALECT_OPENAI,
    base_url="https://api.perplexity.ai",
    env_keys=("PERPLEXITY_API_KEY", "PPLX_API_KEY"),
    docs="https://docs.perplexity.ai",
    models=(
        _m("sonar", "Sonar (com busca)", 127_072, 1.0, 1.0),
        _m("sonar-pro", "Sonar Pro", 200_000, 3.0, 15.0),
    ),
)

OPENROUTER = Provider(
    id="openrouter", label="OpenRouter (agregador)", dialect=DIALECT_OPENAI,
    base_url="https://openrouter.ai/api/v1",
    env_keys=("OPENROUTER_API_KEY",),
    docs="https://openrouter.ai/docs",
    signup="https://openrouter.ai/keys",
    free_tier="Modelos com sufixo `:free` não custam nada — os primeiros da "
              "lista abaixo. Uma chave só dá acesso a todos.",
    models=(
        # Os `:free` vêm primeiro: são o padrão quando ninguém escolhe modelo.
        _m("deepseek/deepseek-r1:free", "DeepSeek R1 (grátis)", 64_000, 0.0, 0.0,
           caps=_COMMON | {CAP_THINKING}),
        _m("meta-llama/llama-3.3-70b-instruct:free", "Llama 3.3 70B (grátis)",
           128_000, 0.0, 0.0),
        _m("qwen/qwen-2.5-coder-32b-instruct:free", "Qwen 2.5 Coder 32B (grátis)",
           32_768, 0.0, 0.0),
        _m("google/gemini-2.0-flash-exp:free", "Gemini 2.0 Flash exp (grátis)",
           1_000_000, 0.0, 0.0),
        _m("anthropic/claude-opus-5", "Claude Opus 5 (via OpenRouter)",
           1_000_000, 5.0, 25.0),
        _m("openai/gpt-4o", "GPT-4o (via OpenRouter)", 128_000, 2.5, 10.0),
        _m("google/gemini-2.0-flash-001", "Gemini 2.0 Flash (via OpenRouter)",
           1_000_000, 0.1, 0.4),
    ),
    note="Dá acesso a centenas de modelos com uma única chave. Use o id no "
         "formato `fornecedor/modelo`.",
)

CLOUDFLARE = Provider(
    id="cloudflare", label="Cloudflare Workers AI", dialect=DIALECT_OPENAI,
    # O endpoint carrega o id da conta; sem ele o provedor não tem para onde
    # apontar, e por isso ele fica fora da lista de prontos até ser definido.
    base_url=(f"https://api.cloudflare.com/client/v4/accounts/"
              f"{os.environ.get('CLOUDFLARE_ACCOUNT_ID', '')}/ai/v1"),
    env_keys=("CLOUDFLARE_API_TOKEN", "CF_API_TOKEN"),
    docs="https://developers.cloudflare.com/workers-ai",
    signup="https://dash.cloudflare.com/profile/api-tokens",
    free_tier="Cota diária gratuita, renovada todo dia. Precisa também de "
              "CLOUDFLARE_ACCOUNT_ID.",
    models=(
        _m("@cf/meta/llama-3.3-70b-instruct-fp8-fast", "Llama 3.3 70B",
           24_000, 0.0, 0.0),
        _m("@cf/qwen/qwen2.5-coder-32b-instruct", "Qwen 2.5 Coder 32B",
           32_768, 0.0, 0.0),
    ),
)

AZURE = Provider(
    id="azure", label="Azure OpenAI", dialect=DIALECT_OPENAI,
    base_url="",   # o endpoint é por recurso: definido em AZURE_OPENAI_ENDPOINT
    env_keys=("AZURE_OPENAI_API_KEY",),
    docs="https://learn.microsoft.com/azure/ai-services/openai",
    models=(
        _m("gpt-4o", "GPT-4o (deployment)", 128_000, 2.5, 10.0),
    ),
    note="Requer também AZURE_OPENAI_ENDPOINT e o nome do deployment como "
         "id do modelo.",
)

MOONSHOT = Provider(
    id="moonshot", label="Moonshot (Kimi)", dialect=DIALECT_OPENAI,
    base_url="https://api.moonshot.cn/v1",
    env_keys=("MOONSHOT_API_KEY",),
    docs="https://platform.moonshot.cn/docs",
    models=(
        _m("moonshot-v1-128k", "Moonshot v1 128k", 128_000, 0.84, 0.84),
    ),
)

DASHSCOPE = Provider(
    id="dashscope", label="Alibaba (Qwen)", dialect=DIALECT_OPENAI,
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
    env_keys=("DASHSCOPE_API_KEY", "QWEN_API_KEY"),
    docs="https://help.aliyun.com/zh/dashscope",
    models=(
        _m("qwen-max", "Qwen Max", 32_768, 1.6, 6.4),
        _m("qwen-coder-plus", "Qwen Coder Plus", 128_000, 0.5, 1.5),
    ),
)

ZHIPU = Provider(
    id="zhipu", label="Zhipu (GLM)", dialect=DIALECT_OPENAI,
    base_url="https://open.bigmodel.cn/api/paas/v4",
    env_keys=("ZHIPU_API_KEY", "GLM_API_KEY"),
    docs="https://open.bigmodel.cn/dev/api",
    models=(
        _m("glm-4-plus", "GLM-4 Plus", 128_000, 7.0, 7.0),
    ),
)

NVIDIA = Provider(
    id="nvidia", label="NVIDIA NIM", dialect=DIALECT_OPENAI,
    base_url="https://integrate.api.nvidia.com/v1",
    env_keys=("NVIDIA_API_KEY", "NVIDIA_NIM_API_KEY"),
    docs="https://docs.nvidia.com/nim",
    signup="https://build.nvidia.com",
    free_tier="Créditos gratuitos ao criar conta, sem cartão.",
    models=(
        _m("meta/llama-3.3-70b-instruct", "Llama 3.3 70B", 128_000, 0.0, 0.0),
        _m("qwen/qwen2.5-coder-32b-instruct", "Qwen 2.5 Coder 32B",
           32_768, 0.0, 0.0),
    ),
)

CEREBRAS = Provider(
    id="cerebras", label="Cerebras", dialect=DIALECT_OPENAI,
    base_url="https://api.cerebras.ai/v1",
    env_keys=("CEREBRAS_API_KEY",),
    docs="https://inference-docs.cerebras.ai",
    signup="https://cloud.cerebras.ai",
    free_tier="Camada gratuita com limite diário de tokens.",
    models=(
        _m("llama-3.3-70b", "Llama 3.3 70B", 128_000, 0.85, 1.2),
    ),
)

HUGGINGFACE = Provider(
    id="huggingface", label="Hugging Face", dialect=DIALECT_OPENAI,
    base_url="https://router.huggingface.co/v1",
    env_keys=("HF_TOKEN", "HUGGINGFACE_API_KEY"),
    docs="https://huggingface.co/docs/inference-providers",
    signup="https://huggingface.co/settings/tokens",
    free_tier="Cota mensal gratuita para contas comuns.",
    models=(
        _m("meta-llama/Llama-3.3-70B-Instruct", "Llama 3.3 70B", 128_000, 0.0, 0.0),
        _m("Qwen/Qwen2.5-Coder-32B-Instruct", "Qwen 2.5 Coder 32B",
           32_768, 0.0, 0.0),
    ),
)

GITHUB = Provider(
    id="github", label="GitHub Models", dialect=DIALECT_OPENAI,
    base_url="https://models.inference.ai.azure.com",
    env_keys=("GITHUB_TOKEN", "GH_TOKEN"),
    docs="https://docs.github.com/github-models",
    signup="https://github.com/settings/tokens",
    free_tier="Gratuito com limite de requisições, usando um token comum do "
              "GitHub — sem cadastro novo se você já tem conta.",
    models=(
        _m("gpt-4o", "GPT-4o (GitHub)", 128_000, 0.0, 0.0),
        _m("gpt-4o-mini", "GPT-4o mini (GitHub)", 128_000, 0.0, 0.0),
    ),
)

OLLAMA = Provider(
    id="ollama", label="Ollama (local)", dialect=DIALECT_OPENAI,
    base_url=os.environ.get("OLLAMA_HOST", "http://localhost:11434") + "/v1",
    env_keys=(),
    local=True,
    docs="https://ollama.com",
    free_tier="Roda na sua máquina: sem chave, sem cota, sem custo.",
    models=(
        _m("qwen2.5-coder:14b", "Qwen 2.5 Coder 14B", 32_768, 0.0, 0.0),
        _m("llama3.3", "Llama 3.3", 128_000, 0.0, 0.0),
        _m("deepseek-r1:14b", "DeepSeek R1 14B", 64_000, 0.0, 0.0,
           caps=_COMMON | {CAP_THINKING}),
    ),
    note="Roda na sua máquina. Custo zero e nada sai da rede local — a melhor "
         "opção quando o app testado é interno.",
)

LMSTUDIO = Provider(
    id="lmstudio", label="LM Studio (local)", dialect=DIALECT_OPENAI,
    base_url=os.environ.get("LMSTUDIO_HOST", "http://localhost:1234") + "/v1",
    env_keys=(),
    local=True,
    docs="https://lmstudio.ai/docs",
    free_tier="Roda na sua máquina: sem chave, sem cota, sem custo.",
    models=(
        _m("local-model", "Modelo carregado no LM Studio", 32_768, 0.0, 0.0),
    ),
)


PROVIDERS: tuple[Provider, ...] = (
    NATIVE, ANTHROPIC, OPENAI, GOOGLE, MISTRAL, GROQ, DEEPSEEK, XAI, COHERE,
    TOGETHER, FIREWORKS, PERPLEXITY, OPENROUTER, CLOUDFLARE, AZURE, MOONSHOT,
    DASHSCOPE, ZHIPU, NVIDIA, CEREBRAS, HUGGINGFACE, GITHUB, OLLAMA, LMSTUDIO,
)

BY_ID: dict[str, Provider] = {p.id: p for p in PROVIDERS}


def get(provider_id: str) -> Provider | None:
    return BY_ID.get(provider_id)


def resolve(provider_id: str, model_id: str | None = None) -> tuple[Provider, Model] | None:
    """Par (provedor, modelo) a partir dos ids. Cai no modelo padrão se preciso."""
    provider = BY_ID.get(provider_id)
    if not provider:
        return None
    model = provider.model(model_id) if model_id else None
    if model is None:
        # Provedores agregadores aceitam ids que não estão no catálogo local.
        if model_id and provider.id in ("openrouter", "ollama", "lmstudio",
                                        "azure", "huggingface"):
            model = Model(model_id, model_id, 32_768, 0.0, 0.0)
        else:
            model = provider.default_model()
    if model is None:
        return None
    return provider, model


def configured() -> list[Provider]:
    """Provedores prontos para uso (chave presente, ou locais)."""
    return [p for p in PROVIDERS if p.configured()]


def catalog() -> list[dict[str, Any]]:
    """Catálogo serializável, para a tela de configurações."""
    return [p.to_dict() for p in PROVIDERS]


def free() -> list[Provider]:
    """Provedores com camada gratuita — inclusive os locais."""
    return [p for p in PROVIDERS if p.free_tier]


def stats() -> dict[str, int]:
    return {
        "providers": len(PROVIDERS),
        "models": sum(len(p.models) for p in PROVIDERS),
        "configured": len(configured()),
        "local": sum(1 for p in PROVIDERS if p.local),
        "free": len(free()),
    }


def set_key(provider_id: str, value: str, *, persist: bool = True) -> bool:
    """Guarda a chave deste provedor.

    O Cygen nunca grava segredo em arquivo — é uma decisão de projeto, não um
    detalhe: `settings.json` fica no disco do usuário, entra em backup e sai em
    print de tela. Mas exigir que a pessoa saiba definir variável de ambiente
    antes de experimentar um provedor gratuito é uma barreira alta demais para
    o que ela quer, que é ver se vale a pena.

    Com `persist`, ela vai também para o arquivo de chaves do usuário — fora
    do projeto e fora do git — e sobrevive a fechar o app. Sem, vale só nesta
    sessão. O auto-teste depende de uma chave presente, e pedir a mesma chave
    toda vez que o app abre não é uma decisão de segurança, é um incômodo.
    """
    provider = BY_ID.get(provider_id)
    if not provider or not provider.env_keys:
        return False

    nome = provider.env_keys[0]
    if value.strip():
        os.environ[nome] = value.strip()
    else:
        os.environ.pop(nome, None)

    if persist:
        from ..store import Keys
        Keys().set(nome, value)
    return True
