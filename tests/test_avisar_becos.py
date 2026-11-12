"""Hook `UserPromptSubmit` que avisa o beco que o pedido parece tocar (ADR-0013).

Roda o script por subprocess, como a plataforma roda: com o evento no stdin e `env` sem
`CLAUDE_PROJECT_DIR`, que dentro do Claude Code apontaria para este repositório.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from test_busca import ALVOS, CONSULTAS, PREENCHIMENTO

from harness_memoria import diario
from harness_memoria.config import carregar
from harness_memoria.hooks import avisar_becos as AB

SRC = Path(__file__).resolve().parents[1] / "src"
HOOK = SRC / "harness_memoria" / "hooks" / "avisar_becos.py"
CABECALHO = "## Memória: este pedido parece tocar um beco já registrado"


@pytest.fixture
def raiz(projeto: Path) -> Path:
    """O projeto válido do conftest, com os becos da busca num mês arquivado."""
    arquivo = projeto / "docs" / "diario" / "arquivo"
    arquivo.mkdir(parents=True, exist_ok=True)
    itens = "".join(f"- {t}\n" for t in [*ALVOS.values(), *PREENCHIMENTO])
    (arquivo / "2026-09.md").write_text(
        f"# Diário · 2026-09\n\n## 2026-09-01 — Fixture\n\n### Tentativas descartadas\n\n{itens}",
        encoding="utf-8",
    )
    return projeto.resolve()


def _rodar(
    raiz: Path,
    prompt: str,
    sessao: str = "s1",
    *,
    extra: dict | None = None,
    env_extra: dict | None = None,
    hook: Path = HOOK,
    args: tuple[str, ...] = (),
) -> subprocess.CompletedProcess:
    evento = {"hook_event_name": "UserPromptSubmit", "session_id": sessao, "cwd": str(raiz)}
    evento["prompt"] = prompt
    evento.update(extra or {})
    env = {k: v for k, v in os.environ.items() if k not in ("CLAUDE_PROJECT_DIR",)}
    env.pop("HARNESS_MEMORIA_NARRANDO", None)
    env.update(env_extra or {})
    return subprocess.run(
        [sys.executable, str(hook), *args],
        input=json.dumps(evento),
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=str(raiz),
        env=env,
        timeout=60,
    )


def _aviso(r: subprocess.CompletedProcess) -> str:
    assert r.returncode == 0, r.stderr
    dados = json.loads(r.stdout)
    assert dados["hookSpecificOutput"]["hookEventName"] == "UserPromptSubmit"
    return dados["hookSpecificOutput"]["additionalContext"]


def test_pedido_que_toca_um_beco_recebe_o_aviso(raiz: Path):
    texto = _aviso(_rodar(raiz, CONSULTAS["modal"]))
    assert texto.startswith(f"{CABECALHO}\n\n- 2026-09-01 · `docs/diario/arquivo/2026-09.md:")
    assert "Montar modal dentro do" in texto
    assert "`harness-memoria:consultor-memoria`" in texto
    assert texto.endswith("procura nos ADRs e no resto do diário.")


def test_a_linha_citada_e_a_do_beco(raiz: Path):
    texto = _aviso(_rodar(raiz, CONSULTAS["worktree"]))
    rel, linha = texto.split("`")[1].rsplit(":", 1)
    conteudo = (raiz / rel).read_text(encoding="utf-8").splitlines()[int(linha) - 1]
    assert conteudo.startswith("- `isolation: worktree`")


def test_mesmo_beco_nao_repete_na_sessao(raiz: Path):
    _aviso(_rodar(raiz, CONSULTAS["modal"], "s1"))
    segundo = _rodar(raiz, CONSULTAS["modal"], "s1")
    assert segundo.returncode == 0 and segundo.stdout == ""
    assert CABECALHO in _aviso(_rodar(raiz, CONSULTAS["modal"], "s2"))


@pytest.mark.parametrize(
    "caso",
    [
        "sem-relacao",
        "comando",
        "curto",
        "so-simbolos",
        "subagente",
        "narrando",
        "sem-harness",
        "sem-diario",
    ],
)
def test_silencio(raiz: Path, caso: str):
    prompt, extra, env_extra = CONSULTAS["modal"], {}, {}
    if caso == "sem-relacao":
        prompt = "Já tentamos pôr um cache Redis na frente das respostas?"
    elif caso == "comando":
        prompt = "/commit " + CONSULTAS["modal"]
    elif caso == "curto":
        prompt = "sim ok"
    elif caso == "so-simbolos":
        prompt = "!!! 123 🙂"
    elif caso == "subagente":
        extra = {"agent_id": "a-1"}
    elif caso == "narrando":
        env_extra = {"HARNESS_MEMORIA_NARRANDO": "1"}
    elif caso == "sem-harness":
        (raiz / ".claude" / "harness.json").unlink()
    elif caso == "sem-diario":
        shutil.rmtree(raiz / "docs" / "diario")
    r = _rodar(raiz, prompt, extra=extra, env_extra=env_extra)
    assert r.returncode == 0, r.stderr
    assert r.stdout == "", r.stdout


def test_pedido_em_utf8_cru_com_stdin_cp1252(raiz: Path):
    """No Windows o stdin abre em cp1252, e o Claude Code manda o JSON em UTF-8 sem escapar.

    "Á" é C3 81 em UTF-8, e 0x81 não existe em cp1252: o hook caía com UnicodeDecodeError e
    saía calado. `PYTHONIOENCODING=cp1252` reproduz o Windows em qualquer sistema.
    """
    evento = {"hook_event_name": "UserPromptSubmit", "session_id": "s1", "cwd": str(raiz)}
    evento["prompt"] = CONSULTAS["modal"] + " Área de exclusão."
    env = {k: v for k, v in os.environ.items() if k != "CLAUDE_PROJECT_DIR"}
    env.pop("HARNESS_MEMORIA_NARRANDO", None)
    env["PYTHONIOENCODING"] = "cp1252"
    r = subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(evento, ensure_ascii=False).encode("utf-8"),
        capture_output=True,
        cwd=str(raiz),
        env=env,
        timeout=60,
    )
    assert r.returncode == 0, r.stderr
    assert b"UnicodeDecodeError" not in r.stderr, r.stderr
    assert CABECALHO.encode("cp1252", "replace") in r.stdout or b"Montar modal" in r.stdout


def test_sem_consultor_o_aviso_manda_conferir(raiz: Path):
    cfg = carregar(raiz)
    beco = diario.becos_com_origem(cfg.pasta_diario)[0]
    texto = AB.montar_aviso(raiz, cfg, beco, None)
    assert texto.startswith(CABECALHO)
    assert texto.endswith("Busca textual, pode errar. Confira o item antes de propor.")


def test_pacote_quebrado_sai_0(tmp_path: Path, raiz: Path):
    src = tmp_path / "src"
    shutil.copytree(SRC, src, ignore=shutil.ignore_patterns("__pycache__"))
    alvo = src / "harness_memoria" / "config.py"
    alvo.write_text(alvo.read_text(encoding="utf-8") + "\ndef quebrado(:\n", encoding="utf-8")
    r = _rodar(raiz, CONSULTAS["modal"], hook=src / "harness_memoria" / "hooks" / HOOK.name)
    assert r.returncode == 0
    assert r.stdout.strip() == ""
    assert "Traceback" not in r.stderr, r.stderr
    assert "[avisar-becos]" in r.stderr, r.stderr


def test_autoteste_ok_e_inerte(raiz: Path):
    r = _rodar(raiz, "", args=("--autoteste", "--projeto", str(raiz)))
    assert r.returncode == 0, r.stdout + r.stderr
    assert "[avisar-becos] ok —" in r.stdout + r.stderr
    shutil.rmtree(raiz / "docs" / "diario")
    r = _rodar(raiz, "", args=("--autoteste", "--projeto", str(raiz)))
    assert r.returncode == 0, r.stdout + r.stderr
    assert "inerte" in r.stdout + r.stderr
