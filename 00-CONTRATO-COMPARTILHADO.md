# Patch do Contrato — v1 → v1.1

> Aplique este patch em **`docs/ECOSYSTEM_CONTRACT.md` dos quatro repositórios**, na mesma
> sessão, antes de iniciar a rodada 2. Depois rode o script de verificação de hash.
> Nenhum agente aplica este patch sozinho. Você aplica.

Origem: quatro objeções levantadas pelos agentes na rodada 0. Todas aceitas. Três eram erro meu.

---

## Mudança 1 — Cabeçalho

Substitua a linha de versão no topo do documento:

```
# Contrato do Ecossistema — v1.1 (CONGELADO)
```

E na seção 12, `contract_version` passa a ser `"1.1"`.

---

## Mudança 2 — Seção 2, tabela de modos

**Substitua a tabela inteira por:**

| Modo | Deadline primeiro token | Deadline total | Uso |
|---|---|---|---|
| `INTERACTIVE` | 800 ms | 2000 ms | botão de UI, capability direta, comando de voz curto |
| `BALANCED` | 2500 ms | 8000 ms | chat em texto livre, pergunta que precisa de dados |
| `DEEP` | 10000 ms | 60000 ms | análise, planejamento, múltiplas ferramentas |
| `STREAM` | 3000 ms | 300000 ms | resposta longa em SSE, geração extensa |

**Acrescente logo abaixo:**

> `INTERACTIVE` é para interação sem ambiguidade: o botão já sabe o que quer, o comando de voz
> é determinístico. **Chat em texto livre nunca nasce `INTERACTIVE`** — nasce `BALANCED`.
> Um orçamento de 2 s aplicado a texto livre quebra qualquer caminho com modelo.
>
> `STREAM` existe porque um SSE longo tem duas exigências distintas: o primeiro token precisa
> ser rápido, o total pode ser longo. Um orçamento único não modela isso.

---

## Mudança 3 — Seção 1, regra 3 (deadline duplo)

**Substitua a regra 3 por:**

> 3. **Existem dois deadlines, ambos timestamps absolutos ISO-8601 em UTC:**
>    - `X-Eco-Deadline-First-Token` — prazo para o primeiro byte útil chegar ao usuário
>    - `X-Eco-Deadline-Total` — prazo para a resposta terminar
>
>    Cada serviço calcula seu orçamento restante como `deadline - now()`. Isso elimina o bug
>    de "cada tentativa de fallback recebe timeout cheio".
>
>    **Estouro de `Deadline-First-Token` não mata a requisição.** Ele dispara a política de
>    latência: hedge, troca de rota, ou aviso ao usuário. Só o estouro de `Deadline-Total`
>    encerra com `DEADLINE_EXCEEDED`.
>
>    O header `X-Eco-Deadline` de v1 fica aceito como sinônimo de `X-Eco-Deadline-Total`
>    durante a transição, e sai na v2.

**Na tabela de headers da seção 1**, substitua a linha `X-Eco-Deadline` por:

| `X-Eco-Deadline-First-Token` | sim | `2026-09-07T14:32:09.800Z` |
| `X-Eco-Deadline-Total` | sim | `2026-09-07T14:32:11.480Z` |

---

## Mudança 4 — Seção 5, métricas

**Substitua o bloco de métricas por:**

```
t_total_ms            tempo total dentro deste serviço
t_queue_ms            tempo esperando fila/worker antes de começar
t_resolve_ms          capability resolution (embedding + slot filling)
t_tool_ms             chamada de tool (soma, se mais de uma)
t_ats_ms              round-trip para o AI Token Suppressor
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
```

**Substitua a regra de soma por:**

> **Só campos marcados como ESTÁGIO somam.** A conta que precisa fechar é:
>
> ```
> t_total_ms = t_queue_ms + t_resolve_ms + t_tool_ms + t_ats_ms
>            + t_router_ms + t_provider_total_ms + t_verify_ms
>            + t_unaccounted_ms
> ```
>
> `t_provider_ttft_ms`, `t_ollama_load_ms` e `tokens_per_second` são recortes ou derivados de
> `t_provider_total_ms`. **Somá-los junto conta o mesmo tempo duas vezes.** A regra de soma
> de v1 estava errada neste ponto.
>
> `t_unaccounted_ms` é obrigatório e nunca é omitido. Ele é o que revela que a instrumentação
> tem buraco. `t_unaccounted_ms` acima de 15% de `t_total_ms` é defeito de instrumentação e
> deve aparecer como alerta no Control Center.
>
> Campo ausente continua sendo omitido, nunca preenchido com `0`.

---

## Mudança 5 — Seção 5, diagnóstico de provider lento

**Acrescente ao final da seção 5:**

> ### Distinguir fila, prefill e geração
>
> Provider lento tem três causas com correções diferentes. A combinação de campos identifica qual:
>
> | TTFT | tokens_per_second | Diagnóstico | Correção |
> |---|---|---|---|
> | alto | alto | fila no provider, ou prefill longo | trocar de rota, comprimir contexto |
> | alto | baixo | modelo lento ponta a ponta | rebaixar o modelo no score |
> | baixo | baixo | geração lenta, modelo subdimensionado | trocar de modelo, não de provider |
> | alto | alto, com `t_ollama_load_ms` > 0 | cold start local | keep-alive e preload |
>
> Nenhum incidente de latência pode ser fechado como "provider lento" sem estes três campos.

---

## Mudança 6 — Nova seção 13

**Acrescente ao final do documento:**

```markdown
## 13. Compatibilidade e prazo de remoção

Integrações anteriores ao contrato continuam funcionando durante a transição, com duas
condições obrigatórias.

1. **Toda ponte de compatibilidade é marcada na métrica.** Envelope sintetizado por ausência
   marca `envelope_synthesized: true`. Autenticação por esquema antigo marca
   `auth_scheme: legacy`. Sem marcação, a ponte é invisível e vira permanente.

2. **Toda ponte tem data de remoção definida no momento em que é criada**, registrada em
   `docs/COMPAT_DEBT.md` do repositório, com: o que é, por que existe, o que precisa acontecer
   para sair, e a data-alvo. Ponte sem data no documento é defeito.

O Control Center exibe a contagem de requisições servidas por ponte de compatibilidade. Se ela
não cair ao longo do tempo, a migração não está acontecendo.
```

---

## Depois de aplicar

```bash
REPOS=(~/dev/jarvis ~/dev/edith ~/dev/consumo-esperto ~/dev/ai-token-suppressor)
REF=$(sha256sum "${REPOS[0]}/docs/ECOSYSTEM_CONTRACT.md" | cut -d' ' -f1)
for r in "${REPOS[@]}"; do
  h=$(sha256sum "$r/docs/ECOSYSTEM_CONTRACT.md" 2>/dev/null | cut -d' ' -f1)
  [ "$h" = "$REF" ] && echo "ok          $r" || echo "DIVERGENTE  $r"
done
```

As quatro cópias precisam bater antes de qualquer agente rodar.