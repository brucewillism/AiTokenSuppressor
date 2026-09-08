# AUTHORITY_INVENTORY.md — o que sobrevive como biblioteca

**Pergunta:** o que deste projeto sobrevive como código de biblioteca **dentro da E.D.I.T.H.?**  
**Não:** o que o microserviço “deveria fazer”.  
**Data:** 2026-09-07 · **Fase 1** · Sem desligar código nesta fase.  
**Contrato:** v1.1 esperado; cópia local em `docs/ECOSYSTEM_CONTRACT.md` ainda pode estar em v1 — ver ROUND_2_REPORT (patch em `00-CONTRATO-COMPARTILHADO.md` não aplicado por agente).

Tamanhos ≈ linhas de código Python no módulo citado (contagem aproximada).

---

## Tabela

| Componente | O que faz de verdade | Guarda estado entre chamadas? | Duplica E.D.I.T.H.? | Destino |
|---|---|---|---|---|
| **LiteLLM** (`litellm_service.py` ~294) | Cliente multi-provider: completion/stream + **fallback ordenado** Groq→OpenAI→Anthropic→… Escolhe provider efetivo. | Não (processo); usa env keys | **Sim — Model Router** | **REMOVER** |
| **Proxy OpenAI** (`/v1/chat/completions`, `proxy_service.py` ~233) | Fala protocolo chat.completions; comprime e **roteia** ao LLM | Não | **Sim — gateway LLM** | **REMOVER** |
| **Proxy Anthropic** (`/v1/messages`, `anthropic_proxy_service.py` ~245) | Idem para Messages API / Claude Code | Não | **Sim** | **REMOVER** |
| **Cost optimizer** (`cost_optimizer_service.py` ~80) | Heurísticas: `should_compress`, `should_use_local`, budget tokens a partir de custo *estimado* | Não | **Sim — decide política** que é da EDITH | **REMOVER** como decisor; opcional extrair `estimate_tokens_cost()` como **sinal** se EDITH quiser — senão **REMOVER** |
| **Contextual routing** (`router_service.py` ~178) | Classifica complexidade/task e **escolhe modelo** (`MODEL_TIERS`, `TASK_MODEL_MAP`) | Não | **Sim — Model Router** | **REMOVER** |
| **Context Graph** (`context_graph_service.py` ~174) | NetworkX **in-memory** por `user_id`: regex de frameworks/DBs + relações. `ingest` + `build_context`. **Não é grafo persistente enterprise** — ~174 linhas, estado de processo | **Sim** (`_graphs` dict) | **Sim — Context Engine / memória** | **DESLIGAR** (estado); não migrar como fonte da verdade. Se EDITH quiser NER regex, reimplementa lá |
| **Hierarchical Memory** (`hierarchical_memory_service.py` ~134) | L1 Redis + L2 `MemoryService`/pgvector + L3 Redis cold; `save`/`build_context` entre requests | **Sim** (Redis+Postgres) | **Sim — memória EDITH** | **MIGRA PARA E.D.I.T.H.** (conceitual) / **DESLIGAR** neste repo |
| **MemoryService** (`memory_service.py` ~189) | CRUD + busca vetorial pgvector / fallback texto | **Sim** | **Sim** | **DESLIGAR** |
| **Adaptive RAG** (`rag_service.py` ~212 + `chunking_service.py` ~146) | Ingest chunks → embeddings Ollama → pgvector; query top-k. Nome “Adaptive” **não** implica adaptação online sofisticada — é RAG clássico com chunk AST opcional | **Sim** (Postgres) | **Sim — retrieval EDITH** | **DESLIGAR** neste repo; chunking AST pode ser **VIRA BIBLIOTECA SEM ESTADO** se EDITH precisar só do splitter |
| **Context Manager** (`context_manager.py` ~151) | Sliding window, trim, remove irrelevantes **dentro da chamada** | Não (por request) | Parcial (orquestração de contexto) | **VIRA BIBLIOTECA SEM ESTADO** (útil dentro de `compress` / prep) |
| **Compressão** (`compression_service.py` ~249 + specialized/dedup ~250) | Motor real: minify, dedup, specialized por tipo, quality merge; Ollama opcional para summarize/semantic_reduce | Não (exceto se Ollama side-effect) | Não (primitiva) | **VIRA BIBLIOTECA** (núcleo) |
| **Quality Guard** (`quality_guard_service.py` ~130) | Protege mensagens críticas / restaura system | Não | Não | **VIRA BIBLIOTECA** (essencial p/ `must_preserve`) |
| **Semantic Loss** (`semantic_loss_service.py` ~76) | Similaridade via embeddings Ollama + score | Não (chama Ollama) | Parcial (qualidade) | **VIRA BIBLIOTECA SEM ESTADO** *só se* EDITH passar embeddings/modelo; senão sinal opcional — **não** dono de Ollama |
| **Token budgeting** (`token_service.py` + enforce em compress) | Contagem tiktoken + trim | Não | Não | **VIRA BIBLIOTECA** |
| **Fingerprint** (`fingerprint_service.py` ~83) | MinHash/LSH near-duplicate (datasketch) | Estado em processo / opcional DB fingerprints | Parcial (cache key) | **VIRA BIBLIOTECA SEM ESTADO** (primitiva de similaridade); **não** decide servir cache |
| **Cache semântico** (`cache_service.py` ~119) | Redis get/set compress + cosine scan | **Sim** (Redis) | Decisão de *quando* cachear = EDITH | Primitivas get/put isoladas por `user_id`: **MIGRA** ownership para EDITH; código de similaridade **VIRA BIBLIOTECA**; **proibido** auto-hit dentro de `compress` |
| **Workers Celery** | Tasks async summarize/embed/RAG/cleanup | Fila = estado operacional | Não (infra) | **REMOVER** no destino biblioteca (sync basta) |
| **Painel React** | UI dashboard ATS | N/A | Control Center EDITH | **REMOVER** (produto) |
| **Nginx próprio** | SPA + reverse `/api` `/v1` | N/A | Proxy compartilhado | **REMOVER** no destino lib |
| **Prometheus** | Métricas scrapadas | Time-series | EDITH/CC | **REMOVER** do ATS; métricas `t_ats_ms` etc. emitem no processo EDITH |
| **Grafana** | Dashboards | N/A | Control Center | **REMOVER** |
| **Flower** | UI Celery | N/A | — | **REMOVER** |
| **OllamaService** (~167) | HTTP client para generate/embed | keep_alive no host | Contrato: Ollama **só EDITH** | **REMOVER** deste pacote como dono; compressão rule-based sem Ollama no default |
| **Analytics/RequestLog** (~212) | Grava logs Postgres | **Sim** | Telemetria EDITH | **DESLIGAR** persistência de conteúdo; métricas canônicas no caller |
| **proxy_strategy_service** (~89) | Auto-escolhe strategy | Não | Decisão de *quando* = EDITH | **REMOVER** decisões; ratio/target podem ser params da API `compress` |

---

## Honestidade nome vs código

| Nome de marketing | Realidade |
|-------------------|-----------|
| Adaptive RAG | RAG pgvector + chunking; pouca “adaptação” online |
| Context Graph | Regex + NetworkX em dict de processo; some no restart |
| Hierarchical Memory | 3 camadas Redis/PG reais, mas **memória pessoal** — território EDITH |
| Ultra + Ollama | Caminho legado; contrato ecossistema não quer ATS falando com Ollama |
| Cost optimizer | Ifs sobre tokens/custo estimado — não otimizador de mercado |

---

## Resumo por destino

| Destino | Componentes |
|---------|-------------|
| **VIRA BIBLIOTECA** | Compressão, Quality Guard, TokenService/budgeting |
| **VIRA BIBLIOTECA SEM ESTADO** | Context Manager (trim), Fingerprint (similaridade), Chunking (opcional), Semantic Loss (opcional, sem dono Ollama) |
| **MIGRA PARA E.D.I.T.H.** | Decisão de cache, memória, RAG como produto, roteamento, telemetria de provider |
| **DESLIGAR** | Hierarchical Memory, Context Graph persistente-entre-calls, MemoryService, RAG store neste repo |
| **REMOVER** | LiteLLM, proxies `/v1/*`, router de modelo, cost optimizer decisor, Celery, React, Nginx ATS, Prometheus/Grafana/Flower, chaves de provider |

---

## Estimativa de sobrevivência (ordem de grandeza)

| Camada | LOC hoje (aprox.) | Sobrevive na lib |
|--------|-------------------|------------------|
| Backend `app/` serviços+rotas | ~5–7k | **~800–1500** (compress+guard+token+dedup+specialized+fingerprint thin) |
| Frontend | grande | **0** |
| Compose profiles monitoring/workers | — | **0** |

**Estimativa honesta: ~15–25% do código de serviço de compressão sobrevive; ~0% da superfície de “gateway LLM / segundo cérebro”.**  
Se a avaliação de qualidade (Rodada 2) mostrar perda crítica alta **e** `must_preserve` falhar, a fatia viva cai para **quase nenhuma** (só token count + trim manual na EDITH).
