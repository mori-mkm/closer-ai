# Privacy Boundary

Auditoria prática do que pode/não pode entrar no Git público, e como transformar um caso real
em fixture sintética no futuro sem vazar PII. Não é interpretação jurídica — autorização/
compliance é decisão humana (`docs/context/OPEN_QUESTIONS.md`, `docs/context/HUMAN_DECISIONS.md`),
este documento só define a fronteira técnica.

## O que os dados reais podem conter

Nomes, emails, telefones, nomes de empresa, gravações de reunião, transcrições, valores
financeiros de deal, notas de CRM.

## SAFE FOR PUBLIC GIT

- Fixtures sintéticas (`tests/fixtures/`, `evals/datasets/`) — geradas, nunca derivadas
  diretamente de um caso real (ver "Redaction strategy" abaixo).
- Schemas e contratos (`src/closer_ai/**`, `docs/domain/**`).
- Nomes de campo, tipos, invariantes.
- Exemplos agregados não-identificáveis (ex.: "3 das 5 calls tiveram `duration_mismatch`").
- Documentação (este pack incluído).

## NEVER PUBLIC GIT

- Transcrições reais (qualquer formato).
- Emails/telefones reais.
- Gravações de reunião.
- Exports de CRM (mesmo parciais).
- Nomes reais de participante/lead.
- Tokens de acesso/API keys.
- URLs de reunião com segredo embutido (ex.: link do Zoom com senha na query string).

## CAUTION / REVIEW FIRST

- Estatísticas agregadas (podem reidentificar se a amostra for pequena — ex.: "a única call
  perdida da operação X" já identifica um deal específico).
- Screenshots (podem conter PII fora do que se pretende mostrar).
- Trechos pequenos de evidência (um segmento de transcript "só para mostrar o parser" ainda é
  transcript real).
- Output de modelo derivado de dado real (um `ObjectionEvent` extraído de uma call real ainda
  referencia `call_id`/`segment_id` reais — sem a `Call` real ao lado ele não vaza texto, mas
  não deve ser commitado como "exemplo" sem revisão).

## Onde o dado real vive localmente

`data/raw/`, `data/interim/`, `data/processed/private/` — todos no `.gitignore`
(`data/raw/`, `data/interim/`, `data/processed/private/`, mais `*.csv`/`*.parquet`/`*.xlsx`
exceto fixtures sintéticas explicitamente permitidas). Ver estrutura recomendada em
`data/README.md`.

## Redaction / sanitization strategy

Objetivo: transformar um caso real em fixture de regressão sintética no futuro, **sem nunca
copiar uma call real e trocar o nome** — texto de transcrição carrega PII indireta (jeito de
falar, referências a lugares/empresas, números específicos) que redação por substituição de
nome não remove.

```
real sample
    ↓
identify essential structural behavior   (o que este caso testa: ex. "objeção de preço no
                                           meio da call, dita por um lead com 2 participantes
                                           mais um observador silencioso")
    ↓
synthesize/redact                        (preferir RECRIAR um equivalente sintético a
                                           redigir o texto original)
    ↓
verify no PII                            (revisão manual — nenhum nome/email/telefone/valor
                                           real, nenhuma frase literal copiada do original)
    ↓
commit synthetic fixture                 (tests/fixtures/ ou evals/datasets/)
```

**Quando recriar em vez de redigir:** sempre que possível. Redação textual (trocar "João
Silva" por "Fulano") preserva a estrutura de frase original, que pode ainda ser
identificável combinada com outro contexto. Recriar do zero (escrever uma frase sintética nova
que exercita o mesmo comportamento) é mais seguro e é exatamente como
`tests/fixtures/synthetic_objection_calls.py` já foi construído.

**Regras por tipo de dado**, quando a recriação total não for viável (ex.: preservar
estrutura de timing real de um transcript ruidoso):

| Tipo | Regra |
|---|---|
| Nomes | Nunca reusar nome real, nem parcial. Usar nome sintético genérico. |
| Emails | Nunca reusar. Usar domínio sintético (`exemplo.test`). |
| Telefones | Nunca reusar, nem parcialmente (DDD real + resto trocado ainda é PII parcial). |
| Empresas | Nunca reusar nome real de empresa do lead. |
| Valores monetários | Trocar por valor sintético de mesma ordem de grandeza, nunca o valor exato. |
| URLs | Remover ou substituir por placeholder — nunca manter URL real (pode conter token). |
| IDs | Nunca reusar id externo real (source_id, meeting_id, deal external_id) — gerar novo. |
| Datas | Pode generalizar (mesmo dia da semana/hora aproximada) sem manter timestamp exato se a data em si for identificável combinada com outro dado público. |
| Texto livre (transcript, notas) | Recriar, não redigir — ver acima. |

## Escopo desta task

Este documento define a fronteira técnica. Autorização de uso do dado em si (se a empresa
parceira permite que estas calls/deals sejam usados de qualquer forma pelo AI Closer) é
decisão humana separada — ver `docs/context/HUMAN_DECISIONS.md`.
