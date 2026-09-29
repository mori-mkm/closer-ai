# Synthetic Calibration Cases v0.1

**Sintético.** Nenhum trecho vem de call real; nenhuma pessoa, empresa, Deal, contato ou resultado
comercial real. Calibration kit **v0.1** (ids `CALnn` são deste kit, não do kit v0).

Anote com a [guideline v0.1](../OBJECTION_ANNOTATION_GUIDELINE_V0_1.md) e o
[template v0.1](ANNOTATION_TEMPLATE_V0_1.md). **Não abra `REFERENCE_ANSWERS_V0_1.md` antes de submeter
todas as anotações.**

Formato:

- `call_id`: `CALnn`.
- `segment_id`: `CALnn_Sii`, onde `ii` = `segment_index` (contíguo a partir de 0, como na Canonical Call).
- `speaker_role`: `lead`, `closer` ou `other`. Cada call tem no máximo um participante por papel;
  `speaker_id` = `CALnn_LEAD` / `CALnn_CLOSER` / `CALnn_OTHER`.
- `segment_sequence_hash`: calculado pela serialização canônica do contrato `ObjectionEpisode` §11
  (`[segment_id, segment_index, speaker_id, speaker_role, sha256(texto)]` por segmento), sobre o texto
  exatamente como aparece abaixo. Copie-o para o template; ele identifica a segmentação anotada.
- Um segmento marcado `[trecho inaudível]` é parte do texto da call, não comentário do kit.

---

## CAL01

- call_id: `CAL01`
- segment_sequence_hash: `42cafed6c4383da67f4a7d3e85297c504ae63808902ac6a22ca6ec8a65768a46`

| segment_id | segment_index | speaker_role | text |
|---|---|---|---|
| CAL01_S00 | 0 | closer | Pelo que vimos, a plataforma cobre matrícula, cobrança e agenda das turmas. Podemos começar a implantação no mês que vem? |
| CAL01_S01 | 1 | lead | Até julho a diretoria só libera o que for da migração do financeiro; o resto fica na fila. |
| CAL01_S02 | 2 | closer | Entendo. Podemos deixar a implantação agendada para agosto, com o valor de hoje garantido. |
| CAL01_S03 | 3 | lead | Agosto funciona para nós. |
| CAL01_S04 | 4 | closer | Ótimo. Sobre o treinamento: prefere turmas ao vivo ou aulas gravadas para os professores? |
| CAL01_S05 | 5 | lead | Gravadas. Os professores têm horários muito diferentes. |
| CAL01_S06 | 6 | closer | Perfeito, deixo tudo gravado na primeira semana. |
| CAL01_S07 | 7 | lead | Ah, lembrei de uma coisa: em agosto acontece a auditoria anual da rede. Antes de setembro a gente não consegue começar nada. |
| CAL01_S08 | 8 | closer | Sem problema, passamos o início para setembro. |
| CAL01_S09 | 9 | lead | Setembro dá. |
| CAL01_S10 | 10 | closer | Combinado, te mando o cronograma. |

---

## CAL02

- call_id: `CAL02`
- segment_sequence_hash: `a57a1003e0b2266d5a4ef69b2ee49f46056a11e818a12af4c86f6962d526adc3`

| segment_id | segment_index | speaker_role | text |
|---|---|---|---|
| CAL02_S00 | 0 | closer | Para os três consultórios, a licença fica em 1.290 por mês, e cada usuário além de cinco custa 90. |
| CAL02_S01 | 1 | lead | E no plano anual sai por quanto? |
| CAL02_S02 | 2 | closer | No anual a licença cai um pouco; posso detalhar. |
| CAL02_S03 | 3 | lead | Olha, para a licença a gente tinha reservado bem menos do que isso, e cada usuário extra ainda encarece mais. |
| CAL02_S04 | 4 | closer | Na licença consigo chegar a 990 no contrato anual. |
| CAL02_S05 | 5 | lead | Com esse desconto a licença fica ok. Os usuários extras é que continuam pesando demais pra gente. |
| CAL02_S06 | 6 | closer | Vou ver com o financeiro o que dá para fazer nos usuários extras e te retorno até sexta. |
| CAL02_S07 | 7 | lead | Combinado. |

---

## CAL03

- call_id: `CAL03`
- segment_sequence_hash: `a9bf9603717dd48a1ab8c68e5b1e68a038fe901ade1b2b486ac94703467c67df`

| segment_id | segment_index | speaker_role | text |
|---|---|---|---|
| CAL03_S00 | 0 | closer | Tem cliente que estranha o valor na primeira reunião, mas depois vê o tempo que economiza. |
| CAL03_S01 | 1 | lead | Quanto custa a licença para cinco usuários? |
| CAL03_S02 | 2 | closer | Para cinco usuários são 750 por mês. |
| CAL03_S03 | 3 | lead | Quando abrimos o escritório, esse tipo de sistema estava fora do nosso alcance. Hoje o orçamento comporta. |
| CAL03_S04 | 4 | lead | Se vocês cobrassem por nota emitida, aí complicaria. Mas pelo que entendi é valor fixo, né? |
| CAL03_S05 | 5 | closer | É fixo, sim. E como vocês lançam as notas hoje? |
| CAL03_S06 | 6 | lead | Manualmente. Treinar a equipe em sistema novo sempre dá um trabalhinho, né. |
| CAL03_S07 | 7 | closer | A gente faz esse treinamento junto com vocês. |
| CAL03_S08 | 8 | lead | Estamos vendo outra proposta também, só para ter base de comparação. |
| CAL03_S09 | 9 | lead | E com o sistema de folha que a gente usa, conversa? |
| CAL03_S10 | 10 | closer | Temos conector pronto; ele sincroniza todo dia à noite. |
| CAL03_S11 | 11 | lead | Vou mostrar a proposta para a minha sócia, e o nosso advogado dá uma olhada no contrato antes de assinar. |
| CAL03_S12 | 12 | closer | Perfeito. Posso te ligar na semana que vem? |
| CAL03_S13 | 13 | lead | Deixa que eu te procuro quando der; manda o material por e-mail. |

---

## CAL04

- call_id: `CAL04`
- segment_sequence_hash: `48f6edda11e56e144d115f56a448a56a568d8f05725b6d7af1658499d1979f11`

| segment_id | segment_index | speaker_role | text |
|---|---|---|---|
| CAL04_S00 | 0 | closer | Para as quatro unidades, o contrato anual fica em 86 mil. |
| CAL04_S01 | 1 | lead | Eu gostei bastante. Só que compra desse porte passa pelo conselho da rede, e eu não posso comprometer a empresa sem a assinatura deles. |
| CAL04_S02 | 2 | closer | Posso montar uma apresentação com os números para você levar ao conselho. |
| CAL04_S03 | 3 | lead | E você acha que o conselho aprova? |
| CAL04_S04 | 4 | closer | Com o retorno que mostramos, acredito que sim. |
| CAL04_S05 | 5 | lead | Tá bom. |
| CAL04_S06 | 6 | closer | Te mando a apresentação amanhã. |
| CAL04_S07 | 7 | lead | Ok, obrigado. |

---

## CAL05

- call_id: `CAL05`
- segment_sequence_hash: `2ee44fa49fc1b970a1a5b5fe68ae9afd058185d528dbbe177781b374770564aa`

| segment_id | segment_index | speaker_role | text |
|---|---|---|---|
| CAL05_S00 | 0 | closer | São 2.400 por mês, com relatórios automáticos para todos os clientes da agência. |
| CAL05_S01 | 1 | lead | Pelo que isso entrega, o preço não se justifica pra gente. O modelo de relatório que montamos internamente cobre o que os clientes pedem. |
| CAL05_S02 | 2 | closer | Hoje vocês gastam umas trinta horas por mês montando esses relatórios; o sistema devolve esse tempo. |
| CAL05_S03 | 3 | lead | Pode até ser, mas para o nosso volume não compensa trocar. |
| CAL05_S04 | 4 | closer | Entendi. Posso te mostrar o módulo de agendamento de posts? |
| CAL05_S05 | 5 | lead | Pode. |

---

## CAL06

- call_id: `CAL06`
- segment_sequence_hash: `435c4176e1d7e2182da2475e62e275fe5e5bfea68565f6d4cf3e61b70bfc674a`

| segment_id | segment_index | speaker_role | text |
|---|---|---|---|
| CAL06_S00 | 0 | closer | A proposta inclui prontuário, agenda e estoque, por 3.800 por mês. |
| CAL06_S01 | 1 | lead | Olha, do jeito que está, o valor pesa demais pra gente, e além disso não sobra ninguém aqui para levar os dados antigos para o sistema novo. |
| CAL06_S02 | 2 | closer | A migração fica toda por nossa conta; a equipe de vocês não precisa fazer nada. |
| CAL06_S03 | 3 | lead | Se vocês fazem a migração, isso deixa de ser problema. |
| CAL06_S04 | 4 | closer | E no valor, consigo 10% de desconto no pagamento anual. |
| CAL06_S05 | 5 | lead | Mesmo com 10%, são quase 3.500 por mês. Onde uma clínica do nosso tamanho arruma isso todo mês? |
| CAL06_S06 | 6 | closer | Muitas clínicas do seu porte pagam e recuperam o valor no primeiro ano. |
| CAL06_S07 | 7 | lead | Hum. |
| CAL06_S08 | 8 | closer | Vamos ver a agenda, então? |

---

## CAL07

- call_id: `CAL07`
- segment_sequence_hash: `2a5b3d45a8e564e2915cbef7dee98bbaecf1103c82454836553a26f7cf289192`

| segment_id | segment_index | speaker_role | text |
|---|---|---|---|
| CAL07_S00 | 0 | closer | Com o volume de pedidos de vocês, a plataforma fica em 5.200 por mês. |
| CAL07_S01 | 1 | lead | É um investimento e tanto, hein. |
| CAL07_S02 | 2 | closer | É. Deixa eu te mostrar como fica o painel de pedidos. |
| CAL07_S03 | 3 | lead | Legal, o painel é bem claro. |
| CAL07_S04 | 4 | closer | Conseguimos começar a configuração já no mês que vem? |
| CAL07_S05 | 5 | lead | A gente vê isso depois. |
| CAL07_S06 | 6 | closer | Tem alguma data que funcione melhor? |
| CAL07_S07 | 7 | lead | Com esse [trecho inaudível] fica complicado pra gente fechar. |
| CAL07_S08 | 8 | closer | Desculpa, cortou. Pode repetir? |

---

## CAL08

- call_id: `CAL08`
- segment_sequence_hash: `79c6441e3449990b77ebde71e120fed15972b9b090e1018c9964b454579ea962`

| segment_id | segment_index | speaker_role | text |
|---|---|---|---|
| CAL08_S00 | 0 | lead | Qual a diferença de vocês para o sistema que a gente usa hoje? |
| CAL08_S01 | 1 | closer | Principalmente a automação de prazos e a busca de publicações. |
| CAL08_S02 | 2 | lead | Entendi. Vou ser sincero: o escritório roda nesse sistema desde o primeiro dia, a equipe domina, e a gente não vai sair dele. |
| CAL08_S03 | 3 | closer | A migração é gratuita e fazemos em uma semana. |
| CAL08_S04 | 4 | lead | Não é questão de custo nem de trabalho. Estamos bem com o que temos. |
| CAL08_S05 | 5 | closer | Entendo. Posso pelo menos te mandar um comparativo? |
| CAL08_S06 | 6 | lead | Pode mandar. |

---

## CAL09

- call_id: `CAL09`
- segment_sequence_hash: `aa94b8700fe0ff01f6d3124f8a354c54e7c19a7a2acd4374961b86da8832e7ac`

| segment_id | segment_index | speaker_role | text |
|---|---|---|---|
| CAL09_S00 | 0 | closer | O sistema substitui o cadastro e o faturamento que vocês fazem hoje. |
| CAL09_S01 | 1 | lead | Quem tocaria essa troca? A equipe já está no limite com o dia a dia; sem alguém dedicado a isso, não tenho como seguir. |
| CAL09_S02 | 2 | closer | A migração fica toda com a nossa equipe, em etapas. |
| CAL09_S03 | 3 | lead | Em quantas etapas? E quem da nossa equipe precisaria acompanhar cada uma? |
| CAL09_S04 | 4 | closer | São três etapas, e só a coordenadora participa, uma hora por etapa. |
| CAL09_S05 | 5 | closer | Vou te mandar o cronograma com as etapas. |
| CAL09_S06 | 6 | lead | Ok. |

---

## CAL10

- call_id: `CAL10`
- segment_sequence_hash: `fe4fcaf6bd3171b94c181bf636eeac571a4ccd0f85c9fd9db4174f744839e01f`

| segment_id | segment_index | speaker_role | text |
|---|---|---|---|
| CAL10_S00 | 0 | closer | O serviço de manutenção cobre as doze lojas, com visita mensal. |
| CAL10_S01 | 1 | lead | Vou ser direto: eu tenho uma regra, só compro de quem também compra da gente. Vocês não são nossos clientes, então fica difícil. |
| CAL10_S02 | 2 | closer | Entendo. Posso ver com o nosso time se há interesse em conhecer o serviço de vocês. |
| CAL10_S03 | 3 | lead | Enquanto isso não acontecer, eu não fecho. |
| CAL10_S04 | 4 | closer | Certo. Mudando de assunto: as lojas abrem aos domingos? |
| CAL10_S05 | 5 | lead | Só as de shopping. |
| CAL10_S06 | 6 | closer | Ótimo, isso ajuda a montar a escala. |
| CAL10_S07 | 7 | lead | Outra coisa: a verba de manutenção deste ano já acabou. Só em março eu teria como pagar. |
| CAL10_S08 | 8 | closer | Podemos agendar o início para março. |
| CAL10_S09 | 9 | lead | Março funciona. |

---

## CAL11

- call_id: `CAL11`
- segment_sequence_hash: `f824fd66f6981abf8a702239fada42c6ff44caedbec2adb35c95bbb640aaffec`

| segment_id | segment_index | speaker_role | text |
|---|---|---|---|
| CAL11_S00 | 0 | closer | O contrato é de 24 meses, com pagamento anual antecipado. |
| CAL11_S01 | 1 | lead | Aqui tem um problema: pelas normas do departamento de compras da mantenedora, contrato com prazo mínimo acima de doze meses nem entra na análise. |
| CAL11_S02 | 2 | closer | Fazemos o contrato de doze meses, sem problema. |
| CAL11_S03 | 3 | lead | Doze meses a gente consegue assinar. |
| CAL11_S04 | 4 | closer | E o pagamento anual antecipado, tudo certo? |
| CAL11_S05 | 5 | lead | Antecipado não. Pagar o ano todo adiantado não cabe no nosso fluxo de caixa. |
| CAL11_S06 | 6 | closer | Pode ser mensal, mesmo valor. |
| CAL11_S07 | 7 | lead | Mensal fica bom. |
| CAL11_S08 | 8 | closer | Então fechamos doze meses, mensal. Te mando a minuta. |

---

## CAL12

- call_id: `CAL12`
- segment_sequence_hash: `67f0bb0f64e87afc23386af0dbeeeb785e420e4751d3727dabeb7bcafa363d16`

| segment_id | segment_index | speaker_role | text |
|---|---|---|---|
| CAL12_S00 | 0 | lead | Vocês têm algum cliente do nosso tamanho usando? |
| CAL12_S01 | 1 | closer | Temos três distribuidoras com volume parecido. |
| CAL12_S02 | 2 | lead | Anos atrás um fornecedor nos deixou na mão logo depois de fechar, mas vocês vieram bem indicados. |
| CAL12_S03 | 3 | closer | Fico feliz. Quer ver a parte de inventário? |
| CAL12_S04 | 4 | lead | Antes, minha preocupação é outra: no fechamento do mês o volume de pedidos triplica. Se o sistema cair nesse dia, a entrega para — e eu não arrisco isso sem ter certeza. |
| CAL12_S05 | 5 | closer | Nosso sistema aguenta esse volume, pode ficar tranquilo. |
| CAL12_S06 | 6 | other | Desculpa interromper, a internet aqui caiu por um segundo. Vocês estão me ouvindo? |
| CAL12_S07 | 7 | closer | Estamos, sim. |
| CAL12_S08 | 8 | lead | Então, como eu dizia: todo fornecedor fala que aguenta. Sem ver funcionando no nosso volume, eu não fecho. |
| CAL12_S09 | 9 | closer | Entendo. Vou ver como te mostrar isso e te retorno. |
| CAL12_S10 | 10 | lead | Tá. |
