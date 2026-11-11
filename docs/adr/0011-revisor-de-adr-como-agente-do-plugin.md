---
status: proposed
data: 2026-11-11
---

# ADR-0011 — Revisar a aderência a ADR com um agente do plugin, chamado sob demanda

## Regra

- O plugin entrega o revisor em `agents/revisor-adr.md` (`harness-memoria:revisor-adr`). Ele
  é chamado sob demanda, antes do PR, e não entra em nenhum hook.
- O revisor só lê, e a trava mecânica é a lista `tools`. Não ponha ferramenta de escrita
  nela, nem `hooks`/`permissionMode` no frontmatter: agente de plugin ignora esses campos.
- O passo 0 do prompt é o gate. Sem `.claude/harness.json`, o revisor para.

## Contexto

O harness diz ao agente o que vale em três momentos: o índice de ADR no `SessionStart`, as
invioláveis a cada 15 escritas e o ADR do caminho no `PreToolUse` de escrita (ADR-0009). Os
sensores do `Stop` (ADR-0007) conferem o que o agente fez, mas só o que um comando confere:
lint e teste. Nenhum mecanismo confere se a mudança contradiz um ADR. O ADR-0007 rejeitou um
`Stop` do tipo `agent` para o turno inteiro e deixou "aderência a ADR" nomeada como o passo
seguinte, "para o que teste não cobre".

Dois fatos, lidos na doc de subagentes (code.claude.com/docs/en/sub-agents) em 2026-11-11,
limitam o desenho:

- Agente entregue por plugin ignora `hooks`, `mcpServers`, `permissionMode` e
  `initialPrompt`. Campo desconhecido no frontmatter também é ignorado sem erro.
- A `description` de todo agente registrado entra no contexto de toda sessão, em todo
  projeto onde o plugin está habilitado, com ou sem `.claude/harness.json`.

E um fato do próprio harness: um subagente que só lê não recebe ADR nenhum. O bloco do
`SubagentStart` é reduzido a invioláveis e becos porque "o subagente escreve mais do que lê"
(ADR-0004), e a injeção por caminho do ADR-0009 só dispara em escrita. O revisor é o caso
oposto ao que o bloco reduzido presume.

## Fatores de decisão

- Custo sempre ligado: a `description` mede 267 ch (~116 tok, pela razão `chars / 2,3` do
  README), contra 1.072 ch das 4 descrições de skill.
- Falso positivo ensina a ignorar o revisor. Um achado precisa citar o ADR e a regra, e uma
  ausência de achado precisa dizer qual régua foi usada.
- Quem avalia a própria saída tende a aprová-la (o modo de falha citado no ADR-0007). O
  revisor precisa de um contexto que não seja o de quem escreveu o diff.
- A política (mapa, ADRs, invioláveis) mora no consumidor. O que mora no plugin tem de ser
  mecanismo, igual para todos os projetos.

## Decisão

1. **Um agente no plugin**, `agents/revisor-adr.md`, com `tools: Read, Grep, Glob, Bash` e
   `model: inherit`. O Bash serve para o `git diff`, e o prompt limita os comandos `git`
   que só leem.
2. **Gate no passo 0**: sem `.claude/harness.json` na raiz do repositório, ele responde que
   o projeto não adotou o harness e para.
3. **A régua de cada arquivo vem do consumidor.** O revisor lê `adr.pasta` no
   `harness.json`, a seção "Qual ADR ler" do `CLAUDE.md` (ou o arquivo para onde ela aponta,
   ADR-0010) e casa os caminhos com a mesma regra do ADR-0009: pasta por prefixo, arquivo
   exato, somando todas as linhas que casam. Também procura nos ADRs o caminho citado
   literalmente, e ADR vivo que cita o caminho sem estar no mapa entra na régua e aparece no
   relatório como buraco do mapa. As invioláveis valem para todo arquivo. ADR morto não é
   régua, e o revisor segue o `substituido-por:`.
4. **Só contradição é achado.** Estilo, bug, teste e "valeria um ADR" ficam de fora. Na
   dúvida, o caso vai para "Dúvidas". Cada contradição diz a saída: corrigir o código ou
   registrar um ADR que substitua ou emende o contrariado.
5. **O relatório termina com a régua usada**: ADRs por arquivo, arquivos sem ADR no mapa e o
   que ficou de fora por tamanho. É o que torna "nenhuma contradição" verificável.
6. **`tests/test_agentes.py`** reprova campo de frontmatter desconhecido ou ignorado em
   plugin, ferramenta de escrita no revisor e a ausência do gate.

## Alternativas consideradas

### Hook `Stop` do tipo `agent`

**Rejeitada porque** é a alternativa que o ADR-0007 já rejeitou: um modelo inteiro a cada
turno que escreveu, julgando sem determinismo, e com poder de bloquear o encerramento. Um
falso positivo que trava o turno custa mais que o mesmo falso positivo num relatório que o
humano lê.

### Skill `/revisar-adr` na thread principal

**Rejeitada porque** a revisão roda no contexto de quem escreveu o diff. Avaliar a própria
saída é o modo de falha que motivou os sensores. Além disso, ler o mapa e os ADRs inteiros na
thread principal ocupa o contexto que o orçamento do ADR-0004 protege.

### Um agente por projeto, em `.claude/agents/`

**Rejeitada porque** o prompt não tem nada de projeto, já que a régua vem do `CLAUDE.md` e
dos ADRs de cada um. Copiar o mesmo mecanismo para cada consumidor faria as cópias
divergirem na primeira correção, e ao contrário de um hook, uma cópia velha não reprova nada.

### Agente que roda os testes e diagnostica a falha

**Rejeitada porque** compete com os sensores do `Stop` pelo mesmo alvo. O sensor roda fora
do raciocínio do modelo e devolve a cauda da saída ao agente, então um subagente para isso
seria uma segunda via, menos determinística, para o mesmo fim.

### Resolver o mapa com `adr.ler_mapa` em vez de o agente ler a tabela

**Adiada, não rejeitada.** Seria a mesma leitura do hook, sem divergência possível. Hoje o
agente não tem como importar o pacote num consumidor: o `src/` do plugin não está no
`sys.path` dele, a substituição de `${CLAUDE_PLUGIN_ROOT}` no corpo de um agente não foi
medida, e o canal do CI (`uv add --dev`) não é obrigatório. Ver "Quando revisitar".

### Instrução no `CLAUDE.md` ("confira os ADRs antes do PR")

**Rejeitada porque** é o tipo de instrução cuja aderência decai por passo
(`arXiv:2605.10039`), a mesma razão de o `reafirmar` existir.

## Consequências

**Boas:** a aderência a ADR ganha um conferente com contexto limpo, que lê a régua inteira
sem gastar o contexto da thread principal. O relatório aponta também os buracos do mapa, que
são ponteiros faltando e que o auditor não vê porque não lê o código.

**Ruins, e aceitas:**

- "Só lê" vale para Read, Grep e Glob por mecanismo, e para o Bash só pelo prompt. Agente
  de plugin não pode carregar hook nem `permissionMode` que travem um `git commit`. As
  guardas do `guardar.py` continuam valendo dentro do subagente, mas só para o que já
  bloqueiam.
- A `description` custa ~116 tok em toda sessão de todo projeto com o plugin habilitado,
  inclusive nos que nunca adotaram o harness. O gate não alcança o registro do agente.
- O agente casa o mapa lendo a tabela, não com `ler_mapa`. Em tabela malformada, ele pode
  divergir do hook.
- O julgamento não é determinístico: duas execuções no mesmo diff podem diferir em
  "Dúvidas".

## Quando revisitar

- Se agente de plugin passar a aceitar `hooks` ou `permissionMode`: travar o Bash por
  mecanismo e tirar a restrição do prompt.
- Na primeira divergência real entre o mapa que o revisor usou ("Régua usada") e o que
  `adr.ler_mapa` devolve: expor `ler_mapa` como comando e fazer o agente chamá-lo.
- Se um relatório trouxer uma contradição que não era: endurecer o passo 3 do prompt com o
  caso, e só depois pensar em levar o revisor para um hook.

## Plano de Implementação

- **Arquivos a tocar:** `agents/revisor-adr.md` (novo), `tests/test_agentes.py` (novo),
  `docs/adr/README.md` (índice), `CLAUDE.md` (mapa: `agents/`), `README.md` (componentes),
  `FUNDAMENTOS.md` (mapa do código).
- **Padrões a seguir:** o gate de `config.carregar()` (inerte sem `harness.json`) e a regra de
  casamento do mapa de `adr.adrs_do_caminho`/ADR-0009, descrita no prompt e não
  reimplementada em código.
- **Testes obrigatórios:** `tests/test_agentes.py` verde, junto com o resto da suíte. Antes
  de promover para `implemented`, rodar o revisor num diff com uma contradição plantada e
  conferir que ele a acha sem acusar a mudança neutra.
- **Não mexer em:** `hooks/hooks.json` e `src/`. O revisor não é hook e não muda o
  mecanismo.
