"""`busca`: BM25 em Python puro e a regra que decide o aviso do `UserPromptSubmit` (ADR-0013).

O corpus é de fixture, com os seis casos que motivaram o ADR reescritos como becos
sintéticos. O corpus real que mediu as constantes é de outro projeto e não entra aqui.
"""

from __future__ import annotations

import time

import pytest

from harness_memoria import busca

ALVOS = {
    "popover": (
        "`position: absolute` num popover dentro de painel com `overflow-y: auto` → o painel "
        "recorta o popover. **Não repetir:** popover em painel que rola vai em portal no body."
    ),
    "modal": (
        'Montar modal dentro do `<nav class="sidebar">` → a nav tem isolation: isolate e o '
        "painel abre invisível. **Não repetir:** monte o modal fora da nav."
    ),
    "border": (
        "Usar `var(--border)` no CSS novo → o token não existe. **Não repetir:** confira o "
        "token em tokens.css antes de escrever a regra."
    ),
    "worktree": (
        "`isolation: worktree` contando com a branch do épico → as worktrees nascem do "
        "master, sem o esqueleto. **Não repetir:** crie a branch a partir da do épico no "
        "prompt."
    ),
    "ganho": (
        "Filtrar o deal ganho por stage, como o card faz → os ganhos estão no stage 36, fora "
        "do escopo do sync. **Não repetir:** filtre por status won."
    ),
    "adr-na-tela": (
        'Citar número de ADR na cópia visível da tela ("desconta semana de prova (ADR-0044 e '
        '0056)"). Saiu na conferência. **Não repetir:** ADR é endereço de código, não de '
        "produto; a tela diz o fato, o comentário no arquivo diz onde a decisão mora."
    ),
}

CONSULTAS = {
    "popover": "Vou abrir um popover com posicionamento absoluto dentro do painel lateral "
    "que tem rolagem.",
    "modal": "Quero renderizar o modal de confirmação como filho da sidebar, dentro do <nav>.",
    "border": "Posso usar a variável CSS --border no componente novo?",
    "worktree": "Vou disparar subagentes com isolation worktree a partir da branch do épico.",
    "ganho": "Para contar os negócios ganhos no Pipedrive, dá para filtrar pelo stage?",
    "adr-na-tela": "Na aba Progresso, acrescenta uma nota explicando ao usuário que o relógio "
    "desconta as semanas de prova, citando o ADR-0056.",
}

ASSUNTOS = [
    "rodar a migração direto pelo SQL editor",
    "subir o deploy na sexta sem o smoke",
    "agendar o cron de hora em hora",
    "mandar o webhook sem assinatura",
    "ler a planilha pela primeira aba",
    "gerar o relatório com o fuso do servidor",
    "enviar o e-mail de cobrança em lote",
    "reprocessar a fila inteira de uma vez",
    "testar com o fixture de produção",
    "conferir o lint só no arquivo alterado",
]
CONSEQUENCIAS = [
    "o histórico ficou sem registro",
    "o job estourou o tempo",
    "o cliente recebeu duas vezes",
    "a conta não bateu no fim do mês",
]
PREENCHIMENTO = [
    f"{a.capitalize()} → {c}. **Não repetir:** confira antes."
    for a in ASSUNTOS
    for c in CONSEQUENCIAS
]


def _corpus() -> tuple[list[str], list[str]]:
    nomes = list(ALVOS) + [f"preenchimento-{i}" for i in range(len(PREENCHIMENTO))]
    return nomes, list(ALVOS.values()) + PREENCHIMENTO


def test_termos_tira_acento_vazias_digitos_e_corta_o_radical():
    assert busca.termos("Citando o ADR-0056 na tela") == ["cita", "adr", "tela"]
    assert busca.termos("Exclusão") == ["excl"]


def test_passa_nas_duas_metades_da_regra():
    assert busca.passa(12, 0)
    assert busca.passa(13, 10)
    assert busca.passa(26, 20)
    assert not busca.passa(11.9, 0)
    assert not busca.passa(13, 10.1)


@pytest.mark.parametrize("caso", list(CONSULTAS))
def test_melhor_acha_o_documento_certo(caso: str):
    nomes, docs = _corpus()
    achado = busca.melhor(docs, CONSULTAS[caso])
    assert achado is not None, f"{caso}: a regra não disparou"
    assert nomes[achado[0]] == caso, (caso, nomes[achado[0]], achado)


HEREDOC_NOVO = (
    "Heredoc com crase dentro de `$(cat <<'EOF')` pelo Bash → a crase fechou a substituição "
    "e o commit saiu cortado. **Não repetir:** grave a mensagem num arquivo e use `git "
    "commit -F`."
)
HEREDOC_VELHO = (
    "Heredoc com crase em `$(cat <<'EOF')` no Bash → a crase fechou a substituição e a "
    "mensagem do commit saiu cortada. **Não repetir:** use `git commit -F` com arquivo."
)
PEDIDO_HEREDOC = "Faz o commit com heredoc pelo Bash, a mensagem tem crase no meio."


def test_beco_repetido_nao_cala_a_si_mesmo():
    """A mesma lição registrada duas vezes: o 2º colocado é a cópia do 1º.

    Com a razão contra a cópia, a lição que mais se repetiu nunca disparava (ADR-0013,
    revisão final: ~5 lições caladas no ValidaNI). A razão passa a ser contra o 2º que NÃO é
    quase cópia, e o aviso aponta o registro mais recente (o de menor índice).
    """
    docs = [HEREDOC_NOVO, *PREENCHIMENTO, HEREDOC_VELHO]
    achado = busca.melhor(docs, PEDIDO_HEREDOC)
    assert achado is not None, "a lição repetida se calou"
    assert achado[0] == 0, "o aviso tem de apontar o registro mais recente"


def test_segundo_parecido_que_nao_e_copia_ainda_bloqueia():
    """A exceção é só para quase cópia: dois becos diferentes empatados seguem em silêncio."""
    docs = [
        "Modal dentro da sidebar abre invisível por causa do isolation da nav. **Não "
        "repetir:** portal.",
        "Modal da sidebar some no celular: a barra vira inferior com transform. **Não "
        "repetir:** teste no telefone.",
        *PREENCHIMENTO,
    ]
    pedido = "modal sidebar abre invisível isolation celular transform barra"
    pontos = busca._pontuar([busca.termos(d) for d in docs], busca.termos(pedido))
    primeiro, segundo = sorted(pontos, reverse=True)[:2]
    assert segundo >= busca.PONTUACAO_MINIMA, "os dois têm de passar da pontuação"
    assert primeiro / segundo < busca.RAZAO_MINIMA, "o empate tem de ser real"
    assert busca.melhor(docs, pedido) is None


def test_melhor_fica_quieto_sem_relacao():
    _, docs = _corpus()
    assert busca.melhor(docs, "Já tentamos pôr um cache Redis na frente das respostas?") is None


def test_corpus_vazio_e_pequeno_nao_quebram():
    assert busca.melhor([], "popover dentro do painel") is None
    um = busca.melhor([ALVOS["popover"]], CONSULTAS["popover"])
    assert um is None or um[0] == 0


def test_consulta_enorme_responde_rapido():
    docs = [f"{d} variante {i}" for i in range(10) for d in _corpus()[1]][:400]
    enorme = "log de erro com stack trace e muitas linhas coladas " * 4_000
    assert len(enorme) > 200_000
    inicio = time.perf_counter()
    busca.melhor(docs, enorme)
    assert time.perf_counter() - inicio < 1.0
