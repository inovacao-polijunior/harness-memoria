"""Busca textual nos becos do diário: BM25 em Python puro (ADR-0013).

Serve ao aviso do `UserPromptSubmit`: dado o pedido do humano, qual beco ele parece tocar, e
se a semelhança é forte o bastante para avisar. Só biblioteca padrão, como todo `src/`.

As constantes vieram de um protótipo medido antes do ADR, sobre os 340 becos de um consumidor
real e 121 pedidos reais de três projetos (ADR-0013, "Medição que sustenta a regra"). Mudar
uma delas é mudar a regra do ADR: meça de novo antes.
"""

from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter

#: Parâmetros do BM25, os de uso corrente. Não foram calibrados: a regra abaixo foi medida
#: com eles.
K1 = 1.2
B = 0.75

#: Cada palavra é cortada nas 4 primeiras letras, um radical cru que junta "citando" e
#: "citar". Escolhido pela margem no caso mais difícil da medição (ADR na tela): 1,35× o 2º
#: colocado, contra 1,21× sem radical e 1,06× a 1,07× com 5 ou 6 letras.
RADICAL = 4

#: A regra de disparo. Medido: com ≥ 12 e ≥ 1,3×, os 6 casos conhecidos dispararam no beco
#: certo e 9 de 121 pedidos reais disparariam. Com 1,5×, 5 de 6 e 5 de 121.
PONTUACAO_MINIMA = 12.0
RAZAO_MINIMA = 1.3

#: Dois becos com pelo menos esta fração de termos em comum (Jaccard dos conjuntos) são a
#: mesma lição registrada outra vez. A razão da regra não é medida contra a cópia: na revisão
#: do ADR-0013, a cópia ficava em 2º com razão de 1,02 a 1,22 e calava as lições que mais se
#: repetiram. Medido em 2026-11-12 nos diários de três consumidores: os 6 pares acima de 0,5
#: no ValidaNI são cópias (0,58 a 0,91), e dos 11 pares entre 0,4 e 0,5 nos três, 10 são a
#: mesma lição em outra redação (heredoc com crase, here-string, `write_text` com CRLF). Becos
#: diferentes sobre o mesmo assunto ficam abaixo (0,17 a 0,22 nos do modal). Com 0,4, os 6
#: casos conhecidos e os 9 disparos em 120 pedidos reais não mudam.
LIMIAR_QUASE_COPIA = 0.4

#: Um pedido com log colado pode ter centenas de milhares de caracteres. O começo é o que o
#: humano escreveu; o resto raramente muda o 1º colocado e custaria tempo no caminho de todo
#: pedido.
MAX_CHARS_DA_CONSULTA = 8_000

#: Palavras vazias genéricas de pt e en, já SEM acento: `termos` tira os acentos antes de
#: comparar, então "não" chega aqui como "nao". Nada de vocabulário de projeto: isso seria
#: política de consumidor dentro de `src/`. As de menos de 3 letras já caem pelo tamanho.
PALAVRAS_VAZIAS = frozenset(
    {
        "das", "dos", "nos", "nas", "uma", "uns", "umas", "para", "pra", "por", "pelo", "pela",
        "pelos",
        "pelas", "com", "sem", "que", "nao", "aos", "como", "mas", "mais", "menos", "tambem",
        "isso", "isto", "esse", "essa", "este", "esta", "esses", "essas", "estes", "estas",
        "ele", "ela", "eles", "elas", "voce", "seu", "sua", "seus", "suas", "meu", "minha",
        "nosso", "nossa", "lhe", "foi", "ser", "era", "sao", "tem", "vai", "vou", "quero",
        "quer", "fazer", "faz", "feito", "quando", "onde", "qual", "quais", "quem", "muito",
        "pouco", "cada", "todo", "toda", "todos", "todas", "outro", "outra", "mesmo", "mesma",
        "entao", "depois", "antes", "aqui", "ali", "ate", "sobre", "entre", "the", "and",
        "for", "with",
    }
)  # fmt: skip

_PALAVRA = re.compile(r"[a-z0-9_]+")


def termos(texto: str) -> list[str]:
    """Os termos de busca de um texto, na ordem em que aparecem."""
    texto = unicodedata.normalize("NFKD", texto[:MAX_CHARS_DA_CONSULTA].lower())
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    saida = []
    for p in _PALAVRA.findall(texto):
        if p in PALAVRAS_VAZIAS or len(p) < 3 or p.isdigit():
            continue
        saida.append(p[:RADICAL])
    return saida


def passa(primeiro: float, segundo: float) -> bool:
    """A regra do ADR-0013. Com o 2º zerado, a razão não se aplica e só a pontuação decide."""
    if primeiro < PONTUACAO_MINIMA:
        return False
    return segundo == 0 or primeiro / segundo >= RAZAO_MINIMA


def _pontuar(documentos: list[list[str]], consulta: list[str]) -> list[float]:
    n = len(documentos)
    contagens = [Counter(d) for d in documentos]
    tamanhos = [len(d) for d in documentos]
    media = sum(tamanhos) / n or 1.0
    df = Counter(t for d in contagens for t in d)
    pontos = [0.0] * n
    for termo in set(consulta):
        if termo not in df:
            continue
        idf = math.log(1 + (n - df[termo] + 0.5) / (df[termo] + 0.5))
        for i, cont in enumerate(contagens):
            f = cont.get(termo)
            if f:
                norma = K1 * (1 - B + B * tamanhos[i] / media)
                pontos[i] += idf * f * (K1 + 1) / (f + norma)
    return pontos


def _jaccard(a: set[str], b: set[str]) -> float:
    return len(a & b) / len(a | b) if a or b else 0.0


def melhor(documentos: list[str], consulta: str) -> tuple[int, float, float] | None:
    """`(índice escolhido, pontuação do 1º, razão)` quando o 1º passa da regra; senão None.

    `documentos` vem do mais recente para o mais antigo, a ordem de `becos_com_origem`. As
    quase cópias do 1º (`LIMIAR_QUASE_COPIA`) não contam como 2º colocado, e o índice
    devolvido é o do registro MAIS RECENTE entre o 1º e as cópias dele, que é o que o aviso
    deve citar. A razão vale `math.inf` quando nenhum outro documento pontua.
    """
    if not documentos:
        return None
    termos_docs = [termos(d) for d in documentos]
    pontos = _pontuar(termos_docs, termos(consulta))
    ordem = sorted(range(len(pontos)), key=lambda i: -pontos[i])
    topo = ordem[0]
    do_topo = set(termos_docs[topo])
    copias = {
        i
        for i in ordem[1:]
        if pontos[i] > 0 and _jaccard(do_topo, set(termos_docs[i])) >= LIMIAR_QUASE_COPIA
    }
    primeiro = pontos[topo]
    segundo = next((pontos[i] for i in ordem[1:] if i not in copias), 0.0)
    if not passa(primeiro, segundo):
        return None
    return min({topo} | copias), primeiro, (primeiro / segundo if segundo else math.inf)
