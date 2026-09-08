# PREFILL_CURVE.md — bloqueio

**Status:** BLOQUEADO  
**Data:** 2026-09-07  
**Dono do limiar:** E.D.I.T.H. (config `ats` bypass)  
**Dono da curva:** medição (este script / host Ollama)

## Tentativa

| Alvo | Resultado |
|------|-----------|
| `http://127.0.0.1:11434` | connection failed |
| Script | `scripts/phase0_benchmarks.py` → `ollama_prefill.status = unavailable` |

## O que entregar quando Ollama voltar

1. TTFT (ou `prompt_eval_duration`) para **500, 2000, 8000, 16000, 32000** tokens.  
2. Comparar com custo de compressão in-process (já medido: p95 ≈ 5 ms @2k, 32 ms @16k).  
3. Um número: **`bypass_below_tokens`** = menor N onde  
   `prefill(N) - prefill(N_comprimido) > t_compress_p95`.  
4. Colar tabela aqui; **não** reabrir Decisão A.

## Comando

```bash
set OLLAMA_BASE_URL=http://<host>:11434
set OLLAMA_MODEL=llama3.2:3b
cd backend
python ../scripts/phase0_benchmarks.py
# Atualizar este arquivo com points[] e bypass_below_tokens
```

**Este bloqueio não segura inventário, ADR nem Decisão A.**
