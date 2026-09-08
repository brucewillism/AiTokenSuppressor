# ADR-005 — ATS como biblioteca dentro da E.D.I.T.H.

**Status:** Proposto (Fase 1.1)  
**Data:** 2026-09-07  
**Decisão A (JUSTIFICATION):** biblioteca — FECHADA  
**Não implementa código nesta fase.**

---

## Contexto

O ATS hoje é um monólito FastAPI com proxy LLM, memória, RAG e painel. A Decisão A da Fase 0/Rodada 2 fecha: **não se justifica como microserviço** (compressão 16k ≈ 32 ms in-process; hop HTTP ≥ trabalho). A E.D.I.T.H. é a única autoridade de provider/modelo/bypass.

## Decisão

Extrair um pacote Python **puro** consumido pela E.D.I.T.H.:

```python
def compress(
    context: list[Block],
    target_tokens: int,
    must_preserve: list[str],  # ids de blocos intocáveis
) -> CompressionResult:
    ...
```

### Tipos (proposta)

```python
class Block(TypedDict):
    id: str
    role: Literal["system", "user", "assistant", "tool"]
    content: str
    kind: Literal["history", "tool_result", "memory", "document", "instruction"]

class CompressionResult(TypedDict):
    context: list[Block]
    tokens_in_original: int
    tokens_in_final: int
    compression_ratio: float
    quality_signal: dict  # semantic_loss_estimate?, dropped_block_ids, preserved_ids
    t_ats_ms: float
```

**Função pura:** mesma entrada → mesma saída. Sem Redis/Postgres/histórico/memória. Sem escolher modelo. Sem servir cache.

`must_preserve`: blocos listados **não** são comprimidos, resumidos nem removidos. Teste obrigatório.

---

## Pacote e tamanho

| Item | Proposta |
|------|----------|
| Nome | `ats_compress` (ou `edith.ats`) |
| LOC alvo | **~800–1500** linhas |
| Inclui | compression, specialized, dedup, quality_guard, token_service, content_detection leve, relevance leve, context trim |
| Exclui | FastAPI routes, LiteLLM, proxies, Celery, React, Grafana, memory/RAG/graph, Ollama client como dependência obrigatória |

---

## Dependências

| Dependência | Destino |
|-------------|---------|
| `tiktoken` | **Permanece** |
| `datasketch` (fingerprint) | Opcional, extrato `similarity` |
| `networkx` | **Some** (Context Graph não vem) |
| `sqlalchemy` / `asyncpg` / `pgvector` | **Somem** da lib |
| `redis` / `celery` / `flower` | **Somem** |
| `litellm` / `httpx` para providers | **Somem** |
| `fastapi` / `uvicorn` | **Somem** |
| Ollama | **Some** do default; se EDITH quiser semantic_reduce, ela injeta um callback `summarize_fn` — ATS lib não abre Ollama |

---

## Cache — fronteira

```
EDITH:
  hit = cache.get(user_id, fingerprint, sensitivity)
  if hit: use
  else:
      result = ats_compress.compress(...)
      cache.put(user_id, fingerprint, result, sensitivity, ttl)
```

- A biblioteca **pode** expor `fingerprint(context) -> str` e `similarity(a, b) -> float`.
- **`compress()` nunca lê nem escreve cache.**
- Chave Redis (na EDITH): `edith:ats_cache:{user_id}:{fp}` — **isolamento por user_id obrigatório**.
- TTL por `sensitivity` (FINANCIAL/PERSONAL mais curto ou zero persistência de payload).
- Teste: user A nunca recebe entrada de user B (lib unit + integração EDITH).

---

## FINANCIAL / PERSONAL no processo da E.D.I.T.H.

Ao rodar in-process:

1. A lib **não loga** `content` — só métricas (`tokens_*`, `t_ats_ms`, `dropped_block_ids`).
2. A EDITH já é o processo que vê o dado; a lib não cria **segunda** superfície de persistência (sem RequestLog de prompt, sem fila Celery com body).
3. `must_preserve` é o mecanismo para blindar blocos financeiros na compressão.
4. Se EDITH cachear resultado, **ela** aplica política de não persistir cru FINANCIAL/PERSONAL (contrato). Preferência: cache só fingerprint+metadados ou ciphertext com TTL zero para FINANCIAL.

---

## Migração sem parar o que funciona hoje

| Etapa | Ação |
|-------|------|
| 1 | Extrair pacote no monorepo ATS (`packages/ats_compress`) mantendo FastAPI chamando a lib |
| 2 | EDITH adiciona dependência e path `ats: ENABLED` chama lib in-process |
| 3 | ConsumoEsperto/Claude Code deixam de apontar para proxy ATS; passam pela EDITH |
| 4 | Marcar pontes legacy (`envelope_synthesized`, `auth_scheme: legacy`) com data em `COMPAT_DEBT.md` |
| 5 | Remover rotas `/v1/*`, LiteLLM, Celery, React, Nginx ATS (Fase 5) |
| 6 | Arquivar ou deletar repo de serviço quando tráfego = 0 |

Durante a transição, o serviço antigo pode permanecer como **wrapper fino** sobre a mesma lib (compat), sem autoridade de roteamento nova.

---

## Consequências

**Positivas:** zero hop; um cérebro; superfície mínima; alinhado ao contrato.  
**Negativas:** EDITH carrega a dependência; versionamento acoplado; testes de compressão migram de CI ATS para CI EDITH.  
**Riscos:** vazamento de cache se EDITH errar a chave — mitigar com testes e code review obrigatório.

---

## Alternativas rejeitadas

| Alternativa | Por quê não |
|-------------|-------------|
| Manter microserviço “fino” só `/compress` | RTT ≈ trabalho; Decisão A fechada |
| Lib + ainda falar com Ollama sozinha | Viola contrato (Ollama só EDITH) |
| Desligar compressão agora | Qualidade por acerto ainda em medição; limiar bypass é Decisão B |

---

## Checklist de aceite do ADR (implementação futura)

- [ ] `compress` pura + testes `must_preserve`
- [ ] Teste isolamento cache por `user_id` (lado EDITH + chave)
- [ ] Zero import litellm/openai/anthropic SDK na lib
- [ ] Zero escrita de content FINANCIAL/PERSONAL em log da lib
- [ ] Métricas canônicas retornadas no `CompressionResult` para a EDITH emitir
