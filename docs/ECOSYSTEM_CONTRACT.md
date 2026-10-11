# Contrato do Ecossistema — v1.2 (CONGELADO)

> Copie este arquivo para `docs/ECOSYSTEM_CONTRACT.md` em **cada um dos cinco repositórios**,
> substituindo a versão anterior por completo. Nenhum projeto pode alterar este documento sozinho.
> Mudanças aqui exigem atualização simultânea nos cinco repos e bump de versão.

Projetos: `jarvis`, `edith`, `consumo-esperto`, `ai-token-suppressor` (`ats`), `arman`.

**Mudanças de v1 para v1.1:** deadline duplo (primeiro token e total), modo `STREAM`,
correção da regra de soma das métricas, `t_unaccounted_ms` e `tokens_per_second` obrigatórios,
tabela de diagnóstico de provider lento, e nova seção 13 sobre pontes de compatibilidade.
Origem: quatro objeções levantadas pelos agentes na rodada 0, todas aceitas.

**Mudanças de v1.1 para v1.2:** entrada do Arman; classes `HEALTH` e `CLIENT_SOURCE`;
regra fail closed para dados restritos sem a E.D.I.T.H.; §9 reescrito com string canônica exata,
rotação de chaves e vetores de teste; ponte legada de autenticação com data; ATS como biblioteca
em processo; exemplo de usuário neutro. Origem: auditorias de engenharia de 09/10/2026, aprovado em 11/10/2026.

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
| `X-Eco-User-Id` | sim | `usr_01J8Z9K2M4N6P8Q0R2S4T6VA` |
| `X-Eco-App-Origin` | sim | `jarvis` |
| `X-Eco-App-Current` | sim | `consumo-esperto` |
| `X-Eco-Conversation-Id` | não | `conv_987` |
| `X-Eco-Task-Id` | não | `task_445` |
| `X-Eco-Tool-Call-Id` | só em chamada de tool | `tool_991` |
| `X-Eco-Mode` | sim | `INTERACTIVE` \| `BALANCED` \| `DEEP` \| `STREAM` |
| `X-Eco-Deadline-First-Token` | sim | `2026-09-07T14:32:09.800Z` |
| `X-Eco-Deadline-Total` | sim | `2026-09-07T14:32:11.480Z` |
| `X-Eco-Sensitivity` | sim | `PUBLIC` \| `INTERNAL` \| `PERSONAL` \| `FINANCIAL` \| `HEALTH` \| `CLIENT_SOURCE` |

- `X-Eco-User-Id` **nunca** carrega nome, e-mail ou login. É sempre `usr_` + ULID.
- Classes de `X-Eco-Sensitivity`: definições no §8.
- `X-Eco-App-Origin`/`X-Eco-App-Current` aceitam `arman`.
- Os headers de autenticação (`X-Eco-Key-Id`, `X-Eco-Timestamp`, `X-Eco-Nonce`, `X-Eco-Signature`) estão no §9.

### Regras não negociáveis do envelope

1. **`trace_id` é criado uma única vez, na borda** (JARVIS UI, Angular do ConsumoEsperto,
   WhatsApp handler, Arman). Nunca é regerado. É propagado sem alteração até o último salto.

2. **`span_id` é novo a cada salto.** O `span_id` do chamador vira o `parent_span_id` do chamado.

3. **Existem dois deadlines, ambos timestamps absolutos ISO-8601 em UTC:**
   - `X-Eco-Deadline-First-Token` — prazo para o primeiro byte útil chegar ao usuário
   - `X-Eco-Deadline-Total` — prazo para a resposta terminar

   Cada serviço calcula seu orçamento restante como `deadline - now()`. Isso elimina o bug
   clássico de "cada tentativa de fallback recebe timeout cheio".

   **Estouro de `Deadline-First-Token` não mata a requisição.** Ele dispara a política de
   latência: hedge, troca de rota, ou aviso ao usuário. Só o estouro de `Deadline-Total`
   encerra com `DEADLINE_EXCEEDED`.

   O header `X-Eco-Deadline` de v1 fica aceito como sinônimo de `X-Eco-Deadline-Total`
   durante a transição, até 2027-01-31 (§13).

4. **Deadline nunca é estendido.** Um serviço pode encurtar (reservar margem para si), nunca
   aumentar. Se `Deadline-Total - now() <= 0` ao receber a requisição, responda imediatamente
   `DEADLINE_EXCEEDED` sem executar trabalho.

5. **`X-Eco-Sensitivity` só sobe, nunca desce.** Se uma resposta de tool contém dado
   `FINANCIAL`, todo o restante da cadeia herda `FINANCIAL`.
   Ordem total usada para "subir":
   `PUBLIC < INTERNAL < PERSONAL < FINANCIAL < HEALTH < CLIENT_SOURCE`.
   Quando dois dados restritos se combinam, vale o maior na ordem. Todas as classes a partir de `PERSONAL`
   têm a mesma regra de roteamento (§8); a ordem só desempata.

6. **Valor de sensibilidade desconhecido ou ausente.** Um receptor que encontrar um valor que não
   conhece trata como o **mais restritivo** (`CLIENT_SOURCE`). Isso garante que um serviço ainda na v1.1 nunca
   rebaixe `HEALTH` para nuvem. Header ausente: o receptor sintetiza `INTERNAL` **somente** dentro de uma ponte
   registrada (§13); fora dela, rejeita com `INVALID_INPUT`.

7. **Envelope obrigatório para participantes novos.** Para o `arman` (e qualquer participante que
   entre a partir da v1.2), o envelope incompleto é rejeitado (`INVALID_INPUT`). A síntese de envelope
   (`envelope_synthesized: true`) vale só para as pontes já listadas no §13.

### ULID

Todos os IDs usam ULID com prefixo (`tr_`, `sp_`, `conv_`, `task_`, `tool_`, `ctx_`).
ULID e não UUID porque é ordenável por tempo, o que facilita leitura de log.

Prefixos adicionais: `usr_` (usuário), `n_` (nonce do §9, opcional), `req_` (request id da ponte legada).

---

## 2. Modos de execução

| Modo | Deadline primeiro token | Deadline total | Uso |
|---|---|---|---|
| `INTERACTIVE` | 800 ms | 2000 ms | botão de UI, capability direta, comando de voz curto |
| `BALANCED` | 2500 ms | 8000 ms | chat em texto livre, pergunta que precisa de dados |
| `DEEP` | 10000 ms | 60000 ms | análise, planejamento, múltiplas ferramentas |
| `STREAM` | 3000 ms | 300000 ms | resposta longa em SSE, geração extensa |

`INTERACTIVE` é para interação sem ambiguidade: o botão já sabe o que quer, o comando de voz
é determinístico. **Chat em texto livre nunca nasce `INTERACTIVE`** — nasce `BALANCED`.
Um orçamento de 2 s aplicado a texto livre quebra qualquer caminho com modelo.

`STREAM` existe porque um SSE longo tem duas exigências distintas: o primeiro token precisa
ser rápido, o total pode ser longo. Um orçamento único não modela isso.

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
  deadline_first_token: <ISO-8601>
  deadline_total: <ISO-8601>
  model_class: NONE | FAST_SMALL | BALANCED | STRONG
  ats: BYPASS | ENABLED
  sensitivity: PUBLIC | INTERNAL | PERSONAL | FINANCIAL | HEALTH | CLIENT_SOURCE
}
```

O estágio `ats` passa a ser, por padrão, uma chamada **em processo** à biblioteca `ats_core` (§11); `t_ats_ms` mede essa chamada.

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

### Capabilities do Arman

- O `arman` expõe `GET /capabilities` no servidor local de tools (bind obrigatório em `127.0.0.1`).
- Sensibilidade **padrão** de toda capability do Arman: `PERSONAL`. Capability que devolve código-fonte,
  DDL ou PL/SQL de ambiente de cliente: `CLIENT_SOURCE`. Capability que pode devolver dado de paciente ou
  beneficiário: `HEALTH`. O manifesto não pode declarar sensibilidade menor que a padrão.
- Famílias permitidas nesta versão: `arman.screen.inspect` (escopo `arman:screen:inspect`) e
  `arman.context.*` (escopo `arman:context:read`, só dicionário/metadados: `ALL_SOURCE`, `ALL_ERRORS` e afins).
- **Proibido nesta versão:** qualquer capability que execute SQL livre ou devolva linhas de tabelas de
  cliente (ex.: `arman.oracle.query_readonly`, `arman.oracle.metadata` com dados). O escopo
  `arman:oracle:read` existe só para ser **negado**.
- **Regra geral:** capability `kind: READ` que devolve dado de cliente final não pode ter `sensitivity` abaixo de `PERSONAL`.

`arman.context.*` que devolve fonte/DDL de cliente é `CLIENT_SOURCE`; metadados sem código ficam `PERSONAL`.

---

## 5. Métricas de tempo — nomes canônicos

Todo serviço emite estes campos no log estruturado de cada requisição. Nomes idênticos nos
cinco projetos, senão o Control Center não consegue somar nada.

```
t_total_ms            tempo total dentro deste serviço
t_queue_ms            tempo esperando fila/worker antes de começar
t_resolve_ms          capability resolution (embedding + slot filling)
t_tool_ms             chamada de tool (soma, se mais de uma)
t_ats_ms              tempo da compressão ATS (chamada em processo; ou round-trip na ponte de serviço)
t_router_ms           decisão de roteamento (não inclui o provider)
t_provider_total_ms   do envio ao último token — ESTÁGIO
t_verify_ms           verificação
t_unaccounted_ms      t_total_ms menos a soma dos estágios acima

t_provider_ttft_ms    do envio ao primeiro token — RECORTE, não estágio
t_ollama_load_ms      carregamento de modelo, quando houve — RECORTE de t_provider_total_ms
tokens_per_second     taxa de geração medida — DERIVADO

tokens_in_original    contexto antes da compressão
tokens_in_final       contexto enviado ao modelo
tokens_out            tokens gerados
compression_ratio     tokens_in_final / tokens_in_original
fallback_count        quantas rotas foram tentadas e falharam
hedge_fired           true | false
cache_hit             true | false
envelope_synthesized  true quando o envelope foi criado por compatibilidade, não recebido
execution_path        INSTANT | FAST | DEEP
ats_mode              BYPASS | ENABLED
provider              provider efetivamente usado
model                 modelo efetivamente usado
outcome               SUCCESS | DEGRADED | FAILED

auth_scheme           eco-hmac-v1 | legacy
legacy_kind           x-edith-hmac | bearer-app-key | sdk-hmac    só quando auth_scheme = legacy
auth_key_id           key id usado (nunca o segredo)
sensitivity           classe efetiva ao final da cadeia
sensitivity_block     true quando uma rota foi vetada pelo §8
fail_closed           true quando o §8 negou execução por falta da E.D.I.T.H.
optin_id              id do opt-in usado (§8.4), quando houver
deadline_v1_synonym   true quando só veio X-Eco-Deadline (v1)
```

Os campos `auth_scheme` a `deadline_v1_synonym` não entram na regra de soma.

### Regra de soma

**Só campos marcados como ESTÁGIO somam.** A conta que precisa fechar é:

```
t_total_ms = t_queue_ms + t_resolve_ms + t_tool_ms + t_ats_ms
           + t_router_ms + t_provider_total_ms + t_verify_ms
           + t_unaccounted_ms
```

`t_provider_ttft_ms`, `t_ollama_load_ms` e `tokens_per_second` são recortes ou derivados de
`t_provider_total_ms`. **Somá-los junto conta o mesmo tempo duas vezes.** A regra de soma
de v1 estava errada neste ponto.

`t_unaccounted_ms` é obrigatório e nunca é omitido. Ele é o que revela que a instrumentação
tem buraco. `t_unaccounted_ms` acima de 15% de `t_total_ms` é defeito de instrumentação e
deve aparecer como alerta no Control Center.

Campo ausente continua sendo omitido, nunca preenchido com `0`. `0` significa "mediu e deu zero".

### Distinguir fila, prefill e geração

Provider lento tem três causas com correções diferentes. A combinação de campos identifica qual:

| TTFT | tokens_per_second | Diagnóstico | Correção |
|---|---|---|---|
| alto | alto | fila no provider, ou prefill longo | trocar de rota, comprimir contexto |
| alto | baixo | modelo lento ponta a ponta | rebaixar o modelo no score |
| baixo | baixo | geração lenta, modelo subdimensionado | trocar de modelo, não de provider |
| alto | alto, com `t_ollama_load_ms` > 0 | cold start local | keep-alive e preload |

Nenhum incidente de latência pode ser fechado como "provider lento" sem estes três campos.

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

Mapeamento obrigatório:
> - Toda falha do §9 (assinatura, timestamp, nonce repetido, key id desconhecido ou revogado) responde `UNAUTHORIZED`, HTTP 401, `retryable: false`, e `message` genérica. O motivo exato vai só para o log interno, nunca para a resposta.
> - Escopo ou capability fora da allowlist do chamador: `SCOPE_DENIED` (403).
> - Bloqueio fail closed do §8: `UPSTREAM_UNAVAILABLE` com `retryable: true`. Ou, se existir algo útil, uma resposta `DEGRADED` com `degraded_reason: "SENSITIVE_ROUTING_UNAVAILABLE"`.
> - Valor de sensibilidade inválido fora de ponte: `INVALID_INPUT`.

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

Fica registrado o valor `degraded_reason: "SENSITIVE_ROUTING_UNAVAILABLE"` (§8.3). O aviso ao usuário diz que a parte de IA ficou indisponível para proteger os dados dele. Não oferece "enviar mesmo assim" na própria resposta: o opt-in segue o §8.4.

---

## 8. Sensibilidade de dado e roteamento

| Classe | Exemplos | Providers permitidos |
|---|---|---|
| `PUBLIC` | notícias, definições | qualquer |
| `INTERNAL` | preferências de UI, estado de app | qualquer |
| `PERSONAL` | agenda, e-mail, nome, contatos | apenas allowlist `no_train` + Ollama local |
| `FINANCIAL` | transações, faturas, saldos, cartões | apenas allowlist `no_train` + Ollama local |
| `HEALTH` | dado clínico, de paciente ou beneficiário, laudos | apenas allowlist `no_train` + Ollama local |
| `CLIENT_SOURCE` | código-fonte, DDL, PL/SQL, logs e metadados de ambiente de cliente/empregador | Ollama local; nuvem só em provider da allowlist `no_train`, com autorização escrita do cliente dono do código **e** opt-in do usuário (§8.4) |

### 8.1 Regra dura

**Regra dura:** requisição com `sensitivity` em `PERSONAL`, `FINANCIAL`, `HEALTH` ou `CLIENT_SOURCE`
**não pode ser roteada para um provider fora da allowlist**, independentemente do que o score de custo,
qualidade ou latência disser. Isso é uma restrição, não um peso no score.

A allowlist `no_train` vive na E.D.I.T.H. em configuração, com o termo de uso de cada provider
documentado e datado. Provider sem documentação verificada entra como **não permitido**.

Além disso: **nunca envie linhas cruas de tabela financeira para nenhum modelo.** Agregados,
somas e recortes por categoria sim; dump de transações não.
A mesma proibição vale para linhas cruas de tabela com dado `HEALTH` e para resultados de
consulta SQL em banco de cliente. Para modelo vão só agregados, metadados e dicionário de dados.

### 8.2 Quem decide o roteamento

Só a E.D.I.T.H. aplica a allowlist, porque a allowlist vive nela. Um serviço que **não é** a E.D.I.T.H.
(JARVIS, ConsumoEsperto, ATS em modo serviço, Arman) e precisa de modelo para dado `PERSONAL` ou acima tem
dois caminhos permitidos:

1. pedir à E.D.I.T.H. (caminho padrão);
2. usar um modelo local, nas condições do §11.4.

Chamar provedor de nuvem direto com dado `PERSONAL` ou acima é proibido, com ou sem chave própria.

### 8.3 Fail closed quando a E.D.I.T.H. está indisponível

Se a E.D.I.T.H. estiver fora do ar, lenta além do deadline, ou devolver erro, **e** o dado for
`PERSONAL`, `FINANCIAL`, `HEALTH` ou `CLIENT_SOURCE`:

- **é proibido** cair para qualquer provedor de nuvem (inclusive fallback "direto" que exista hoje no código, como o fallback OpenAI/Gemini do ConsumoEsperto ou o cliente de nuvem do JARVIS);
- o serviço responde `DEGRADED` (`degraded_reason: "SENSITIVE_ROUTING_UNAVAILABLE"`) com o que tiver de determinístico (ex.: lista de cartões sem análise), ou `UPSTREAM_UNAVAILABLE`;
- emite `fail_closed: true` e `outcome: DEGRADED|FAILED` na métrica;
- se a classe estiver ausente ou for desconhecida, vale o §1 regra 6: trata como `CLIENT_SOURCE` e falha fechado.

O fallback para nuvem continua permitido **somente** para `PUBLIC` e `INTERNAL`.

### 8.4 Opt-in explícito

O padrão é **desligado** para todos os usuários. Um opt-in só é válido se cumprir **todos** os itens:

1. **Granularidade:** por usuário, por funcionalidade (capability ou família) e por provider. Não existe "opt-in geral".
2. **Provider:** apenas providers já na allowlist `no_train` da E.D.I.T.H. O opt-in **nunca** libera provider fora da allowlist.
3. **O que ele libera:** só usar um provider `no_train` de nuvem **quando o caminho local não estiver disponível**. Ele não desliga a regra fail closed para chamadas diretas (§8.2): a chamada continua passando pela E.D.I.T.H.
4. **Classes:** permitido para `PERSONAL`. **Proibido** para `FINANCIAL` e `HEALTH` nesta versão. Para `CLIENT_SOURCE`, só com autorização escrita do cliente dono do código, registrada por ambiente/cliente e com validade definida, além do opt-in do usuário.
5. **Consentimento:** dado pelo próprio usuário numa tela de configuração, com texto que nomeia o provider e a classe de dado. Nunca por padrão de instalação, flag de ambiente ou prompt.
6. **Registro:** quem, quando, qual funcionalidade, qual provider, qual versão do texto. Guardado no banco do serviço dono (nunca em log de conteúdo). Toda requisição que usar o opt-in emite `optin_id` na métrica.
7. **Revogação:** imediata, a qualquer momento, pela mesma tela. Expira sozinho em 180 dias.

A proibição de opt-in para `FINANCIAL` e `HEALTH` vale só no caminho de **fallback** quando o local falha; o roteamento normal da E.D.I.T.H. para a allowlist `no_train` não muda. `CLIENT_SOURCE` pode usar nuvem `no_train` só com autorização escrita do cliente dono do código (item 4), além do opt-in do usuário.

---

## 9. Autenticação entre serviços

### 9.1 Headers

| Header | Formato | Exemplo |
|---|---|---|
| `X-Eco-Key-Id` | `^[a-z0-9-]+\.[a-z0-9-]+\.[0-9]{8}(\.[0-9]+)?$` | `edith.consumo.20261009` |
| `X-Eco-Timestamp` | segundos Unix (UTC), inteiro decimal, sem sinal, sem zeros à esquerda, sem fração | `1791547200` |
| `X-Eco-Nonce` | `^[A-Za-z0-9_-]{16,64}$`, com ≥ 128 bits de aleatoriedade de CSPRNG; prefixo `n_` + ULID é aceito | `n_01J9ZK3Q7R8S9T0V1W2X3Y4Z5A` |
| `X-Eco-Signature` | 64 caracteres hex **minúsculos** (`^[0-9a-f]{64}$`) | `e9f3e445…aa05` |

A versão do algoritmo é fixada pela primeira linha da string canônica (`ECO-HMAC-SHA256-V1`). Não existe header de algoritmo. Qualquer mudança de algoritmo é um novo valor dessa linha e um bump de contrato.

### 9.2 String canônica (exata)

Dez linhas em UTF-8, separadas por **um único `\n` (LF, 0x0A)**, **sem** `\n` no final e sem espaços extras:

```
linha 1:  ECO-HMAC-SHA256-V1
linha 2:  MÉTODO            — método HTTP em MAIÚSCULAS (GET, POST, …)
linha 3:  PATH_CANÔNICO     — 9.3
linha 4:  QUERY_CANÔNICA    — 9.3 (linha vazia se não houver query)
linha 5:  TIMESTAMP         — exatamente o valor enviado em X-Eco-Timestamp
linha 6:  NONCE             — exatamente o valor enviado em X-Eco-Nonce
linha 7:  KEY_ID            — exatamente o valor enviado em X-Eco-Key-Id
linha 8:  USER_ID           — valor de X-Eco-User-Id, ou vazio se ausente
linha 9:  SENSITIVITY       — valor de X-Eco-Sensitivity, ou vazio se ausente
linha 10: BODY_SHA256       — SHA-256 dos bytes exatos do corpo, hex minúsculo (64 chars)
```

Regras:

- **Corpo:** são os **bytes exatamente como transmitidos** (após qualquer `Content-Encoding` ser *aplicado*, ou seja, os bytes no fio). Proibido re-serializar JSON antes de hashear. Corpo vazio ou ausente usa o SHA-256 de zero bytes: `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`.
- **Valores de header:** usados como recebidos, sem trim interno. Espaço nas pontas é removido, conforme a semântica HTTP. Header com valor contendo `\n` é rejeitado antes da verificação.
- **Por que `User-Id` e `Sensitivity` entram:** sem isso, um intermediário com a requisição em mãos troca o usuário ou rebaixa `FINANCIAL` para `PUBLIC` sem invalidar a assinatura (vetor N2). Os demais headers do envelope (trace, span, modo, deadlines) **não** são assinados: são de observabilidade e podem ser reescritos legitimamente a cada salto.
- **Assinatura:** `hex_minúsculo( HMAC-SHA256( key = bytes UTF-8 do segredo, msg = bytes UTF-8 da string canônica ) )`.

### 9.3 Normalização de path e query

**Path** (a parte antes de `?`, sem esquema, host ou porta; é o path **como recebido no fio pelo serviço final**: proxies não podem reescrevê-lo, e quem precisa reescrever re-assina):

1. Path vazio → `/`.
2. Dividir em `/`. Para cada segmento: decodificar `%XX` em bytes e **re-codificar** mantendo literais só os não reservados do RFC 3986 (`A-Z a-z 0-9 - . _ ~`). Todo o resto vira `%XX` com hex **MAIÚSCULO**.
3. Juntar com `/`. **Não** resolver `.`/`..`, **não** colapsar `//`, **não** remover `/` final.
4. `+` no path é literal e vira `%2B`.

**Query** (a parte após `?`, sem o `?`; sem query ou `?` vazio → linha vazia):

1. Dividir em `&`; descartar partes vazias.
2. Cada parte: separar no **primeiro** `=` em chave e valor. Parte sem `=` vira chave com valor vazio (`flag` → `flag=`).
3. Em chave e valor: `+` vira espaço; decodificar `%XX` em bytes; re-codificar como no path (espaço vira `%20`).
4. Ordenar os pares pela chave codificada e depois pelo valor codificado, por **comparação de bytes ASCII** (repetições preservadas).
5. Juntar como `chave=valor` com `&`.

Fragmento (`#…`) nunca entra.

### 9.4 Verificação (ordem obrigatória)

1. Os quatro headers presentes e com o formato de 9.1. Caso contrário, `UNAUTHORIZED`.
2. `X-Eco-Key-Id` existe, está **ativo**, e pertence ao par (chamador → este serviço). Caso contrário, `UNAUTHORIZED`.
3. Janela: `|now_utc_s − timestamp| ≤ 60`. Caso contrário, `UNAUTHORIZED`. O relógio vem de NTP. Janela maior que 60 s é proibida.
4. Recalcular a assinatura e comparar **em tempo constante** sobre os bytes ASCII dos dois hex: Python `hmac.compare_digest`, Java `MessageDigest.isEqual`, Node `crypto.timingSafeEqual` (com checagem prévia de tamanho). Proibido `==`, `equals`, `equalsIgnoreCase`. Assinatura com hex maiúsculo é rejeitada no passo 1, nunca normalizada.
5. **Só depois** de a assinatura bater, registrar o nonce de forma atômica: Redis `SET <ns>:nonce:<key_id>:<nonce> 1 NX EX 120`, com `<ns>` = prefixo do serviço receptor (§11). Se a chave já existir, é replay → `UNAUTHORIZED`.
   - **Redis indisponível = rejeitar** (fail closed). Nunca aceitar sem checar o nonce.
   - O Arman (desktop, **instância única**, sem Redis) pode usar um cache de nonce em memória com o mesmo TTL e o mesmo limite de tamanho, descartando por expiração. Ao reiniciar, rejeita timestamps anteriores ao próprio boot.
   - O **JARVIS não** usa cache em memória: mantém o nonce fora da memória do processo (armazenamento persistente), com o mesmo registro atômico e o mesmo TTL.
6. Aplicar a allowlist de capabilities e os escopos do chamador (9.6). Fora dela → `SCOPE_DENIED`.

TTL 120 s = 2 × janela, cobrindo `ts` até 60 s no futuro e 60 s no passado.

Toda falha dos passos 1–5 vira `UNAUTHORIZED` genérico (§6). O log interno registra `auth_key_id`, o passo que falhou e o `trace_id`, **nunca** o segredo, a assinatura esperada ou a string canônica completa.

### 9.5 Segredos, key ids e rotação

- **Um segredo por par direcionado** (`edith→consumo` ≠ `consumo→edith`). Nunca um segredo global, nunca reutilizar o mesmo segredo em dois pares.
- **Segredo:** ≥ 32 bytes de CSPRNG, codificado em base64url sem padding (≥ 43 caracteres ASCII, ex.: `secrets.token_urlsafe(32)`, que é o que a E.D.I.T.H. já usa). A chave HMAC é **a string ASCII como bytes UTF-8**, não o resultado de decodificar o base64.
- **Key id:** `<chamador>.<chamado>.<aaaammdd>[.n]`, com a data de emissão (ex.: `consumo.edith.20261009`, `edith.consumo.20261009.2`). O key id é público e aparece em log. O segredo, nunca.
- **Armazenamento:** variável de ambiente ou cofre do servidor. Em app desktop, o armazenamento protegido do SO (DPAPI/Credential Manager, Keychain, libsecret). Proibido em repositório, `.env` versionado, log, URL ou prompt.
- **Rotação** (sem downtime):
  1. O receptor cadastra a chave nova como **ativa** (passa a aceitar as duas).
  2. O emissor troca para a chave nova.
  3. A chave antiga é revogada em no máximo **7 dias**.
  - No máximo **2 chaves ativas** por par.
  - Vida máxima de uma chave: **180 dias**.
  - **Comprometimento** = revogação imediata (sem janela de sobreposição) e registro no `docs/SECURITY_LOG.md` do serviço.
- `GET /capabilities` também é assinado. Não existe endpoint de serviço sem assinatura, exceto `GET /health`.

### 9.6 Escopos e allowlist

- Allowlist de capabilities **por key id/chamador**, na configuração do receptor.
- Escopos: `finance:read`, `finance:write`, `desktop:action`, `email:read`, `agenda:read`,
  `arman:context:read`, `arman:screen:inspect`, `arman:oracle:read`.
- Separador **sempre `:`** (`domínio:recurso[:ação]`). Variantes com `.` encontradas no código (ex.: `arman.oracle.read` em `edith/services/application_gateway/scopes.py:19-39`) são normalizadas para `:` na migração.
- **Default deny.** Escopo ausente é escopo negado.
- `finance:write` e `desktop:action` **desabilitados nesta versão**.
- `arman:oracle:read` **desabilitado nesta versão** (só existe para ser negado e auditado; ver §4).

### 9.7 Vetores de teste oficiais

Calculados em 09/10/2026 com a implementação de referência em Python (`eco_hmac_v12_ref.py`, anexo A). V1 e V2 foram conferidos de forma independente com `openssl dgst -hmac` e V4 com Node `crypto.createHmac`; todos bateram. **Toda implementação (Python, Java, TypeScript, PowerShell/C#) deve ter um teste unitário que reproduz estes valores.**

Segredo de teste (público, **nunca** usar fora de teste):

```
eco_test_secret_NAO_USAR_EM_PRODUCAO_0123456789abcdef
```

Timestamp comum: `1791547200` (= 2026-10-09T12:00:00Z).

**V1 — POST de tool com JSON**

| Entrada | Valor |
|---|---|
| método | `POST` |
| path bruto / query bruta | `/api/internal/edith/tools` / (nenhuma) |
| nonce | `n_01J9ZK3Q7R8S9T0V1W2X3Y4Z5A` |
| key id | `edith.consumo.20261009` |
| user id / sensitivity | `usr_01J8Z9K2M4N6P8Q0R2S4T6VA` / `FINANCIAL` |
| body (bytes UTF-8, sem espaço nem newline) | `{"capability":"finance.cards.list","input":{}}` |
| SHA-256 do body | `f04f378225178b2444889edab248f11064922a5bba6ab4dc7b9476caa527a796` |

String canônica (as linhas abaixo separadas por LF, sem LF final; a linha 4 é vazia):

```
ECO-HMAC-SHA256-V1
POST
/api/internal/edith/tools

1791547200
n_01J9ZK3Q7R8S9T0V1W2X3Y4Z5A
edith.consumo.20261009
usr_01J8Z9K2M4N6P8Q0R2S4T6VA
FINANCIAL
f04f378225178b2444889edab248f11064922a5bba6ab4dc7b9476caa527a796
```

**Assinatura esperada:** `e9f3e445af232413449e66a60e7f6e88e924bb2ed35a67e9673b7d430d6aaa05`

**V2 — GET com método minúsculo e query fora de ordem**

| Entrada | Valor |
|---|---|
| método recebido | `get` (canoniza para `GET`) |
| path bruto | `/api/v1/integrations/tasks/task_445/events` |
| query bruta | `since=10&b=caf%c3%a9+bar&a=2&a=1&flag&x=%7e` |
| nonce / key id | `n_01J9ZK3Q7R8S9T0V1W2X3Y4Z5B` / `consumo.edith.20261009` |
| user id / sensitivity | `usr_01J8Z9K2M4N6P8Q0R2S4T6VA` / `FINANCIAL` |
| body | vazio (0 bytes) → `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| **query canônica** | `a=1&a=2&b=caf%C3%A9%20bar&flag=&since=10&x=~` |

```
ECO-HMAC-SHA256-V1
GET
/api/v1/integrations/tasks/task_445/events
a=1&a=2&b=caf%C3%A9%20bar&flag=&since=10&x=~
1791547200
n_01J9ZK3Q7R8S9T0V1W2X3Y4Z5B
consumo.edith.20261009
usr_01J8Z9K2M4N6P8Q0R2S4T6VA
FINANCIAL
e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
```

**Assinatura esperada:** `5a3695f9be037417152f03359e7c4d91df95461118fb508de86f05660fd85683`

O que V2 testa: método em maiúsculas; `%c3%a9` minúsculo vira `%C3%A9`; `+` vira `%20`; `%7e` vira `~` (não reservado); `flag` vira `flag=`; ordenação com repetição (`a=1` antes de `a=2`).

**V3 — `GET /capabilities` sem usuário nem sensibilidade (Arman)**

| Entrada | Valor |
|---|---|
| método / path / query | `GET` / `/capabilities` / (nenhuma) |
| nonce / key id | `n_01J9ZK3Q7R8S9T0V1W2X3Y4Z5C` / `edith.arman.20261009` |
| user id / sensitivity | ausentes → linhas 8 e 9 vazias |
| body | vazio |

```
ECO-HMAC-SHA256-V1
GET
/capabilities

1791547200
n_01J9ZK3Q7R8S9T0V1W2X3Y4Z5C
edith.arman.20261009

e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
```

**Assinatura esperada:** `9adf9772f6f8ef0f4a248c17bd5b33d7b7f3bca2d349591bd0603f1dc6f7bd51`

**V4 — path com acento e espaço codificados; body com UTF-8 multibyte**

| Entrada | Valor |
|---|---|
| método | `POST` |
| path bruto | `/api/v1/integrations/notas/Relat%c3%b3rio%20mensal` |
| **path canônico** | `/api/v1/integrations/notas/Relat%C3%B3rio%20mensal` |
| nonce / key id | `n_01J9ZK3Q7R8S9T0V1W2X3Y4Z5D` / `jarvis.edith.20261009` |
| user id / sensitivity | `usr_01J8Z9K2M4N6P8Q0R2S4T6VA` / `PERSONAL` |
| body (UTF-8; `á` = `C3 A1`) | `{"texto":"olá"}` |
| SHA-256 do body | `3883720899a3e4f084e237d1c9a48f06e8405c7f5d61b58f5450c808fde7d2d4` |

**Assinatura esperada:** `05044ddb4ed570b8fc89a2218e8cb638aad4a5b77067cf93202c9980333e70df`

**Negativos (o verificador deve rejeitar a assinatura de V1 nestes casos)**

| Vetor | Alteração em V1 | Assinatura correta para a requisição alterada | Esperado ao apresentar a assinatura de V1 |
|---|---|---|---|
| N1 | path `/api/internal/edith/tools2` | `3068e21e0e29c81809f8cc062e100ce694e5843a4e990ff7f826bd920f30228f` | `UNAUTHORIZED` |
| N2 | `X-Eco-Sensitivity: PUBLIC` (rebaixamento) | `96e5517ab2506c3a4441f13ab2f9cd9abc4f6e76bcee3b8cb07362628c2b991b` | `UNAUTHORIZED` |
| N3 | V1 reenviado com o mesmo nonce dentro de 120 s | (igual a V1) | `UNAUTHORIZED` (replay) |
| N4 | V1 com `now = 1791547261` (61 s depois) | (igual a V1) | `UNAUTHORIZED` (janela) |
| N5 | V1 com a assinatura em MAIÚSCULAS | — | `UNAUTHORIZED` (formato) |

### 9.8 Ponte legada `X-Edith-*` e Bearer de app

O que existe hoje continua aceito **até a data de remoção**, como ponte do §13:

| Esquema legado | Onde está | String assinada | Métrica |
|---|---|---|---|
| `X-Edith-Timestamp`, `X-Edith-Nonce`, `X-Edith-Request-Id`, `X-Edith-Signature` | callbacks E.D.I.T.H. ↔ ConsumoEsperto (`callback_auth.py`; `EdithCallbackHeaders.java:8-11`) | `timestamp\nnonce\nrequest_id\nsha256(body)hex` → HMAC-SHA256 hex | `auth_scheme: legacy`, `legacy_kind: x-edith-hmac` |
| `Authorization: Bearer edith_*` (chave de app) | clientes → E.D.I.T.H. (JARVIS, ConsumoEsperto) | — | `auth_scheme: legacy`, `legacy_kind: bearer-app-key` |
| HMAC do `EdithToolAuthenticator` do SDK no servidor de tools do Arman (`127.0.0.1:18765/edith-tools`) | E.D.I.T.H. → Arman (`ArmanLocalToolServer.java:25,51-58,96-99`) | (esquema do SDK; a equivalência com `X-Edith-*` é verificada na migração do Arman) | `auth_scheme: legacy`, `legacy_kind: sdk-hmac` |

Regras da ponte (valem **já**, mesmo antes da migração):

1. **Marcação:** toda requisição aceita por esquema legado emite `auth_scheme: legacy` e `legacy_kind`. O Control Center conta por `legacy_kind` e por serviço.
2. **Endurecimento mínimo:**
   - janela ≤ **60 s** (o ConsumoEsperto baixa de 300 para 60);
   - TTL do nonce ≥ **120 s** (a E.D.I.T.H. já usa 180, o que é aceito);
   - comparação em tempo constante;
   - Redis/Postgres indisponível = rejeitar.
3. **Precedência:** se a requisição trouxer `X-Eco-Signature`, **só** o esquema v1.2 é verificado. Os headers `X-Edith-*` são ignorados, sem fallback para o legado em caso de falha.
4. **Participantes novos:** o `arman` não ganha ponte de `X-Edith-*`. A única ponte dele é `sdk-hmac`.
5. **Remoção:** data-alvo **2027-01-31**. Depois dela, o legado responde `UNAUTHORIZED`. Cada repositório que ainda aceita ou emite o legado registra a ponte em `docs/COMPAT_DEBT.md`:

```markdown
| Ponte | Por que existe | Para sair | Métrica | Data-alvo |
|---|---|---|---|---|
| Auth legada `X-Edith-*` (HMAC timestamp/nonce/request_id/body) | callbacks já em produção entre E.D.I.T.H. e ConsumoEsperto antes do contrato v1.2 §9 | os dois lados assinam e verificam `ECO-HMAC-SHA256-V1` (vetores §9.7 passando) e a contagem `legacy_kind=x-edith-hmac` fica em zero por 14 dias | `auth_scheme=legacy`, `legacy_kind=x-edith-hmac` | 2027-01-31 |
| Auth legada `Bearer edith_*` entre serviços | clientes usam chave de app em vez de HMAC por par | clientes de serviço migram para HMAC v1.2; Bearer continua só para usuário final | `auth_scheme=legacy`, `legacy_kind=bearer-app-key` | 2027-01-31 |
```

O `Bearer edith_*` continua para **usuário final** (UI → E.D.I.T.H.) depois de 2027-01-31: fica fora do §9 e fora da ponte. A v1.2 só proíbe esse Bearer **entre serviços**.

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

Stream usa os dois deadlines de forma independente: `Deadline-First-Token` governa quanto tempo
o usuário espera pelo evento `token` inicial, e `Deadline-Total` governa o encerramento.
Um stream não é morto por estourar o prazo de primeiro token.

A assinatura do §9 cobre a **requisição** que abre o stream. Os eventos não são assinados individualmente: o canal é a resposta da mesma conexão.

---

## 11. Namespaces de infraestrutura

Servidor compartilhado, dados separados.

### 11.1 Serviços de servidor

- Postgres: bancos `edith_db` e `consumo_db`, com **roles distintos**.
  Nenhum role tem acesso de leitura ao banco de outro serviço. Sem exceção.
- Redis: prefixos `edith:`, `consumo:`, `jarvis:`. Redis **sempre com senha** e nunca publicado fora de loopback ou da rede interna. Nonces do §9: `<prefixo>nonce:<key_id>:<nonce>`.
- Ollama: instância única, acessada **apenas pela E.D.I.T.H.**. Nenhum outro **serviço de servidor** abre conexão direta.

### 11.2 ATS como biblioteca em processo

- O modo canônico do ATS é a biblioteca `ats_core` (`TokenSuppressor().compress(...)`), **importada pela E.D.I.T.H.** e executada no processo dela, com versão fixada (pacote versionado).
- **Sem infraestrutura própria:** a biblioteca não abre conexão de banco, Redis, Ollama, LiteLLM ou provedor. Tudo chega por *ports* injetados pelo hospedeiro (cache, embedding, métricas, sumarização).
- **Armazenamento:** cache e estado vivem no Redis **do hospedeiro**, com prefixo `edith:ats:` (ex.: `edith:ats:compress:<tenant>:<hash>`). Dados persistentes, se houver, ficam no `edith_db`, sob o role da E.D.I.T.H. e num schema dedicado (`ats`). Isso regulariza o `EDITH_MANAGED_SCHEMA` atual. **O tenant entra sempre na chave.**
- **Ollama:** se o ATS precisar de embedding ou sumarização local, chama a port, que a E.D.I.T.H. implementa com **a Ollama dela**. A regra "só a E.D.I.T.H. acessa Ollama" continua valendo sem exceção.
- **Sem conteúdo em log:** a biblioteca não registra prompt nem texto comprimido. Emite só contagens e tempos (`tokens_in_original`, `tokens_in_final`, `compression_ratio`, `t_ats_ms`).
- **Sensibilidade:** a biblioteca recebe a classe do §8 e **nunca** chama provedor (a compressão é local). Por isso não muda o roteamento. Se uma estratégia de compressão precisar de modelo, para `PERSONAL` ou acima ela só pode usar a port local.
- **Modo serviço (FastAPI `/compress`, `/optimize`, proxy `/v1/*`, `ats_db`, Redis `ats:`):** passa a ser **ponte de compatibilidade** com data no `docs/COMPAT_DEBT.md` do ATS (**2027-03-31**). Enquanto existir:
  - aceita só HMAC §9;
  - aplica o §8 (o proxy `/v1/*` recusa `PERSONAL` ou acima para nuvem);
  - usa `ats_db` com role próprio e Redis `ats:` com senha.

### 11.3 Apps desktop (JARVIS, Arman)

- Dados locais ficam no perfil do usuário (`%APPDATA%\<app>` ou equivalente), nunca na pasta de instalação nem no repositório.
- Segredos (chaves do §9, tokens) ficam no armazenamento protegido do SO (§9.5). JSON em texto puro é proibido.
- Servidor local de tools: bind **somente** em `127.0.0.1`, com §9 obrigatório.

### 11.4 Ollama local do usuário (desktop)

A regra de 11.1 vale para o **servidor**. Um app desktop pode chamar uma Ollama **na própria máquina do usuário** (`127.0.0.1`) para dado `PERSONAL` ou acima **somente** se:

1. o endpoint for loopback (não configurável para host remoto sem passar pelo §8.4);
2. a chamada emitir as métricas do §5 com `provider: ollama-local`.

Ollama local nos apps desktop (Arman/JARVIS) é permitida **só em loopback**, como exceção explícita ao 11.1.

---

## 12. Versionamento

Este contrato é `v1.2`. Serviços expõem `GET /health` retornando:

```json
{ "service": "consumo-esperto", "contract_version": "1.2", "status": "ok|degraded", "checks": {} }
```

Incompatibilidade de `contract_version` é falha de integração, deve aparecer no Control Center.

- **Transição:** durante a migração, o Control Center aceita `"1.1"` e `"1.2"` como compatíveis e mostra alerta amarelo para `"1.1"`. `"1"` (o que a E.D.I.T.H. devolve hoje em `main.py:374`) aparece como incompatível.
- Um serviço só pode declarar `"1.2"` quando passar nos vetores do §9.7 e cumprir o §8.3.

---

## 13. Compatibilidade e prazo de remoção

Integrações anteriores ao contrato continuam funcionando durante a transição, com duas
condições obrigatórias.

1. **Toda ponte de compatibilidade é marcada na métrica.** Envelope sintetizado por ausência
   marca `envelope_synthesized: true`. Autenticação por esquema antigo marca
   `auth_scheme: legacy` e `legacy_kind` (§9.8). Sem marcação, a ponte é invisível e vira permanente.

2. **Toda ponte tem data de remoção definida no momento em que é criada**, registrada em
   `docs/COMPAT_DEBT.md` do repositório, com: o que é, por que existe, o que precisa acontecer
   para sair, e a data-alvo. Ponte sem data no documento é defeito.

O Control Center exibe a contagem de requisições servidas por ponte de compatibilidade. Se ela
não cair ao longo do tempo, a migração não está acontecendo.

3. **Pontes não se aplicam a participantes novos.** O `arman` entra com envelope obrigatório
   (§1 regra 7). A única ponte dele é `sdk-hmac` (§9.8).

4. **Nenhuma ponte pode relaxar o §8.** Envelope sintetizado nunca gera sensibilidade abaixo
   da classe do dado. Na dúvida, vale o §1 regra 6.

### Pontes conhecidas na data desta versão

| Ponte | Repositórios | Métrica | Data-alvo |
|---|---|---|---|
| Auth `X-Edith-*` (§9.8) | edith, consumo-esperto | `legacy_kind=x-edith-hmac` | 2027-01-31 |
| Bearer `edith_*` entre serviços (§9.8) | edith, jarvis, consumo-esperto | `legacy_kind=bearer-app-key` | 2027-01-31 (Bearer de usuário final continua) |
| HMAC do SDK no tool server do Arman (§9.8) | arman, edith | `legacy_kind=sdk-hmac` | 2027-01-31 |
| Header `X-Eco-Deadline` de v1 (§1 regra 3) | edith, consumo-esperto (o frontend envia só ele: `eco-envelope.ts:11,73`) | `deadline_v1_synonym=true` (§5) | 2027-01-31 |
| Envelope sintetizado (ausência de `X-Eco-*`) | edith (já registrado em `edith/docs/COMPAT_DEBT.md`), consumo-esperto | `envelope_synthesized=true` | **2026-12-07**, a data já registrada; mantida. Se a migração de JARVIS e ConsumoEsperto não terminar até lá, a data é revista no COMPAT_DEBT, nunca removida |
| ATS em modo serviço (§11.2) | ats | `ats_mode` + contagem de chamadas HTTP ao ATS | 2027-03-31 |

---

## Anexo A — Implementação de referência (Python)

Implementação que gerou os vetores do §9.7. Núcleo:

```python
import hashlib, hmac
from urllib.parse import unquote_to_bytes

UNRESERVED = set(b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~")

def _enc(b: bytes) -> str:
    return "".join(chr(c) if c in UNRESERVED else "%%%02X" % c for c in b)

def canonical_path(raw_path: str) -> str:
    if not raw_path:
        return "/"
    return "/".join(_enc(unquote_to_bytes(seg)) for seg in raw_path.split("/"))

def canonical_query(raw_query: str) -> str:
    if not raw_query:
        return ""
    pairs = []
    for part in raw_query.split("&"):
        if part == "":
            continue
        k, _, v = part.partition("=")
        pairs.append((_enc(unquote_to_bytes(k.replace("+", "%20"))),
                      _enc(unquote_to_bytes(v.replace("+", "%20")))))
    pairs.sort()
    return "&".join(f"{k}={v}" for k, v in pairs)

def canonical_string(method, raw_path, raw_query, timestamp, nonce, key_id,
                     user_id, sensitivity, body: bytes) -> str:
    return "\n".join(["ECO-HMAC-SHA256-V1", method.upper(), canonical_path(raw_path),
                      canonical_query(raw_query), str(timestamp), nonce, key_id,
                      user_id or "", sensitivity or "", hashlib.sha256(body).hexdigest()])

def sign(secret: str, **kw) -> str:
    return hmac.new(secret.encode("utf-8"), canonical_string(**kw).encode("utf-8"),
                    hashlib.sha256).hexdigest()

def verify(secret: str, received_sig: str, **kw) -> bool:
    # formato (64 hex minúsculos) é checado antes; comparação em tempo constante
    return hmac.compare_digest(sign(secret, **kw).encode("ascii"), received_sig.encode("ascii"))
```

Legado (só para teste da ponte, §9.8), vetor **L1**:

```
timestamp  = 1791547200
nonce      = n_01J9ZK3Q7R8S9T0V1W2X3Y4Z5A
request_id = req_01J9ZK3Q7R8S9T0V1W2X3Y4Z5E
body       = {"capability":"finance.cards.list","input":{}}
string     = "1791547200\nn_01J9ZK3Q7R8S9T0V1W2X3Y4Z5A\nreq_01J9ZK3Q7R8S9T0V1W2X3Y4Z5E\nf04f378225178b2444889edab248f11064922a5bba6ab4dc7b9476caa527a796"
assinatura = e856f0676f4ffa6eb494d2bfe16607961f00bcd5821f8ce53f3247fd241d4342
```
