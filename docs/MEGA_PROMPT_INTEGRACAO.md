# MEGA PROMPT — AI Token Suppressor (ATS)

> Cole este bloco inteiro no contexto de uma IA/agente que vai **integrar o AiTokenSuppressor** em outro projeto.
> Substitua `BASE_URL`, `API_KEY` e o IP/host reais do ambiente.

---

## INSTRUÇÕES PARA A IA INTEGRADORA

Você está integrando o **AI Token Suppressor (ATS)** — um middleware de compressão de tokens para LLMs.

**Missão:** conectar o projeto-alvo ao ATS de forma correta, segura e eficiente (sem estourar RAM, sem enviar chaves erradas, sem pular auth).

**Regras obrigatórias:**
1. Autentique sempre com a **API_KEY do ATS**, nunca com chaves de provedor (`sk-`, `sk-ant-`, `gsk_`, etc.).
2. Prefira compressão **sem Ollama** em VPS pequena (`use_ollama: false`, strategy `fast` ou `balanced`).
3. Escolha **um** canal de integração: API nativa **ou** proxy OpenAI **ou** proxy Anthropic.
4. Não invente endpoints; use somente os listados abaixo.
5. Após integrar, valide com health check + um request de teste medindo `tokens_before` / `tokens_after` ou headers `X-ATS-*`.

---

## 1. O QUE É O AI TOKEN SUPPRESSOR

O **AI Token Suppressor (ATS)** é um middleware inteligente entre aplicações cliente (APIs Java/Python/Node, Cursor, Claude Code, bots, gateways) e provedores de LLM (Groq, OpenAI, Anthropic/Claude, Gemini, DeepSeek, Ollama).

### Problema que resolve
Prompts longos (histórico, código, logs, system prompts) geram alto custo e latência em APIs de LLM. Muito desse texto é redundante, irrelevante ou repetitivo.

### O que o ATS faz
Antes (ou no meio) do envio ao LLM, o ATS:
- **Comprime** o prompt (deduplicação, minificação, compressão especializada por tipo de conteúdo, sumarização opcional via Ollama)
- **Preserva qualidade** (quality guard: não destrói system prompts críticos nem instruções essenciais)
- **Opcionalmente injeta memória** semântica (pgvector) e contexto RAG
- **Roteia** modelo conforme complexidade (no pipeline `optimize`)
- **Cacheia** compressões similares (Redis + fingerprint)
- **Mede** economia de tokens, latência e custo estimado

### Proposta de valor
Redução típica de **~60–95%** de tokens (depende da estratégia e do conteúdo), mantendo o sentido útil do prompt.

### Dois modos de uso

| Modo | Quando usar | Fluxo |
|------|-------------|--------|
| **API nativa** (`/optimize`, `/compress`) | Você já tem cliente LLM próprio | ATS devolve `messages` otimizadas → seu código chama o LLM |
| **Proxy LLM** (`/v1/chat/completions`, `/v1/messages`) | Quer drop-in OpenAI/Anthropic | ATS comprime **e** chama o LLM; devolve a resposta final |

---

## 2. ARQUITETURA (VISÃO PARA INTEGRAÇÃO)

```
[Seu projeto]
    |
    |  HTTP + API_KEY ATS
    v
[Nginx :8100]  ----/api/*---->  [FastAPI API :8105]
    |  /v1/*  ---------------->       |
    |                                  |
    |                          Pipeline compress | optimize
    |                                  |
    |                     Redis cache · Postgres/pgvector
    |                                  |
    |                     (± Ollama local para ultra/resumo)
    |                                  |
    |                          [só no proxy]
    |                     LiteLLM fallback:
    |                     groq → openai → anthropic → gemini → deepseek → ollama
    v
[Resposta otimizada OU resposta do LLM]
```

### Componentes relevantes
- **FastAPI** — API + proxy
- **Redis** — cache de compressão, rate limit
- **PostgreSQL + pgvector** — memórias, RAG, analytics
- **Ollama (opcional)** — sumarização/`semantic_reduce` e embeddings
- **Nginx** — front + reverse proxy (`/api`, `/v1`)

### Portas típicas (Docker produção)

| Serviço | Porta host |
|---------|------------|
| Frontend + Nginx | **8100** |
| API direta | **8105** |
| Redis | 8106 |

**Bases URL para integração (exemplos):**
- Nativa via nginx: `http://HOST:8100/api`
- Proxy OpenAI via nginx: `http://HOST:8100/v1`
- API direta: `http://HOST:8105`
- Claude Code (Anthropic base): `http://HOST:8100` (sem `/v1` no base URL; o path `/v1/messages` é concatenado pelo cliente)

> No código FastAPI as rotas nativas **não** têm prefixo `/api`; o nginx faz o strip. Em `:8105`, use `/optimize` (não `/api/optimize`).

---

## 3. AUTENTICAÇÃO (CRÍTICO)

### Formas aceitas
1. Header `X-API-Key: <API_KEY_ATS>`
2. Header `x-api-key: <API_KEY_ATS>` (Claude Code / Anthropic)
3. Header `Authorization: Bearer <API_KEY_ATS>`
4. Header `Authorization: Bearer <JWT>` (JWT obtido em `POST /auth/login`)

### O que NÃO fazer
- **Não** colocar `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` do provedor como auth do ATS.
- O ATS rejeita chaves que parecem de provedor (`sk-`, `gsk_`, `sk-ant-`, …) com 401.
- As chaves dos LLMs ficam **no servidor ATS** (`.env`), não no cliente integrador (modo proxy).

### Login JWT (opcional, dashboard)
- `POST /auth/login` body: `{ "username": "admin", "password": "admin123" }`
- Retorna `access_token` — usar só se o projeto precisar de JWT; para integração máquina-a-máquina prefira `API_KEY`.

---

## 4. ESTRATÉGIAS DE COMPRESSÃO

| Estratégia | Economia alvo | Ollama default | Ideal para |
|------------|---------------|----------------|------------|
| `fast` | leve (~10%) | **não** | prompts curtos, latência mínima, VPS fraca |
| `code-focused` | média-alta | **não** | código, diffs, repositórios |
| `balanced` | ~50% | sim* | uso geral produção |
| `chat-focused` | ~55% | sim* | conversas longas |
| `aggressive` | ~70% | sim* | prompts grandes |
| `semantic` | ~60% | sim* | redução semântica via Ollama |
| `ultra` | ~85% | sim* | máxima economia (cara em RAM/CPU) |

\*Se `use_ollama=false`, o ATS **não** chama Ollama. No proxy, estratégias pesadas sem Ollama são **rebaixadas para `balanced`** (rule-based forte, sem modelo local).

### Auto-estratégia no proxy (sem header `X-ATS-Strategy`)
- &lt; ~400 tokens → `fast`
- conteúdo de código → `code-focused`
- prompts médios/grandes → `balanced`

### Recomendação prática para integração
| Ambiente | strategy | use_ollama | use_memory |
|----------|----------|------------|------------|
| VPS ≤ 8 GB / muitos requests | `fast` ou `balanced` | `false` | `false` |
| Servidor ≥ 16 GB, poucos usuários | `balanced` ou `ultra` | `true` (se precisar) | opcional |
| Código pesado | `code-focused` | `false` | `false` |
| Claude Code no editor | auto / `fast` | `false` | `false` |

**Nunca** ligue `ultra` + Ollama em VPS de ~4 GB com vários usuários — estoura RAM/swap.

---

## 5. CANAIS DE INTEGRAÇÃO (ESCOLHA UM)

### Canal A — API nativa `/optimize` (recomendado para apps próprios)

**Quando:** seu projeto já chama Groq/OpenAI/Claude e só quer otimizar o prompt antes.

**Fluxo:**
1. `POST {BASE}/optimize` com `messages`
2. Recebe `messages` comprimidas + métricas
3. Envia essas `messages` ao seu LLM

**Campos request principais:**
```json
{
  "messages": [
    {"role": "system", "content": "..."},
    {"role": "user", "content": "..."}
  ],
  "strategy": "balanced",
  "target_model": "claude-3-5-sonnet",
  "provider": "anthropic",
  "use_memory": false,
  "use_rag": false,
  "use_hierarchical_memory": false,
  "use_semantic_cache": true,
  "user_id": "meu-app-user-123",
  "session_id": "sess-abc",
  "max_tokens": null,
  "check_semantic_loss": false,
  "use_ollama": false,
  "cost_budget_usd": null
}
```

**Campos response principais:**
- `messages` — array otimizado (use este no LLM)
- `tokens_before`, `tokens_after`, `tokens_saved`, `savings_percent`
- `operations_applied` — lista do que foi feito
- `cache_hit`, `latency_ms`
- `quality_preserved`, `semantic_loss_score` (se medido)
- `recommended_model`, `model_reason` (pipeline optimize)

**Alternativa mais leve:** `POST /compress` — só compressão, sem memory/RAG/router.

**Análise sem comprimir:** `POST /analyze` — recomenda estratégia e estima economia.

### Canal B — Proxy OpenAI-compatible `/v1/chat/completions`

**Quando:** SDK/cliente OpenAI (Cursor, LangChain OpenAI, etc.).

**Config típica:**
- Base URL: `http://HOST:8100/v1`
- API Key: `API_KEY` do ATS

**Headers opcionais ATS:**
- `X-ATS-Strategy: balanced`
- `X-ATS-Pipeline: compress` | `optimize`
- `X-ATS-Use-Memory: false`
- `X-ATS-Use-Ollama: false`
- `X-ATS-Skip-Optimize: false`

**Headers de resposta (economia):**
- `X-ATS-Tokens-Before`
- `X-ATS-Tokens-After`
- `X-ATS-Tokens-Saved`
- `X-ATS-Optimize-Ms`
- `X-ATS-Provider-Used`
- `X-ATS-Fallback-Chain`
- `X-ATS-Strategy`
- `X-ATS-Pipeline`

Body: formato OpenAI padrão (`model`, `messages`, `stream`, `temperature`, `max_tokens`).

### Canal C — Proxy Anthropic `/v1/messages` (Claude Code / VS Code)

**Quando:** extensão Claude Code ou cliente Anthropic Messages API.

**Config:**
- `ANTHROPIC_BASE_URL=http://HOST:8100`
- `ANTHROPIC_API_KEY=<API_KEY_ATS>`

**Particularidades:**
- Aceita `role: "system"` **dentro** de `messages[]` (Claude Code faz isso) — o ATS consolida no bloco system.
- Sem headers `X-ATS-*`, ollama/memória **não** herdam o `.env` (default seguro para editor).
- `stream: true` usa pseudo-stream SSE compatível com Anthropic.
- `max_tokens` é obrigatório.

---

## 6. CATÁLOGO DE ENDPOINTS

### Health (sem auth)
- `GET /health` · `GET /health/live`
- `GET /health/detail` · `GET /health/redis` · `GET /health/postgres` · `GET /health/ollama`
- `GET /health/full`

### Auth
- `POST /auth/login`

### Core (auth)
- `POST /optimize`
- `POST /compress`
- `POST /analyze`

### Memory (auth)
- `POST /memory/save` — `{ content, memory_type, user_id, session_id?, metadata?, entities? }`
- `POST /memory/search` — `{ query, user_id, top_k?, memory_types?, min_score? }`

### RAG (auth)
- `POST /rag/ingest` — `{ content, collection_id, source?, metadata?, language?, chunk_by_ast? }`
- `POST /rag/query` — `{ query, collection_id, top_k?, rerank? }`

### Stats
- `GET /stats?days=7` (auth)
- `GET /metrics` (Prometheus, se habilitado)

### Advanced (auth)
- `POST /advanced/benchmark`
- `POST /advanced/heatmap`
- `POST /advanced/graph/query`
- `POST /advanced/codebase/index`
- `POST /advanced/stream/compress` (NDJSON)

### Proxy (auth)
- `GET /v1/models`
- `POST /v1/chat/completions`
- `POST /v1/messages`

### Formato Message
```json
{
  "role": "system|user|assistant|tool",
  "content": "string",
  "name": "opcional",
  "metadata": {}
}
```
Máximo: **500** mensagens por request. Payload típico máx. ~10 MB.

---

## 7. CAPACIDADES DETALHADAS (O QUE O SISTEMA É CAPAZ)

### Compressão inteligente
- Minificação de whitespace
- Remoção de linhas duplicadas
- Compactação de JSON embutido
- Deduplicação de mensagens e blocos de código
- Compressão especializada por tipo: código, JSON, logs, stacktrace, chat, documentação
- Quality guard: protege mensagens críticas / system prompts
- Sumarização hierárquica de histórico longo (com Ollama, quando ligado)
- `semantic_reduce` no modo `ultra`/`semantic` (Ollama)

### Memória semântica
- Salva e busca memórias com embeddings (Ollama `nomic-embed-text` ou fallback texto)
- Tipos: context, preference, prompt, etc.
- Memória hierárquica (L1 Redis / L2 pgvector / L3 cold)
- Context graph (entidades e relações)

### RAG
- Ingestão com chunking (± AST para código)
- Query com similaridade vetorial e contexto montado

### Cache
- Cache exato por hash do prompt
- Cache semântico por fingerprint/similaridade
- Respostas de compressão reutilizadas → latência baixíssima em hits

### Proxy multi-provedor
- Fallback ordenável via `PROXY_PROVIDER_FALLBACK`
- Streaming OpenAI e Anthropic (Anthropic: pseudo-stream quando necessário)

### Observabilidade
- Headers `X-ATS-*` em cada proxy call
- Analytics em Postgres (`/stats`)
- Prometheus metrics (opcional)

---

## 8. VARIÁVEIS DE AMBIENTE (SERVIDOR ATS)

O cliente integrador normalmente só precisa de **URL + API_KEY**.  
No servidor ATS (para você operar):

| Variável | Significado |
|----------|-------------|
| `API_KEY` | Chave que os clientes usam |
| `PROXY_DEFAULT_STRATEGY` | Default do proxy (`fast` recomendado em VPS) |
| `PROXY_PIPELINE` | `compress` ou `optimize` |
| `PROXY_USE_MEMORY` | default memory no OpenAI proxy |
| `PROXY_USE_OLLAMA` | default ollama no OpenAI proxy |
| `PROXY_SKIP_OPTIMIZE` | pula compressão |
| `PROXY_PROVIDER_FALLBACK` | ordem dos LLMs |
| `GROQ_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, … | chaves no **servidor** |
| `OLLAMA_BASE_URL`, `OLLAMA_MODEL` | inferência local |
| `DATABASE_URL`, `REDIS_URL` | persistência |
| `LOW_MEMORY_MODE`, `PROMETHEUS_ENABLED` | VPS |

---

## 9. EXEMPLOS PRÁTICOS DE INTEGRAÇÃO

### A) Java / Spring (estilo ConsumoEsperto) — nativo
```http
POST http://191.252.210.60:8100/api/optimize
X-API-Key: ats-super-api-key
Content-Type: application/json

{
  "messages": [
    {"role": "user", "content": "PROMPT LONGO AQUI"}
  ],
  "strategy": "balanced",
  "use_memory": false,
  "use_ollama": false,
  "check_semantic_loss": false
}
```
Depois: pegar `response.messages` e enviar ao provedor LLM do Java.

### B) Python OpenAI SDK — proxy
```python
from openai import OpenAI

client = OpenAI(
    base_url="http://HOST:8100/v1",
    api_key="ats-super-api-key",
    default_headers={
        "X-ATS-Strategy": "balanced",
        "X-ATS-Use-Ollama": "false",
        "X-ATS-Use-Memory": "false",
    },
)

r = client.chat.completions.create(
    model="gpt-4o-mini",
    messages=[{"role": "user", "content": "Explique X em detalhes..."}],
)
```

### C) curl — Anthropic messages
```bash
curl -s http://HOST:8100/v1/messages \
  -H "x-api-key: ats-super-api-key" \
  -H "Content-Type: application/json" \
  -H "anthropic-version: 2023-06-01" \
  -d '{
    "model": "claude-3-5-sonnet-20241022",
    "max_tokens": 512,
    "messages": [{"role": "user", "content": "Olá"}]
  }'
```

### D) Health check antes de integrar
```bash
curl -s http://HOST:8100/api/health/live
# ou direto:
curl -s http://HOST:8105/health/live
```

---

## 10. PADRÃO DE DECISÃO (ALGORITMO PARA A IA INTEGRADORA)

```
SE o projeto já tem cliente LLM próprio:
  → usar Canal A (/optimize ou /compress)
  → strategy = balanced (ou code-focused se for código)
  → use_ollama = false  (salvo infra forte)
  → use_memory = false  (ligar só se precisar de recall)

SE o projeto usa SDK OpenAI / Cursor:
  → Canal B (base_url .../v1 + API_KEY ATS)
  → headers X-ATS-* conforme acima

SE o projeto é Claude Code / Anthropic Messages:
  → Canal C (ANTHROPIC_BASE_URL + API_KEY ATS)

SE VPS com pouca RAM:
  → NUNCA ultra+ollama por default
  → preferir fast/balanced + use_ollama false

SE precisar máxima economia e servidor ≥16–32GB:
  → pode testar ultra + use_ollama true
  → monitore RAM/swap
```

---

## 11. LIMITAÇÕES E ARMADILHAS

1. **Chave errada** → 401; use API_KEY ATS.
2. **ultra + Ollama em VPS fraca** → swap, 502, load altíssimo.
3. **`/v1/messages`** ignora ollama/memory do `.env` sem headers explícitos (isso é feature de segurança de memória).
4. **Sem chaves de provedor no servidor ATS** → proxy retorna 502 `llm_upstream_failed`.
5. Rate limit padrão ~100 req/60s (configurável).
6. `fast` no proxy força ollama off no pipeline de compressão.
7. Memória/RAG precisam de Postgres saudável + embeddings (Ollama ou fallback).
8. README antigo pode citar portas `8000`/`5173` — em Docker produção use **8100/8105**.
9. `APP_NAME` no `.env` com espaços precisa de aspas: `APP_NAME="AI Token Suppressor"`.

---

## 12. CHECKLIST DE INTEGRAÇÃO (EXECUTE NESTA ORDEM)

- [ ] Confirmar `GET /health/live` OK
- [ ] Confirmar auth com `X-API-Key` em um `POST /optimize` simples
- [ ] Escolher Canal A, B ou C
- [ ] Definir `strategy` + `use_ollama` + `use_memory` seguros para a infra
- [ ] Implementar chamada e mapear `messages` otimizadas (Canal A) ou resposta LLM (B/C)
- [ ] Logar economia (`tokens_saved` ou headers `X-ATS-Tokens-*`)
- [ ] Testar prompt curto e prompt longo (~1500+ tokens)
- [ ] Testar falha de auth e timeout
- [ ] Documentar no projeto-alvo: `TOKEN_SUPPRESSOR_URL` + `TOKEN_SUPPRESSOR_API_KEY`

---

## 13. VARIÁVEIS SUGERIDAS NO PROJETO-ALVO

```env
TOKEN_SUPPRESSOR_URL=http://HOST:8100/api
TOKEN_SUPPRESSOR_API_KEY=ats-super-api-key
TOKEN_SUPPRESSOR_STRATEGY=balanced
TOKEN_SUPPRESSOR_USE_OLLAMA=false
TOKEN_SUPPRESSOR_USE_MEMORY=false
# Se for proxy OpenAI:
# OPENAI_BASE_URL=http://HOST:8100/v1
# OPENAI_API_KEY=ats-super-api-key
# Se for Claude Code:
# ANTHROPIC_BASE_URL=http://HOST:8100
# ANTHROPIC_API_KEY=ats-super-api-key
```

---

## 14. RESUMO EM UMA FRASE

**AI Token Suppressor** é um gateway HTTP autenticado que comprime prompts (e opcionalmente chama o LLM) para reduzir drasticamente tokens/custo, com estratégias configuráveis, cache, memória/RAG opcionais e proxies compatíveis com OpenAI e Anthropic.

---

## 15. TAREFA FINAL PARA A IA INTEGRADORA

Com base neste documento:
1. Analise o projeto-alvo e escolha o canal (A/B/C).
2. Proponha o menor diff possível para integrar.
3. Use defaults seguros (`balanced`/`fast`, `use_ollama=false`, `use_memory=false`) salvo pedido contrário.
4. Inclua health check e tratamento de 401/502.
5. Mostre um exemplo de request/response esperado e como ler a economia de tokens.

**NÃO** altere o código do ATS a menos que seja necessário; integre pelo contrato HTTP acima.
