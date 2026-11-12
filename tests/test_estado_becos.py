"""Estado por sessão dos becos já avisados no `UserPromptSubmit` (ADR-0013).

Um aviso por beco por sessão: repetir o mesmo beco a cada pedido é o ruído que ensina a
ignorar o aviso. A compactação zera a lista, como já faz com os ADRs vistos (ADR-0009),
porque o resumo não leva o aviso.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from harness_memoria.hooks import _comum as C

SESSION_START = Path(__file__).resolve().parents[1] / "src/harness_memoria/hooks/session_start.py"


@pytest.fixture(autouse=True)
def _sem_projeto_herdado(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)


def test_marca_le_e_esquece(tmp_path: Path):
    C.marcar_beco_avisado(tmp_path, "s1", "docs/diario/2026-11.md:12")
    assert C.ler_becos_avisados(tmp_path, "s1") == {"docs/diario/2026-11.md:12"}
    C.esquecer_becos_avisados(tmp_path, "s1")
    assert C.ler_becos_avisados(tmp_path, "s1") == set()


def test_esquecer_nao_toca_outra_sessao(tmp_path: Path):
    C.marcar_beco_avisado(tmp_path, "s1", "a.md:1")
    C.marcar_beco_avisado(tmp_path, "s10", "b.md:2")
    C.esquecer_becos_avisados(tmp_path, "s1")
    assert C.ler_becos_avisados(tmp_path, "s10") == {"b.md:2"}


def test_pasta_sem_escrita_nao_lanca(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Estado embaixo de um ARQUIVO comum: `OSError` em qualquer sistema.

    `chmod` só-leitura num diretório não serve: no Windows, que está na matriz do CI, o
    atributo read-only não vale para diretório e a escrita passaria.
    """
    arquivo = tmp_path / "nao-e-pasta"
    arquivo.write_text("x", encoding="utf-8")
    monkeypatch.setattr(C, "pasta_estado", lambda raiz: arquivo / "estado")
    C.marcar_beco_avisado(tmp_path, "s1", "a.md:1")
    assert C.ler_becos_avisados(tmp_path, "s1") == set()
    C.esquecer_becos_avisados(tmp_path, "s1")


def test_compactacao_esquece_os_becos_avisados(projeto: Path):
    raiz = projeto.resolve()
    C.marcar_beco_avisado(raiz, "s1", "docs/diario/2026-11.md:12")
    evento = {"hook_event_name": "SessionStart", "source": "compact", "session_id": "s1"}
    evento["cwd"] = str(raiz)
    r = subprocess.run(
        [sys.executable, str(SESSION_START)],
        input=json.dumps(evento),
        capture_output=True,
        text=True,
        cwd=str(raiz),
        env={k: v for k, v in os.environ.items() if k != "CLAUDE_PROJECT_DIR"},
        timeout=60,
    )
    assert r.returncode == 0, r.stderr
    assert C.ler_becos_avisados(raiz, "s1") == set()


def test_o_estado_de_becos_expira_como_o_resto():
    assert C._ESTADO_QUE_EXPIRA.get("becos_avisados_*.txt") == C.VALIDADE_ESTADO_DIAS
