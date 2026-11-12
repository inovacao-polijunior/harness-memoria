---
status: proposed
data: 2026-11-12
---

# ADR-0013 — Avisar, no envio do pedido, o beco que ele parece tocar, e mandar chamar o consultor

## Regra

- O `UserPromptSubmit` busca por texto nos becos; se o 1º passa da regra (≥ 12 e ≥ 1,3× o
  2º que não é quase cópia dele), injeta o beco e manda chamar o consultor (ADR-0012).
- Um aviso por beco por sessão. Nunca bloqueia; silêncio sem harness, em `/`, em pedido curto
  e em subagente.
- Regra e vocabulário são constantes no código, não chave do `harness.json`.

## Contexto

O consultor da memória (ADR-0012) funciona quando é chamado: com o agente carregado pelo
plugin, acertou as 6 perguntas de teste. O que não funcionou foi o Claude chamá-lo por conta
própria. Em 5 sessões novas do ValidaNI, com pedidos cuja lição estava num beco e sem citar o
consultor, ele foi chamado em 0, conferido no transcript de cada uma:

| Pedido                                | Versão do gatilho        | Consultor chamado |
| ------------------------------------- | ------------------------ | ----------------- |
| Modal de exclusão dentro da sidebar   | frase de sugestão        | não               |
| Subagentes em worktree, por épico     | frase de sugestão        | não               |
| Citar o ADR-0056 na tela de Progresso | frase de sugestão        | não               |
| Citar o ADR-0056 na tela de Progresso | `description` proativa   | não               |
| Modal de exclusão dentro da sidebar   | `description` proativa   | não               |

Nas 5, a sessão procurou no código e nos ADRs. Em 4 delas a resposta saiu certa, porque a
lição também estava num comentário de código, num ADR ou no próprio digest. Na terceira, o
beco específico (`arquivo/2026-08j.md:53`, "ADR é endereço de código, não de produto") não
apareceu.

O gatilho das duas versões era uma frase: no bloco do `SessionStart`, que mede perto de
10.000 ch e entra uma vez no começo da sessão, e na `description` do agente. As duas ficam
longe do momento em que o Claude decide o que fazer com o pedido.

O pedido do humano é que o Claude decida chamar o consultor sem que ele precise pedir.

Dois fatos da plataforma, conferidos no executável instalado (2.1.322) em 2026-11-12: a
entrada do `UserPromptSubmit` traz o texto do pedido (`prompt`) junto dos campos da sessão,
e o `hookSpecificOutput` desse evento aceita `additionalContext`.

## Fatores de decisão

- O aviso tem de chegar colado ao pedido, no momento da decisão.
- Disparar pouco. Aviso a todo pedido vira ruído de fundo, e cada chamada do consultor custa
  de 31 mil a 56 mil tokens no Haiku e de 26 a 42 s (ADR-0012).
- O hook roda síncrono no caminho de todo pedido, então a busca tem de ser barata.
- Invioláveis: só biblioteca padrão em `src/`, `main()` captura tudo, inerte sem
  `.claude/harness.json`, nada de política de projeto em `src/`.
- Chave nova no `harness.json` invalida a config de quem ainda roda a versão anterior do
  plugin (beco de 2026-10-09).

## Decisão

1. **Hook novo**, `src/harness_memoria/hooks/avisar_becos.py`, registrado em
   `hooks/hooks.json` para `UserPromptSubmit`, síncrono, com timeout de 5 s e o mesmo
   bootstrap e pré-gate barato dos outros hooks.
2. **Silêncio** quando não há `.claude/harness.json`, dentro do `claude -p` que narra o
   diário, quando o pedido começa com `/`, quando tem menos de 3 palavras úteis e quando o
   evento traz `agent_id`.
3. **Um parser só.** `diario.py` ganha uma função que devolve cada beco com arquivo, linha,
   data e texto, e `becos_sem_saida` passa a usá-la.
4. **A busca**, em `src/harness_memoria/busca.py`: BM25 (k1 = 1,2, b = 0,75) sobre o texto
   de cada beco, com acentos removidos, palavras vazias genéricas de pt e en, e cada palavra
   cortada nas 4 primeiras letras. Dispara quando o 1º colocado tem pontuação ≥ 12
   (`PONTUACAO_MINIMA`) e ≥ 1,3× a do 2º (`RAZAO_MINIMA`). O 2º é o melhor colocado que
   NÃO é quase cópia do 1º: dois becos com pelo menos 40% dos termos em comum (Jaccard,
   `LIMIAR_QUASE_COPIA`) são a mesma lição registrada outra vez. Entre o 1º e as cópias
   dele, o aviso cita o registro mais recente.
5. **O aviso** traz só o 1º colocado: data, `arquivo:linha` e o item cortado por
   `_resumir_beco`, a mesma função do digest, que preserva o que vem depois de
   `**Não repetir:**`. Depois do item vem: "Busca textual, pode errar. Antes de propor ou
   implementar, chame o subagente `harness-memoria:consultor-memoria` com o pedido: ele
   confere se o beco se aplica e procura nos ADRs e no resto do diário." Sem o agente no
   plugin, a frase vira "confira o item antes de propor". `consultor_disponivel` sai de
   `session_start.py` para `hooks/_comum.py`, usada pelos dois hooks.
6. **Uma vez por sessão por beco**, num arquivo de estado `becos_avisados_{sessao}.txt` em
   `pasta_estado`, com a mesma validade dos `adrs_vistos`. O `SessionStart` de compactação
   apaga a lista, como já faz com os ADRs.
7. **Os becos que o digest do `SessionStart` já mostra não são excluídos.** O ganho é o beco
   aparecer colado ao pedido. O caso do worktree, que estava no digest, também dispararia.
8. **Nada muda no ADR-0012.** A `description` proativa e a frase do bloco continuam e dizem
   o mesmo que o aviso.

### Medição que sustenta a regra

Feita com um protótipo descartável (BM25 em Python puro), antes deste ADR, sobre os 340 becos
do ValidaNI e sobre pedidos reais guardados nos transcripts desta máquina.

Os 6 casos conhecidos, com o radical de 4 letras:

| Caso                | Posição do beco certo | Pontuação | 1º ÷ 2º |
| ------------------- | --------------------- | --------- | ------- |
| Popover em painel   | 1º                    | 24,5      | 1,73    |
| Modal na sidebar    | 1º                    | 14,7      | 1,64    |
| `var(--border)`     | 1º                    | 18,0      | 1,74    |
| Worktree por épico  | 1º                    | 28,6      | 2,67    |
| Ganho por estágio   | 1º                    | 15,3      | 2,27    |
| ADR na tela         | 1º                    | 17,9      | 1,35    |
| Redis (negativo)    | —                     | 5,7       | 1,02    |

Sem radical, e com 5 ou 6 letras, o beco certo também ficou em 1º nos 6 casos. O radical de
4 letras foi escolhido pela margem no caso mais difícil, o do ADR na tela: 1,35× o 2º,
contra 1,21× sem radical e 1,06× a 1,07× com 5 ou 6 letras.

As regras contra 121 pedidos reais distintos (ValidaNI 14, rede-inspira 11, plum-cali 96),
cada um contra os becos do próprio projeto:

| Regra                         | Casos conhecidos | Dispara em      |
| ----------------------------- | ---------------- | --------------- |
| ≥ 12 e ≥ 1,5×                 | 5 de 6           | 5 de 121 (4%)   |
| **≥ 12 e ≥ 1,3×** (escolhida) | **6 de 6**       | **9 de 121 (7%)** |
| ≥ 10 e ≥ 1,3×                 | 6 de 6           | 11 de 121       |
| ≥ 14 e ≥ 1,5×                 | 5 de 6           | 1 de 121        |

Na leitura de quem mediu, de 5 a 6 dos 9 disparos da regra escolhida eram pertinentes. Um
exemplo pertinente: "tem como seguirmos sem fazer a verificação da empresa?" trouxe o beco
sobre onde fica o "Iniciar verificação" da Meta. Um exemplo de ruído: "quero criar uma nova
skin no modelo do rei da RN" trouxe um beco sobre settings de blueprint.

Ler os 22 arquivos do diário, montar o índice e buscar levou 10 ms por pedido (média de 5).

Limites: 121 pedidos é pouco, "pertinente" foi julgado por uma pessoa, e o protótipo não é o
código final. A regra é para ser revista com os disparos reais (ver "Quando revisitar").

### Becos repetidos

A revisão final da implementação achou um defeito da regra: quando a mesma lição foi
registrada duas vezes, o 2º colocado é a cópia do 1º, a razão fica entre 1,02 e 1,22 e a
lição que mais se repetiu nunca dispara. Daí a exceção das quase cópias na decisão 4.

O limiar de 40% foi medido em 2026-11-12, com o código final, nos diários de três
consumidores:

- No ValidaNI, os 6 pares acima de 50% são cópias (de 0,58 a 0,91: heredoc com crase,
  here-string do PowerShell, o mesmo `select` de leitor, a entrega dada por fechada).
- Dos 11 pares entre 40% e 50% nos três diários, 10 são a mesma lição em outra redação. O
  que sobra é um par do plum-cali sobre o que a sessão consegue fazer sozinha.
- Becos diferentes sobre o mesmo assunto ficam bem abaixo: 17% a 22% nos casos do modal.
- Com 40%, os 6 casos conhecidos dão as mesmas posições e razões da tabela acima, o pedido
  do Redis segue em silêncio e os pedidos reais seguem disparando 9 vezes (agora em 120,
  porque um pedido antigo saiu do histórico).

Três pedidos que tocam lições repetidas do ValidaNI: o do heredoc com crase passou a
disparar. Os do here-string do PowerShell e do `\n` dentro de heredoc seguem em silêncio,
porque essas famílias têm de 4 a 6 variantes, e o 2º colocado é uma variante com 24% a 33%
de termos em comum, abaixo do limiar.

## Alternativas consideradas

### Aviso a todo pedido que pareça pedir mudança, sem busca

**Rejeitada porque** dispara muito mais, e cada disparo que vira chamada custa de 26 a 42 s.
"Parecer pedir mudança" é difícil de detectar sem errar, e uma frase repetida a todo pedido
tende a ser ignorada, que é o defeito que este ADR existe para resolver.

### Travar a primeira escrita da sessão até o consultor ser chamado

**Rejeitada porque** não cobre proposta sem escrita, que foi o caso dos 5 testes, e trava
edição trivial. Bloquear por suspeita é o falso positivo caro que o harness evita.

### Regra estrita (≥ 1,5× o 2º)

**Rejeitada por ora porque** perde o caso do ADR na tela, o único que as 5 sessões deixaram
passar. O disparo falso da regra escolhida custa uma chamada do consultor, que responde "não
se aplica", e não uma resposta errada.

### Injetar o beco sem mandar chamar o consultor

**Rejeitada porque** o humano quer que o Claude chame o consultor, e a busca textual sozinha
não confere se o beco se aplica nem chega aos ADRs.

### Rodar um modelo dentro do hook (`claude -p` com Haiku a cada pedido)

**Rejeitada porque** a consulta mede de 26 a 42 s e ficaria no caminho de todo pedido.

### Busca por embeddings

**Rejeitada porque** exige biblioteca de terceiro em `src/`, o que é inviolável.

### Chave no `harness.json` para ligar, desligar ou ajustar a regra

**Rejeitada porque** chave desconhecida invalida a config da versão instalada anterior, que
desliga o harness inteiro naquele projeto (beco de 2026-10-09).

### Excluir os becos que o digest já mostra

**Rejeitada porque** o ganho é a proximidade com o pedido. O beco do worktree estava no
digest, e repeti-lo colado ao pedido certo custa pouco, uma vez por sessão.

## Consequências

**Boas:** o aviso chega no momento da decisão, é determinístico e custa ~10 ms de busca.
Mesmo quando o Claude não chama o consultor, o beco candidato já está no contexto.

**Ruins, e aceitas:**

- A busca é por palavra: um beco escrito com vocabulário diferente do pedido não dispara.
- Uma lição registrada muitas vezes, com redações distantes entre si (o here-string do
  PowerShell tem 6 variantes no ValidaNI), pode seguir em silêncio: as variantes abaixo de
  40% contam como 2º colocado. Baixar o limiar juntaria lições diferentes.
- Diário pequeno quase nunca dispara: com 4 a 9 becos, o IDF não leva nenhum à pontuação
  mínima. Esses diários cabem inteiros no digest do `SessionStart`.
- Disparo falso custa uma chamada do consultor. Na medição, de 3 a 4 dos 9 disparos eram
  ruído.
- Mais um interpretador Python por pedido. Medido na implementação, tempo de parede do hook
  por subprocess, n=20 cada: 39 ms (p25) num pedido que dispara e 36 ms num que não
  dispara, no diário do ValidaNI (340 becos), e 9 ms num projeto sem harness, que sai no
  pré-gate. O aviso mede de 541 a 555 ch nos três pedidos de teste.
- O radical de 4 letras e a lista de palavras vazias são crus e só cobrem pt e en.
- Nada garante que o Claude chame o consultor: o aviso continua sendo instrução, só que no
  momento certo.

## Quando revisitar

- Se, nos 3 pedidos de teste em sessões novas do ValidaNI, o consultor for chamado em menos
  de 2: o aviso colado ao pedido também não basta, e a pergunta volta a ser se o acionamento
  automático é possível.
- Se o disparo real passar de ~10% dos pedidos, ou se o consultor responder "não se aplica"
  na maioria das chamadas: apertar a regra para 1,5×.
- Se um beco pertinente não disparar: registrar o pedido e medir a regra contra ele. Se for
  de uma família de variantes, medir juntar a família inteira (fecho transitivo das quase
  cópias) em vez de baixar o limiar.
- Se a plataforma passar a deixar um hook chamar um subagente: trocar o aviso pela chamada.

## Plano de Implementação

- **Arquivos a tocar:** `src/harness_memoria/busca.py` (novo),
  `src/harness_memoria/hooks/avisar_becos.py` (novo), `src/harness_memoria/diario.py`
  (parser com origem; `becos_sem_saida` passa a usá-lo), `src/harness_memoria/hooks/_comum.py`
  (`consultor_disponivel`, estado de becos avisados, `_ESTADO_QUE_EXPIRA`),
  `src/harness_memoria/hooks/session_start.py` (usa o `consultor_disponivel` de `_comum`; a
  compactação esquece os becos avisados), `hooks/hooks.json`, `tests/test_busca.py` e
  `tests/test_avisar_becos.py` (novos), `CLAUDE.md` (mapa, quando os caminhos existirem),
  `docs/adr/README.md`, `README.md` e `FUNDAMENTOS.md`.
- **Padrões a seguir:** o bootstrap e o pré-gate de `session_start.py`; o estado por sessão
  de `adrs_vistos`; o corte de item de `_resumir_beco`; constantes ao lado da medição que as
  produziu.
- **Testes obrigatórios:** a suíte verde e o autoteste do hook. Os casos de ranking usam um
  corpus de fixture, porque o corpus do ValidaNI é de outro projeto. Antes de promover para
  `implemented`, os 3 pedidos de teste em sessões novas do ValidaNI, com o consultor chamado
  em pelo menos 2.
- **Não mexer em:** `TETO_PLATAFORMA_CHARS`, `TETO_SUBAGENTE_CHARS`, a montagem do bloco do
  `SessionStart` (além de esquecer os becos avisados na compactação) e as decisões do
  ADR-0012.
