"""
Valores plausíveis para preencher formulários.

É o obstáculo que derruba a maioria dos exploradores autônomos. Um modelo de
linguagem escreve `123.456.789-00` num campo de CPF com a maior confiança do
mundo; o formulário recusa, o agente não entende por quê e passa o resto da
execução tentando variações do mesmo valor inválido.

Aqui os campos que têm regra recebem valores que satisfazem a regra —
calculados, não inventados. O modelo continua decidindo *o que* preencher; o
*como* fica com código determinístico, que é onde ele pertence.
"""

from __future__ import annotations

import random
import re
from typing import Any

_SEMENTE = random.Random(20260820)


def _digitos(valor: str) -> str:
    return re.sub(r"\D", "", valor or "")


def cpf() -> str:
    """CPF com dígitos verificadores corretos.

    O cálculo importa: um CPF com formato certo e dígito errado é recusado por
    qualquer formulário brasileiro sério, e é exatamente o que sai de um modelo
    quando se pede "um CPF de teste".
    """
    base = [_SEMENTE.randint(0, 9) for _ in range(9)]

    def verificador(nums: list[int]) -> int:
        peso = len(nums) + 1
        total = sum(n * (peso - i) for i, n in enumerate(nums))
        resto = (total * 10) % 11
        return 0 if resto == 10 else resto

    d1 = verificador(base)
    d2 = verificador(base + [d1])
    n = "".join(map(str, base + [d1, d2]))
    return f"{n[:3]}.{n[3:6]}.{n[6:9]}-{n[9:]}"


def cnpj() -> str:
    """CNPJ com dígitos verificadores corretos."""
    base = [_SEMENTE.randint(0, 9) for _ in range(8)] + [0, 0, 0, 1]

    def verificador(nums: list[int]) -> int:
        pesos = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2][-len(nums):]
        total = sum(n * p for n, p in zip(nums, pesos))
        resto = total % 11
        return 0 if resto < 2 else 11 - resto

    d1 = verificador(base)
    d2 = verificador(base + [d1])
    n = "".join(map(str, base + [d1, d2]))
    return f"{n[:2]}.{n[2:5]}.{n[5:8]}/{n[8:12]}-{n[12:]}"


_NOMES = ["Ana Souza", "Bruno Lima", "Carla Nunes", "Diego Alves",
          "Elisa Prado", "Fábio Rocha", "Gabriela Melo", "Hugo Martins"]

_GERADORES = {
    "cpf": cpf,
    "cnpj": cnpj,
    "email": lambda: f"teste.cygen+{_SEMENTE.randint(1000, 9999)}@exemplo.com",
    "telefone": lambda: f"(11) 9{_SEMENTE.randint(1000, 9999)}-"
                        f"{_SEMENTE.randint(1000, 9999)}",
    "cep": lambda: f"{_SEMENTE.randint(10000, 99999)}-{_SEMENTE.randint(100, 999)}",
    "data": lambda: f"{_SEMENTE.randint(1, 28):02d}/"
                    f"{_SEMENTE.randint(1, 12):02d}/199{_SEMENTE.randint(0, 9)}",
    "nome": lambda: _SEMENTE.choice(_NOMES),
    "numero": lambda: str(_SEMENTE.randint(1, 999)),
    "valor": lambda: f"{_SEMENTE.randint(10, 9999)},{_SEMENTE.randint(0, 99):02d}",
    "texto": lambda: "Registro criado pelo auto-teste do Cygen",
}

# Como reconhecer o tipo pelo rótulo. A ordem importa: `cnpj` antes de `cpf`
# porque um contém o outro em vários formulários ("CPF/CNPJ").
_PISTAS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"cnpj", re.I), "cnpj"),
    (re.compile(r"\bcpf\b|documento|\bdoc\b", re.I), "cpf"),
    (re.compile(r"e-?mail", re.I), "email"),
    (re.compile(r"telefone|celular|whats|fone|contato", re.I), "telefone"),
    (re.compile(r"\bcep\b|c[oó]digo\s*postal", re.I), "cep"),
    (re.compile(r"data|nascimento|vencimento|prazo", re.I), "data"),
    (re.compile(r"nome|raz[aã]o|respons[aá]vel|cliente|titular", re.I), "nome"),
    (re.compile(r"valor|pre[çc]o|total|sal[aá]rio|renda", re.I), "valor"),
    (re.compile(r"quantidade|qtd|n[uú]mero|idade|c[oó]digo", re.I), "numero"),
]


def guess(elemento: dict[str, Any], regras: dict[str, str] | None = None) -> str:
    """Um valor plausível para este campo.

    `regras` são os valores que o usuário ditou no briefing — eles vencem
    qualquer heurística, porque quem descreveu o sistema sabe mais sobre ele do
    que qualquer padrão de rótulo.
    """
    rotulo = f"{elemento.get('nome', '')} {elemento.get('seletor', '')}".strip()

    for chave, valor in (regras or {}).items():
        if chave and re.search(re.escape(chave), rotulo, re.I):
            return valor

    tipo = (elemento.get("tipo") or "").lower()
    if tipo == "senha":
        return "Teste@123"

    for padrao, nome in _PISTAS:
        if padrao.search(rotulo):
            return _GERADORES[nome]()

    # `pattern` no HTML é a regra explícita do formulário. Não resolvemos o
    # regex de trás para frente — mas os formatos comuns dão para reconhecer.
    padrao_html = elemento.get("padrao") or ""
    if padrao_html:
        if "d{11}" in padrao_html or "d{3}.?d{3}" in padrao_html:
            return _digitos(cpf())
        if "@" in padrao_html:
            return _GERADORES["email"]()

    maximo = elemento.get("maximo")
    valor = _GERADORES["texto"]()
    if maximo and str(maximo).isdigit():
        valor = valor[: int(maximo)]
    return valor


def repair(elemento: dict[str, Any], aviso: str) -> str | None:
    """Outro valor, depois que o formulário recusou o primeiro.

    Lê a mensagem de erro em vez de repetir a mesma tentativa. É o que separa
    um agente que aprende de um que insiste — e insistir no mesmo campo é o
    jeito mais comum de uma exploração autônoma travar.
    """
    texto = (aviso or "").lower()

    if "cpf" in texto:
        return cpf()
    if "cnpj" in texto:
        return cnpj()
    if "mail" in texto:
        return _GERADORES["email"]()
    if "cep" in texto:
        return _GERADORES["cep"]()
    if "telefone" in texto or "celular" in texto:
        return _GERADORES["telefone"]()
    if "data" in texto:
        return _GERADORES["data"]()
    if any(p in texto for p in ("curto", "curta", "m[ií]nimo", "minimo", "least")):
        return _GERADORES["texto"] () + " " + _GERADORES["numero"]()
    if any(p in texto for p in ("longo", "longa", "m[aá]ximo", "maximo", "most")):
        return "Teste"
    if "obrigat" in texto or "required" in texto:
        return guess(elemento)
    return None
