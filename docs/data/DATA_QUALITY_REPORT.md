# Data Quality Report — Template

Métricas a reportar por dataset quando dado real for processado. Define só as métricas, não
thresholds de sucesso — nenhum piso "aceitável" foi definido ainda (isso é decisão de produto,
ver `docs/context/HUMAN_DECISIONS.md`, e só faz sentido depois de ver a primeira amostra real).

## Calls (Agro / Empreende)

| Métrica | Definição |
|---|---|
| Total calls processadas | contagem de tentativas |
| Transcript available % | % com transcript não-vazio na fonte |
| Participant metadata % | % com lista de participantes utilizável (sem cair em `missing_participants`) |
| Speaker resolution % | % de segmentos cujo `speaker_id` resolveu sem `unresolved_speaker` |
| Timestamp completeness % | % de entradas de transcript com `start`/`end` válidos (sem `missing_timestamp`) |
| Duration completeness % | % com `duration_seconds` presente na fonte (sem cair em `missing_duration`, estimado) |
| Closer resolution % | % com `closer_id` resolvido (não `None` por falha de resolução) |
| Parse success % | % que produziu um `Call` válido (não levantou `AgroParseError`) |
| Lead role resolution % | % de calls com pelo menos um participante `role="lead"` depois do parser — métrica crítica: sem isso, `RuleBasedObjectionExtractor` não detecta nada naquela call, mesmo com `Call` válido (ver `docs/data/FIRST_CALLS_VALIDATION.md`, passo 13) |
| Transcript intelligibility (qualitativo) | amostra revisada manualmente (não 100% — nem viável nem necessário para 5-108 calls): o texto é português legível, ou predominantemente ruído/erro de transcrição/troca de idioma? Métrica estrutural (presença/completude) não captura isso — um transcript "completo" pelos campos acima ainda pode ser ilegível |
| Quality flags distribution | contagem por flag (`missing_transcript`, `empty_transcript`, `missing_participants`, `unresolved_speaker`, `missing_timestamp`, `missing_duration`, `transcript_parse_error`, `metadata_incomplete`, `participant_id_collision` — lista completa em `docs/domain/AGRO_INGESTION_CONTRACT.md`) |

## CRM (Kommo)

| Métrica | Definição |
|---|---|
| Total deals na amostra | contagem |
| Won / Lost / Open | contagem por outcome |
| Missing lead % | % de deals sem `lead_id` resolvível |
| Missing owner % | % sem `owner_id` |
| Missing value % | % sem `value` |
| Missing created_at % | % sem `created_at` válido |
| Missing outcome semantics | quantos deals têm status ambíguo (não claramente won/lost/open) |
| Stage history availability | % de deals com histórico de stage disponível vs. só estado atual |
| Contacts with usable identifiers % | % de contatos com pelo menos email OU telefone utilizável (sinal de matching) |

## Matching (Call ↔ Deal)

| Métrica | Definição |
|---|---|
| Matched | contagem de `CallDealMatch(status='matched')` |
| Ambiguous | contagem de calls com múltiplas linhas `status='ambiguous'` |
| Unmatched | contagem de `status='unmatched'` |
| Manual review | contagem de `status='manual_review'` |
| Rejected | contagem de `status='rejected'` (revisão humana descartou) |

## Como usar

Um relatório por dataset, gerado depois de rodar `docs/data/FIRST_CALLS_VALIDATION.md`
(calls) ou `docs/data/KOMMO_DISCOVERY.md` (CRM) contra a amostra real. Alimenta os gates
"5-CALL VALIDATION PASSED" e "CRM SEMANTICS VALIDATED" (`docs/context/EXECUTION_GATES.md`).
Nenhum valor de exemplo é dado aqui — preencher só com dado real, e o relatório em si nunca
contém PII (contagens e percentuais, não os registros individuais).
