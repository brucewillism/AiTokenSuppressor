# Contrato do Ecossistema — v1 (CONGELADO)

> Copie este arquivo para `docs/ECOSYSTEM_CONTRACT.md` em **cada um dos quatro repositórios**
> antes de iniciar qualquer agente. Nenhum projeto pode alterar este documento sozinho.
> Mudanças aqui exigem atualização simultânea nos quatro repos e bump de versão.

Projetos: `jarvis`, `edith`, `consumo-esperto`, `ai-token-suppressor` (`ats`).
Futuro: `arman`.

---

## 1. Envelope de requisição

Todo salto entre serviços do ecossistema carrega o envelope. Ele viaja em **headers HTTP**
para chamadas simples e como campo `envelope` no corpo JSON para chamadas de tool.

### Headers

| Header | Obrigatório | Exemplo |
|---|---|---|
| `X-Eco-Trace-Id` | sim | `tr_01J8Z9K2M4N6P8Q0R2S4T6V8` |
| `X-Eco-Span-Id` | sim | `sp_01J8Z9K2M4N6P8Q0R2S4T6V9` |
| `X-Eco-Parent-Span-Id` | não (ausente na borda) | `sp_01J8Z9K2M4N6P8Q0R2S4T6V8` |
| `X-Eco-User-Id` | sim | `usr_bruce` |
| `X-Eco-App-Origin` | sim | `jarvis` |
| `X-Eco-App-Current` | sim | `consumo-esperto` |
| `X-Eco-Conversation-Id` | não | `conv_987` |
| `X-Eco-Task-Id` | não | `task_445` |
| `X-Eco-Tool-Call-Id` | só em chamada de tool | `tool_991` |
| `X-Eco-Mode` | sim | `INTERACTIVE` \| `BALANCED` \| `DEEP` |
| `X-Eco-Deadline` | sim | `2026-09-07T14:32:11.480Z` |
| `X-Eco-Sensitivity` | sim | `PUBLIC` \| `INTERNAL` \| `PERSONAL` \| `FINANCIAL` |

### Regras não negociáveis do envelope

1. **`trace_id` é criado uma única vez, na borda** (JARVIS UI, Angular do ConsumoEsperto,
   WhatsApp handler). Nunca é regerado. É propagado sem alteração até o último salto.
2. **`span_id` é novo a cada salto.** O `span_id` do chamador vira o `parent_span_id` do chamado.
3. **`X-Eco-Deadline` é a fonte da verdade da latência, não um contador de milissegundos.**
   Um timestamp absoluto ISO-8601 em UTC. Cada serviço calcula seu orçamento restante como
   `deadline - now()`. Isso elimina o bug clássico de "cada tentativa recebe timeout cheio".
4. **Deadline nunca é estendido.** Um serviço pode encurtar (reservar margem para si), nunca
   aumentar. Se `deadline - now() <= 0` ao receber a requisição, responda imediatamente
   `DEADLINE_EXCEEDED` sem executar trabalho.
5. **`X-Eco-Sensitivity` só sobe, nunca desce.** Se uma resposta de tool contém dado
   `FINANCIAL`, todo o restante da cadeia herda `FINANCIAL`.

### ULID

Todos os IDs usam ULID com prefixo (`tr_`, `sp_`, `conv_`, `task_`, `tool_`, `ctx_`).
ULID e não UUID porque é ordenável por tempo, o que facilita leitura de log.

---

## 2. Modos de execução

| Modo | Deadline padrão | Uso |
|---|---|---|
| `INTERACTIVE` | 2000 ms | chat digitando, botão de UI, comando de voz |
| `BALANCED` | 8000 ms | pergunta que precisa de dados + explicação |
| `DEEP` | 60000 ms | análise, planejamento, múltiplas ferramentas |

O modo é **declarado pela borda**, não inferido por LLM. Um botão de UI sempre é `INTERACTIVE`.
A E.D.I.T.H. pode **rebaixar** o modo (de `DEEP` para `BALANCED`) mas nunca promover sem
sinalizar isso na resposta.

---

## 3. Caminhos de execução

Não são três fluxos de código. São três presets do mesmo plano.

```
ExecutionPlan {
  path: INSTANT | FAST | DEEP     // rótulo para observabilidade
  stages: [resolve, tool?, ats?, model?, verify?]   // lista, estágios opcionais
  deadline: <ISO-8601>
  model_class: NONE | FAST_SMALL | BALANCED | STRONG
  ats: BYPASS | ENABLED
  sensitivity: PUBLIC | INTERNAL | PERSONAL | FINANCIAL
}
```

| Path | Chamadas de LLM | Estágios típicos |
|---|---|---|
| `INSTANT` | 0 | `resolve` → `tool` |
| `FAST` | 0 ou 1 | `resolve` → `tool` → `model?` |
| `DEEP` | 1+ | `resolve` → `plan` → `tool*` → `ats?` → `model` → `verify?` |

**Proibido:** criar um quarto path. Se surgir a necessidade de "FAST com verifier", isso é
`stages: [resolve, tool, model, verify]` com `path: FAST`, não um novo caminho.

---

## 4. Manifesto de capabilities

Toda aplicação que fornece tools expõe `GET /capabilities`, sem autenticação de usuário
(apenas o segredo de serviço), retornando:

```json
{
  "provider": "consumo-esperto",
  "manifest_version": "1",
  "generated_at": "2026-09-07T14:00:00Z",
  "capabilities": [
    {
      "id": "finance.cards.list",
      "description": "Lista os cartões de crédito ativos do usuário com bandeira, limite, dia de fechamento e dia de vencimento.",
      "aliases": [
        "listar meus cartões",
        "quais cartões eu tenho",
        "meus cartoes",
        "mostrar cartões"
      ],
      "input_schema": { "type": "object", "properties": {}, "required": [] },
      "output_schema": { "type": "object", "properties": { "cards": { "type": "array" } } },
      "execution": "DETERMINISTIC",
      "kind": "READ",
      "scope": "finance:read",
      "idempotent": true,
      "sensitivity": "FINANCIAL",
      "p95_latency_ms": 120,
      "cache_ttl_s": 60,
      "requires_confirmation": false,
      "local_resolvable": true
    }
  ]
}
```

### Campos que existem por um motivo específico

- **`aliases`** — alimenta o índice de embeddings do Capability Resolver da E.D.I.T.H.
  Sem isso, o resolver não tem como casar linguagem natural sem chamar LLM.
  Escreva de 3 a 8 aliases por capability, incluindo variações sem acento e com erro comum.
- **`execution: DETERMINISTIC`** — declara que a capability **não precisa de LLM**.
  É o que autoriza o path `INSTANT`.
- **`local_resolvable: true`** — declara que o próprio app dono da capability pode resolvê-la
  sem passar pela E.D.I.T.H. quando ele mesmo é o chamador. É o que elimina o salto redundante
  `ConsumoEsperto → EDITH → ConsumoEsperto`.
- **`requires_confirmation`** — toda capability `kind: WRITE` ou `kind: ACTION` **deve** ter
  `true`. Sem exceção nesta versão do contrato.
- **`p95_latency_ms`** — valor **medido**, não estimado. Atualize com dados reais.

O formato é compatível com tool definitions do MCP. Não invente um protocolo paralelo.

---

## 5. Métricas de tempo — nomes canônicos

Todo serviço emite estes campos no log estruturado de cada requisição. Nomes idênticos nos
quatro projetos, senão o Control Center não consegue somar nada.

```
t_total_ms            tempo total dentro deste serviço
t_queue_ms            tempo esperando fila/worker antes de começar
t_resolve_ms          capability resolution (embedding + slot filling)
t_tool_ms             chamada de tool (soma, se mais de uma)
t_ats_ms              round-trip para o AI Token Suppressor
t_router_ms           decisão de roteamento (não inclui o provider)
t_provider_ttft_ms    do envio ao primeiro token recebido
t_provider_total_ms   do envio ao último token
t_verify_ms           verificação
tokens_in_original    contexto antes da compressão
tokens_in_final       contexto enviado ao modelo
tokens_out            tokens gerados
compression_ratio     tokens_in_final / tokens_in_original
fallback_count        quantas rotas foram tentadas e falharam
cache_hit             true | false
execution_path        INSTANT | FAST | DEEP
ats_mode              BYPASS | ENABLED
provider              nome do provider efetivamente usado
model                 modelo efetivamente usado
outcome               SUCCESS | DEGRADED | FAILED
```

Campo ausente é omitido, nunca preenchido com `0`. `0` significa "mediu e deu zero".

---

## 6. Contrato de erro

```json
{
  "error": {
    "code": "DEADLINE_EXCEEDED",
    "message": "texto curto para log, nunca exposto cru ao usuário",
    "retryable": false,
    "trace_id": "tr_01J8Z9K2M4N6P8Q0R2S4T6V8"
  }
}
```

Códigos válidos: `DEADLINE_EXCEEDED`, `UNAUTHORIZED`, `SCOPE_DENIED`,
`CAPABILITY_NOT_FOUND`, `AMBIGUOUS_PARAMS`, `CONFIRMATION_REQUIRED`,
`UPSTREAM_UNAVAILABLE`, `RATE_LIMITED`, `INVALID_INPUT`, `INTERNAL`.

Nenhum outro código. Se precisar de um novo, isso é mudança de contrato.

---

## 7. Resposta degradada

Quando o resultado ideal não foi possível mas existe algo útil:

```json
{
  "outcome": "DEGRADED",
  "degraded_reason": "PROVIDER_TIMEOUT",
  "data": { },
  "trace_id": "tr_..."
}
```

`DEGRADED` nunca é apresentado ao usuário como erro. É uma resposta válida, com aviso.

---

## 8. Sensibilidade de dado e roteamento

| Classe | Exemplos | Providers permitidos |
|---|---|---|
| `PUBLIC` | notícias, definições | qualquer |
| `INTERNAL` | preferências de UI, estado de app | qualquer |
| `PERSONAL` | agenda, e-mail, nome, contatos | apenas allowlist `no_train` + Ollama local |
| `FINANCIAL` | transações, faturas, saldos, cartões | apenas allowlist `no_train` + Ollama local |

**Regra dura:** requisição com `sensitivity` em `PERSONAL` ou `FINANCIAL` **não pode ser
roteada para um provider fora da allowlist**, independentemente do que o score de custo,
qualidade ou latência disser. Isso é uma restrição, não um peso no score.

A allowlist `no_train` vive na E.D.I.T.H. em configuração, com o termo de uso de cada provider
documentado e datado. Provider sem documentação verificada entra como **não permitido**.

Além disso: **nunca envie linhas cruas de tabela financeira para nenhum modelo.** Agregados,
somas e recortes por categoria sim; dump de transações não.

---

## 9. Autenticação entre serviços

Mantido o esquema já em uso entre E.D.I.T.H. e ConsumoEsperto, padronizado para todos:

- HMAC-SHA256 sobre `método + path + body + timestamp + nonce`
- Header `X-Eco-Signature`, `X-Eco-Timestamp`, `X-Eco-Nonce`
- Janela de tolerância de 60 s
- Nonce armazenado em Redis com TTL de 120 s, rejeição em replay
- Segredo por par de serviços, nunca um segredo global
- Allowlist de capabilities por chamador
- Scopes: `finance:read`, `finance:write`, `desktop:action`, `email:read`, `agenda:read`
- **Default deny.** Escopo ausente é escopo negado.
- `finance:write` e `desktop:action` **desabilitados nesta versão**

---

## 10. Streaming

Quando houver modelo no plano, a resposta é SSE. Eventos:

```
event: start      data: {"trace_id":"...","execution_path":"FAST"}
event: token      data: {"t":"texto"}
event: tool       data: {"id":"finance.cards.list","status":"running|done"}
event: metrics    data: { ...campos da seção 5... }
event: done       data: {"outcome":"SUCCESS"}
event: error      data: { ...contrato da seção 6... }
```

O evento `metrics` é sempre emitido, inclusive em erro.

---

## 11. Namespaces de infraestrutura

Servidor compartilhado, dados separados.

- Postgres: bancos `edith_db`, `consumo_db`, `ats_db`, com **roles distintos**.
  Nenhum role tem acesso de leitura ao banco de outro serviço. Sem exceção.
- Redis: prefixos `edith:`, `ats:`, `consumo:`, `jarvis:`.
- Ollama: instância única, acessada **apenas pela E.D.I.T.H.**. Nenhum outro serviço
  abre conexão direta.

---

## 12. Versionamento

Este contrato é `v1`. Serviços expõem `GET /health` retornando:

```json
{ "service": "consumo-esperto", "contract_version": "1", "status": "ok|degraded", "checks": {} }
```

Incompatibilidade de `contract_version` é falha de integração, deve aparecer no Control Center.
