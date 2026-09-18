# Data Access Matrix

Estado de acesso a cada dataset real, e (segunda tabela) confiabilidade qualitativa de cada
sinal candidato a matching Call↔Deal. Sem nomes pessoais onde não há evidência no repo — usa
papéis (roles).

Papéis: **Partner Owner** (dono do dado do lado do parceiro), **Product/RevOps**,
**Data/Analytics**, **AI/Backend**.

Estados: **UNKNOWN**, **REQUESTED**, **AVAILABLE**, **VALIDATED**, **BLOCKED**.

## Datasets

| Dataset | Business owner | Technical source | Expected records | Current access | Authorization | Contains PII? | Contains sensitive commercial data? | Storage location | Git allowed? | Status | Next action |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Agro/BeefPoint calls | Partner Owner | Zoom (formato exato não confirmado) | ~108 (5 na primeira amostra) | Não disponível localmente nesta sessão | Não confirmada (`docs/context/OPEN_QUESTIONS.md`) | Sim — nome, voz, transcript | Sim — conteúdo de venda, possível valor mencionado em call | `data/raw/agro/` (nunca Git) | Não | BLOCKED | Enviar `docs/data/REAL_DATA_REQUEST.md` Package A |
| Empreende Brazil calls | Partner Owner | fonte não confirmada (Zoom ou outra ferramenta) | ~35 (3-5 na primeira amostra) | Não disponível localmente nesta sessão | Não confirmada | Sim | Sim | `data/raw/empreende/` (nunca Git) | Não | BLOCKED | Enviar Package B; confirmar se fonte é Zoom |
| Kommo CRM sample | Partner Owner / Product-RevOps | API v4 ou export manual (formato não confirmado) | 20-50 na primeira amostra | Não disponível localmente nesta sessão | Não confirmada | Sim — nome/email/telefone de lead | Sim — valor de deal, estágio, loss reason | `data/raw/kommo/` (nunca Git) | Não | BLOCKED | Enviar Package C; confirmar se API v4 ou export |
| Pipedrive (segunda operação, mencionado em `docs/architecture/INTEGRATIONS.md`) | Partner Owner | não confirmado | não confirmado | Não solicitado ainda | Não confirmada | Provável | Provável | N/A ainda | Não | UNKNOWN | Fora do escopo desta rodada — `INTEGRATIONS.md` já registra Pipedrive como CRM da "outra operação do corpus"; confirmar com Product/RevOps se entra num pacote futuro antes de pedir amostra |

Nota: `docs/architecture/INTEGRATIONS.md` já documentava que uma operação do corpus usa Kommo e
a outra usa Pipedrive — esta rodada de onboarding pede amostra só de Kommo (conforme escopo
desta task); Pipedrive fica registrado aqui para não ser esquecido, não para ser pedido agora.

## Matching signal reliability (Call↔Deal)

Confiabilidade **qualitativa**, não numérica — não há evidência real ainda para atribuir
número. Ver `src/closer_ai/domain/matching.py` para o contrato de `CallDealMatch`/
`MatchEvidence` que estes sinais alimentam.

| Signal | Expected reliability | PII? | Normalized? | Exact or heuristic? | Currently available? | Requires authorization? | Can be persisted? |
|---|---|---|---|---|---|---|---|
| External meeting id (Zoom) == Deal external id | Potentially strong — só se o CRM de fato armazena o id da reunião | Não | Sim, já é o contrato de `ExactExternalIdMatcher` | Exact | Sim, no código (`src/closer_ai/domain/matching.py`); dado real não confirmado | Não (não é PII) | Sim |
| CRM activity id ligado à call | Potentially strong, se existir | Não | Não confirmado | Exact | Unknown até amostra Kommo | Não | Sim |
| Email (participante da call vs. contato do Deal) | Medium — depende de o Zoom/Agro capturar email do participante, que `Participant` hoje não modela | Sim | Não | Exact | Não — `Participant` (`normalization/models.py`) não tem campo de email hoje | Sim | Não em texto puro (ver `docs/data/PRIVACY_BOUNDARY.md`) |
| Telefone (participante vs. contato) | Medium — mesma limitação de `Participant` acima | Sim | Não | Exact | Não — campo não existe no schema hoje | Sim | Não em texto puro |
| Participant external id estável (Zoom UUID) | Unknown — não confirmado se a fonte real fornece | Não (é um id, não um dado pessoal em si) | Sim, se existir | Exact | Não confirmado — ver `docs/domain/AGRO_INGESTION_CONTRACT.md` (limitação conhecida) | Não | Sim |
| Nome (participante vs. contato) | Weak isoladamente — nome é ambíguo, mas serve como sinal complementar (`name_and_datetime`/`name_only` em `MatchMethod`) | Sim | Parcial (`_slugify`) | Heuristic | Sim, já existe como hipótese no parser Agro | Sim para uso real | Não em texto puro |
| Closer (call) vs. owner_id (deal) | Weak como sinal isolado — `docs/domain/DEAL_MODEL.md` documenta explicitamente que `Deal.owner_id` nunca deve ser assumido igual a `Call.closer_id` (um colega pode conduzir a call) | Não diretamente | N/A | Heuristic (apoio, não decisivo) | Sim, ambos os campos existem no schema | Não | Sim |
| Datetime da call vs. `Deal.created_at`/`StageEvent.occurred_at` | Medium como sinal complementar, nunca isolado | Não | Sim (tz-aware) | Heuristic (proximidade) | Sim, campos existem | Não | Sim |
| Notas do CRM mencionando a call | Unknown — depende do formato real de notas | Sim, provável | Não | Heuristic | Unknown até amostra Kommo | Sim | Não em texto puro |
| Link de calendário/convite | Unknown | Possível (pode conter email) | Não | Heuristic | Unknown até amostra | Sim | Cauteloso — pode conter token/URL sensível |

**Leitura:** hoje só existe um sinal com implementação real (`exact_external_id`, via
`ExactExternalIdMatcher`) — todo o resto é candidato até a amostra Kommo/Agro confirmar quais
campos de fato chegam populados. Nenhum matcher heurístico deve ser implementado antes dessa
confirmação (ver `docs/context/OPEN_QUESTIONS.md`, seção MATCHING).
