#!/usr/bin/env python3
"""Hook Stop — roda os sensores do projeto antes de o agente encerrar o turno (ADR-0007).

O resto do harness diz ao agente o que vale; este confere o que ele fez. Quando o turno
escreveu arquivos que casam com `sensores.comandos[].extensoes`, roda os comandos de
verificação do `harness.json` e, se algum reprovar, devolve `decision: block` com a cauda da
saída e o que fazer — o agente continua o turno em vez de dizer "pronto". A lógica mora em
`harness_memoria.sensores`; este arquivo é a casca de hook.

Antes dos sensores, formata o que o agente escreveu no turno (ADR-0014).

Falha aberta: timeout, executável ausente e erro do próprio harness liberam o encerramento
com um `systemMessage`. `HARNESS_MEMORIA_SENSORES=0` desliga os sensores sem mexer na config;
a formatação continua (para desligá-la, tire `formatadores` do `harness.json`).

Autoteste:  python src/harness_memoria/hooks/verificar.py --autoteste [--projeto CAMINHO]
"""

from __future__ import annotations

import os
import sys

ROTULO = "verificar"

#: Erro do bootstrap, se houver — mesmo desenho dos outros hooks: o import do pacote fica
#: DENTRO da rede, e o erro é relatado rotulado em vez de virar traceback cru.
_ERRO_DE_BOOTSTRAP: str | None = None

#: `_leve`, quando ele importar. Começa em `None` porque ele pode ser o arquivo quebrado.
L = None

try:
    _AQUI = os.path.dirname(os.path.realpath(__file__))
    sys.path.insert(0, os.path.dirname(os.path.dirname(_AQUI)))

    from harness_memoria.hooks import _leve as L  # noqa: E402

    # PRÉ-GATE — ver `_leve.gate_barato`. O `Stop` dispara uma vez por turno, em todo
    # projeto onde o plugin está habilitado no nível do usuário; num projeto que não adotou
    # o harness, o custo tem de ser o do interpretador nu.
    if __name__ == "__main__" and "--autoteste" not in sys.argv and L.gate_barato() is False:
        L.sair_sem_fazer_nada()

    import json  # noqa: E402
    from pathlib import Path  # noqa: E402

    from harness_memoria import sensores  # noqa: E402
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

    # A sessão filha do narrador opt-in do SessionEnd também dispara `Stop`; ela não
    # escreve código e não pode ficar presa num sensor.
    if C.narrando():
        return 0

    evento = C.ler_evento()
    ctx = C.contexto(evento, ROTULO)
    if ctx is None:
        return 0
    raiz, cfg = ctx
    # Uma leitura do transcript serve aos dois: a formatação usa só o que o agente escreveu
    # por ferramenta; os sensores somam o que o git viu mudar no turno.
    do_agente, inicio = sensores.escritas_do_transcript(evento.get("transcript_path"))
    formatar_do_turno(raiz, cfg, do_agente)
    if os.environ.get("HARNESS_MEMORIA_SENSORES") == "0":
        return 0
    escritos = sensores.somar_sujos(raiz, do_agente, inicio) if cfg.sensores.comandos else []
    saida = sensores.verificar(raiz, cfg, evento, escritos=escritos)
    if saida:
        print(json.dumps(saida, ensure_ascii=False))
    return 0


ORCAMENTO_FORMATACAO_S = 30


def formatar_do_turno(raiz: Path, cfg, escritos: list[str]) -> None:
    """ADR-0014: os formatadores do `harness.json`, uma vez por turno, ANTES dos sensores.

    Era o hook `PostToolUse` `formatar.py`, um interpretador por escrita. Aqui roda sobre os
    arquivos que o agente escreveu no turno por `Write`/`Edit`/…, segundo o transcript — não
    sobre o que o git viu mudar, que pode ser lockfile ou edição do usuário. Antes dos
    sensores porque um sensor de estilo tem de ver o arquivo já formatado. A regra por
    arquivo (extensão, executável no PATH, `exige`, `cwd`) é a de
    `formatar._talvez_formatar`, sem cópia.
    """
    if not escritos or not cfg.formatadores:
        return
    import time

    from harness_memoria.hooks.formatar import _talvez_formatar

    # Teto da formatação: o `Stop` tem 180 s no `hooks.json` e os sensores, 120 de orçamento
    # (`sensores.orcamento_total_s`). Sobram 60; a formatação fica com metade, e o que não
    # couber fica sem formatar — formatação nunca pode custar o sensor nem o encerramento.
    limite = time.monotonic() + ORCAMENTO_FORMATACAO_S
    for caminho in escritos:
        if time.monotonic() > limite:
            return
        p = Path(caminho)
        if not p.is_file():
            continue
        for regra in cfg.formatadores:
            # O relógio é conferido por COMANDO, e cada comando recebe só o que sobra: com
            # duas regras na mesma extensão, conferir só entre arquivos deixava passar ~80 s.
            restante = limite - time.monotonic()
            if restante <= 0:
                return
            _talvez_formatar(regra, p, raiz, timeout=restante)


def _autoteste(projeto: str) -> int:
    """Diz, NA MÁQUINA onde o hook vai rodar, se cada sensor configurado consegue rodar."""
    from harness_memoria.config import ErroDeConfig, carregar

    # `Path(projeto)` e não `raiz_projeto(projeto)`: `--projeto` é escolha explícita e
    # ganha de `CLAUDE_PROJECT_DIR` — ver o comentário em `auditar/__main__.py`.
    raiz = Path(projeto)
    try:
        cfg = carregar(raiz)
    except ErroDeConfig as e:
        print(f"FALHA config inválida: {e}")
        return 1
    if cfg is None:
        print(f"[{ROTULO}] {raiz} não tem `.claude/harness.json` — hook inerte por desenho")
        return 0
    return sensores.autoteste(raiz, cfg)


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
