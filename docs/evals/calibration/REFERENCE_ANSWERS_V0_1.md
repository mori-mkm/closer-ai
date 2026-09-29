# Reference Answers v0.1

> **Abra só depois de submeter todas as anotações** (modo A) **ou depois da adjudicação** (modo B).

**REFERENCE ≠ GOLD.** Estas são respostas de calibração derivadas da
[guideline v0.1](../OBJECTION_ANNOTATION_GUIDELINE_V0_1.md), escritas pelo mesmo autor dos casos. Não
são gold adjudicado, não medem ninguém e podem estar erradas — quando a sua leitura divergir e você
tiver uma regra da guideline a favor, registre: é exatamente o que a calibração procura.

- Categorias (`PRICE_BUDGET`, …, `OTHER`) são **labels de anotação/eval** (CIT-O1), não valores de
  produção. Nada aqui é `ObjectionEpisode` de produção; `ep-a`, `ep-b` são ids locais.
- UNKNOWN e AMBIGUOUS são **status**, nunca categoria nem valor de `resolution_status`.
- Rótulos de resposta (ACCEPT, REJECT, MIXED, NEUTRAL, OFF_CATEGORY, UNKNOWN) são os do contrato §9.1;
  CLARIFICATION é a nota GL-3.

---

## CAL01 — tier `happy_path` (boundary)

| | ep-a | ep-b |
|---|---|---|
| Detection | PRESENT | PRESENT |
| Anchor / objection | `S01` / [`S01`] | `S07` / [`S07`] |
| Context | [`S02`, `S03`] | [`S08`, `S09`] |
| Category | `TIMING_PRIORITY` | `TIMING_PRIORITY` |
| Handling | PRESENT (`S02`) | PRESENT (`S08`) |
| Reaction | `S03` ACCEPT | `S09` ACCEPT |
| Resolution | `resolved` | `resolved` |
| Uncertainty | nenhuma | nenhuma |

**Why:** `S01` dá um motivo de prioridade/momento dito (até julho só entra o que for da migração do
financeiro; "o resto fica na fila") contra começar. `S04` (treinamento) é assunto substantivo fora do fio → closure. `S07` volta à
mesma categoria **depois** da closure → novo episódio (recorrência, não reabertura).

**Common wrong:** um episódio só (ignorar a closure em `S04`); `IMPLEMENTATION_INTEGRATION` em `S01`
(o que é resistido é o momento/prioridade, não o esforço de implantar); `ep-a` virar `unresolved` por
causa de `S07`.

**Acceptable alternatives:** nenhuma de categoria. **Rules:** Timing (motivo dito); Repeated objections;
Episode boundaries (closure).

---

## CAL02 — tier `happy_path` (resolution)

| | ep-a |
|---|---|
| Detection | PRESENT |
| Anchor / objection | `S03` / [`S03`] |
| Context | [`S04`, `S05`, `S06`] |
| Category | `PRICE_BUDGET` |
| Handling | PRESENT (`S04`, `S06`) |
| Reaction | `S05` MIXED; `S07` NEUTRAL |
| Resolution | `partially_resolved` |
| Uncertainty | nenhuma |

**Why:** na **mesma resposta** (`S05`) um aspecto é aceito (licença) e **outro aspecto da mesma
categoria** (usuários extras) continua pendente → MIXED (contrato §9.1). `S07` é interjeição.
**Negatives:** `S01` pergunta neutra de preço → NO_OBJECTION.

**Common wrong:** dois episódios (licença × usuários extras — mesma categoria, mesmo fio);
`resolved` porque o closer vai retornar; `unresolved` ignorando o aspecto aceito; âncora em `S01`.

**Acceptable alternatives:** `S06` fora do contexto (divergência menor). **Rules:** partially_resolved;
Topic ≠ objection.

---

## CAL03 — tier `adversarial`

**Expected:** anotável; call revisada inteira; **nenhum episódio** → call-level ABSENT; demais perguntas N/A.

| Segmento | Por que NO_OBJECTION |
|---|---|
| `S00` | fala do closer |
| `S01` | pergunta de preço |
| `S03` | objeção passada, superada ("hoje o orçamento comporta") |
| `S04` | hipótese + pergunta |
| `S06` | preocupação sem função impeditiva (não liga a não avançar) |
| `S08` | menção a outra proposta (informação competitiva) |
| `S09` | pergunta técnica de integração |
| `S11` | menção a stakeholder + etapa normal de revisão jurídica |
| `S13` | brush-off genérico, sem barreira dita |

**Common wrong:** episódios por tópico/palavra ("valor", "orçamento", "complicaria", "outra
proposta", "sócia", "advogado"); `TIMING_PRIORITY` em `S13`; AUTHORITY em `S11`.

**Acceptable alternatives:** `S13` como AMBIGUOUS na detecção (objeção sem categoria × adiamento
neutro), com as leituras em nota — nesse caso a call fica sem episódios e com um trecho AMBIGUOUS;
discuta se isso deveria impedir o ABSENT call-level. **Nunca** `TIMING_PRIORITY`.
**Rules:** Sales resistance vs objection; Topic ≠ objection; NO_OBJECTION; Brush-off; Negative labels.

---

## CAL04 — tier `ambiguous` (GL-3)

| | ep-a |
|---|---|
| Detection | PRESENT |
| Anchor / objection | `S01` / [`S01`] |
| Context | [`S02`, `S03`, `S04`] (`S06` opcional) |
| Category | `AUTHORITY_INTERNAL_BUY_IN` |
| Handling | PRESENT (`S02`, `S04`) |
| Reaction | `S03` **AMBIGUOUS** {CLARIFICATION (pede a opinião do closer), REJECT (dúvida de que a aprovação saia)}; `S05`, `S07` NEUTRAL |
| Resolution | `unknown` |
| Uncertainty | reação AMBIGUOUS |

**Why:** `S01` diz restrição de autoridade como bloqueio ("não posso comprometer a empresa sem a
assinatura deles"). `S03` é pergunta sem posição clara; as duas leituras seguem plausíveis → reação AMBIGUOUS e
`resolution_status = unknown` (GL-3).

**Common wrong:** `PRICE_BUDGET` (os valores aparecem, mas o que é resistido é quem aprova);
`resolved` por "Tá bom"/"Ok"; **resolution = AMBIGUOUS** (valor inválido).

**Acceptable alternatives:** `S03` como CLARIFICATION → `unknown` (mesmo resultado). Ler `S03`
claramente como REJECT → `unresolved` é **discutível**: registre qual trecho decidiu e se o diagnóstico
de GL-3 bastou. **Rules:** Authority; GL-3 (caso ambíguo); Resolution.

---

## CAL05 — tier `happy_path` (boundary)

| | ep-a |
|---|---|
| Detection | PRESENT |
| Anchor / objection | `S01` / [`S01`] |
| Context | [`S02`, `S03`] |
| Category | `NEED_VALUE_FIT` (sub-conceito lido: VALUE) |
| Handling | PRESENT (`S02`) |
| Reaction | `S03` REJECT |
| Resolution | `unresolved` |
| Uncertainty | nenhuma |

**Why:** a barreira dita é o **valor** frente ao preço, reforçada pelo modelo interno que "cobre o que os
clientes pedem" e por "não compensa trocar". `S04` muda de assunto → closure. NEED_VALUE_FIT é abstração provisória
do AI Closer (fusão).

**Common wrong:** `PRICE_BUDGET` pela palavra "preço"; `COMPETITION_EXISTING_SOLUTION` (a alternativa é
processo interno, não fornecedor — CIT-O6).

**Acceptable alternatives:** AMBIGUOUS {`NEED_VALUE_FIT`, `PRICE_BUDGET`} é discutível se o anotador
ler só a primeira frase de `S01`; a segunda frase e `S03` pesam para valor. **Rules:** NEED_VALUE_FIT; Topic ≠ objection.

---

## CAL06 — tier `adversarial` (multi-objection)

| | ep-a | ep-b |
|---|---|---|
| Detection | PRESENT | PRESENT |
| Anchor / objection | `S01` / [`S01`] | `S01` / [`S01`] |
| Context | [`S04`, `S05`, `S06`] | [`S02`, `S03`] |
| Category | `PRICE_BUDGET` | `IMPLEMENTATION_INTEGRATION` |
| Handling | PRESENT (`S04`, `S06`) | PRESENT (`S02`) |
| Reaction | `S05` REJECT (GL-3: pergunta que reafirma a barreira); `S07` NEUTRAL | `S03` ACCEPT |
| Resolution | `unresolved` | `resolved` |
| Uncertainty | nenhuma | nenhuma |

**Why:** duas barreiras de categorias diferentes na mesma fala → **dois episódios, mesma âncora**
(CIT-M2). `S05` é pergunta, mas repete o valor e questiona de onde viria o dinheiro → reafirma a barreira →
REJECT (pergunta retórica, não pedido de informação). Alternar entre os fios não fecha nenhum; `S08` fecha.

**Common wrong:** um episódio `partially_resolved` (preço pendente + implantação resolvida são
**categorias diferentes**); `S05` como CLARIFICATION → `unknown`; novo episódio de preço em `S05`.

**Acceptable alternatives:** nenhuma de estrutura. **Rules:** Episode boundaries (atômico por
categoria); GL-3 (reafirma); partially_resolved (restrição).

---

## CAL07 — tier `ambiguous` / `missing_context`

| Trecho | Decisão |
|---|---|
| `S01` | AMBIGUOUS na detecção {comentário, preocupação, `PRICE_BUDGET`}; sem episódio. `S02` muda de assunto e nada retoma |
| `S05` | AMBIGUOUS na detecção {`TIMING_PRIORITY`, adiamento sem barreira (brush-off)}; sem motivo dito → **não** é `TIMING_PRIORITY` |
| `S07` | episódio PRESENT (barreira dita: "fica complicado pra gente fechar"), categoria **UNKNOWN** (o objeto está no trecho inaudível), objection [`S07`], contexto vazio (`S08` opcional); resolução `unknown` (nenhuma resposta; a call termina) |

**Why:** `S01`/`S05` têm informação e mais de uma leitura → **AMBIGUOUS**. `S07` não tem a informação
que decidiria → **UNKNOWN**.

**Common wrong:** `PRICE_BUDGET` em `S01` pelo valor; `TIMING_PRIORITY` em `S05`; categoria definida em
`S07`; `unresolved` em `S07`; trocar UNKNOWN por AMBIGUOUS (ou vice-versa).

**Acceptable alternatives:** `S07` como trecho UNKNOWN na detecção (sem episódio) — a guideline trata
o caso como episódio com categoria UNKNOWN, mas o teste C ("barreira identificável") pode ler diferente;
registre como possível lacuna da guideline. **Rules:** UNKNOWN vs AMBIGUOUS; Hesitation/Brush-off.

---

## CAL08 — tier `adversarial`

| | ep-a |
|---|---|
| Detection | PRESENT |
| Anchor / objection | `S02` / [`S02`] |
| Context | [`S03`, `S04`, `S05`, `S06`] |
| Category | `COMPETITION_EXISTING_SOLUTION` |
| Handling | PRESENT (`S03`, `S05`) |
| Reaction | `S04` REJECT; `S06` sem posição sobre a barreira (aceitar receber material não pressupõe a objeção superada) |
| Resolution | `unresolved` |
| Uncertainty | nenhuma |

**Why:** o fornecedor atual é dito como razão para não trocar. **Negatives:** `S00` pergunta
comparativa → NO_OBJECTION.

**Common wrong:** `resolved` por "Pode mandar"; `NEED_VALUE_FIT` por "estamos bem com o que temos" (o
bloqueio dito é o fornecedor atual → regra de status quo); episódio em `S00`.

**Acceptable alternatives:** omitir `S06` do contexto. **Rules:** Competition; status quo; Resolution
(próximo passo ≠ aceitação).

---

## CAL09 — tier `missing_context` (GL-3)

| | ep-a |
|---|---|
| Detection | PRESENT |
| Anchor / objection | `S01` / [`S01`] |
| Context | [`S02`, `S03`, `S04`, `S05`] |
| Category | `IMPLEMENTATION_INTEGRATION` |
| Handling | PRESENT (`S02`, `S04`, `S05`) |
| Reaction | `S03` CLARIFICATION (GL-3); `S06` NEUTRAL |
| Resolution | `unknown` |
| Uncertainty | nenhuma |

**Why:** a barreira é a capacidade de tocar a troca do sistema. `S03` pede informação — não é ACCEPT
nem REJECT — e é a única reação substantiva → `unknown`.

**Common wrong:** `resolved` porque o closer respondeu e o lead disse "Ok"; `unresolved`;
`TIMING_PRIORITY` por "a equipe já está no limite" (o que é resistido é o esforço de implantar, não o
momento da compra).

**Acceptable alternatives:** AMBIGUOUS {`IMPLEMENTATION_INTEGRATION`, `TIMING_PRIORITY`} é discutível;
registre o raciocínio. **Rules:** Implementation; GL-3 (clarificação real).

---

## CAL10 — tier `adversarial` (OTHER)

| | ep-a | ep-b |
|---|---|---|
| Detection | PRESENT | PRESENT |
| Anchor / objection | `S01` / [`S01`] | `S07` / [`S07`] |
| Context | [`S02`, `S03`] | [`S08`, `S09`] |
| Category | `OTHER` (nota: reciprocidade comercial como condição) | AMBIGUOUS {`PRICE_BUDGET`, `TIMING_PRIORITY`} |
| Handling | PRESENT (`S02`) | PRESENT (`S08`) |
| Reaction | `S03` REJECT | `S09` ACCEPT |
| Resolution | `unresolved` | `resolved` |
| Uncertainty | nenhuma | categoria AMBIGUOUS |

**Why:** `S01` é objeção clara (A–D) cujo bloqueio — reciprocidade — não é preço, momento,
necessidade, autoridade, confiança, concorrente, implantação nem termo contratual/processo formal →
`OTHER`, com a descrição em nota. `S04` fecha o fio. `S07` liga verba a uma data; nada decide se o
resistido é a verba ou o momento → AMBIGUOUS (fronteira aberta na KB). A resolução independe da
categoria.

**Common wrong:** `UNKNOWN` em `ep-a` (a barreira é clara); `TERMS_PROCESS` (é regra pessoal do lead, não
termo de contrato nem etapa de compra); `COMPETITION`; `ep-b` dentro de `ep-a`.

**Acceptable alternatives:** `ep-b` = `PRICE_BUDGET` ("não teria como pagar") com justificativa;
`ep-a` = `TERMS_PROCESS` é **discutível** — registre como insumo de TAX. **Rules:** OTHER; Brush-off
(verba ligada a data); Episode boundaries.

---

## CAL11 — tier `adversarial` (boundary)

| | ep-a | ep-b |
|---|---|---|
| Detection | PRESENT | PRESENT |
| Anchor / objection | `S01` / [`S01`] | `S05` / [`S05`] |
| Context | [`S02`, `S03`] | [`S06`, `S07`] |
| Category | `TERMS_PROCESS` | `PRICE_BUDGET` |
| Handling | PRESENT (`S02`) | PRESENT (`S06`) |
| Reaction | `S03` ACCEPT | `S07` ACCEPT |
| Resolution | `resolved` | `resolved` |
| Uncertainty | nenhuma | nenhuma (ver alternativas) |

**Why:** `S01` é regra formal de compras como impedimento → TERMS. `S05` resiste à **capacidade de
caixa** para pagar adiantado → PRICE_BUDGET (fronteira AC da KB: "não cabe pagar adiantado" = preço;
estrutura de contrato = termos). Categoria nova → episódio novo.

**Common wrong:** tudo como um episódio TERMS sem justificar; `resolved` do `ep-a` usado para `ep-b`.

**Acceptable alternatives:** `ep-b` AMBIGUOUS {`PRICE_BUDGET`, `TERMS_PROCESS`}. Se o anotador ler `S05`
como `TERMS_PROCESS`, `S04`–`S07` viram contexto de um único episódio TERMS (fio ainda aberto), também
`resolved` — discutível; registre. **Rules:** Terms/process; Price (forma de pagamento).

---

## CAL12 — tier `ambiguous` (boundary)

| | ep-a |
|---|---|
| Detection | PRESENT |
| Anchor / objection | `S04` / [`S04`] |
| Context | [`S05`, `S08`, `S09`] (`S06`, `S07` opcionais) |
| Category | `TRUST_RISK` |
| Handling | PRESENT (`S05`, `S09`) |
| Reaction | `S08` REJECT; `S10` NEUTRAL |
| Resolution | `unresolved` |
| Uncertainty | nenhuma |

**Why:** receio de falha do sistema no pico, dito como razão para não fechar sem prova → TRUST_RISK
(abstração provisória do AI Closer). `S06`/`S07` são logística da call (outro participante) e **não**
fecham o fio; `S08` ("como eu dizia") é o mesmo episódio. **Negatives:** `S00` pedido de referência;
`S02` experiência ruim passada sem bloqueio atual → NO_OBJECTION.

**Common wrong:** TRUST_RISK em `S02`; novo episódio em `S08`; closure em `S06`;
`IMPLEMENTATION_INTEGRATION` (não é esforço de implantar, é confiança na entrega); `resolved` por "Tá".

**Acceptable alternatives:** AMBIGUOUS {`TRUST_RISK`, `IMPLEMENTATION_INTEGRATION`} é discutível.
**Rules:** Trust/risk; Observed vs inferred; Episode boundaries (logística não fecha).

---

## Coverage matrix (só para discussão pós-calibração)

| Ponto da guideline | Calls |
|---|---|
| PRICE_BUDGET real / pergunta neutra / × NEED / × TERMS / verba com data | CAL06, CAL02 / CAL02, CAL03 / CAL05 / CAL11 / CAL10 |
| TIMING real / brush-off / frase ambígua | CAL01 / CAL03 / CAL07 |
| NEED_VALUE_FIT | CAL05 |
| AUTHORITY real × menção a stakeholder | CAL04 × CAL03 |
| TRUST_RISK × pedido de case × experiência passada | CAL12 |
| COMPETITION × concorrente mencionado | CAL08 × CAL03, CAL08 |
| IMPLEMENTATION × pergunta técnica × TIMING | CAL09, CAL06 × CAL03 × CAL09 |
| TERMS × processo normal | CAL11 × CAL03 |
| OTHER | CAL10 |
| UNKNOWN × AMBIGUOUS | CAL07 (+ CAL10 categoria AMBIGUOUS) |
| NO_OBJECTION adversarial | CAL03 |
| GL-3 clarificação / reafirma / ambígua | CAL09 / CAL06 / CAL04 |
| partially_resolved válido × armadilha multi-categoria | CAL02 × CAL06 |
| Multi-objection mesma âncora | CAL06 |
| Logística + retorno ao mesmo fio | CAL12 |
| Mesma categoria após closure | CAL01 |
