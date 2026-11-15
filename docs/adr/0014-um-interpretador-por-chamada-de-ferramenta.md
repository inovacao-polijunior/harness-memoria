---
status: proposed
data: 2026-11-15
substitui: [ADR-0003]
---

# ADR-0014 — Rodar um só interpretador por chamada de ferramenta: reafirmação no `guardar`, formatação no `Stop`

## Regra

- Por chamada de ferramenta roda só o `guardar` (`PreToolUse`, síncrono). Hook novo por
  ferramenta só entra se for regra que não pode falhar (bloqueio).
- Lembrete que depende de contar escritas vai para o processo do `guardar`, no mesmo JSON
  de saída do ADR por caminho.
- Trabalho sobre os arquivos escritos (formatar, verificar) roda uma vez por turno, no `Stop`.
- Não registre `PostToolUse` neste plugin.

## Contexto

Em 2026-11-15 o plugin estava ligado em 10 repositórios e registrava três processos Python
por escrita (`guardar` síncrono no `PreToolUse`; `formatar` e `reafirmar` assíncronos no
`PostToolUse`) e um por Bash. A orientação adotada no harness pessoal é que hook sirva para
regra que não pode falhar e que cada hook fique abaixo de 100 ms.

Classificação de cada hook:

| Evento             | Script            | O que faz                                                       | Natureza      |
| ------------------ | ----------------- | --------------------------------------------------------------- | ------------- |
| `PreToolUse`       | `guardar.py`      | nega `.env`, `--no-verify`, `git add --force` e as guardas do projeto; injeta o ADR do caminho (ADR-0009) | inviolável (+ contexto) |
| `PostToolUse`      | `formatar.py`     | roda o formatador do `harness.json` no arquivo escrito          | conveniência  |
| `PostToolUse`      | `reafirmar.py`    | conta escritas e reinjeta as invioláveis a cada 15 (ADR-0003)   | lembrete      |
| `SessionStart`     | `session_start.py`| reinjeta diário e ADRs                                          | contexto      |
| `SubagentStart`    | `session_start.py`| bloco reduzido para o subagente                                 | contexto      |
| `UserPromptSubmit` | `avisar_becos.py` | avisa o beco que o pedido toca (ADR-0013)                       | lembrete      |
| `PreCompact`       | `pre_compact.py`  | instrui o resumo a preservar invioláveis                        | contexto      |
| `Stop`             | `verificar.py`    | roda os sensores e bloqueia o encerramento se reprovarem (ADR-0007) | verificação |
| `SessionEnd`       | `session_end.py`  | grava o piso determinístico no diário (ADR-0002)                | registro      |

Latência medida nesta máquina (macOS, Python 3.13 do PATH, piso `python3 -c pass` = 9,0 ms),
mediana de 5 execuções com entrada de amostra, num clone deste repositório. "Com config" é
o caso dos 10 repositórios; "sem config" é onde o pré-gate de `_leve.py` sai cedo.

| Evento / script                  | Antes, com config | Depois, com config | Antes, sem config | Depois, sem config |
| -------------------------------- | ----------------: | -----------------: | ----------------: | -----------------: |
| `SessionStart` session_start     |           28,6 ms |            31,1 ms |           11,5 ms |            12,0 ms |
| `SubagentStart` session_start    |           27,8 ms |            28,7 ms |           11,2 ms |            12,1 ms |
| `UserPromptSubmit` avisar_becos  |           27,2 ms |            28,0 ms |            9,7 ms |            10,3 ms |
| `PreCompact` pre_compact         |           22,4 ms |            23,3 ms |            9,6 ms |            11,6 ms |
| `SessionEnd` session_end         |           70,4 ms |            81,5 ms |           28,7 ms |            36,1 ms |
| `PreToolUse` Write guardar       |           23,9 ms |            27,5 ms |           10,8 ms |            11,6 ms |
| `PreToolUse` Bash guardar        |           24,7 ms |            25,5 ms |           10,7 ms |            11,4 ms |
| `PostToolUse` formatar (async)   |           24,4 ms |                  — |            9,6 ms |                  — |
| `PostToolUse` reafirmar (async)  |           24,6 ms |                  — |            9,9 ms |                  — |
| `Stop` verificar, turno sem escrita |        27,0 ms |            28,0 ms |            9,6 ms |            10,3 ms |
| `Stop` verificar, 1 `.py` escrito, sensores desligados | — |       28,0 ms |                 — |                  — |

Todos já estavam abaixo de 100 ms antes: o pré-gate e os imports preguiçosos de 2026-09
fizeram esse trabalho. As diferenças de 1 a 3 ms entre colunas estão no ruído entre
rodadas (uma segunda rodada do "antes" deu 29,7 ms no `SessionStart` e 72,5 ms no
`SessionEnd`), exceto o `guardar` em Write, que ganhou ~3 ms reais: importa
`reafirmar.montar_mensagem` sob demanda e grava o contador a cada escrita.

O custo que sobrava não era latência por hook, era número de processos: 3 por escrita. Numa
sessão de 120 escritas e 80 Bash, 440 interpretadores, dos quais 240 só para formatar e
contar. Os dois `PostToolUse` são `async`, então não bloqueavam, mas disputavam CPU com o
trabalho e, no caso do `formatar`, reescreviam o arquivo logo depois da edição, enquanto o
modelo seguia editando o mesmo arquivo.

## Fatores de decisão

- Cada hook abaixo de 100 ms, medido.
- Preservar o comportamento visível: mesmas guardas, mesma reafirmação (contador, intervalo
  e texto), formatador do `harness.json` aplicado ao que o agente escreveu.
- A reafirmação continua por PASSO, não por pedido: o motivo de o ADR-0003 rejeitar o
  `UserPromptSubmit` segue valendo.
- Zero dependência nova e todo hook saindo com 0.

## Decisão

1. **Reafirmação no `guardar`.** Depois da decisão de bloqueio, numa escrita liberada, o
   `guardar` incrementa o mesmo contador por sessão e, quando ele fecha o intervalo, junta o
   texto de `reafirmar.montar_mensagem` ao ADR por caminho num único `additionalContext`.
   Escrita negada não conta, como o `PostToolUse` não via escrita que não aconteceu. O
   narrador do `SessionEnd` não conta nem recebe.
2. **Formatação no `Stop`.** `verificar.py` roda os formatadores uma vez por turno, antes
   dos sensores, sobre o que o agente escreveu por `Write`/`Edit`/… segundo o transcript
   (`sensores.escritas_do_transcript`). O que o git viu mudar no turno continua acionando os
   sensores, mas não é formatado: pode ser lockfile de `npm install` ou edição do usuário.
   Teto de 30 s, conferido a cada comando, e cada comando recebe só o tempo que sobra; com os
   120 s dos sensores e até 20 s de `git`, cabe nos 180 s do `Stop`.
   `HARNESS_MEMORIA_SENSORES=0` desliga só os sensores; a formatação sai tirando
   `formatadores` do `harness.json`. O transcript é lido uma vez por `Stop`.
3. **`PostToolUse` sai do `hooks.json`.** `formatar.py` e `reafirmar.py` ficam como módulos
   (as funções são usadas pelos dois hooks acima) e com os autotestes.

Substitui o ADR-0003: a reafirmação deixa de ser hook `async` próprio e passa a sair
síncrona, antes da escrita, no processo que já existia. A regra do ADR-0003 de que guarda
de bloqueio nunca é `async` continua valendo.

## Alternativas consideradas

### Reafirmar no `UserPromptSubmit`, junto do `avisar_becos`

**Rejeitada porque** o ADR-0003 já mediu o motivo: uma instrução rende 40 escritas sem
prompt novo, e é nesse trecho que a aderência cai.

### Formatar num git hook `pre-commit`

**Rejeitada porque** o plugin não instala git hook no consumidor, e o arquivo ficaria sem
formatar até o commit, depois de os sensores do `Stop` já o terem lido.

### Reescrever o `guardar` em bash

**Rejeitada porque** as guardas do projeto são regex do `harness.json` aplicadas a JSON do
evento; em bash isso exige `jq` (dependência) ou parser frágil. O Python com pré-gate já
fica em 11 ms sem config e 25 a 28 ms com config.

### Não mudar nada

**Rejeitada porque** todos os hooks passavam no teto de 100 ms, mas dois processos por
escrita existiam só para formatar e contar, e o `formatar` mexia no arquivo durante o turno.

## Consequências

**Boas:** de 3 para 1 processo por escrita (Bash segue com 1). Numa sessão de 120 escritas
e 80 Bash, de 440 para 200. A reafirmação chega antes da escrita que fecha o intervalo, e
não um turno depois. O arquivo não muda sob o modelo durante o turno, e os sensores leem o
arquivo já formatado.

**Ruins, e aceitas:** o `guardar` em Write fica ~3 ms mais lento. O arquivo fica sem
formatar até o fim do turno, e se a sessão cair antes do `Stop`, fica sem formatar. Arquivo
escrito por subagente deixa de ser formatado: o `tool_use` dele mora no transcript do
subagente, não no da sessão principal, e o `PostToolUse` o pegava. Sem `transcript_path` no
evento, nada é formatado. Uma escrita que o usuário recusa no diálogo de permissão conta
para a reafirmação, porque o `PreToolUse` roda antes desse diálogo.

## Quando revisitar

Se a reafirmação parar de aparecer no transcript de uma sessão longa, ou se algum
consumidor depender de ver o arquivo formatado no meio do turno (por exemplo, um agente que
lê o arquivo e compara com o formato esperado antes de terminar).

## Plano de Implementação

- **Arquivos a tocar:** `hooks/hooks.json`, `src/harness_memoria/hooks/guardar.py`,
  `src/harness_memoria/hooks/verificar.py`, `src/harness_memoria/sensores.py`,
  `.github/workflows/ci.yml` (contagem de alvos 9 → 7).
- **Padrões a seguir:** o ADR por caminho do ADR-0009, que já mora no `guardar` pelo mesmo
  motivo.
- **Testes obrigatórios:** `tests/test_hooks_quentes.py` (reafirmação no `guardar`, JSON
  único, escrita negada, narrador), `tests/test_verificar.py` (formatação no `Stop`, antes
  dos sensores, com sensores desligados, sem tocar o que só o git viu, teto por comando),
  `tests/test_eventos_novos.py` (sem `PostToolUse`).
- **Não mexer em:** o texto da reafirmação, o intervalo padrão (15) e as guardas.
