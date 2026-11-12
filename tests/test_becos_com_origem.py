"""`diario.becos_com_origem`: cada beco com o arquivo e a linha de onde veio (ADR-0013).

O aviso do `UserPromptSubmit` cita `arquivo:linha`, e o digest do `SessionStart` lista os
mesmos itens. Os dois saem deste parser: dois parsers do mesmo formato divergiriam na
primeira correção.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from harness_memoria import diario
from harness_memoria.config import ConfigDiario

NOVEMBRO = """\
# Diário · 2026-11

## 2026-11-03 — Primeira

### Tentativas descartadas

- Montar modal dentro do `<nav class="sidebar">` → abre invisível.
  **Não repetir:** use portal.
- item repetido → falhou. **Não repetir.**

## 2026-11-10 — Segunda

### O que foi feito

- nada

### Tentativas descartadas

- Filtrar ganho por estágio → a aba nasce vazia, porque o estágio
  dos ganhos fica fora do escopo
  do sync. **Não repetir:** filtre por status.

### Verificação

- ok
"""

SETEMBRO = """\
# Diário · 2026-09

## 2026-09-01 — Velha

### Tentativas descartadas

- item repetido → falhou. **Não repetir.**
- Usar var(--border) → não existe. **Não repetir.**
"""


@pytest.fixture
def pasta(tmp_path: Path) -> Path:
    p = tmp_path / "diario"
    (p / "arquivo").mkdir(parents=True)
    (p / "2026-11.md").write_text(NOVEMBRO, encoding="utf-8")
    (p / "arquivo" / "2026-09.md").write_text(SETEMBRO, encoding="utf-8")
    return p


def test_linha_aponta_o_traco_do_item(pasta: Path):
    becos = diario.becos_com_origem(pasta)
    assert becos
    for b in becos:
        linha = b.arquivo.read_text(encoding="utf-8").splitlines()[b.linha - 1]
        assert linha.startswith("- "), (b, linha)
        assert b.texto[:20] in linha, (b, linha)


def test_item_de_varias_linhas_vira_uma(pasta: Path):
    filtrar = next(b for b in diario.becos_com_origem(pasta) if b.texto.startswith("Filtrar"))
    assert "\n" not in filtrar.texto
    assert filtrar.texto.endswith("**Não repetir:** filtre por status.")


def test_ordem_do_mais_recente_e_arquivo_por_ultimo(pasta: Path):
    becos = diario.becos_com_origem(pasta)
    assert [b.texto.split()[0] for b in becos] == ["Filtrar", "Montar", "item", "Usar"]
    assert [b.data for b in becos] == ["2026-11-10", "2026-11-03", "2026-11-03", "2026-09-01"]
    assert becos[-1].arquivo.parent.name == "arquivo"


def test_item_repetido_fica_so_o_mais_recente(pasta: Path):
    repetidos = [b for b in diario.becos_com_origem(pasta) if b.texto.startswith("item")]
    assert len(repetidos) == 1
    assert repetidos[0].data == "2026-11-03"


def test_arquivo_com_utf8_invalido_e_pulado(pasta: Path):
    quebrado = (
        b"## 2026-10-05 \xe2\x80\x94 Quebrada\n\n### Tentativas descartadas\n\n"
        b"- beco \xff\xfe ilegivel. **N\xc3\xa3o repetir.**\n"
    )
    (pasta / "2026-10.md").write_bytes(quebrado)
    becos = diario.becos_com_origem(pasta)
    assert [b.texto.split()[0] for b in becos] == ["Filtrar", "Montar", "item", "Usar"]


def test_becos_sem_saida_bate_com_becos_com_origem(pasta: Path):
    cfg = ConfigDiario()
    itens, total = diario.becos_sem_saida(pasta, cfg)
    becos = diario.becos_com_origem(pasta)
    assert total == len(becos)
    esperado = [
        f"{b.data} · " + diario._resumir_beco(b.texto, cfg.teto_item_beco_chars) for b in becos
    ]
    assert itens == esperado[: len(itens)]
