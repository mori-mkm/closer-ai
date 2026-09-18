# Real Data Request

O que pedimos, a quem, em que formato — pronto para virar mensagem para Gabriel/Otávio/
parceiros. Princípio central: **"send the rawest practical export available"**. Não pedimos
para o parceiro reformatar nada segundo nosso schema antes de vermos a fonte — todo contrato
hoje (`AgroRawCall`, campos de Kommo) é hipótese não confirmada
(`docs/domain/AGRO_INGESTION_CONTRACT.md`), e pedir pré-formatação forçaria o parceiro a
adivinhar um schema que nós mesmos ainda não validamos. Se o formato original for estranho ou
"sujo", é exatamente isso que precisamos ver primeiro.

## Package A — Agro/BeefPoint calls

**Objetivo:** validar `raw source → Agro adapter → AgroRawCall → Canonical Call`.

- **Minimum sample:** 5 calls reais, antes das 108. Se possível, incluir diversidade — mas
  **não assumir** que essas categorias estão disponíveis, só pedir quando fizer sentido:
  - 1 call "normal" (fechamento comum)
  - 1 call com vários participantes
  - 1 call com transcript imperfeito/ruidoso (ligação com falhas, sobreposição de fala)
  - 1 call de um deal com mais de um encontro, se houver
  - 1 call com outcome conhecido (ganho ou perdido), se souberem qual foi
- **Preferred format:** o formato ORIGINAL disponível, qualquer um destes:
  - transcript nativo do Zoom (`.vtt`, `.srt`, `.txt`)
  - resposta JSON da API do Zoom (recording/transcript endpoint)
  - export de metadata da reunião (meeting id, participantes, duração)
  - qualquer outro formato que já exista — **não converter antes de enviar**.
- **Required metadata:** meeting id (ou identificador equivalente), data/hora da call,
  duração (mesmo que a unidade não esteja clara — preferimos saber depois do que assumir
  agora).
- **Optional metadata:** nome do closer, tópico/assunto da call, resumo automático (se o Zoom
  gerar um), qualquer id de CRM já vinculado à call.
- **What NOT to transform:** não reescrever o transcript em outro formato, não anonimizar
  antes de enviar (o dado já sai de um ambiente controlado — anonimização prematura pode
  esconder exatamente o que precisamos validar, como a forma real dos labels de speaker),
  não resumir ou truncar.
- **Security requirements:** nunca por e-mail/Slack em texto puro se contiver PII de terceiros
  fora do parceiro — usar o canal seguro já definido com o parceiro (ex.: pasta compartilhada
  com acesso controlado). Nunca vai para o Git público — ver `docs/data/PRIVACY_BOUNDARY.md`.

## Package B — Empreende Brazil calls

**Objetivo:** o mesmo pipeline acima, mais uma pergunta de arquitetura: a segunda fonte exige
um **novo adapter** ou só um **novo source parser** dentro da mesma estrutura de
`ingestion/`? Isso valida se a arquitetura de ingestão generaliza ou é acoplada ao formato
Agro.

- **Minimum sample:** 3-5 calls reais, antes das 35.
- **Preferred format / required metadata / what NOT to transform / security:** mesmos
  princípios do Package A — formato original, sem pré-formatação, mesmo canal seguro.
- **Pergunta adicional a responder com a amostra:** o formato de origem da Empreende é do
  mesmo tipo (Zoom) ou outra ferramenta de call/transcrição? Isso muda se o trabalho futuro é
  "reusar `ingestion/agro/` com outro parser" ou "criar `ingestion/empreende/` do zero".

## Package C — Kommo/CRM

**Objetivo:** um **minimum CRM sample**, não o CRM inteiro.

- **Minimum sample (recomendação, não requisito absoluto):** 20-50 deals, idealmente com
  alguns WON, alguns LOST, alguns OPEN, e — quando possível — com calls conhecidas associadas.
- **Preferred format:** export/API response original (JSON da API v4 do Kommo é o preferido se
  disponível; um export CSV/Excel manual também serve como primeiro passo).
- **Campos possíveis** — não afirmamos que o Kommo retorna todos; classificação por
  necessidade, a confirmar contra a amostra real:

| Campo | Classificação |
|---|---|
| deal external id | REQUIRED |
| pipeline | REQUIRED |
| stage | REQUIRED |
| status/outcome (won/lost/open) | REQUIRED |
| created_at | REQUIRED |
| lead/contact external id | USEFUL |
| responsible user (owner) | USEFUL |
| value + currency | USEFUL |
| closed_at | USEFUL |
| stage history | USEFUL (crítico para `StageEvent`, mas pode não estar na API padrão) |
| loss reason | USEFUL |
| contacts (nome/email/telefone) | USEFUL — sinal de matching Call↔Deal (ver `docs/data/DATA_ACCESS_MATRIX.md`) |
| tags | OPTIONAL |
| custom fields | UNKNOWN UNTIL SAMPLE |
| activities/tasks | UNKNOWN UNTIL SAMPLE |
| notes | UNKNOWN UNTIL SAMPLE — provável fonte de PII, cuidado extra |
| call/meeting references | UNKNOWN UNTIL SAMPLE — sinal mais forte de matching, se existir |

- **What NOT to transform:** não pré-mapear campos do Kommo para `Lead`/`Deal`/`StageEvent`
  antes de enviar — precisamos ver o payload bruto primeiro (`docs/data/KOMMO_DISCOVERY.md`).
- **Security requirements:** nunca token/API key em texto puro em qualquer canal não seguro;
  se for um export manual, mesmo canal seguro do Package A/B.

## Quando o conjunto completo for mais fácil de exportar

Deixar claro para o parceiro: **"se for mais fácil exportar o conjunto completo de forma
segura, podemos trabalhar com ele localmente — não será enviado ao Git público."** Preferimos
começar pequeno (5/3-5/20-50), mas não é bloqueio se o parceiro só conseguir exportar tudo de
uma vez.

---

## A. Internal request (para o time)

> Precisamos de acesso aos primeiros dados reais do AI Closer para destravar a validação dos
> pipelines Agro e o matching Call↔Deal. Pedido específico: (1) 5 calls reais do
> Agro/BeefPoint no formato original (Zoom, qualquer formato — vtt/srt/txt/JSON), (2) 3-5 calls
> reais da Empreende Brazil no formato original, (3) uma amostra de 20-50 deals do Kommo
> (JSON de API ou export), incluindo alguns WON/LOST/OPEN e, se possível, com calls conhecidas
> associadas. Precisamos também confirmar a autorização formal de uso desses dados antes de
> processá-los (`docs/context/OPEN_QUESTIONS.md`). Nenhum dado bruto entra no Git — vai para
> armazenamento local privado (`docs/data/PRIVACY_BOUNDARY.md`).

## B. Partner request (linguagem simples)

> Para avançar no projeto, precisamos de uma primeira amostra pequena dos dados reais:
>
> - **5 chamadas** gravadas/transcritas (Agro/BeefPoint) — pode ser o arquivo original do Zoom,
>   qualquer formato que vocês já tenham (não precisa converter nada).
> - **3 a 5 chamadas** da Empreende Brazil, no mesmo formato original.
> - Uma amostra de **20 a 50 negociações** do Kommo (pode ser um export ou acesso à API),
>   incluindo algumas ganhas, algumas perdidas e algumas ainda em aberto.
>
> Se for mais fácil exportar o conjunto completo de forma segura, também funciona — vamos
> trabalhar com ele localmente, e nada disso vai para um repositório público. O objetivo dessa
> primeira amostra é confirmar o formato real dos dados antes de processar tudo.
