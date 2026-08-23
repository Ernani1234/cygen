"""
O que o agente não pode fazer.

Um explorador autônomo clica no que encontra. Numa tela de sistema real, o que
ele encontra inclui "Excluir", "Cancelar contrato" e "Enviar para produção" —
e isso não é hipótese, é o que acontece por volta do terceiro minuto. A
diferença entre uma ferramenta útil e um incidente é este arquivo.

A regra é conservadora de propósito: na dúvida, não clica. Um teste a menos
custa um passo; um registro apagado custa o dia de alguém.
"""

from __future__ import annotations

import re
from typing import Any

# Verbos que destroem ou publicam. Comparados contra o rótulo do elemento, que
# é o que uma pessoa leria antes de clicar.
_DESTRUTIVO = re.compile(
    r"\b(excluir|deletar|remover|apagar|delete|remove|drop|"
    r"cancelar\s+(assinatura|contrato|plano|pedido)|"
    r"encerrar\s+conta|desativar|inativar|arquivar|"
    r"publicar|deploy|enviar\s+para\s+produ|liberar\s+para\s+produ|"
    r"resetar|restaurar\s+padr|limpar\s+(tudo|base|dados)|"
    r"revogar|banir|bloquear\s+usu)\b",
    re.I,
)

# Sair derruba a sessão e joga o agente de volta ao login — não é destrutivo,
# mas desperdiça a exploração inteira. Fica de fora por outro motivo.
_SAIDA = re.compile(r"\b(sair|logout|log\s*out|encerrar\s+sess|desconectar)\b", re.I)

# Domínios que não devem receber um agente clicando sozinho.
_PRODUCAO = re.compile(r"\b(prod|producao|produção|www)\b", re.I)


def classify(elemento: dict[str, Any]) -> str:
    """`ok`, `destrutivo` ou `saida` para um elemento da tela."""
    texto = f"{elemento.get('nome', '')} {elemento.get('seletor', '')}"
    if _DESTRUTIVO.search(texto):
        return "destrutivo"
    if _SAIDA.search(texto):
        return "saida"
    return "ok"


def allowed(elemento: dict[str, Any], *, permitir_destrutivo: bool) -> tuple[bool, str]:
    """O agente pode agir sobre este elemento?

    Devolve também o motivo, porque um passo recusado em silêncio vira um
    agente que parece burro: ele tentaria de novo, e de novo.
    """
    tipo = classify(elemento)
    if tipo == "destrutivo" and not permitir_destrutivo:
        return False, (f"“{elemento.get('nome', '')}” parece uma ação destrutiva. "
                       "Ligue “permitir ações destrutivas” se for intencional.")
    if tipo == "saida":
        return False, ("sair da conta encerraria a exploração no meio; "
                       "o agente evita esse botão.")
    return True, ""


def check_target(url: str, *, confirmado: bool) -> str:
    """Aviso quando o alvo tem cara de produção. Vazio quando está tudo bem.

    Não bloqueia sozinho — endereços internos variam demais para um padrão
    decidir por conta própria. Mas exige que alguém tenha dito, por escrito,
    que é para rodar ali.
    """
    if confirmado:
        return ""
    host = re.sub(r"^https?://", "", url or "").split("/")[0]
    if not host:
        return ""

    parece_local = bool(re.match(r"^(localhost|127\.|0\.0\.0\.0|\[::1\]|192\.168\.|10\.)",
                                 host))
    parece_teste = bool(re.search(r"\b(hom|homolog|staging|stage|qa|test|dev|sandbox|uat)\b",
                                  host, re.I))
    if parece_local or parece_teste:
        return ""
    if _PRODUCAO.search(host) or "." in host:
        return (f"“{host}” não parece um ambiente de teste. Um agente autônomo "
                f"vai preencher formulários e criar registros reais. Confirme "
                f"que pode rodar aqui antes de continuar.")
    return ""
