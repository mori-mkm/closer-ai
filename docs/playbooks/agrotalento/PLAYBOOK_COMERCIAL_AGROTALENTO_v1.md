# Playbook Comercial AgroTalento v1 — Mastermind Aliança (para o Live Copilot)

> **Tarefa:** AC-10 / MAT-35 · **Autor:** Gabriel Guarnieri · **Data:** 23/10/2026 · **Status:** v1 para revisão do Matheus
> **Uso:** fonte de verdade de negócio para *Playbook Compliance* (MAT-69) e *Opportunity Detection* (MAT-70).
> **Formato:** cada regra tem ID, classe (OBRIGATÓRIO / RECOMENDADO / OPCIONAL / PROIBIDO), e a pergunta
> "como o sistema saberia, olhando a transcrição, se isso aconteceu?" respondida no campo **Evidência**.

---

## 0. Contexto do negócio (o que o Copilot precisa saber antes de qualquer regra)

### 0.1 O produto
- **Mastermind Aliança AgroTalento** — conselho consultivo de donos do agro conduzido por Miguel Cavalcanti. Ciclo de **12 meses**.
  Não é curso, não é mentoria de massa, não é networking: é uma **sala de decisão** entre pares + plano individual + implementação acompanhada.
- **Promessa em 3 pilares** (vocabulário oficial do deck 2026):
  1. **Lucro Incontestável** — margem, custo por hectare, fluxo de caixa, capital alocado com critério, gestão empresarial.
  2. **Fazenda Autônoma** — dono estratégico fora da operação, pessoas capazes, responsabilidades claras, lideranças formadas, indicadores e rotinas.
  3. **Alavanca do Legado** — governança, harmonia familiar, formação de sucessores, papéis entre pais, filhos e irmãos.
- **Mecanismo** ("por que funciona"): direção individual · implementação · placar · conselho · experiência emprestada · ambiente ("sua régua muda").
- **Sistema Aliança de Implementação** (6 passos): Diagnóstico (reunião estratégica com Miguel) → Plano individual de 12 meses → Projeto prioritário de 6 semanas → Placar semanal → Conselho (curadoria e contraste da sala) → Evidência (Relatório da Primeira Vitória).
- **Ritmo do ano:** reunião estratégica individual + plano; projeto de 6 semanas com placar semanal; mentorias mensais de gestão financeira; análise de mercado (boi e grãos) 2x por mês; **3 grandes encontros presenciais por ano (2 dias cada)** + visitas técnicas a fazendas; encontros online mensais; especialistas convidados; suporte jurídico para sucessão; grupo VIP no WhatsApp com o Miguel; tudo gravado; Botão Vermelho (segunda opinião em 24 h em decisão crítica) + "as 3 pessoas que você precisa conhecer".
- **Garantia de Implementação:** se ao final das 6 semanas não existir evidência concreta de avanço, a equipe continua acompanhando aquele projeto até produzi-la.
- **Filtro de entrada ("nem todo mundo que pode pagar deve entrar")** — é para quem já produz, trata a fazenda como empresa (número, processo, gente) e tem experiência para contribuir. Não é para quem procura fórmula mágica, não quer rever como decide, ou quer "mais um certificado".

### 0.2 Para quem (ICP vigente, regra do Miguel em 19/10/2026)
- **Dentro do ICP:** operação com **4 ou mais pessoas trabalhando fixo** (família que trabalha no dia a dia + contratados; o próprio dono não conta) **E** faturamento estimado **≥ R$ 1 milhão/ano** (~R$ 83 mil/mês). Faturamento **declarado** ≥ R$ 1 mi/ano basta sozinho (22/10/2026).
- **Régua de porte → faturamento (~R$ 83 mil/mês):** leite ~900 L/dia · cria ~400 matrizes · recria ~220 animais vendidos/ano · engorda ~160 terminados/ano · ciclo completo ~260 matrizes · soja ~125 ha · soja+safrinha ~75 ha · café arábica ~19 ha em produção. Armadilhas: "cabeças" sem o sistema (cria × recria × ciclo completo) não é faturamento; integrado (aves/suínos) fatura só o alojamento; café/fruta rendem muito por hectare.
- **Perfis que vêm à call:** dono/produtor (maioria), sucessor assumindo (comum), casal, gestor/consultor que não é dono (não decide: ver DECISION_AUTHORITY), ex-membro/ex-aluno do AgroTalento.
- **Sinais históricos de compra:** 19/20 compradores tinham dor em pelo menos um dos 3 pilares; 18/18 que informaram faturamento estavam acima de R$ 100 mil/mês; 17/20 tinham equipe com 10+ pessoas.

### 0.3 Como a call chega (o que já aconteceu antes)
- Lead vem de formulário (aula / página / workshop), disparo pelo CRM, Diagnóstico do Dono (eventos.agrotalento.com.br/diagnostico-do-dono), indicação ou base de eventos/imersões (Texas, Colorado etc.).
- A pré-venda **não fala de preço, formato, calendário, escassez nem promete o Miguel**. Vende a reunião: "conversa individual, online, ~40–60 min, com um especialista do time do Miguel, para avaliar o fit dos dois lados, sem compromisso".
- Depois de agendar, o lead recebe como "tarefa de casa" o **Diagnóstico do Dono** (se ainda não fez) + o **podcast do Miguel (MF Cast 73)**, e um depoimento em vídeo escolhido pelo tema da dor (8 templates: liderança, financeiro/tributário, eficiência, crescimento, posicionamento, sucessão prática, conflito de gerações, RH).
- O closer recebe um **briefing pré-call** com: dor principal nas palavras do lead, atividade e porte, pessoas na operação, quem decide, origem, histórico (objeção anterior, no-show, proposta) e o que ficou como "Validar em call" (tipicamente faturamento, capacidade de investimento, participação do decisor).
- **Tipos de call observados (139 calls comerciais, jul–out/2026):** primeira call 79%, retorno 10%, reunião com o mentor (Miguel entra) 9%. Duração típica 35–60 min; algumas passam de 1h30.

### 0.4 O que os dados dizem sobre a call de hoje (base para o Copilot priorizar)
Fonte: análise de 139 calls comerciais (AGT-0001..0165, prompt agro-v1, sem CRM; frequência ≠ eficácia).

| Comportamento | Observado | Leitura |
|---|---:|---|
| Dor identificada | 89% | ✅ já acontece |
| Consequência da dor explorada | 28% | ❌ principal lacuna |
| Impacto financeiro quantificado (número do produtor) | 25% | ❌ |
| Prioridade checada | 16% | ❌ |
| Momento / caixa / safra checado | 22% | ❌ (33% das calls têm objeção de caixa/momento) |
| Capacidade de investimento checada antes do preço | 19% | ❌ (37% das calls têm objeção de preço) |
| Quem decide checado | 51% | ⚠️ (38% das calls têm objeção de autoridade) |
| Preço apresentado | 80% (mediana: a 85% do tempo da call) | ⚠️ preço tarde = objeção no último quarto (75% das resistências) |
| Decisão pedida explicitamente | 44% | ❌ |
| Próximo passo com data e hora | 53% | ❌ |
| Argumento de valor com números do produtor | 4% dos argumentos | ❌ (genérico 26%, prova social 27%, conectado à dor 35%) |

---

## 1. Etapas da venda (o que o closer faz e fala na reunião)

Convenção: **E1..E12**. Para cada etapa: objetivo · quando · ações/perguntas esperadas · evidência mínima de cumprimento · sinais de incompleta · regras (ID, classe).
Ordem de referência (deck oficial, 25 min + conversa): **O seu cenário → O que construímos → A sala → Condições e decisão**.
Metodologia de fundo: SPIN (Situação, Problema, Implicação, Necessidade) + GPCT (Goals, Plans, Challenges, Timeline) + BANT para decisor/orçamento/momento.

### E1 · Abertura e contrato da conversa
- **Objetivo:** criar segurança, confirmar quem está na sala e combinar o roteiro ("em algum momento, se não fizer sentido, a gente para").
- **Quando:** minutos 0–5. Em call com Miguel: ele abre com "mundo compartilhado" (ESALQ, região, conhecidos).
- **Ações/perguntas esperadas:**
  - Apresentar-se como time do Miguel Cavalcanti / AgroTalento; confirmar nome e quem mais está presente (cônjuge, filho, sócio).
  - Checar se o lead fez o Diagnóstico do Dono / viu o podcast ou o depoimento enviado; usar o briefing ("vi que você toca [atividade] em [região]…").
  - Combinar a agenda em 4 blocos: seu cenário · o que construímos · a sala · condições e decisão.
  - Permissão para parar se não fizer sentido ("prefiro que a gente diga isso").
  - **Pergunta de partida (oficial):** *"Qual é a decisão mais importante da sua fazenda que você ainda está tentando resolver sozinho?"* (menu: lucro, equipe, gestão, família, sucessão, crescimento).
- **Evidência mínima (transcrição):** closer cita o roteiro/agenda OU pede permissão para perguntar; pergunta de partida feita (ou equivalente "o que te trouxe aqui / o que mais pesa hoje").
- **Sinais de incompleta:** closer vai direto para "deixa eu te explicar o Mastermind"; ninguém confirma quem está na sala; mais de 10 min só de rapport sem pergunta de partida.
- **Regras:**
  - `E1-R1` OBRIGATÓRIO — Fazer a pergunta de partida (decisão/gargalo que está resolvendo sozinho). *Evidência:* pergunta aberta sobre decisão/desafio/gargalo nos primeiros 10 min.
  - `E1-R2` OBRIGATÓRIO — Confirmar quem está presente e seu papel (dono, cônjuge, sucessor, gestor). *Evidência:* closer nomeia/pergunta o papel de cada participante.
  - `E1-R3` RECOMENDADO — Explicitar a agenda em blocos e a permissão para parar. *Evidência:* menção a "próximos X minutos", "quatro pontos", "se não fizer sentido a gente para".
  - `E1-R4` RECOMENDADO — Referenciar o material pré-call (Diagnóstico do Dono, podcast, depoimento). *Evidência:* menção a "diagnóstico", "podcast", "vídeo que te mandei".
  - `E1-R5` PROIBIDO — Dizer o ano de fundação da Aliança (materiais divergem 2014/2015). Use "há mais de uma década", "12 anos de método".

### E2 · Contexto da operação (SPIN-Situação / qualificação de porte)
- **Objetivo:** situar o negócio com **nome e número** e confirmar o ICP (pessoas E faturamento) sem interrogatório.
- **Quando:** minutos 5–15, antes de qualquer apresentação.
- **Ações/perguntas esperadas:**
  - Atividade e sistema (cria / recria / engorda / ciclo completo; leite; grãos; café; integrado ou independente).
  - Tamanho na unidade da atividade (cabeças/matrizes, hectares, litros/dia) e **faturamento** (declarado ou estimado pela régua).
  - **Quantas pessoas trabalham fixo** na operação (regra do Miguel: 4+).
  - Estrutura: quem toca o dia a dia, quem é dono, família envolvida, sociedades, arrendamentos, holding.
  - Quebrar vagueza ("quem é 'todo mundo'?", "pagou ou não pagou?", "quanto sobrou no final?").
- **Evidência mínima:** transcrição contém atividade + tamanho + nº de pessoas (ou faturamento) ditos pelo lead ou confirmados pelo closer.
- **Sinais de incompleta:** closer apresenta o programa sem saber o porte; "cabeças" sem o sistema; não sabe se quem fala é dono.
- **Regras:**
  - `E2-R1` OBRIGATÓRIO — Confirmar atividade + tamanho + pessoas fixas (ou faturamento declarado). *Evidência:* os três slots aparecem na fala do lead ou em pergunta do closer respondida.
  - `E2-R2` OBRIGATÓRIO — Identificar o papel do lead (dono / sucessor / gestor / consultor). *Evidência:* pergunta "você que toca?/é sua a operação?" ou declaração do lead.
  - `E2-R3` RECOMENDADO — Pedir um número que o dono "deveria saber de cor" (lucro por hectare, custo por arroba, margem, resultado do último ano). O silêncio já é diagnóstico. *Evidência:* pergunta com "quanto", "qual a margem", "quanto sobrou".
  - `E2-R4` RECOMENDADO — Para gestor/consultor que não é dono: perguntar cedo quem decide e quem paga (ele ou a fazenda atendida). *Evidência:* pergunta de alçada/decisão antes da apresentação.
  - `E2-R5` PROIBIDO — Perguntar faturamento de forma seca e isolada ("quanto você fatura?") logo no início; chegar ao número pela atividade e porte ou perguntar depois da dor.

### E3 · Dor (SPIN-Problema) — qual pilar e qual o problema específico
- **Objetivo:** sair de "quero melhorar a gestão" para um problema nomeado em um dos 3 pilares.
- **Quando:** minutos 10–20.
- **Ações/perguntas esperadas:**
  - "Dentro disso, qual gargalo mais ocupa sua cabeça hoje?" · "Onde a fazenda trava: financeiro apertado, equipe dependente de você, sucessão adiada?"
  - Pedir exemplo concreto e recente ("me conta a última vez que isso aconteceu").
  - Separar a dor declarada da dor principal (ex.: começa em "comunicação" e revela medo da sucessão, perda de controle, sobrecarga).
  - Em casal/família: dar voz aos dois; separar papel de cada um.
- **Evidência mínima:** problema específico com exemplo, classificado em pilar (lucro/gestão · equipe/autonomia · família/sucessão).
- **Sinais de incompleta:** dor genérica ("quero crescer", "quero organizar"); closer aceita a primeira resposta; só um dos participantes fala.
- **Regras:**
  - `E3-R1` OBRIGATÓRIO — Dor específica identificada e nomeada em um pilar. *Evidência:* fala do lead contendo problema + contexto (quem, onde, quando) e closer resumindo/confirmando.
  - `E3-R2` RECOMENDADO — Aprofundar com pergunta aberta logo após o lead admitir problema ("como isso aparece no dia a dia?"). *Evidência:* ≥ 2 perguntas de aprofundamento seguidas no mesmo tema.
  - `E3-R3` RECOMENDADO — Em dois participantes, perguntar a dor de cada um. *Evidência:* pergunta dirigida ao segundo participante.
  - `E3-R4` PROIBIDO — Rebater dor com aula/apresentação antes de implicar (E4).

### E4 · Impacto e implicação (SPIN-Implicação) — a maior lacuna hoje (28% / 25%)
- **Objetivo:** fazer o lead dizer **o que a dor custa** (dinheiro, tempo, margem, risco, família) e o que acontece se continuar por mais uma safra.
- **Quando:** logo após a dor, antes da apresentação. Nunca pular.
- **Ações/perguntas esperadas:**
  - "Quanto isso custa por ano, no seu número?" · "Quanto vale 1% de margem na sua operação?" · "Quantas horas por semana você gasta apagando incêndio?" · "Quanto custou a última decisão errada / o funcionário que saiu / a safra arrendada parada?"
  - "Se nada mudar, como está isso daqui a 12 meses? E na sucessão, quem assume?"
  - Devolver o diagnóstico e pedir assinatura: *"Estou fazendo a leitura certa do negócio de vocês?"* (tie-down).
  - Pedir licença antes da verdade dura: *"Posso ser muito direto com você?"*
- **Evidência mínima:** pelo menos uma consequência dita pelo lead **e** pelo menos um número do produtor ligado à dor (R$, %, horas, cabeças perdidas, hectares parados).
- **Sinais de incompleta:** só o closer fala de impacto ("isso custa caro"); números genéricos de mercado no lugar dos do lead; pergunta de número feita e não respondida sem retomada.
- **Regras:**
  - `E4-R1` OBRIGATÓRIO — Consequência da dor explorada (o que acontece se continuar). *Evidência:* pergunta "o que acontece se…/como fica daqui a…" + resposta do lead.
  - `E4-R2` OBRIGATÓRIO — Impacto quantificado com número do próprio produtor. *Evidência:* valor numérico (R$, %, horas, cabeças, ha) dito pelo lead em contexto de custo/perda/margem.
  - `E4-R3` RECOMENDADO — Tie-down do diagnóstico ("estou lendo certo?") antes de apresentar. *Evidência:* pergunta de confirmação de leitura + concordância do lead.
  - `E4-R4` RECOMENDADO — Retomar perguntas de número não respondidas antes de seguir. *Evidência:* segunda tentativa da mesma pergunta.
  - `E4-R5` PROIBIDO — Usar afirmações absolutas ("risco zero", "se paga sozinho", "todo mundo está endividado", "garanto que sua margem vai subir").

### E5 · Urgência, gatilho e prioridade (GPCT-Timeline / momento de caixa)
- **Objetivo:** encontrar o relógio real do lead (evento com data) e saber se isso é prioridade **agora** e se o momento de caixa/safra permite. Antecipa 1/3 das objeções (CASH_FLOW_TIMING, OTHER_PRIORITY).
- **Quando:** ainda na descoberta, antes do preço.
- **Ações/perguntas esperadas:**
  - "O que te fez aplicar/aceitar essa conversa **agora**?" · "Sobre o que era a reunião que vocês tiveram? O que estavam buscando?"
  - "Tem alguma data no horizonte (safra, arrendamento voltando, troca de gerente, saída do pai, nascimento, venda de área)?"
  - "Isso é prioridade neste semestre ou está atrás de outro investimento (máquina, terra, reforma, outro curso)?"
  - "Como está o seu caixa nos próximos meses? Entrada de safra quando?" — perguntar **antes** do preço.
- **Evidência mínima:** gatilho ou data declarada pelo lead; prioridade e momento de caixa checados.
- **Sinais de incompleta:** urgência só na voz do closer (vagas, virada de preço); lead diz "não invisto até outubro" só depois do preço.
- **Regras:**
  - `E5-R1` OBRIGATÓRIO — Checar prioridade e momento (caixa/safra/outro investimento) antes do preço. *Evidência:* pergunta com "prioridade", "momento", "caixa", "safra", "quando pretende" antes do primeiro valor em R$.
  - `E5-R2` RECOMENDADO — Localizar o gatilho real com data. *Evidência:* lead cita evento com prazo.
  - `E5-R3` RECOMENDADO — Urgência biográfica (fato do lead) em vez de escassez artificial. *Evidência:* closer liga a urgência a um fato do lead.
  - `E5-R4` PROIBIDO — Inventar escassez. Vagas são limitadas de fato (4–5 por turma) e a virada de preço, quando existe, é comunicada como fato, uma vez.

### E6 · Decisor, buy-in e comprometimento (BANT-Authority)
- **Objetivo:** saber quem assina e trazer essa pessoa para a mesa (2ª cadeira) **antes** do preço; medir prontidão.
- **Quando:** durante a descoberta (mapa de atores) e imediatamente antes das condições.
- **Ações/perguntas esperadas:**
  - Mapa de atores em rajada curta: "É casado? Filhos trabalham na fazenda? Quem é sócio? Quem assina o cheque? Quem precisa concordar?"
  - Se o decisor não está: propor que entre na próxima reunião **com data** (ou reunião com o Miguel), ou oferecer a 2ª cadeira para o cônjuge/sucessor.
  - "Se eu fosse um mágico, quais os três pedidos que você resolveria?" (o lead dita a ementa).
  - "De 0 a 10, quanto você está comprometido em resolver isso?" + metáfora da cirurgia (nota baixa = tratar o medo agora).
  - "Você está disposto a fazer o que eu estou imaginando?" antes do investimento.
- **Evidência mínima:** quem decide está identificado; se ausente, há plano com data para envolvê-lo.
- **Sinais de incompleta:** preço apresentado sem o decisor presente e sem plano; lead diz "vou levar pro sogro/esposa/sócios" e closer só manda material.
- **Regras:**
  - `E6-R1` OBRIGATÓRIO — Identificar quem decide e quem precisa concordar. *Evidência:* pergunta direta sobre decisão/sócio/cônjuge + resposta.
  - `E6-R2` OBRIGATÓRIO — Se decisor ausente: agendar reunião com ele (data/hora) ou oferecer 2ª cadeira **antes** de pedir decisão. *Evidência:* proposta de reunião com o decisor com data OU menção à 2ª cadeira para ele.
  - `E6-R3` RECOMENDADO — Pergunta do mágico / três pedidos. *Evidência:* pergunta "três coisas/pedidos/projetos".
  - `E6-R4` RECOMENDADO — Nota 0–10 de comprometimento antes do preço. *Evidência:* "de 0 a 10".
  - `E6-R5` PROIBIDO — Insistir que o lead "tem autonomia" quando ele declarou limite de alçada/decisão compartilhada.

### E7 · Apresentação da solução (SPIN-Necessidade, ligada à dor)
- **Objetivo:** mostrar o Mastermind como resposta aos **três pedidos** do lead, com checagem bloco a bloco.
- **Quando:** só depois de E3–E6. Tipicamente minutos 20–40.
- **Conteúdo esperado (ordem do deck):** não é curso, é sala de decisão → 3 pilares (começar pelo pilar da dor) → a variável que decide é a capacidade do dono → mecanismo (direção individual, implementação, placar, conselho, experiência emprestada, ambiente) → Sistema de Implementação em 6 passos → "você começa vencendo" (6 semanas, Relatório da Primeira Vitória) → ritmo do ano (individual / implementação / conselho e formação / experiência) → "você não precisa consumir tudo; seu plano define".
- **Ações:** pontuar cada bloco com *"Faz sentido isso aqui?"*; ao mostrar as linhas de formação perguntar *"Onde está o maior potencial: gestão, equipe, sucessão, família, liderança?"*; traduzir cada entrega para a dor dita ("você falou de gerente que não decide; aqui é o pilar Fazenda Autônoma, e o seu projeto de 6 semanas pode ser…").
- **Evidência mínima:** ≥ 3 blocos do deck mencionados (pilares, implementação/6 semanas, ritmo do ano/encontros) **e** ≥ 1 ligação explícita com a dor do lead **e** ≥ 1 checagem "faz sentido?".
- **Sinais de incompleta:** apresentação como lista de benefícios sem ligar à dor; ênfase no pilar errado (financeiro para quem não cuida do financeiro); monólogo > 5 min sem pergunta; lead técnico/consultor sem adaptação.
- **Regras:**
  - `E7-R1` OBRIGATÓRIO — Apresentar os 3 pilares + o projeto de 6 semanas/placar + o ritmo do ano. *Evidência:* termos "lucro incontestável/fazenda autônoma/legado (ou sucessão)", "6 semanas/primeira vitória/placar", "encontros presenciais/mentorias/online".
  - `E7-R2` OBRIGATÓRIO — Conectar ao menos uma entrega à dor dita pelo lead. *Evidência:* frase do closer que repete palavra/termo da dor do lead + entrega.
  - `E7-R3` RECOMENDADO — Checagem a cada bloco ("faz sentido?"). *Evidência:* ≥ 2 checagens com resposta do lead.
  - `E7-R4` RECOMENDADO — Explicar a dedicação de tempo esperada (projeto, ~2 h/semana, encontros) de forma proativa. *Evidência:* menção a horas/semana ou calendário.
  - `E7-R5` PROIBIDO — Apresentar antes de ter dor + impacto (E3/E4) — exceto call de retorno onde isso já foi feito.
  - `E7-R6` PROIBIDO — Prometer resultado específico ("vai dobrar o lucro", "vai aumentar sua margem"). O deck fala em "lucro incontestável" como objetivo, não como garantia.

### E8 · Prova e cases
- **Objetivo:** reduzir dúvida de valor/credibilidade com prova **adequada ao tema do lead**.
- **Quando:** dentro da apresentação (slides "Caso de referência") e ao surgir dúvida de ROI/confiança.
- **Provas aprovadas (do material oficial):**
  - **Roberto Patucci Turci** — lucratividade de **R$ 8.000/ha/ano** na pecuária de corte (pilar Lucro). Antes: já tinha resultado bom, queria dominar o negócio; o que mudou: gestão, processos, pessoas, foco e método.
  - **Osmar Caires** — de **3 para 11 granjas** com estrutura de gestão e time (pilar Fazenda Autônoma).
  - **Sala:** 12 anos de método; +80 membros de 15 estados; +34 imersões presenciais; membros há até 10 anos na sala.
  - **Miguel:** ESALQ/USP, 5ª geração no agro desde 1889, criador da BeefPoint e do AgroTalento, 25+ anos em gestão e liderança no agro, ex-presidente da ASSOCON.
  - **Depoimentos por tema** (vídeos legendados, 8): Leonardo Ramos (liderança / virada de dono), Tatiana Lima (financeiro/tributário), Alaor Ávila (eficiência, "fazer o simples"), Ricardo Santinoni (crescimento/alavancagem), Anita Bufaiçal (posicionamento/comunicação), Matheus Sebben (sucessão prática), Marco Antonio Sebben (conflito de gerações), Euripedes do Carmo Filho (gestão de pessoas/RH).
  - **Frases de membros (deck):** "hoje as fazendas são como uma empresa, tem que ter os departamentos controlados" · "Miguel é muito bom nas provocações, tirando a gente da zona de conforto" · "a gente sai com plano daqui pra executar até o próximo encontro" · "é como se você identificasse outras pessoas vivendo os mesmos conflitos".
- **Evidência mínima:** ≥ 1 case/prova citado, do mesmo pilar da dor principal.
- **Sinais de incompleta:** case de pilar diferente da dor; "um membro pequeno" sem detalhe; prova pedida pelo lead e não trazida; prova genérica ("muitos produtores").
- **Regras:**
  - `E8-R1` RECOMENDADO — Citar ao menos um case do pilar da dor. *Evidência:* nome do case/depoimento + pilar coerente.
  - `E8-R2` OBRIGATÓRIO quando o lead pede prova/referência — trazer case nomeado ou propor enviar o depoimento do tema. *Evidência:* pergunta do lead ("alguém como eu?", "funciona em leite?") seguida de case nomeado.
  - `E8-R3` PROIBIDO — Citar cliente/membro que não existe no material oficial, inventar número de resultado, ou afirmar que um indicador "já é membro" sem confirmação.

### E9 · Condições comerciais (investimento)
- **Objetivo:** apresentar o investimento **cedo o suficiente** (após E7, com decisor presente e comprometimento medido) com ancoragem e todas as condições de uma vez.
- **Quando:** depois de E6/E7, idealmente antes de 70% do tempo da call (hoje a mediana é 85%).
- **Sequência aprovada:**
  1. **Ancoragem de valor (slide "Antes de falar de investimento"):** "Quanto vale 1% de margem? Quanto custa um erro relevante de decisão? Quanto vale uma liderança formada dentro de casa? Quanto custa uma fazenda dependente do dono? Quanto vale evitar um conflito patrimonial? Quanto vale o tempo que você não tem hoje?"
  2. **Ancoragem numérica (padrão Miguel):** o closer **faz ele mesmo** a pergunta do preço ("qual é o investimento?") e ancora alto antes do número (consultoria individual com o Miguel começa em R$ 400 mil; "fica tranquilo, é menos de R$ 200 mil").
  3. **Investimento do ciclo de 12 meses** (ver tabela em §2.1).
  4. **O que está incluído sem custo adicional:** 2ª cadeira (quem decide com você), bônus Mentoria AgroTalento (R$ 7.997), cursos online BeefPoint/AgroTalento + ingressos para eventos abertos (até R$ 5.000).
  5. **Garantia de Implementação** (§2.3) e **próximo passo** (sessão estratégica → curadoria → embarque com projeto de 6 semanas na semana seguinte).
  6. Pergunta de reação: "Como isso cabe para você?" / "O que você precisa decidir?"
- **Evidência mínima:** valor em R$ dito pelo closer + ao menos uma forma de pagamento + 2ª cadeira **ou** bônus + garantia **ou** próximo passo.
- **Sinais de incompleta:** preço sem ancoragem; preço sem perguntar antes sobre caixa/decisor; condições parceladas em várias falas ao longo da objeção (desconto aparece só como reação); lead pergunta "e como funciona o pagamento?" e não recebe resposta completa.
- **Regras:**
  - `E9-R1` OBRIGATÓRIO — Apresentar o investimento na call (salvo decisor ausente com reunião já marcada). *Evidência:* valor em R$ (53/63 mil ou parcelas) dito pelo closer.
  - `E9-R2` OBRIGATÓRIO — Ancorar valor antes do número (perguntas "quanto vale/quanto custa" ou âncora alta). *Evidência:* ≥ 1 pergunta de ancoragem ou menção a valor maior (consultoria individual, R$ 200 mil) imediatamente antes do preço.
  - `E9-R3` OBRIGATÓRIO — Apresentar as formas de pagamento junto com o valor (à vista, 4x, 12x; Pix, cartão, boleto). *Evidência:* "à vista", "parcelas", "12x", "4x", "Pix", "cartão", "boleto" na mesma janela do preço.
  - `E9-R4` OBRIGATÓRIO — Mencionar a 2ª cadeira incluída. *Evidência:* "segunda cadeira", "acompanhante", "traga seu sócio/filho".
  - `E9-R5` RECOMENDADO — Mencionar bônus e garantia na mesma janela. *Evidência:* "mentoria AgroTalento", "cursos", "ingressos", "garantia".
  - `E9-R6` RECOMENDADO — Primeiro preço antes de 70% do tempo da call. *Evidência:* timestamp do primeiro R$ / duração.
  - `E9-R7` PROIBIDO — Abrir a conversa de preço com o desconto. O desconto (quando existir) entra como condição da turma, depois do valor cheio.
  - `E9-R8` PROIBIDO — Dar condição fora da tabela §2.1 sem autorização (registrar "vou confirmar e volto" é permitido).

### E10 · Objeções (ver §4)
- **Objetivo:** tratar cada resistência com a sequência **reconhecer → investigar a causa → responder/reenquadrar → confirmar**; nunca ignorar, nunca "atropelar" com argumento.
- **Evidência mínima:** para cada episódio de resistência, há uma pergunta de causa **ou** reconhecimento antes da resposta, e uma checagem de reação depois.
- **Regras:**
  - `E10-R1` OBRIGATÓRIO — Nenhuma resistência explícita fica sem resposta. *Evidência:* fala do lead classificada como resistência seguida de fala do closer no mesmo tema.
  - `E10-R2` OBRIGATÓRIO — Investigar a causa antes de responder a preço/momento/"vou pensar" ("o que exatamente você precisa avaliar?"). *Evidência:* pergunta do closer entre a objeção e o argumento.
  - `E10-R3` RECOMENDADO — Confirmar se a resposta resolveu ("isso responde?/faz sentido?"). *Evidência:* checagem + reação do lead.
  - `E10-R4` PROIBIDO — Responder objeção com pressão de prazo/vaga antes de investigar a causa.

### E11 · Fechamento (pedir a decisão)
- **Objetivo:** pedir a decisão de forma **explícita e binária**, e abrir o "vou pensar" enquanto ainda está na sala.
- **Quando:** depois de condições + objeções. Em sinal de compra (perguntas sobre parcela, data de início, onboarding, agenda) pedir imediatamente.
- **Ações/perguntas aprovadas:**
  - "Faz sentido a gente seguir? Você quer colocar o pé na peia ou não?"
  - "O que exatamente você precisa pensar e decidir?" (nomear o que trava: medo, dinheiro, cônjuge).
  - Future pacing: "Posso exercitar minha leitura de futuro?" — narrar o lead daqui a 12 meses e as objeções que ele vai se fazer.
  - Recapitular em uma frase os três resultados buscados e as condições acordadas antes do pagamento.
  - Se decisor ausente: fechar a **reunião com o decisor** (data/hora) como fechamento desta call.
- **Evidência mínima:** pergunta de decisão explícita (sim/não, "vamos seguir?", "você entra?") dirigida ao lead.
- **Sinais de incompleta:** closer encerra com "te mando o material"; "vou pensar" aceito sem pergunta; proposta por e-mail no lugar da decisão; pedido de indicações antes do próximo passo.
- **Regras:**
  - `E11-R1` OBRIGATÓRIO — Pedido explícito de decisão quando preço foi apresentado. *Evidência:* pergunta fechada de decisão do closer.
  - `E11-R2` OBRIGATÓRIO — "Vou pensar" sempre seguido de "o que você precisa pensar/avaliar?". *Evidência:* resposta do closer a "pensar/avaliar/analisar" contém pergunta.
  - `E11-R3` RECOMENDADO — Recapitulação final (3 resultados + condições). *Evidência:* fala do closer listando resultados/condições antes do encerramento.
  - `E11-R4` RECOMENDADO — Sinal de compra detectado → pedir decisão na sequência. *Evidência:* lead pergunta sobre parcela/início/onboarding e o closer pede o "sim" em ≤ 2 turnos.
  - `E11-R5` PROIBIDO — Pedir indicações antes de definir decisão ou próximo passo.

### E12 · Próximo passo com data, hora e responsável
- **Objetivo:** nenhuma call termina sem compromisso operacional. "Sem prazo, 'a gente pensa' morre na garagem."
- **Se fechou:** link de pagamento (Pix/cartão/boleto), comprovante para o closer, onboarding (equipe de onboarding, no dia seguinte), entrada no grupo e acessos, **agendamento da reunião estratégica com o Miguel** (define os 3 projetos), envio dos números da operação para a primeira reunião.
- **Se não fechou:** uma destas, **com data e hora**: (a) reunião com o decisor; (b) reunião com o Miguel (call 2 / reunião com o mentor); (c) retorno de decisão com hora ("até às 18h de amanhã você me dá o ok?"); (d) data futura de entrada ancorada ao gatilho do lead (safra, implantação). Material por e-mail/WhatsApp é **complemento**, não próximo passo.
- **Evidência mínima:** data (ou "amanhã/segunda") **e** hora **e** quem faz o quê.
- **Sinais de incompleta:** "te mando a apresentação e a gente se fala"; "qualquer coisa me chama"; retorno delegado à pré-venda sem data; data vaga ("semana que vem").
- **Regras:**
  - `E12-R1` OBRIGATÓRIO — Próximo passo com data e hora combinados na call. *Evidência:* expressão de data + hora na fala do closer ou do lead, confirmada.
  - `E12-R2` OBRIGATÓRIO (se fechou) — Combinar pagamento, comprovante, onboarding e reunião com o Miguel. *Evidência:* menção aos quatro itens.
  - `E12-R3` RECOMENDADO — Closer marca ele mesmo o retorno (não delega à pré-venda). *Evidência:* "eu te chamo/eu te ligo [dia] às [hora]".
  - `E12-R4` PROIBIDO — Encerrar com envio de material como único próximo passo.

---

## 2. Argumentos e condições comerciais (o que pode/deve ser dito)

### 2.1 Investimento e formas de pagamento (vigentes em out/2026 — confirmar a cada turma)

| Item | Condição | Fonte / observação |
|---|---|---|
| **Valor cheio do ciclo de 12 meses** | **R$ 63.000 à vista** ou **12x de R$ 6.800** | Deck "Apresentação Comercial MasterMind" (turma 2026) e página pública |
| **Condição de turma (usada na maioria das calls)** | **R$ 53.000 à vista** (desconto de R$ 10 mil) · **até 4x sem juros** (Pix ou cartão) · **ou 12x de R$ 5.700** (Pix ou cartão) | Convite Seleção jun/2026; recorrente nas calls jul–out |
| **Variantes já praticadas** (exigem autorização) | 12x de R$ 5.300 · 10 parcelas sem juros no boleto/Pix pelo valor cheio · 1ª parcela no cartão + demais Pix/boleto com vencimento alinhado (ex.: dia 25) · dividir a 1ª parcela em duas datas · parcelamento por duas pessoas (sócios dividem) · boleto | Relatórios de call e análise das 165 calls |
| **Meios** | Pix, cartão de crédito, boleto | Idem |
| **2ª cadeira** | **Incluída sem custo adicional**: sócio, filho, cônjuge ou braço direito da mesma operação ("a transformação é mais forte com duas pessoas da mesma operação na mesa"). Já praticado: duas cadeiras pelo mesmo R$ 53 mil à vista | Deck 2026, convite jun/2026 |
| **Bônus** | Mentoria AgroTalento: 1 inscrição cortesia (valor R$ 7.997) · Cursos online BeefPoint e AgroTalento + ingressos para eventos abertos (valor até R$ 5.000) · US$ 500 de desconto em imersão internacional para quem já viajou com o Miguel | Deck e página pública |
| **Vagas** | 4 a 5 por turma ("vagas limitadas para preservar a qualidade da sala") | Deck, convites |
| **Virada de preço** | Quando houver turma com condição promocional encerrando, comunicar uma vez, como fato, com data | Observado nas calls (set–out) |
| **Política de reembolso (página pública)** | Não há reembolso de pagamentos realizados; parcelas devem ser quitadas integralmente | eventos.agrotalento.com.br |

> ⚠️ **A confirmar com Miguel/closers antes de virar knowledge unit:** (1) a condição R$ 53 mil é permanente ou por turma? (2) a 2ª cadeira vale também para o acompanhante nos encontros presenciais (um relatório de jun/2026 fala em "taxa adicional" para levar pai/sogro; o deck de ago/2026 diz "acompanhante incluso sem custo adicional"); (3) existe hoje "garantia de 30 dias com cancelamento das parcelas seguintes" (praticada em jun/2026) além da Garantia de Implementação do deck?

### 2.2 Benefícios que o closer pode/deve mencionar (vocabulário oficial)
- Plano estratégico individual de 12 meses construído com o Miguel (reunião estratégica individual na entrada; em média ~6 reuniões individuais no ciclo).
- Projeto prioritário de 6 semanas com placar semanal e **Relatório da Primeira Vitória**.
- 3 imersões presenciais por ano (2 dias cada) + visitas técnicas a fazendas e empresas.
- Encontros online mensais do grupo; mentorias mensais de gestão financeira; análise de mercado de boi e grãos 2x/mês; workshops; especialistas convidados.
- Conselho consultivo: curadoria individual, "as 3 pessoas que você precisa conhecer", Botão Vermelho (segunda opinião em 24 h em decisão crítica, negociação, crise familiar, problema societário, risco patrimonial).
- Suporte jurídico para sucessão e temas relacionados; Sessão Estratégica de Família com o Miguel (condição da turma ago/2026).
- Grupo VIP no WhatsApp com interação direta com o Miguel; tudo gravado; plataforma com conteúdos e mais de 55 mentores.
- Acesso prioritário a eventos AgroTalento/BeefPoint; comunidade com renovação contínua (membros há até 10 anos).

### 2.3 Garantias e redução de risco
- **Garantia de Implementação (oficial, deck 2026):** "Construímos juntos um projeto viável; você mantém o placar, participa e executa os compromissos; nós acompanhamos e ajudamos a destravar. Se ao final das 6 semanas não existir evidência concreta de avanço, continuamos acompanhando aquele projeto até produzi-la."
- **Garantia de 30 dias** (praticada em jun/2026: cancelamento das parcelas seguintes se não continuar) — **usar só se confirmada para a turma atual** (§2.1).
- Como usar: garantia **depois** de valor construído (dor + confiança); nunca como abertura do preço.

### 2.4 Argumentos de valor aprovados (ordem de força)
1. **Com números do produtor** (o melhor e o mais raro: 4% hoje): "você disse que perde ~15 bezerros/ano e que cada um vale X; só esse projeto…".
2. **Conectado à dor**: "você disse que a fazenda fica dias sem responsável; Fazenda Autônoma é exatamente…".
3. **Prova social nomeada** (Turci R$ 8.000/ha; Caires 3→11; depoimento do tema).
4. **Mecanismo**: "não é curso, é sala de decisão; o custo de decidir sozinho aparece anos depois, no lucro e na mesa de família".
5. **Comparações legítimas**: custo do programa × custo de um gerente/consultor; × um erro de decisão; × consultoria individual com o Miguel (≥ R$ 400 mil).
6. **Genérico/motivacional** (evitar como argumento principal): "vai mudar sua vida", "todo mundo que entra…".

### 2.5 Restrições — o que NÃO oferecer / NÃO afirmar
- Não oferecer **visita presencial do Miguel à fazenda** como parte do programa (não está incluída).
- Não prometer **software de gestão** ou ferramenta própria; o que existe é indicação pela rede e pelo Miguel.
- Não prometer **resultado numérico** (dobrar lucro, X% de margem).
- Não dar desconto além do praticado na turma nem prazo fora da tabela sem autorização ("vou confirmar e te retorno às [hora]").
- Não oferecer o programa a lead **fora do ICP** (menos de 4 pessoas E abaixo de R$ 1 mi/ano) — encaminhar para a porta lateral: Mentoria AgroTalento, cursos, imersões (Texas etc.), UBeef; registrar como "fora de ICP".
- Não vender para quem **não decide e não pagará** (gestor/consultor) sem trazer o dono: a venda é com o dono.
- Não usar "risco zero", "se paga sozinho", "todo mundo está endividado", "garanto".
- Não pedir indicações antes do fechamento/próximo passo.
- Não comparar ou ranquear vendedores na frente do lead; não citar outros leads pelo nome.

---

## 3. Oportunidades que não podem ser esquecidas (contexto do cliente → o que o closer deve apresentar)

Formato: **gatilho detectável na fala do lead → verificação (o closer já falou?) → ação sugerida**. Classe = o que o Copilot faz: AVISO (opportunity detection) ou CHECK (compliance).

| ID | Gatilho na transcrição | Verificar se já foi dito | Ação / argumento |
|---|---|---|---|
| OP-01 | "caixa apertado", "endividado", "safra só entra em…", "não tenho esse dinheiro agora" | Parcelamento (12x), 1ª parcela no cartão + demais Pix/boleto, dia de vencimento alinhado à entrada de caixa, divisão entre sócios | Oferecer forma de pagamento alinhada ao fluxo; perguntar o mês de entrada de caixa; comparar com o custo da dor |
| OP-02 | "não gosto de juros", "à vista fica pesado" | 4x sem juros · 12x sem juros no Pix | Apresentar as duas opções sem juros |
| OP-03 | "preciso falar com minha esposa / sócio / pai / filhos", decisor citado ausente | 2ª cadeira incluída; reunião com o decisor marcada | Convidar o decisor como 2ª cadeira; marcar data/hora da reunião com ele (ou com o Miguel) |
| OP-04 | Casal ou pai e filho na call; "meu filho vai assumir", "estou passando pro meu genro" | 2ª cadeira; pilar Alavanca do Legado; Sessão Estratégica de Família; suporte jurídico para sucessão; depoimentos Sebben | Posicionar sucessão como projeto de 6 semanas; oferecer 2ª cadeira ao sucessor |
| OP-05 | "conflito com irmão/pai", "sociedade", "holding", "inventário", "arrendamento com problema de contrato" | Suporte jurídico; Botão Vermelho; conselho de família | Mencionar suporte jurídico e Botão Vermelho; case Marco Antonio Sebben |
| OP-06 | "não consigo sair da operação", "tudo depende de mim", "gerente não decide", "funcionário saiu" | Pilar Fazenda Autônoma; case Osmar Caires (3→11); depoimento Euripedes (RH) / Leonardo (virada de dono) | Ligar à Fazenda Autônoma e ao projeto de 6 semanas em pessoas |
| OP-07 | "não sei minha margem / custo por arroba / quanto sobra", "não tenho controle" | Pilar Lucro Incontestável; mentoria mensal de gestão financeira; case Turci R$ 8.000/ha; depoimento Tatiana (financeiro) | Pedir o número; ligar à mentoria financeira e ao case |
| OP-08 | "preço do boi / mercado / quando vender" | Análise de mercado de boi e grãos 2x/mês | Mencionar as mentorias de mercado |
| OP-09 | "funciona para alguém como eu? (leite, café, grãos, região, tamanho)" | Case/depoimento do tema; "+80 membros de 15 estados, diferentes culturas" | Trazer case nomeado; propor enviar o depoimento do tema |
| OP-10 | "quanto tempo isso vai tomar?", "não tenho tempo", "tenho filho pequeno" | Dedicação esperada (~2 h/semana no projeto), tudo gravado, plano individual define o que usar | Responder com número de horas e formato dirigido |
| OP-11 | "já fiz curso/mentoria e não apliquei", "sou cético com mentoria" | "Não é curso, é sala de decisão"; placar semanal; Garantia de Implementação; depoimento Leonardo ("era cético") | Diferenciar pelo mecanismo de implementação; garantia |
| OP-12 | "vou pensar", "me manda por escrito/por e-mail" | Pergunta "o que precisa pensar?"; próximo passo com hora | Abrir a objeção; converter em reunião com data (não em e-mail) |
| OP-13 | "já conheço o Miguel", "acompanho há anos", ex-aluno do AgroTalento | Reunião com o Miguel como passo seguinte; Botão Vermelho; sala | Encurtar a apresentação e ir para condições; oferecer reunião com o Miguel |
| OP-14 | Lead pergunta sobre início, onboarding, data do próximo encontro, parcela | **Sinal de compra** | Pedir a decisão agora (E11-R4); informar próximo encontro presencial e início na semana seguinte |
| OP-15 | "tenho outro evento/curso pago agora", "estou terminando outra mentoria" | Entrada ancorada ao término; complementaridade | Perguntar quando termina; propor data de entrada; não apresentar preço "mesmo assim" sem tratar |
| OP-16 | "estou implantando sistema/fazenda nova/reforma" | Projeto de 6 semanas alinhado à implantação | Propor que o 1º projeto seja a própria implantação |
| OP-17 | Lead já viajou com o Miguel (Texas, Colorado, Austrália…) | US$ 500 de desconto em imersão internacional; ponte Texas → Mastermind | Usar a imersão como ponte; mencionar o benefício |
| OP-18 | Lead fora do ICP (< 4 pessoas E < R$ 1 mi/ano) ou não produtor | Porta lateral | Não ofertar o Mastermind; indicar Mentoria AgroTalento / cursos / imersões / UBeef; registrar fora de ICP |
| OP-19 | Lead pergunta "é só o Miguel ou tem outros mentores?" | Especialistas convidados; +55 mentores na plataforma; pares da sala | Responder com a sala + especialistas |
| OP-20 | Lead cita indicação ("fulano me indicou") | Confirmar se o indicador é membro antes de afirmar | Não afirmar que é membro sem confirmação |
| OP-21 | Pedido de visita técnica presencial do Miguel | Não incluída | Dizer que não está no pacote; oferecer visitas técnicas da sala e Botão Vermelho |
| OP-22 | Lead está no Diagnóstico do Dono / mencionou o resultado | Finalizar o diagnóstico com ele; enviar o diagnóstico pronto depois | Usar o diagnóstico como estrutura da descoberta |

---

## 4. Objeções e contornos (contextualizados para a AgroTalento)

Base: 580 episódios em 139 calls; taxonomia objection-v1 (categorias abaixo). Para cada objeção: como aparece · melhor abordagem · o que evitar · perguntas/respostas aprovadas. Regra geral de condução: **reconhecer → investigar a causa → responder ligando à dor/números do lead → confirmar**.
Resolução explícita observada hoje é rara (15/384); as respostas que mais levaram a reação positiva/parcial foram **NEGOCIOU** em condições de pagamento e **REENQUADROU** em fit/tempo; **ADIAR** sem pergunta quase nunca resolve.

### 4.1 Preço / orçamento (PRICE_BUDGET — 37% das calls)
- **Como aparece:** "é um valor considerável", "sai do caixa da fazenda", "não conhecia o valor", "comparei com X que custa menos", "isso é mais do que ganho/pago por…".
- **Melhor abordagem:** (1) perguntar o que o número representa para ele ("em relação a quê?"); (2) voltar ao custo da dor com os números dele (E4); (3) comparar com referências legítimas (gerente, consultor, erro de decisão, 1% de margem); (4) só então condições (4x/12x) e 2ª cadeira (divide com o sócio); (5) checar.
- **O que evitar:** desconto como primeira resposta; mandar material e encerrar; pressionar prazo; "você consegue pagar sim".
- **Aprovadas:** "Quando você diz caro, está comparando com o quê?" · "Você me disse que [dor] custa cerca de [R$ X]/ano. O programa custa menos que isso, parcelado em 12." · "Quanto vale 1% de margem na sua operação?" · "Se o investimento não fosse o ponto, você entraria? Então vamos olhar a forma."

### 4.2 Caixa e momento (CASH_FLOW_TIMING — 34% das calls; a mais difícil hoje)
- **Como aparece:** "agora não, só depois da safra", "não invisto nada até outubro", "estou pagando dívida/reforma/plantio", "ano que vem".
- **Melhor abordagem:** perguntar **antes do preço** (E5); se surgir depois: investigar a data real de entrada de caixa; alinhar parcelamento/vencimento à entrada; mostrar o custo de esperar mais uma safra com números dele; ancorar a entrada a uma data (não "qualquer hora").
- **O que evitar:** apenas reconhecer e marcar retorno vago; reenquadrar sem investigar capacidade; repetir escassez.
- **Aprovadas:** "Quando entra o caixa da safra? Se eu alinhar o vencimento a essa data, muda?" · "O que acontece com [dor] se passar mais uma safra assim?" · "Entrar agora e começar o projeto de 6 semanas antes da safra te deixa em que posição em março?"

### 4.3 Decisor / autoridade (DECISION_AUTHORITY — 38% das calls)
- **Como aparece:** "vou levar pro meu sogro/esposa/sócios/filhos", "minha alçada é até R$ X", "a decisão é do pai", "preciso ver com a empresa".
- **Melhor abordagem:** mapear cedo (E6); oferecer a 2ª cadeira ao decisor; marcar **reunião com o decisor** (ou com o Miguel) com data/hora como fechamento desta call; pedir ao lead o que ele mesmo precisa para recomendar.
- **O que evitar:** apresentar preço sem o decisor e sem plano; insistir que "você decide"; sugerir decidir sem os filhos quando ele quer envolvê-los; mandar material e esperar.
- **Aprovadas:** "Quem mais precisa estar nessa decisão? Vamos marcar com ele(a): terça 10h ou quarta 14h?" · "A segunda cadeira é exatamente para quem decide com você." · "Se fosse só você, qual seria a decisão?"

### 4.4 Encaixe / relevância (FIT_RELEVANCE — 30% das calls)
- **Como aparece:** "não sou eu que faço a gestão", "isso é mais para quem cuida do financeiro", "já faço esse planejamento", "não me vejo no grupo", "sou pequeno", "sou de leite/café/outra região".
- **Melhor abordagem:** reenquadrar pelo pilar certo (quem toca equipe → Fazenda Autônoma; sucessor → Legado); trazer case do tema; redirecionar para o participante certo (cônjuge, sucessor) com a 2ª cadeira; explorar o que ele já faz antes de afirmar que falta visão de fora.
- **O que evitar:** insistir em networking genérico; afirmar capacidade sem mostrar entrega; case "pequeno" sem detalhe.
- **Aprovadas:** "Dos três pilares, qual está mais perto do seu dia a dia?" · "Me conta como você faz esse planejamento hoje; onde ele trava?" · "A sala tem produtores de 15 estados e culturas diferentes; o que muda é o seu plano individual."

### 4.5 "Vou pensar" (NEED_TO_THINK — 27% das calls; quase nunca resolvido hoje)
- **Como aparece:** "vou pensar", "me manda por escrito", "vou analisar com calma", "te respondo semana que vem".
- **Melhor abordagem:** "O que exatamente você precisa pensar e decidir?"; nomear o que trava (medo de não executar, dinheiro, cônjuge); future pacing; prazo com hora e nome; converter "por escrito" em nova reunião curta com data.
- **O que evitar:** aceitar sem pergunta; só pedir prazo; rotular como insegurança (gera defesa).
- **Aprovadas:** "Quando você diz pensar, o que está na balança?" · "Se até amanhã 18h você me dá um ok ou um não, fecho a vaga ou libero para o próximo. Combinado?" · "Posso exercitar minha leitura de futuro?"

### 4.6 Tempo / dedicação (TIME_AVAILABILITY — 25%)
- **Como aparece:** "não tenho tempo", "viajo muito", "tenho filho pequeno", "quando é o encontro presencial?".
- **Melhor abordagem:** separar agenda × prioridade; dizer a dedicação real (projeto ~2 h/semana; encontros gravados; plano define o que usar); mostrar que falta de direção consome mais tempo que o programa; calendário dos encontros.
- **O que evitar:** interpretar "tempo" como duração do contrato; não ter o calendário.
- **Aprovadas:** "O problema é a agenda dos encontros ou a prioridade neste momento?" · "São cerca de 2 horas por semana no projeto; o resto é gravado." · "Quantas horas por semana você perde apagando incêndio hoje?"

### 4.7 Formato / logística (LOGISTICS_FORMAT — 17%; a mais bem resolvida hoje)
- **Como aparece:** horários, local dos encontros, internet, exposição no grupo, "quantas aulas".
- **Melhor abordagem:** responder concreto (recorrência, calendário, gravações, grupo); oferecer alternativas (áudio privado ao mentor, horário flexível).
- **O que evitar:** não ter o calendário; prometer ferramenta que não existe.

### 4.8 Condições de pagamento (PAYMENT_TERMS — 13%; alta resolução quando NEGOCIOU)
- **Como aparece:** "parcela menor", "não gosto de juros", "só consigo pagar depois", "e se eu desistir?".
- **Melhor abordagem:** apresentar a tabela completa; perguntar o valor de parcela possível e a data; variantes autorizadas (1ª no cartão + Pix/boleto, divisão entre sócios, vencimento alinhado); explicar a política de contrato quando perguntado.
- **O que evitar:** "a parcela é despesa da fazenda" como única resposta; não responder à pergunta sobre obrigação contratual.

### 4.9 Dúvida de retorno / valor (ROI_VALUE_DOUBT — 12%)
- **Como aparece:** "vai resolver meu problema de gente?", "e se descobrir que meu negócio é inviável?", "qual o retorno?".
- **Melhor abordagem:** montar a conta com números dele (E4); case do pilar; Garantia de Implementação; explicar o mecanismo (plano individual + projeto + placar).
- **O que evitar:** responder com desconto/2ª vaga; números genéricos de mercado.

### 4.10 Alternativa / concorrente (ALTERNATIVE_COMPETITOR — 10%)
- **Como aparece:** consultoria de RH/financeira, assessoria local, outro curso, "já faço", preferir a viagem (Texas) ao programa.
- **Melhor abordagem:** diferenciar explicitamente (consultoria resolve uma variável; a sala trabalha o dono e o sistema); posicionar como complementar e prioritário; quando o lead prefere a imersão, usar como porta lateral sem desmerecer.
- **O que evitar:** não diferenciar e só sugerir "fala com o Miguel".

### 4.11 Confiança / credibilidade (TRUST_CREDIBILITY — 4%)
- **Como aparece:** "quero conhecer o Miguel antes", "fulano é membro?", "vocês falam em convite mas anunciam aberto", "quem fez meu cadastro?".
- **Melhor abordagem:** transparência (como o lead chegou; seleção + aplicação pública coexistem); oferecer reunião com o Miguel; não afirmar membro que não é.
- **O que evitar:** respostas defensivas; prometer exclusividade que o marketing não sustenta.

### 4.12 Experiência anterior (PRIOR_EXPERIENCE — 5%)
- **Como aparece:** "comprei outro produto e não tive contato com o mentor", "comprei por impulso antes", "fiz programa com tarefas semanais e não aproveitei".
- **Melhor abordagem:** diferenciar formato (projeto, não aulas; reunião individual; ~2 h/semana); respeitar o prazo pedido quando há histórico de compra por pressão.

### 4.13 Outra prioridade (OTHER_PRIORITY — 10%)
- **Como aparece:** eleições, saúde dos pais, outro curso em andamento, evento já pago, viagem.
- **Melhor abordagem:** investigar a restrição real e a data de fim; ancorar entrada a essa data; se o impedimento é luto/doença, pausar com respeito e marcar retorno.
- **O que evitar:** apresentar preço "mesmo assim" sem tratar; escassez/virada de preço como resposta a saúde na família.

### 4.14 Linguagem a evitar em qualquer objeção
"Risco zero" · "se paga sozinho" · "todo mundo está endividado" · "você tem autonomia sim" · "é a última vaga" (sem ser verdade) · "vou mandar o material e você me avisa".

---

## 5. Regras de negócio consolidadas por classe

### 5.1 OBRIGATÓRIO (compliance: o Copilot marca ✅ quando detecta; lista o que falta ao final da etapa)
| ID | Regra | Evidência na transcrição |
|---|---|---|
| E1-R1 | Pergunta de partida (decisão/gargalo resolvido sozinho) | pergunta aberta sobre desafio/decisão nos primeiros 10 min |
| E1-R2 | Confirmar quem está presente e seu papel | nomes/papéis dos participantes |
| E2-R1 | Atividade + tamanho + pessoas fixas (ou faturamento declarado) | os três slots preenchidos |
| E2-R2 | Papel do lead (dono/sucessor/gestor) | pergunta ou declaração |
| E3-R1 | Dor específica nomeada em um pilar | problema + exemplo + confirmação |
| E4-R1 | Consequência da dor explorada | "o que acontece se…" + resposta |
| E4-R2 | Impacto quantificado com número do produtor | R$/%/horas/cabeças/ha do lead ligado à dor |
| E5-R1 | Prioridade e momento (caixa/safra) checados antes do preço | pergunta antes do 1º R$ |
| E6-R1 | Quem decide identificado | pergunta direta + resposta |
| E6-R2 | Decisor ausente → reunião com data ou 2ª cadeira antes de pedir decisão | proposta com data ou menção à 2ª cadeira |
| E7-R1 | 3 pilares + projeto 6 semanas/placar + ritmo do ano | termos oficiais |
| E7-R2 | Pelo menos uma entrega ligada à dor do lead | repetição do termo da dor + entrega |
| E8-R2 | Prova pedida → case nomeado | pergunta do lead + case |
| E9-R1 | Investimento apresentado (salvo decisor ausente com reunião marcada) | valor em R$ |
| E9-R2 | Ancoragem antes do número | perguntas "quanto vale/custa" ou âncora alta |
| E9-R3 | Formas de pagamento junto com o valor | à vista/4x/12x/Pix/cartão/boleto |
| E9-R4 | 2ª cadeira mencionada | "segunda cadeira/acompanhante/traga…" |
| E10-R1 | Nenhuma resistência explícita sem resposta | resistência → fala do closer no tema |
| E10-R2 | Investigar causa antes de responder preço/momento/"pensar" | pergunta entre objeção e argumento |
| E11-R1 | Pedido explícito de decisão (se preço apresentado) | pergunta fechada de decisão |
| E11-R2 | "Vou pensar" → "o que precisa pensar?" | pergunta na resposta |
| E12-R1 | Próximo passo com data e hora | data + hora confirmadas |
| E12-R2 | Se fechou: pagamento, comprovante, onboarding, reunião com o Miguel | os quatro itens |

### 5.2 RECOMENDADO (o Copilot sugere; não penaliza)
E1-R3 agenda e permissão · E1-R4 referenciar pré-call · E2-R3 número "de cor" · E2-R4 gestor: quem decide/paga cedo · E3-R2 aprofundar com aberta · E3-R3 dor dos dois participantes · E4-R3 tie-down · E4-R4 retomar número sem resposta · E5-R2 gatilho com data · E5-R3 urgência biográfica · E6-R3 pergunta do mágico · E6-R4 nota 0–10 · E7-R3 "faz sentido?" por bloco · E7-R4 dedicação de tempo · E8-R1 case do pilar · E9-R5 bônus e garantia · E9-R6 preço antes de 70% do tempo · E10-R3 confirmar resolução · E11-R3 recapitulação · E11-R4 sinal de compra → decisão · E12-R3 closer marca o retorno ele mesmo.

### 5.3 OPCIONAL (depende do perfil / do closer)
- Future pacing ("leitura de futuro") · metáfora da cirurgia · mundo compartilhado (ESALQ, região, conhecidos) · âncora da consultoria individual (R$ 400 mil) · Botão Vermelho e "3 pessoas" como argumento · benefício US$ 500 em imersão · envio de depoimento específico após a call · convite para o próximo encontro presencial como data de embarque · reunião com o Miguel como passo intermediário (quando o lead já conhece e valoriza o Miguel ou pede).

### 5.4 PROIBIDO / NÃO APLICÁVEL
| ID | Regra |
|---|---|
| E1-R5 | Citar ano de fundação (2014/2015 divergem) |
| E2-R5 | Faturamento "seco" na abertura |
| E3-R4 | Rebater dor com apresentação antes de implicar |
| E4-R5 | Afirmações absolutas (risco zero, se paga sozinho, todo mundo endividado, garanto) |
| E5-R4 | Escassez inventada / virada de preço fictícia |
| E6-R5 | Insistir em autonomia que o lead negou |
| E7-R5 | Apresentar sem dor + impacto (exceto retorno) |
| E7-R6 | Prometer resultado específico |
| E8-R3 | Case inexistente / número inventado / "fulano é membro" sem confirmar |
| E9-R7 | Abrir o preço pelo desconto |
| E9-R8 | Condição fora da tabela sem autorização |
| E10-R4 | Pressão de prazo antes de investigar a objeção |
| E11-R5 | Pedir indicação antes do próximo passo |
| E12-R4 | Encerrar só com envio de material |
| N/A-1 | Ofertar o Mastermind a lead fora do ICP ou a não-produtor sem o dono |
| N/A-2 | Prometer visita presencial do Miguel à fazenda, software de gestão, reembolso fora da política |
| N/A-3 | Prometer o Miguel em pessoa em call onde ele não está confirmado |

---

## 6. Notas para o Live Copilot (compliance, oportunidade e gamificação)

- **Checklist por etapa, só positivo.** Decisão da call de 21/10: nada de "menos 10" por gaguejar. O placar sobe quando uma regra OBRIGATÓRIO é cumprida; o que falta aparece como item pendente, não como punição. Sugestão de peso: OBRIGATÓRIO = 3, RECOMENDADO = 1; nota da call = pontos / pontos possíveis (as regras N/A da call saem do denominador, ex.: E12-R2 se não fechou).
- **Tela mínima:** última fala + próximas 1–2 ações. Oportunidades (§3) como *warning* curto ("caixa apertado → ofereça 12x alinhado à safra"). Não mostrar histórico.
- **Ordem esperada (sequência padrão, 30% das calls hoje):** ABERTURA → DESCOBERTA (E2–E5) → QUALIFICAÇÃO (E6) → APRESENTAÇÃO (E7–E8) → PROPOSTA/PREÇO (E9) → OBJEÇÕES (E10) → FECHAMENTO/PRÓXIMO PASSO (E11–E12). Alerta quando E7 começa sem E3/E4 marcados, ou E9 começa sem E5/E6.
- **Marcos de tempo (call de ~45–60 min):** descoberta concluída até ~40% da call; preço até ~70%; últimos 10 min reservados para decisão e próximo passo. Hoje 75% das resistências aparecem no último quarto porque o preço vem a 85%.
- **Detecção de etapa (palavras-âncora, PT-BR):** E2 "cabeças/matrizes/hectares/litros/funcionários/pessoas" · E4 "quanto custa/quanto perde/por ano/margem/se continuar" · E5 "prioridade/momento/safra/caixa/quando" · E6 "esposa/marido/sócio/filho/pai/quem decide/alçada" · E7 "lucro incontestável/fazenda autônoma/legado/6 semanas/placar/encontros presenciais" · E9 "investimento/à vista/parcelas/12x/4x/pix/cartão/boleto/segunda cadeira/bônus/garantia" · E11 "você entra/vamos seguir/fechamos/pé na peia" · E12 "segunda/terça…/às X horas/te ligo/onboarding/comprovante".
- **Sinais de compra (disparar E11-R4):** perguntas do lead sobre parcela, data de início, próximo encontro, onboarding, "como faço para entrar", "pode ser no cartão da empresa?".
- **Pós-call (relatório):** lista de regras cumpridas/pendentes com timestamp; objeções por categoria com resposta e reação; próximo passo registrado (data/hora/responsável). Linguagem para o head: o que fazer na próxima call, não culpa.

---

## 7. Pendências para fechar a v1.1 (decisões de negócio, não de texto)
1. Confirmar tabela de investimento vigente por turma (R$ 63 mil / 12x 6.800 × R$ 53 mil / 4x / 12x 5.700) e quem autoriza variantes.
2. Confirmar 2ª cadeira nos encontros presenciais (incluída × taxa adicional) e política de acompanhante.
3. Confirmar se a "garantia de 30 dias" ainda vale além da Garantia de Implementação.
4. Confirmar lista oficial de cases nomeáveis em call (Turci, Caires + depoimentos) e se há novos de 2026.
5. Confirmar a dedicação de tempo a ser dita (~2 h/semana) e o calendário 2027 de encontros presenciais.
6. Validar com as closers as frases "aprovadas" de §4 (são as já usadas com reação positiva + as do padrão do Miguel).
7. Ligar as regras ao desfecho do CRM (venda ganha/perdida) quando o UpTeam tiver "resultado da reunião" obrigatório (MAT-66), para trocar "frequência" por "eficácia".

---

## Fontes usadas
- Deck "Apresentação Comercial MasterMind" (Mastermind Aliança, turma 2026) · Convite Seleção jun/2026 e ago/2026 · páginas públicas eventos.agrotalento.com.br e mkt.agrotalento.com.br/mastermind-alianca (27/08/2026).
- "O Miguel não vende. Ele pergunta" — 21 perguntas mapeadas em reunião do Miguel (9 fases).
- Relatórios internos de reuniões estratégicas e de fechamento (jun–ago/2026) e análise comercial de call de fechamento (22/06/2026).
- Script de Qualificação (Culture Sales/PCT6), Funil de Follow-up, Sequência Texas, Playbook e Manual Operacional do SDR 2026, Onboarding Aliança, estudo "Plano do Dono 90D".
- Base de qualificação e cérebro da pré-venda (ICP e régua de porte; regra do Miguel 19/10/2026 e atalho 22/10/2026).
- Análise das 165 transcrições (139 calls comerciais, 23/07–14/10/2026): DIAGNOSTICO_AGROTALENTO, PLAYBOOK_AS_IS, PLAYBOOK_TO_BE, episódios de objeção (580) e métricas globais. Nenhuma citação de cliente foi reproduzida neste documento.
