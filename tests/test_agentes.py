"""Contrato dos agentes que o plugin entrega em `agents/` (ADR-0011, ADR-0012).

Três fatos que nenhum outro teste confere e que falham em silêncio na sessão do usuário:

* **Campo de frontmatter que a plataforma ignora.** A doc de subagentes
  (code.claude.com/docs/en/sub-agents, lida em 2026-11-11) diz que campo desconhecido é
  ignorado sem erro, e que agente de PLUGIN ignora `hooks`, `mcpServers`, `permissionMode` e
  `initialPrompt`. Um desses no frontmatter afirma uma proteção que não existe: é o "config
  que mente reprova" aplicado ao agente.
* **Os agentes só leem.** Agente de plugin não carrega `permissionMode` nem hook próprio,
  então a lista `tools` é a única trava mecânica que sobra. Ferramenta de escrita nela
  desfaz a premissa dos dois ADRs.
* **O gate.** O agente é registrado em todo projeto onde o plugin está habilitado, inclusive
  nos que não têm `.claude/harness.json`. Quem garante que ele não age neles é o passo 0 do
  prompt, então o passo 0 não pode sumir numa edição.
"""

from __future__ import annotations

from pathlib import Path

import pytest

RAIZ_DO_REPO = Path(__file__).resolve().parents[1]
AGENTES = sorted((RAIZ_DO_REPO / "agents").glob("*.md"))

#: Os campos que a doc de subagentes lista (2026-11-11). Fora daqui, o campo é ignorado sem
#: erro — um `tool:` no singular ou um `permissionmode` em minúscula passariam despercebidos.
CAMPOS_CONHECIDOS = {
    "name",
    "description",
    "tools",
    "disallowedTools",
    "model",
    "permissionMode",
    "hooks",
    "skills",
    "mcpServers",
    "color",
    "maxTurns",
    "autoCompactWindow",
    "memory",
    "background",
    "omitClaudeMd",
    "effort",
    "isolation",
    "initialPrompt",
    "experimental",
}

#: Aceitos num agente de `.claude/agents/`, ignorados num agente de plugin.
IGNORADOS_EM_PLUGIN = {"hooks", "mcpServers", "permissionMode", "initialPrompt"}

FERRAMENTAS_DE_LEITURA = {"Read", "Grep", "Glob", "Bash"}


def _frontmatter(arquivo: Path) -> tuple[dict[str, str], str]:
    """Frontmatter de chave simples (`chave: valor`) e o corpo. Sem YAML: zero dependências
    vale também para a suíte, e nenhum agente daqui precisa de valor aninhado — o único campo
    que precisaria (`hooks`) é justamente um dos que agente de plugin ignora."""
    texto = arquivo.read_text(encoding="utf-8")
    assert texto.startswith("---\n"), f"{arquivo.name}: sem frontmatter"
    cabeca, _, corpo = texto[4:].partition("\n---\n")
    campos: dict[str, str] = {}
    for linha in cabeca.splitlines():
        if not linha.strip() or linha.startswith((" ", "\t", "#")):
            continue
        chave, sep, valor = linha.partition(":")
        assert sep, f"{arquivo.name}: linha de frontmatter sem `:` — {linha!r}"
        campos[chave.strip()] = valor.strip()
    return campos, corpo


def test_o_plugin_entrega_ao_menos_um_agente():
    """Sem isto, o glob vazio faria os testes parametrizados abaixo passarem por vacuidade."""
    assert AGENTES, "agents/ vazio ou ausente"


@pytest.mark.parametrize("arquivo", AGENTES, ids=lambda p: p.stem)
def test_nome_e_descricao(arquivo: Path):
    campos, _ = _frontmatter(arquivo)
    assert campos.get("name") == arquivo.stem, (
        f"{arquivo.name}: `name` ({campos.get('name')!r}) difere do nome do arquivo"
    )
    assert campos.get("description"), f"{arquivo.name}: sem `description`"


@pytest.mark.parametrize("arquivo", AGENTES, ids=lambda p: p.stem)
def test_nenhum_campo_ignorado_ou_desconhecido(arquivo: Path):
    campos, _ = _frontmatter(arquivo)
    desconhecidos = set(campos) - CAMPOS_CONHECIDOS
    assert not desconhecidos, f"{arquivo.name}: campo desconhecido {sorted(desconhecidos)}"
    ignorados = set(campos) & IGNORADOS_EM_PLUGIN
    assert not ignorados, (
        f"{arquivo.name}: {sorted(ignorados)} é ignorado em agente de plugin — a proteção que "
        "o campo promete não existe"
    )


@pytest.mark.parametrize("arquivo", AGENTES, ids=lambda p: p.stem)
def test_so_tem_ferramentas_de_leitura(arquivo: Path):
    """Os dois agentes do plugin só leem (ADR-0011, ADR-0012). Um agente que escreva vai
    precisar de um ADR que diga por quê, e de mudar esta lista junto."""
    campos, corpo = _frontmatter(arquivo)
    ferramentas = {f.strip() for f in campos.get("tools", "").split(",") if f.strip()}
    assert ferramentas, "sem `tools`, o agente herda todas — inclusive Write e Edit"
    assert ferramentas <= FERRAMENTAS_DE_LEITURA, (
        f"ferramenta fora da lista de leitura: {sorted(ferramentas - FERRAMENTAS_DE_LEITURA)}"
    )
    if "Bash" in ferramentas:
        # Para o Bash, "só lê" é só o prompt: agente de plugin não carrega hook nem
        # `permissionMode` que o trave. Sumir o parágrafo é sumir a trava inteira.
        assert "Você só lê" in corpo, f"{arquivo.name}: Bash sem o parágrafo que o restringe"


@pytest.mark.parametrize("arquivo", AGENTES, ids=lambda p: p.stem)
def test_comeca_pelo_gate(arquivo: Path):
    _, corpo = _frontmatter(arquivo)
    secoes = corpo.split("\n## ")
    gate = next((s for s in secoes if s.startswith("0. Gate")), None)
    assert gate is not None, f"{arquivo.name}: o passo 0 (gate) sumiu do prompt"
    assert ".claude/harness.json" in gate
    assert corpo.index("## 0. Gate") < corpo.index("## 1."), "o gate tem de vir antes de tudo"


def test_o_hook_aponta_para_um_agente_que_existe():
    """O bloco do `SessionStart` manda perguntar ao consultor pelo nome do arquivo dele."""
    from harness_memoria.hooks import session_start as SS

    assert (RAIZ_DO_REPO / "agents" / f"{SS.AGENTE_CONSULTOR}.md").is_file()
