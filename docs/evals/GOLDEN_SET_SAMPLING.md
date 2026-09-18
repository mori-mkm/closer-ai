# Golden Set Sampling Plan

Estratégia de amostragem para o Golden Set real de objeções — preparada antes de qualquer call
real existir localmente. **Não seleciona calls reais aqui.** Complementa
`docs/context/TECH_DEBT.md` (TD-13: o golden set atual em `evals/objection_v0/` é 100%
sintético) e o gate "GOLDEN SET READY" (`docs/context/EXECUTION_GATES.md`).

## Tamanho alvo

~20-30 calls iniciais, conforme já estabelecido em `docs/product/ROADMAP.md` e
`docs/context/EXECUTION_GATES.md`. Amostra pequena de propósito — o objetivo é medir o
extractor v0 contra dado real, não cobrir toda a distribuição do corpus.

## Dimensões desejadas de diversidade

Só usar as dimensões abaixo **se o campo existir de fato** na amostra real recebida — não
estratificar por um campo que não existe. Confirmar disponibilidade em
`docs/data/DATA_QUALITY_REPORT.md` antes de aplicar qualquer uma destas:

- outcome do deal associado (won/lost/open), quando o Call↔Deal match já existir
- closer (se houver mais de um na operação)
- estágio do funil em que a call ocorreu
- duração da call (curta/média/longa)
- tipos de objeção observados numa passada exploratória (não a categoria final, só para não
  concentrar tudo em um único tipo)
- transcript limpo vs. ruidoso (baseado em `quality_flags` — ver `docs/domain/AGRO_INGESTION_CONTRACT.md`)
- múltiplos participantes vs. 1:1
- múltiplas calls por deal vs. call única

## Fallback strategy

Se nenhuma dimensão acima puder ser confirmada antes da seleção (ex.: Call↔Deal matching ainda
não rodou), usar amostragem aleatória simples sobre o corpus disponível, com um único
critério mínimo: cobrir mais de um closer se existir mais de um, para não enviesar o golden set
para o estilo de fala de uma única pessoa.

## Evitar viés de seleção

**Regra central: não selecionar apenas calls "interessantes".** Um golden set enviesado para
casos ricos em objeção óbvia superestima recall; um enviesado para calls "limpas" superestima
precisão. A amostragem deve incluir calls sem nenhuma objeção clara (verdadeiro negativo) na
mesma proporção que apareceria naturalmente no corpus, não removida por parecer "sem sinal
útil".

**A pool de sorteio é o corpus bruto inteiro, não o subconjunto já validado pelo pipeline.**
Se a amostragem sortear só entre calls que já passaram por `docs/data/FIRST_CALLS_VALIDATION.md`
sem nenhuma `quality_flag`, ou que já têm `CallDealMatch` resolvido, o golden set fica
implicitamente enviesado para calls limpas/completas antes mesmo do sorteio acontecer — isso
anula a dimensão "transcript limpo vs. ruidoso" listada acima, porque as ruidosas já teriam
sido excluídas da pool. A pool de sorteio deve incluir calls com `quality_flags` presentes
(incompletas, com `unresolved_speaker`, etc.), não só as que "passaram limpo" — mesmo que
algumas dessas calls acabem descartadas depois por não produzirem `Call` válido, elas devem
competir pela seleção antes disso, não ser filtradas antes do sorteio.

## Annotation prep checklist

Antes de qualquer anotação real começar:

- [ ] Taxonomia congelada para esta rodada? (v0 atual: `price`, `timing_priority`,
      `trust_authority`, `no_need`, `other` — `docs/domain/OBJECTION_MODEL.md`)
- [ ] Exemplos positivos definidos por categoria?
- [ ] Exemplos negativos (não-objeção) definidos, incluindo os casos-limite já identificados
      no golden set sintético (frase ambígua, closer citando o lead, objeção partida entre
      segmentos — `evals/objection_v0/README.md`)?
- [ ] Casos-limite (edge cases) documentados como parte da regra de anotação, não deixados
      para o anotador decidir ad-hoc?
- [ ] Risco de ASR/dialeto/gíria regional registrado como limitação conhecida do extractor v0
      (`_KEYWORDS` em `src/closer_ai/ai/objection_extraction.py` é português formal fixo, sem
      tolerância a erro de transcrição ou termo regional de agronegócio — ver nota em
      `docs/data/FIRST_CALLS_VALIDATION.md`), para que recall baixo em dado real não seja
      confundido com bug do extractor quando a causa raiz é cobertura de vocabulário?
- [ ] Resolução da objeção (foi superada antes do fechamento?) — **fora do escopo do
      `ObjectionEvent` v0** (`src/closer_ai/domain/objection.py` documenta isso como
      deliberadamente deferido); não anotar isso ainda, a menos que se decida expandir o
      contrato primeiro.
- [ ] Evidence span — v0 usa um `segment_id` inteiro, não um trecho de caracteres. Anotadores
      devem marcar o segmento inteiro, não um recorte de texto.
- [ ] Timestamp — não é um campo do `ObjectionEvent`; resolvível via `Call.segments` se
      necessário para análise, não precisa ser anotado separadamente.
- [ ] Stage do deal no momento da call — fora do `ObjectionEvent`; se relevante para a análise,
      vem do `CallDealMatch`/`StageEvent`, não da anotação de objeção.
- [ ] Handling/reação do closer, next step — **não suportado hoje**, ver abaixo.

## O que é suportado hoje vs. requisito futuro de `objection_episode`

| Capacidade | Suportado por `ObjectionEvent` v0? |
|---|---|
| Categoria da objeção (taxonomia fechada) | Sim |
| Localização na call (segmento único) | Sim |
| Múltiplas objeções por call | Sim |
| Repetição da mesma objeção em segmentos diferentes | Sim (ids diferentes, ambos preservados) |
| Evidência multi-segmento | Não — v0 só suporta 1 segmento por evento |
| Resolução (superada ou não) | Não |
| Estratégia do closer em resposta | Não — é um sub-item irmão de `Call`, não parte deste contrato (`docs/architecture/DATA_MODEL.md`) |
| Confiança/severidade | Não |
| Link direto a `Deal`/`Outcome` | Não — só via `call_id` → `CallDealMatch` → `deal_id` |

Isso confirma a avaliação já registrada em `docs/context/NOTION_SYNC.md`: um "objection_episode"
completo (se essa era a intenção original de uma task mais ampla) não está entregue — v0 é um
subconjunto deliberado, suficiente para o Golden Set inicial, mas a lista acima é o que falta
se o escopo precisar crescer depois que o golden set real mostrar necessidade real (não antes).
