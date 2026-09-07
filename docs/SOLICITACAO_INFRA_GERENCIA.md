# Solicitação de Infraestrutura — AI Token Suppressor

**Projeto:** Middleware de compressão de prompts (LLMs)  
**Cenário:** **200+ usuários**, modo **`ultra`** + **`use_ollama: true`**  
**Data:** Junho/2026  

---

## 1. Resumo — três perfis de infraestrutura

| Perfil | Objetivo | RAM | Disco | vCPU |
|--------|----------|-----|-------|------|
| **Mínimo** | Funcionar em produção com restrições | **16 GB** | **80 GB SSD** | **4** |
| **Recomendado** | 200+ usuários, ultra estável | **32 GB** | **120 GB SSD** | **8** |
| **Ideal (rodar liso)** | Sem fila longa, pico confortável, SLA | **48–64 GB** | **250 GB SSD** | **16** (+ GPU opcional) |

> **Não usar** o ambiente atual (4 GB) para 200 usuários em ultra — entra em swap e cai (502).

---

## 2. Perfil MÍNIMO (viável, com limitações)

**Para quem é:** piloto interno, até ~50 usuários ativos simultâneos no pico, ou 200 usuários com **fila** e tolerância a espera de 1–3 min por compressão.

### Hardware

| Recurso | Especificação |
|---------|---------------|
| RAM | **16 GB** (tudo em 1 servidor) |
| vCPU | **4 cores** |
| Disco | **80 GB SSD** |
| GPU | Não |
| Rede | 100 Mbps |

### Software obrigatório

- Docker 24+ e Docker Compose v2  
- PostgreSQL 15+ com **pgvector**  
- Redis 7  
- Ollama com **llama3.2:3b** (1 instância)  
- Nginx + SSL  

### Serviços Docker (stack)

| Serviço | Incluir? |
|---------|----------|
| redis, api, frontend | Sim |
| Ollama (host) | Sim |
| Celery | Opcional (fila manual) |
| Prometheus/Grafana | Não |
| LiteLLM container | Não |

### Comportamento esperado

| Métrica | Valor típico |
|---------|--------------|
| Compressão ultra (1.700 tokens) | **30–90 s** (CPU) |
| Usuários em pico | Fila; 20–30 req simultâneas **não** atendidas em paralelo |
| Disponibilidade | ~95% (picos com lentidão) |
| Risco | Swap em pico; reiniciar Ollama se travar |

### Config `.env` (mínimo)

```env
PROXY_DEFAULT_STRATEGY=ultra
PROXY_USE_OLLAMA=true
DATABASE_POOL_SIZE=5
REDIS maxmemory ~512mb
```

---

## 3. Perfil RECOMENDADO (produção — 200+ usuários)

**Para quem é:** produção oficial com **200+ colaboradores**, ultra sempre ativo, sem aceitar quedas frequentes.

### Hardware

| Recurso | Especificação |
|---------|---------------|
| RAM | **32 GB** |
| vCPU | **8 cores** |
| Disco | **120 GB SSD/NVMe** |
| GPU | Opcional |
| Rede | 500 Mbps – 1 Gbps |

### Arquitetura

**Opção A (1 servidor):** API + Postgres + Redis + Ollama no mesmo host (32 GB).  
**Opção B (2 servidores — preferível):**

| Servidor | RAM | Função |
|----------|-----|--------|
| App | **16 GB** | API x2, Redis, Postgres, Nginx, Celery |
| Inferência | **16 GB** | Só Ollama (llama3.2:3b + nomic-embed) |

### Software

Tudo do mínimo **mais:**

- Celery (2 workers) + fila Redis  
- Prometheus + Grafana (alertas RAM/CPU)  
- Backup diário Postgres  

### Comportamento esperado

| Métrica | Valor típico |
|---------|--------------|
| Compressão ultra (1.700 tokens) | **15–45 s** |
| Pico | 20–30 req com fila Celery; sem swap constante |
| Cache Redis | 2 GB — hits repetidos em **&lt; 1 s** |
| Disponibilidade alvo | **99%** |

### Config `.env` (recomendado)

```env
PROXY_DEFAULT_STRATEGY=ultra
PROXY_USE_OLLAMA=true
DATABASE_POOL_SIZE=10
DATABASE_MAX_OVERFLOW=5
# Redis 2GB no compose
```

---

## 4. Perfil IDEAL — rodar liso (sem gargalo perceptível)

**Para quem é:** experiência fluida para 200+ usuários, picos sem fila visível, compressão ultra **rápida**, margem para crescimento (300–500 usuários).

### Hardware

| Recurso | Especificação |
|---------|---------------|
| RAM total | **48–64 GB** |
| vCPU | **16 cores** |
| Disco | **250 GB NVMe** |
| GPU (opcional) | **1× 16 GB VRAM** (T4 / L4 / RTX 4000) — ultra em **3–8 s** |
| Rede | **1 Gbps** |

### Arquitetura (ideal)

```
[Load Balancer / Nginx]
        |
   +----+----+
   |         |
[API x3]  [API x3]     (12 GB RAM total)
   |         |
   +----+----+
        |
 [Redis 4GB] [Postgres 8GB] [Celery x4]
        |
 [Ollama x2 ou Ollama+GPU]  (24-32 GB dedicados)
        |
 [LLMs cloud: Groq, OpenAI, Claude]
```

| Componente | Especificação ideal |
|------------|---------------------|
| API | **3 réplicas** (load balance) |
| Ollama | **2 instâncias** llama3.2:3b **ou** 1× GPU com 7B |
| Redis | **4 GB**, persistência AOF |
| Postgres | **8 GB RAM**, réplica read (opcional) |
| Celery | **4 workers**, concurrency 2 |
| Monitoramento | Prometheus + Grafana + alertas PagerDuty/Slack |

### Comportamento esperado (rodar liso)

| Métrica | Valor típico |
|---------|--------------|
| Compressão ultra (1.700 tokens) | **3–15 s** (GPU) ou **10–25 s** (2× Ollama CPU) |
| Pico 30 req simultâneas | Fila curta; **p95 &lt; 30 s** |
| Cache hit | Resposta **&lt; 500 ms** |
| Swap | **0%** em operação normal |
| Disponibilidade alvo | **99,5%+** |
| Crescimento | Suporta até **~500 usuários** com mesmo cluster |

### Extras (ideal)

- Domínio dedicado + WAF  
- Backup Postgres **hora em hora** + retenção 30 dias  
- Ambiente de **homologação** (8 GB) separado  
- Rate limit por API key / usuário  

---

## 5. Tabela comparativa completa (para o gerente)

| Critério | Mínimo | Recomendado | Ideal (liso) |
|----------|--------|-------------|--------------|
| **RAM** | 16 GB | 32 GB | 48–64 GB |
| **vCPU** | 4 | 8 | 16 |
| **Disco SSD** | 80 GB | 120 GB | 250 GB |
| **GPU** | Não | Opcional | Recomendada |
| **Servidores** | 1 | 1 ou 2 | 2–3 |
| **Ollama** | 1× 3B | 1× 3B dedicado | 2× 3B ou GPU |
| **API réplicas** | 1 | 2 | 3 |
| **Celery workers** | 0–1 | 2 | 4 |
| **Redis** | 512 MB | 2 GB | 4 GB |
| **Monitoramento** | Não | Sim | Sim + alertas |
| **Tempo ultra ~1.7k tokens** | 30–90 s | 15–45 s | 3–25 s |
| **200 users ultra** | Arriscado | Sim | Sim, folgado |
| **Fila em pico** | Longa | Moderada | Curta / rara |
| **Custo cloud ref.** | R$ 300–600/mês | R$ 800–1.500/mês | R$ 2.000–4.000/mês |

---

## 6. Stack técnica (todos os perfis)

| Componente | Função |
|------------|--------|
| Docker 24+ | Runtime |
| Docker Compose v2 | Orquestração |
| PostgreSQL 15+ + pgvector | Dados e vetores |
| Redis 7 | Cache + fila Celery |
| Ollama | Compressão ultra |
| Nginx + SSL | Entrada HTTPS |
| Python 3.12 (imagem) | Backend |
| Chaves LLM (Groq, OpenAI, etc.) | Após compressão |

---

## 7. Armazenamento por perfil (ano 1)

| Item | Mínimo | Recomendado | Ideal |
|------|--------|-------------|-------|
| SO + Docker | 15 GB | 20 GB | 25 GB |
| Modelos Ollama | 3 GB | 5 GB | 8 GB |
| PostgreSQL | 5 GB | 15 GB | 40 GB |
| Redis/backups/logs | 15 GB | 40 GB | 80 GB |
| Margem | 10 GB | 20 GB | 50 GB |
| **Total** | **~80 GB** | **~120 GB** | **~250 GB** |

---

## 8. Texto para solicitação formal

Solicito provisionamento do **AI Token Suppressor** para **mais de 200 usuários** em modo **ultra** (máxima economia de tokens com Ollama).

Apresento **três opções**:

1. **Mínimo (16 GB / 80 GB / 4 vCPU)** — viável com filas e lentidão em pico.  
2. **Recomendado (32 GB / 120 GB / 8 vCPU)** — produção estável para 200 usuários. **Sugestão para aprovação.**  
3. **Ideal / rodar liso (48–64 GB / 250 GB / 16 vCPU, GPU opcional)** — sem gargalo perceptível, pronto para crescimento.

O ambiente atual de **4 GB não atende** este cenário.

---

*AiTokenSuppressor — Documento para gestão de infraestrutura*
