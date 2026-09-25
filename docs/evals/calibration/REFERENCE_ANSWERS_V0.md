# Calibration Reference Answers v0

**CALIBRATION REFERENCE — não é gold nem ground truth.** Serve para discutir o processo depois que
A, B e o adjudicador terminaram. **Não leia antes de submeter sua anotação ou adjudicação.**

Onde a guideline permite mais de uma resposta, as alternativas aceitáveis estão listadas.
Divergência dentro das alternativas não é erro; é informação para o pilot.

---

## CAL01 — tier `happy_path`

### Expected call-level interpretation
Anotável; call revisada inteira; **um** episódio.

### Expected episodes

| Campo | Referência |
|---|---|
| Detection | PRESENT |
| Anchor | `CAL01_S008` |
| `objection_segment_ids` | [`CAL01_S008`] |
| `context_segment_ids` | [`CAL01_S009`, `CAL01_S010`, `CAL01_S011`, `CAL01_S012`] |
| Handling | PRESENT: `S009` (oferta de pagamento mensal), `S011` (confirma condições) |
| Reaction | PRESENT: `S010` (pergunta de esclarecimento, sem posição), `S012` (aceita) |
| Resolution | `resolved` — última resposta substantiva do lead (`S012`) aceita explicitamente |
| Category | `price` (enum v0 provisório) — o que é resistido é a forma/valor do pagamento, e a resposta que resolve é mudar o pagamento |

Raciocínio: `S008` é resistência dita pelo lead, agora, contra avançar nas condições propostas. O fio
fecha em `S013` (treinamento: assunto de negócio fora do fio).

### Expected negatives
- `S006` "Quanto fica o plano anual?" — pergunta neutra, não é âncora.
- `S004` — relato de problema atual (motivo de compra), não resistência à oferta.
- `S013`–`S017` — próximos passos; nenhuma objeção.

### Common mistakes / falsifying expectations
- Marcar `resolved` em `S009` porque o closer respondeu (a resolução vem do lead, em `S012`).
- Âncora em `S006` por causa da palavra "fica/valor".
- Categoria `timing_priority` por "nessa época" (o que é resistido é o pagamento à vista, não o
  momento da compra). Se alguém marcar AMBIGUOUS {`price`, `timing_priority`}, discuta: a guideline
  pede categoria pelo que é resistido.

### Guideline clauses exercised
Definição (4 testes); "What is not an objection" (pergunta neutra); handling claro; reação; resolução
pela última resposta substantiva; category by meaning.

### Open-decision triggers
TAX (categoria provisória).

---

## CAL02 — tier `adversarial`

### Expected call-level interpretation
Anotável; call revisada inteira; **nenhum episódio** → rótulo negativo call-level ABSENT; demais
perguntas N/A.

### Expected episodes
Nenhum.

### Expected negatives (trechos que **não** devem virar episódio)

| Segmento | Por que não |
|---|---|
| `S003` | fala do closer ("a mensalidade assusta…") |
| `S004` | pergunta neutra de preço |
| `S006` | objeção passada, de outro fornecedor, e o lead diz que o valor atual está dentro do planejado |
| `S008` | fala de prazo sem resistência |
| `S009`–`S010` | hipótese ("se fosse o dobro"), e o lead nega ("não é o caso") |
| `S011` | resistência atribuída à esposa, e o lead diz que a decisão é dele e que achou justo |
| `S013`, `S015` | dúvidas operacionais |

### Common mistakes / falsifying expectations
- Detector por palavra-chave: "assusta" (`S003`), "caro" (`S006`), "reclamar do valor" (`S011`), "prazo" (`S007`),
  "repensar" (`S010`) viram falsos episódios.
- Marcar ABSENT sem ter lido a call toda (vale como processo: o rótulo exige revisão completa).

### Guideline clauses exercised
"What is not an objection" (closer, pergunta neutra, passado resolvido, hipótese, terceiro);
negative labels; N/A em call ABSENT; adversarial A1–A5.

### Open-decision triggers
GL-1 em `S011`: a guideline v0 já decide este caso (o lead **discorda** → não é objeção). Se A ou B
hesitarem, registre como evidência para GL-1; não é uma regra nova.

---

## CAL03 — tier `ambiguous`

### Expected call-level interpretation
Anotável; call revisada inteira; **um** episódio.

### Expected episodes

| Campo | Referência |
|---|---|
| Detection | PRESENT |
| Anchor | `CAL03_S005` (começo incompleto completado por `S007`; `S006` é logística da call — não substantivo) |
| `objection_segment_ids` | [`CAL03_S005`, `CAL03_S007`] |
| `context_segment_ids` | [`CAL03_S008`, `CAL03_S013`, `CAL03_S014`, `CAL03_S015`, `CAL03_S016`, `CAL03_S017`] |
| Handling | PRESENT: `S008` (adiamento explícito: "guarda essa questão… antes, deixa eu mostrar" → fio parked), `S013` (retomada com proposta), `S015` |
| Reaction | PRESENT: `S014` (reitera: ainda apertado), `S017` ("Vou pensar e te falo") |
| Resolution | `unresolved` — ver abaixo |
| Category | `timing_priority` (enum v0 provisório) — o que é resistido é o prazo de implantação diante da colheita |

Alternativas aceitáveis de fronteira: incluir `S006` no contexto (logística) não muda o episódio;
**não** incluir `S009`–`S012` (relatórios, durante o fio parked, não servem à resolução). `S009`
"Pode." é só concordância com o adiamento; incluir ou não no contexto é divergência menor.

**Resolution:** `unresolved`. `S014` reitera a objeção ("ainda é apertado"). `S017` "Vou pensar
e te falo" não aceita nada: lido como pendência declarada, conta como a preocupação continuando
aberta (mesma regra provisória de "ainda preciso ver…" → `unresolved`); lido como interjeição, não sobrescreve `S014`. Nos dois casos, `unresolved`.
`S019` "Combinado." é interjeição. **Não aceitável:** `resolved`.
Leitura divergente: tratar `S017` como resposta ininteligível e marcar `unknown`. A guideline não
sustenta isso (a fala é clara: a decisão ficou pendente), mas se aparecer, registre como evidência
para GL-2 e D6 — não como erro do anotador. GL-2 trata de "vou pensar" **isolado** como possível
objeção (detecção); aqui a objeção já existe e tem reação clara em `S014`.

### Expected negatives
- `S016` (OTHER): contexto; **não** é reação do lead e não resolve o episódio dele; também não é
  episódio próprio (não expressa resistência; e `other` não ancora).
- `S013` e `S014` **não** abrem novo episódio: o fio estava parked (`S008`) e foi retomado; a
  reiteração em `S014` é reação no mesmo episódio.

### Common mistakes / falsifying expectations
- Âncora em `S007` (ignorando o começo incompleto em `S005` porque há uma fala de outro no meio).
- Tratar `S008` como closure e abrir um segundo episódio em `S013`/`S014`.
- Usar `S016` (sócia) para marcar `resolved`.
- Marcar `resolved` porque a call termina cordial ("Combinado.") ou porque a sócia (`S016`) achou viável.

### Guideline clauses exercised
Âncora com fala não substantiva no meio (logística); parked e retomado; repetição no mesmo fio;
terceiro nunca reage pelo objetor; resolução pela última resposta substantiva; interjeição final
não muda a resolução.

### Open-decision triggers
D6 (semântica comercial de pendência declarada); GL-2 só como observação se alguém tratar `S017`
como resposta ininteligível; TAX (categoria de prazo de implantação pode mudar).
