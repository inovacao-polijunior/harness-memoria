---
status: proposed
data: 2026-11-12
---

# ADR-0012 — Consultar os becos e ADRs que o bloco corta com um agente do plugin, apontado pelo `SessionStart`

## Regra

- O plugin entrega o consultor em `agents/consultor-memoria.md`
  (`harness-memoria:consultor-memoria`). Ele só lê e responde pelo que o diário e os ADRs
  registram, com `arquivo:linha` em cada achado.
- Quando o digest de becos sai cortado, o bloco do `SessionStart` manda perguntar ao
  consultor. O bloco do `SubagentStart` continua mandando procurar à mão.
- O ponteiro só entra quando `agents/consultor-memoria.md` está no mesmo plugin que roda o
  hook (`consultor_disponivel`).

## Contexto

O bloco do `SessionStart` tem teto de 10.000 ch (ADR-0004), e nos projetos grandes a maior
parte da memória fica fora dele. Medido em 2026-11-11, rodando o hook em cada projeto:

| Projeto      | Becos no bloco | ADRs no índice injetado |
| ------------ | -------------- | ----------------------- |
| validani     | 20 de 340      | 54 de 103               |
| rede-inspira | 14 de 391      | 40 de 108               |
| plum-cali    | 14 de 98       | 24 de 29                |

O bloco avisa onde está o resto ("Os outros 320 estão nas seções…"). O agente às vezes
procura: nas 20 conversas guardadas nesta máquina desses três projetos, 11 leem o diário
arquivado ou buscam "Tentativas descartadas" ao menos uma vez. A contagem pega qualquer
leitura numa mensagem que cita esses termos, não só a busca por um beco. Quando procura, a
thread principal lê arquivos de mês inteiro (até 400 linhas cada, 22 arquivos no ValidaNI).

Um fato da plataforma mudou o desenho no meio do caminho. Nesta versão do Claude Code as
ferramentas Grep e Glob não existem: a busca é pelo Bash. Um agente com
`tools: Read, Grep, Glob` fica só com o Read.

## Fatores de decisão

- A resposta tem de citar a fonte. Um "já tentamos" sem `arquivo:linha` não dá a quem
  pergunta como conferir, e um "não há registro" sem dizer onde procurou não diz nada.
- Custo sempre ligado: a `description` mede 292 ch (~127 tok, pela razão `chars / 2,3` do
  README), somando 559 ch (~243 tok) com a do revisor.
- O ponteiro do bloco não pode apontar para um agente que a sessão não tem.

## Decisão

1. **Um agente no plugin**, `agents/consultor-memoria.md`, com
   `tools: Read, Grep, Glob, Bash` e `model: haiku`. O Bash entra porque nesta versão da
   plataforma é ele que busca, e o prompt o limita a `grep`, `rg`, `find`, `ls`, `cat`,
   `head`, `tail`, `sed -n` e `wc`.
2. **Gate no passo 0**, igual ao do revisor (ADR-0011).
3. **Fontes, nesta ordem:** os itens de `### Tentativas descartadas` de `diario.pasta` e de
   `arquivo/`; os ADRs vivos e mortos, seguindo `substituido-por:` até o vivo; o resto das
   entradas do diário só se os dois primeiros não responderem. Código fica de fora.
4. **A resposta** traz um veredito ("já tentado", "decidido em ADR", "em parte", "não há
   registro"), até 5 achados com `arquivo:linha`, os relacionados e "Onde procurei" (os
   termos e as pastas).
5. **O `SessionStart` aponta para ele.** Quando o digest sai cortado, a frase "Os outros N
   estão em…" termina mandando perguntar a `harness-memoria:consultor-memoria`, em vez de
   "procure por esse título". O nome vem de `consultor_disponivel()`, que confere
   `agents/consultor-memoria.md` ao lado do hook e lê o nome do plugin no manifesto. Sem o
   arquivo, a frase antiga volta. O bloco reduzido do `SubagentStart` mantém a frase
   antiga, porque subagente não chama subagente.
6. **Testes:** `tests/test_agentes.py` passa a conferir todo agente (só ferramentas de
   leitura; o parágrafo "Você só lê" quando há Bash; o gate) e que o agente que o hook nomeia
   existe. `tests/test_session_start.py` confere o ponteiro no bloco completo, a ausência
   dele no reduzido, a volta da frase antiga sem o agente e nenhum ponteiro quando o digest
   cabe inteiro.

### Medição do modelo

Sete perguntas com resposta conhecida no ValidaNI: cinco becos de meses e arquivos
diferentes, um ADR `superseded` (0021, substituído pelo 0042) e um caso negativo (cache
Redis, que não aparece em diário nem ADR). Cada pergunta rodou num subagente separado, com
o Haiku seguindo o corpo do agente. Foi uma simulação: não era o agente carregado pelo
plugin.

| Rodada                           | Acertos | Tokens por pergunta | Chamadas de ferramenta |
| -------------------------------- | ------- | ------------------- | ---------------------- |
| 1: `tools: Read, Grep, Glob`     | 2 de 7  | 107 mil a 356 mil   | 7 a 33                 |
| 2: com o Bash para buscar        | 7 de 7  | 89 mil a 101 mil    | 5 a 10                 |

"Tokens" é o total que o Claude Code relata para o subagente. Na rodada 1, sem busca, o
agente leu arquivos inteiros e errou 5 de 7, uma delas com "não há registro" para um beco
que existe (`arquivo/2026-10.md:176`). Na rodada 2, as cinco perguntas de beco acharam o
item esperado, a do ADR morto apontou o 0042 e a negativa respondeu "não há registro" sem
inventar achado. O `inherit` não foi medido, porque o Haiku acertou as sete.

A frase "não vá ao código" entrou no prompt depois das rodadas: em 2 das 7 respostas o
agente procurou em `services/api/`. Essa mudança não foi medida de novo.

O ponteiro custa 94 ch a mais na prosa do digest (357 contra 263). Pelo ADR-0004, quem
cede é o índice: nos três projetos acima ele perde uma linha (54→53, 40→39, 24→23), e o
número de becos no bloco não muda.

## Alternativas consideradas

### `tools: Read, Grep, Glob`, sem Bash

**Rejeitada porque** foi a primeira versão, e medida ela acerta 2 de 7. Nesta versão do
Claude Code as ferramentas Grep e Glob não existem, então o agente fica só com o Read, lê
mês a mês e para antes de chegar ao arquivo certo. "Só lê por mecanismo" valia pouco num
agente que não acha nada.

### Deixar o bloco como está e confiar no "procure por esse título"

**Rejeitada porque** a busca, quando acontece, roda no contexto da thread principal, e os
arquivos do diário têm até 400 linhas. Em 9 das 20 conversas medidas ela não aconteceu
nenhuma vez.

### Subir o teto do digest de becos

**Rejeitada porque** o teto de 10.000 ch é da plataforma (ADR-0004): o que o digest
ganhasse sairia do índice de ADR ou da entrada do diário. E nem dobrando o digest se chega
perto de 340 becos.

### Uma skill `/ja-tentamos` em vez de agente

**Rejeitada porque** a skill roda na thread principal e a busca encheria o mesmo contexto
que o consultor existe para poupar.

### Pôr o ponteiro também no bloco do subagente

**Rejeitada porque** subagente não chama subagente. O ponteiro no bloco reduzido mandaria
para uma ferramenta que quem lê não tem, e tiraria dele a instrução que ele pode seguir.

### Escrever o nome do agente fixo no hook, sem conferir o arquivo

**Rejeitada porque** uma cópia do `src/` fora do plugin (a da suíte que copia o pacote para
um diretório temporário, por exemplo) apontaria para um agente que não existe. Ponteiro
velho é pior que ponteiro nenhum.

## Consequências

**Boas:** quem pergunta "já tentamos?" recebe a resposta com `arquivo:linha` sem gastar o
próprio contexto, e o resto que o bloco anuncia passa a ter um caminho barato até ele. Nas 7
perguntas medidas, o achado esperado veio em 5 a 10 chamadas.

**Ruins, e aceitas:**

- Para o Bash, "só lê" vale só pelo prompt, como no revisor (ADR-0011).
- A `description` custa ~127 tok em toda sessão de todo projeto com o plugin habilitado,
  inclusive nos que não adotaram o harness.
- Cada consulta custa ~90 a 100 mil tokens no Haiku, contados no subagente.
- O ponteiro tira uma linha do índice de ADR quando o bloco está no teto.
- A medição foi uma simulação com 7 perguntas de um só projeto, e o prompt mudou uma frase
  depois dela.

## Quando revisitar

- Se Grep e Glob voltarem a existir na plataforma: tirar o Bash da lista `tools`.
- Se um relatório do consultor citar um beco que não diz o que ele afirma, ou responder
  "não há registro" para algo registrado: medir o `inherit` nas mesmas 7 perguntas e no caso
  que falhou.
- Se o índice de ADR cortado virar a pergunta mais comum: levar o ponteiro também para a
  linha do "índice PARCIAL".

## Plano de Implementação

- **Arquivos a tocar:** `agents/consultor-memoria.md` (novo),
  `src/harness_memoria/hooks/session_start.py` (`consultor_disponivel`, `_moldar_becos`),
  `tests/test_agentes.py`, `tests/test_session_start.py`, `docs/adr/README.md`, `CLAUDE.md`
  (mapa), `README.md` (componentes), `FUNDAMENTOS.md` (mapa do código).
- **Padrões a seguir:** o gate do ADR-0011; a prosa do digest medida por
  `_prosa_de_becos`, e não por constante, para o orçamento do ADR-0004 continuar valendo.
- **Testes obrigatórios:** a suíte verde. Antes de promover para `implemented`, chamar o
  agente carregado pelo plugin com 2 das 7 perguntas e conferir o mesmo achado.
- **Não mexer em:** `TETO_PLATAFORMA_CHARS`, `TETO_SUBAGENTE_CHARS` e a ordem de corte do
  ADR-0004.
