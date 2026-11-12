#!/usr/bin/env python3
"""Hook UserPromptSubmit — avisa o beco que o pedido parece tocar (ADR-0013).

O consultor da memória (ADR-0012) acerta quando é chamado, mas em 5 sessões medidas o Claude
não o chamou nenhuma vez: o gatilho era uma frase no bloco do `SessionStart`, longe do
momento da decisão. Este hook põe o gatilho colado ao pedido, e só quando há motivo: uma
busca textual (`busca.melhor`) acha o beco que o pedido parece tocar, e o aviso traz esse
beco e manda chamar o consultor, que confere se ele se aplica.

Síncrono de propósito: o aviso tem de chegar antes de o Claude ler o pedido. A busca mede
~10 ms; o resto é o interpretador.

Autoteste:  python src/harness_memoria/hooks/avisar_becos.py --autoteste [--projeto CAMINHO]
"""

from __future__ import annotations

import os
import sys

ROTULO = "avisar-becos"

#: Pedido com menos termos úteis que isto ("sim", "commit e push") não é busca: a regra de
#: disparo foi medida em pedidos de verdade, e duas palavras não separam beco nenhum.
MIN_PALAVRAS = 3

CABECALHO = "## Memória: este pedido parece tocar um beco já registrado"

_ERRO_DE_BOOTSTRAP: str | None = None

#: `_leve`, quando ele importar. Começa em `None` porque ele pode ser o arquivo quebrado.
L = None

try:
    # `os.path`, não `pathlib`: o pré-gate tem de poder desistir antes do import caro.
    _AQUI = os.path.dirname(os.path.realpath(__file__))
    sys.path.insert(0, os.path.dirname(os.path.dirname(_AQUI)))

    from harness_memoria.hooks import _leve as L  # noqa: E402

    # PRÉ-GATE — ver `_leve.gate_barato`. Este hook roda a cada pedido do humano, em todo
    # projeto onde o plugin está habilitado; num projeto sem `.claude/harness.json` ele sai
    # sem importar o pacote. As duas guardas são as de sempre: `__main__` porque a suíte
    # importa este módulo, e `--autoteste` porque lá o projeto vem por `--projeto`.
    if __name__ == "__main__" and "--autoteste" not in sys.argv and L.gate_barato() is False:
        L.sair_sem_fazer_nada()

    import time  # noqa: E402
    from pathlib import Path  # noqa: E402

    from harness_memoria import busca, diario  # noqa: E402
    from harness_memoria.config import Config, carregar  # noqa: E402
    from harness_memoria.hooks import _comum as C  # noqa: E402
except Exception as e:  # noqa: BLE001 — pacote inconsistente não derruba a sessão
    _ERRO_DE_BOOTSTRAP = f"{type(e).__name__}: {e}"


def main(argv: list[str] | None = None) -> int:
    if _ERRO_DE_BOOTSTRAP is not None:
        aviso = f"[{ROTULO}] pacote não importável, hook inerte: {_ERRO_DE_BOOTSTRAP}"
        if L is None:
            print(aviso, file=sys.stderr)
            return 0
        L.sair_sem_fazer_nada(aviso)
    argv = list(argv if argv is not None else sys.argv[1:])
    C.preparar(ROTULO)
    if "--autoteste" in argv:
        return _autoteste(_arg(argv, "--projeto") or os.getcwd())

    evento = C.ler_evento()
    # O `claude -p` que narra o diário não é sessão de desenvolvimento, e um subagente não
    # chama subagente: nos dois casos o aviso mandaria fazer o que quem lê não pode.
    if C.narrando() or evento.get("agent_id"):
        return 0
    prompt = evento.get("prompt")
    if not isinstance(prompt, str) or prompt.lstrip().startswith("/"):
        return 0
    ctx = C.contexto(evento, ROTULO)
    if ctx is None:
        return 0
    raiz, cfg = ctx
    texto = avaliar(raiz, cfg, prompt, str(evento.get("session_id") or "sem-sessao"))
    if texto:
        C.emitir_contexto("UserPromptSubmit", texto)
    return 0


def avaliar(raiz: Path, cfg: Config, prompt: str, sessao: str) -> str | None:
    """O aviso a injetar para este pedido, ou `None`. Marca o beco avisado na sessão."""
    if len(busca.termos(prompt)) < MIN_PALAVRAS:
        return None
    becos = diario.becos_com_origem(cfg.pasta_diario)
    achado = busca.melhor([b.texto for b in becos], prompt)
    if achado is None:
        return None
    beco = becos[achado[0]]
    chave = f"{_relativo(raiz, beco.arquivo)}:{beco.linha}"
    if chave in C.ler_becos_avisados(raiz, sessao):
        return None
    C.marcar_beco_avisado(raiz, sessao, chave)
    return montar_aviso(raiz, cfg, beco, C.consultor_disponivel())


def montar_aviso(raiz: Path, cfg: Config, beco: diario.Beco, consultor: str | None) -> str:
    """O texto do ADR-0013, decisão 5. Sem o agente no plugin, manda conferir o item."""
    data = f"{beco.data} · " if beco.data else ""
    item = diario._resumir_beco(beco.texto, cfg.diario.teto_item_beco_chars)
    if consultor:
        fim = (
            "Busca textual, pode errar. Antes de propor ou implementar, chame o subagente "
            f"`{consultor}` com o pedido: ele confere se o beco se aplica e procura nos ADRs "
            "e no resto do diário."
        )
    else:
        fim = "Busca textual, pode errar. Confira o item antes de propor."
    return (
        f"{CABECALHO}\n\n- {data}`{_relativo(raiz, beco.arquivo)}:{beco.linha}` · {item}\n\n{fim}"
    )


def _relativo(raiz: Path, arquivo: Path) -> str:
    try:
        return Path(os.path.relpath(arquivo, raiz)).as_posix()
    except ValueError:  # outro drive, no Windows
        return arquivo.as_posix()


def _autoteste(projeto: str) -> int:
    """Lê os becos e cronometra uma busca. Reprova só se a leitura ou a busca quebrarem.

    Não confere se a busca "acha" algo: num diário de um beco só o IDF é quase nulo e a
    regra nunca dispara, o que é o comportamento certo e não uma falha.
    """
    raiz = Path(projeto).resolve()
    try:
        cfg = carregar(raiz)
        if cfg is None:
            print(f"[{ROTULO}] projeto sem `.claude/harness.json` — hook inerte por desenho")
            return 0
        becos = diario.becos_com_origem(cfg.pasta_diario)
        if not becos:
            print(f"[{ROTULO}] ok — diário sem becos, hook inerte")
            return 0
        inicio = time.perf_counter()
        achado = busca.melhor([b.texto for b in becos], becos[0].texto)
        ms = (time.perf_counter() - inicio) * 1000
    except Exception as e:  # noqa: BLE001 — o autoteste relata, não propaga
        print(f"[{ROTULO}] FALHA — {type(e).__name__}: {e}")
        return 1
    dispara = "sim" if achado is not None else "não"
    print(
        f"[{ROTULO}] ok — {len(becos)} becos, busca em {ms:.1f} ms "
        f"(o beco mais recente dispara no próprio texto: {dispara})"
    )
    return 0


def _arg(argv: list[str], nome: str) -> str | None:
    if nome in argv:
        i = argv.index(nome)
        if i + 1 < len(argv):
            return argv[i + 1]
    return None


if __name__ == "__main__":
    try:
        codigo = main()
    except Exception as e:  # noqa: BLE001 — hook nunca propaga exceção
        print(f"[{ROTULO}] hook falhou: {type(e).__name__}: {e}", file=sys.stderr)
        codigo = 0
    sys.exit(codigo)
