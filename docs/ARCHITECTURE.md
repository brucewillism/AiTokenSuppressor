# Arquitetura — AI Token Suppressor

## Visão Geral

O AI Token Suppressor atua como proxy inteligente entre aplicações cliente e provedores LLM. Toda request passa por um pipeline de otimização antes de ser encaminhada ao modelo final.

## Camadas

### 1. Gateway (FastAPI)

- Autenticação JWT + API Key
- Rate limiting por IP
- Validação de payload (Pydantic)
- Limite de tamanho de request
- Instrumentação Prometheus

### 2. Compression Pipeline

Ordem de execução no `/optimize`:

1. **Cache Check** — verifica se prompt similar já foi processado
2. **Model Router** — seleciona modelo ideal baseado em complexidade
3. **Memory Injection** — injeta memórias relevantes do pgvector
4. **RAG Injection** — injeta contexto recuperado (opcional)
5. **Context Manager** — sliding window, trim dinâmico, remove irrelevantes
6. **Compression Engine** — deduplicação, minificação, resumo Ollama
7. **Telemetry** — registra métricas e analytics

### 3. Serviços Core

| Serviço | Responsabilidade |
|---------|-----------------|
| `CompressionService` | 6 estratégias de compressão |
| `ContextManager` | Gerenciamento de janela de contexto |
| `MemoryService` | Memória vetorial pgvector |
| `RAGService` | Chunking + retrieval + reranking |
| `OllamaService` | LLM local para resumo/embeddings |
| `CacheService` | Cache semântico Redis |
| `RouterService` | Roteamento por complexidade |
| `DeduplicationService` | Hash + similarity dedup |
| `TokenService` | Contagem tiktoken |
| `AnalyticsService` | Telemetria e custos |

### 4. Persistência

- **PostgreSQL**: logs, memórias, documentos RAG, fingerprints
- **pgvector**: busca por similaridade (768 dims — nomic-embed-text)
- **Redis**: cache de compressões, embeddings, rate limit counters

### 5. Workers (Celery)

- `summarize_async` — resumo em background
- `create_embeddings_batch` — embeddings em lote
- `ingest_rag_document` — ingestão RAG assíncrona
- `cleanup_old_logs` — limpeza periódica

## Fluxo de Dados

```
Request → Auth → RateLimit → OptimizeService
  ├── CacheService.get_compression()
  ├── RouterService.route()
  ├── MemoryService.build_context()
  ├── RAGService.build_rag_context()
  ├── ContextManager.manage_context()
  ├── CompressionService.compress_prompt()
  │     ├── DeduplicationService
  │     ├── OllamaService.summarize()
  │     └── TokenService.enforce_limit()
  ├── AnalyticsService.log_request()
  └── CacheService.set_compression()
Response ← JSON otimizado
```

## Decisões de Design

- **Async everywhere**: SQLAlchemy async, httpx async, Redis async
- **Graceful degradation**: se Ollama falhar, fallback para truncamento
- **Cache-first**: prompts repetidos retornam instantaneamente
- **SOLID**: services isolados, repositories para data access
- **Config via env**: 12-factor app compliant

## Escalabilidade

- API: múltiplos workers Uvicorn
- Celery: workers horizontais
- Redis: cluster mode ready
- PostgreSQL: read replicas para analytics
- Ollama: GPU node dedicado

## Segurança

- API Keys para integração machine-to-machine
- JWT para dashboard admin
- Rate limiting anti-abuse
- Payload size limits
- Secrets via environment variables
- CORS configurável
