# JUSTIFICATION.md — AI Token Suppressor (Fase 0)

**Data:** 2026-09-07  
**Contrato:** `docs/ECOSYSTEM_CONTRACT.md` v1 (não alterado)  
**Dados brutos:** `docs/phase0/measurements.json`  
**Script:** `scripts/phase0_benchmarks.py`  
**Escopo:** apenas documentação e medições. Sem código de produção. Sem commit.

---

## Veredito em uma frase (corrigido — Rodada 2)

Há **duas decisões**. Só uma estava bloqueada; a outra já estava fechada pelos números da Fase 0.

| Decisão | Status | Dono |
|---------|--------|------|
| **A — serviço vs biblioteca** | **FECHADA → biblioteca na E.D.I.T.H.** | Este projeto / ecossistema |
| **B — limiar de bypass (tokens)** | **ABERTA** até curva de prefill | **E.D.I.T.H.** (config), ATS só fornece a curva |

**Decisão A não depende do Ollama.** Compressão de 16k tokens ≈ **32 ms** in-process; um hop HTTP na rede custa o mesmo ou mais (e o RTT da VPS nem foi mensurável — timeout). Um serviço cujo round-trip custa tanto quanto o trabalho que executa **não se justifica como serviço**.

**Decisão B** é o número “a partir de quantos tokens o prefill economizado supera o custo da compressão”. Isso alimenta `ats: BYPASS|ENABLED` na E.D.I.T.H., não a forma de empacotar o código.

---


## 1. Auditoria de custo

### O que existe hoje no código

| Artefato | O que grava | É gasto real? |
|----------|-------------|---------------|
| `RequestLog.cost_saved_usd` | Estimativa: tokens salvos × taxas estáticas `COST_*` no `.env` | **Não** — é “economia hipotética” |
| LiteLLM `cost_usd` por completion | Custo pontual da chamada (quando litellm calcula) | Parcial — **não** há ledger mensal |
| `/stats` | Agrega `cost_saved_usd` estimado | **Não** é fatura de provider |

**Não há** tabela, export ou dashboard de **USD realmente cobrado** por Groq / OpenAI / Anthropic / Gemini / DeepSeek nos últimos meses.

### Acesso a produção nesta rodada

- `http://191.252.210.60:8105` e `:8100` → **timeout / connection failed** a partir desta workstation.
- Portanto: **não foi possível** puxar `GET /stats?days=90` nem query em `ats_db.request_logs`.

### Conclusão de custo (com todas as letras)

1. **Não há telemetria de gasto real.** O argumento original (“economiza tokens = economiza dinheiro”) **não pode ser sustentado com números de fatura**.
2. Sob **FREE_FIRST** + Ollama local como caminho preferencial da E.D.I.T.H., a maior parte do tráfego **não gera fatura variável de tokens** — comprimir para “economizar dólares” é economizar dinheiro **que não está sendo gasto**.
3. Onde ainda houver provider pago (allowlist `no_train` para PERSONAL/FINANCIAL, ou DEEP em cloud), a economia de tokens **pode** importar — mas isso é **fração do tráfego**, e a **decisão de provider é da E.D.I.T.H.**, não do ATS.
4. **Instrumentação necessária** (para a E.D.I.T.H. / Control Center, não como autoridade do ATS):  
   `provider`, `model`, `tokens_in`, `tokens_out`, `billed_cost_usd`, `trace_id`, `sensitivity`.  
   *Não implementado nesta fase* (proibido código de produção na Fase 0).

**O argumento de custo, como justificativa de existência deste serviço, está invalidado até prova em contrário.**

---

## 2. Benchmark de prefill (Ollama)

### Status da medição

| Alvo | Resultado |
|------|-----------|
| `http://127.0.0.1:11434` | **unavailable** — connection failed |
| Modelo planejado | `llama3.2:3b` (`OLLAMA_MODEL`) |
| Tamanhos planejados | 500, 2.000, 8.000, 16.000, 32.000 tokens |

**Curva TTFT vs tokens: NÃO MEDIDA nesta rodada.**

### Como reproduzir (obrigatório antes de fechar limiar EDITH)

```bash
# Com Ollama no ar:
set OLLAMA_BASE_URL=http://HOST:11434
set OLLAMA_MODEL=llama3.2:3b
cd backend
python ../scripts/phase0_benchmarks.py
```

O script grava `ollama_prefill.points[]` com `ttft_proxy_ms` (via `prompt_eval_duration`) e calcula breakeven vs p95 de compressão.

### Ponto de equilíbrio = Decisão B (só E.D.I.T.H.)

Sem curva real, **não há limiar científico**. Isso **não bloqueia** a Decisão A.

| Campo | Valor | Confiança |
|-------|-------|-----------|
| `bypass_below_tokens` | a entregar em `docs/PREFILL_CURVE.md` quando Ollama estiver no ar | — |
| Chute antigo (2000) | **retirado como “limiar do projeto”** — era misturar Decisão A com B | — |

O argumento de latência/prefill continua sendo o **único candidato** a justificar *quando* comprimir (Decisão B). Não justifica *manter um microserviço* (Decisão A).

---

## 3. Benchmark de qualidade (compressão)

### Retificação (Rodada 2)

A Fase 0 reportou Jaccard **0,84** e “risco heurístico **0%**”. Isso **não mede qualidade**.

- Jaccard mede sobreposição de vocabulário. Se os tokens descartados eram exatamente o número que a pergunta pedia, o modelo erra com Jaccard alto.
- “Risco 0% sem LLM-judge” é **ausência de medição** reportada como resultado zero — inválido.

A métrica correta (Rodada 2): **acerto da resposta do modelo** com contexto completo vs comprimido vs comprimido+`must_preserve`. Ver `docs/phase0/quality_accuracy.json` e `docs/ROUND_2_REPORT.md`.

### Medição Fase 0 (somente compressão estrutural — não usar como prova de qualidade)

| Métrica | Valor | Uso legítimo |
|---------|-------|----------------|
| Casos | 25 | smoke de ratio |
| Ratio médio | **0,42** | economia de tokens |
| Jaccard | **0,84** | **não** usar como qualidade |

---

## 4. Custo do round-trip de compressão

### A) In-process (medido — lower bound sem rede)

| Tokens in | p50 ms | p95 ms | mean ms |
|-----------|--------|--------|---------|
| 500 | 0,59 | **1,32** | 1,05 |
| 2.000 | 2,59 | **4,93** | 5,14 |
| 8.000 | 7,63 | **10,28** | 8,20 |
| 16.000 | 24,01 | **32,27** | 28,70 |

Fonte: 7 runs cada, `CompressionService` balanced, sem Ollama.  
Arquivo: `docs/phase0/measurements.json` → `compress_latency_in_process`.

### B) HTTP ponta a ponta (serviço ATS)

| Alvo | Status |
|------|--------|
| `POST http://191.252.210.60:8105/compress` | **unavailable** (connection failed) |

**RTT de rede + serialização + auth + DB/Redis: NÃO MEDIDO.**

Estimativa operacional (não medição): em LAN típica, RTT HTTP adiciona **5–40 ms**; WAN/VPS pode passar de **50–200 ms**. Esse overhead **some** se o ATS virar biblioteca dentro da E.D.I.T.H.

### O serviço se paga em latência?

| Cenário | Compressão | Prefill economizado | Vale a pena? |
|---------|------------|---------------------|--------------|
| Lib in-process @ 2k tokens | ~5 ms p95 | Desconhecido (Ollama off) | Só se prefill save ≫ 5 ms |
| Microserviço + rede @ 2k | ~5 ms + RTT | Desconhecido | **Muito mais difícil** de se pagar |
| Microserviço @ 16k | ~32 ms + RTT | Potencialmente alto | Possível **se** curva Ollama confirmar |

**Hoje:** a compressão em si é **barata**. O **salto de rede de um serviço a mais** é o custo estrutural sob suspeita — e o contrato já coloca Ollama **só na E.D.I.T.H.**, o que favorece lib local ao router, não hop ATS → Ollama.

---

## 5. Recomendação explícita (separada)

### Decisão A — empacotamento: **FECHADA**

**Biblioteca / módulo dentro da E.D.I.T.H.** (não microserviço).

Evidência que fecha A (independente de Ollama):

1. Compressão in-process p95 @ 16k ≈ **32 ms**; @ 2k ≈ **5 ms**.
2. RTT HTTP do serviço **não medido** porque a VPS deu timeout — já isso é evidência de fragilidade operacional de um hop a mais.
3. Em qualquer rede real, RTT ≥ trabalho para prompts médios → serviço não se paga como serviço.
4. FREE_FIRST invalida tese de fatura; autoridade de roteamento neste repo compete com a E.D.I.T.H.

### Decisão B — limiar de bypass: **ABERTA** (insumo EDITH)

Entregar curva em `docs/PREFILL_CURVE.md` quando Ollama estiver disponível.  
**Não segura** inventário, ADR nem redução a biblioteca.

### Opção C (desligar compressão por completo)

Só se a avaliação por **acerto de resposta** mostrar perda crítica inaceitável **e** `must_preserve` falhar. Ver Rodada 2.

---


## 6. Bloqueios e próximos passos (ainda Fase 0 / entrada Fase 1)

| Item | Status |
|------|--------|
| `docs/JUSTIFICATION.md` | **Feito** |
| Medição custo real (fatura) | **Bloqueado** — instrumentar na EDITH / billing |
| Curva prefill Ollama | **Bloqueado** — sem Ollama nesta workstation |
| RTT HTTP ATS produção | **Bloqueado** — VPS inacessível daqui |
| Qualidade LLM-as-judge | **Pendente** — 25 casos heurísticos só |
| Fase 1 `AUTHORITY_INVENTORY.md` | **Não iniciada** (aguardar aceite desta Fase 0) |

### Comando para completar os gaps (operador com Ollama + ATS no ar)

```bash
set OLLAMA_BASE_URL=http://<edith-ollama-host>:11434
set OLLAMA_MODEL=llama3.2:3b
set ATS_URL=http://<ats-host>:8105
set API_KEY=<ats-api-key>
cd backend
python ../scripts/phase0_benchmarks.py
# Atualizar este documento com a curva e o limiar real de bypass
```

---

## 7. Assinatura

| Campo | Valor |
|-------|--------|
| Decisão A | **Biblioteca na E.D.I.T.H.** — FECHADA |
| Decisão B | Limiar bypass — ABERTA (EDITH); ATS entrega curva |
| Confiança em A | **Alta** (latência in-process vs hop de serviço) |
| Confiança em B | **Nula até Ollama** |
| Próximo artefato | Inventário → ADR-005 (Rodada 2) |

