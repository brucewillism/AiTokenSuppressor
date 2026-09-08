# ROUND_2_REPORT.md — AI Token Suppressor

**Data:** 2026-09-07  
**Sem commit / sem push / sem remoção de código.**  
**Contrato:** pré-requisito v1.1 — ver aviso abaixo.

---

## Aviso — contrato v1.1

`docs/ECOSYSTEM_CONTRACT.md` neste repo **ainda está em v1**.  
`00-CONTRATO-COMPARTILHADO.md` contém o **patch** v1→v1.1 com a instrução: *“Nenhum agente aplica este patch sozinho. Você aplica.”*  
Não apliquei o patch (restrição + texto do patch). **Aplique você nos quatro repos e rode o hash check** antes da próxima rodada.

---

## 1. JUSTIFICATION corrigido — duas decisões

Arquivo: `docs/JUSTIFICATION.md` (atualizado).

| Decisão | Conteúdo | Status | Depende de Ollama? |
|---------|----------|--------|--------------------|
| **A** | Serviço vs biblioteca | **FECHADA → biblioteca na E.D.I.T.H.** | **Não** |
| **B** | Limiar de bypass (tokens) | **ABERTA** — config da E.D.I.T.H. | **Sim** (curva) |

**Por que A está fechada sem Ollama:** compressão 16k ≈ **32 ms** in-process; hop HTTP custa ≥ isso e a VPS nem respondeu (RTT inatingível). Serviço cujo round-trip custa o trabalho não se justifica.

**Erro da Fase 0 admitido:** trateí A e B como uma coisa só e “fiquei parado” no Ollama. Corrigido.

**Erro de qualidade da Fase 0 admitido:** Jaccard 0,84 e “risco 0% sem LLM-judge” **não medem qualidade**. Retirados como prova.

---

## 2. Avaliação de qualidade por acerto (Rodada 2)

### Tentativa neural (modelo)

| Item | Valor |
|------|--------|
| Modelo tentado | Groq `llama-3.1-8b-instant` |
| Casos | 28 × 3 modos = 84 calls |
| Resultado | **HTTP 401 Unauthorized em 100%** |
| Artefato | `docs/phase0/quality_accuracy.json` |
| OpenAI | Probe bloqueado pela política do ambiente (não reenviado) |

**Não há taxa de acerto neural válida nesta rodada.** Reportar 0% seria mentir (é falha de auth, não de compressão).

### Juiz oráculo (fato verificável no contexto)

Para perguntas com resposta no texto, um extrator perfeito acerta **sse** a substring esperada sobrevive à compressão. Em compressão por deleção/minify, isso **é** a taxa de perda de informação crítica.

| Métrica | Valor |
|---------|--------|
| Casos | **28** |
| Juiz | `oracle_substring_in_context` |
| Acerto contexto completo | **100%** |
| Acerto após compressão `balanced` (naive) | **100%** |
| Acerto com `must_preserve` simulado | **100%** |
| **Taxa de perda de info crítica** (full ok → compressed fail) | **0%** |
| Falhas de `must_preserve` quando houve perda | **0** (não houve perda) |
| Ratio médio tokens | **0,43** |
| Artefato | `docs/phase0/quality_oracle.json` |
| Script | `scripts/phase0_quality_oracle.py` |

`must_preserve` foi **simulado** (bloco crítico fora do compressor) — a API pública ainda não existe no `CompressionService`. O teste valida o *desenho*, não um parâmetro de produção.

### Limite honesto do oráculo

Oráculo **não** detecta paráfrase ruim nem alucinação do modelo. Só responde: “o número/nome ainda está no contexto?”. Com neural judge offline, é a melhor evidência disponível; **não** encerra o debate de qualidade até um modelo autenticado rodar os 3 modos.

---

## 3. Inventário de autoridade

Arquivo: `docs/AUTHORITY_INVENTORY.md`

Destinos dominantes:

- **REMOVER:** LiteLLM, proxies `/v1/*`, router de modelo, cost optimizer como decisor, Celery, React, Nginx ATS, Prometheus, Grafana, Flower, Ollama client como dono.
- **DESLIGAR / MIGRA:** Hierarchical Memory, Context Graph (estado), MemoryService, RAG store.
- **VIRA BIBLIOTECA:** compressão, Quality Guard, token budgeting (+ Context Manager / fingerprint como sem-estado).

**Context Graph / Adaptive RAG:** ~174 e ~212 linhas — regex+NetworkX em memória de processo e RAG pgvector clássico; nomes maiores que o código.

---

## 4. ADR da biblioteca

Arquivo: `docs/ADR-005-biblioteca.md`

- API: `compress(context, target_tokens, must_preserve) -> CompressionResult`
- ~**800–1500** LOC
- Some: pgvector, Celery, Postgres, LiteLLM, FastAPI na lib
- Cache: **EDITH decide**; lib só fingerprint/similarity; nunca auto-hit em `compress`
- Isolamento `user_id` + testes; FINANCIAL/PERSONAL sem log de content na lib
- Migração: extrair pacote → EDITH chama in-process → desligar superfície de serviço

---

## 5. Prefill Ollama

Arquivo: `docs/PREFILL_CURVE.md` — **BLOQUEADO** (Ollama down).  
Não segura Decisão A nem o inventário.

---

## 6. Estimativa honesta — quantas linhas sobrevivem?

| Cenário | Sobrevive |
|---------|-----------|
| Biblioteca compressão + guard + tokens (+ trim/fingerprint) | **~15–25%** do backend de serviços (~800–1500 LOC) |
| Gateway / segundo cérebro / painel / workers / monitoring | **~0%** |
| Se neural judge futuro mostrar perda crítica alta **e** must_preserve falhar | **quase nenhuma** — só contagem de tokens na EDITH |

**Resposta direta:** a maior parte deste repositório **não deveria sobreviver** como produto. O que vale a pena é um núcleo pequeno de compressão sem estado. O resto é infra de um serviço que a Decisão A já invalidou, ou memória/RAG/roteamento que pertencem à E.D.I.T.H.

Se a resposta for “quase nenhuma” no sentido de *produto ATS*: **sim — quase nenhuma da superfície atual**. O núcleo de 1k linhas ainda justifica existir **como lib**, não como este monólito.

---

## Entregáveis desta rodada

| Arquivo | Status |
|---------|--------|
| `docs/JUSTIFICATION.md` | Corrigido (A/B separados) |
| `docs/phase0/quality_accuracy.json` | Neural — 401 |
| `docs/phase0/quality_oracle.json` | Oráculo — 0% perda crítica |
| `docs/AUTHORITY_INVENTORY.md` | Feito |
| `docs/ADR-005-biblioteca.md` | Feito |
| `docs/PREFILL_CURVE.md` | Bloqueio documentado |
| `docs/ROUND_2_REPORT.md` | Este arquivo |
| `docs/ECOSYSTEM_CONTRACT.md` v1.1 | **Pendente de você** |

---

## Não feito (proibido nesta rodada)

- Desligar/remover código  
- Implementar a biblioteca  
- Commit / push  
- Alterar o contrato  
