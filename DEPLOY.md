# Deploy na VPS

O AI Token Suppressor sobe só em loopback nesta VPS. Nada deste repositório escuta em `0.0.0.0`. O acesso de fora da máquina é um túnel SSH até `127.0.0.1`. O Caddy do host continua exclusivo do ConsumoEsperto.

O arquivo usado no servidor é `docker-compose.prod.yml`. O `docker-compose.yml` da raiz permanece para desenvolvimento local e não deve ser o comando de produção.

Stack automática: Redis, API e frontend. Celery, Flower, LiteLLM, Prometheus e Grafana ficam em profiles e não sobem no deploy automático.

| Serviço | Bind no host | Porta do container | Profile |
|---|---|---|---|
| frontend | `127.0.0.1:8100` | 80 | padrão |
| api | `127.0.0.1:8105` | 8000 | padrão |
| redis | `127.0.0.1:8106` | 6379 | padrão |
| litellm | `127.0.0.1:8101` | 4001 | `litellm` |
| prometheus | `127.0.0.1:8102` | 9090 | `monitoring` |
| grafana | `127.0.0.1:8103` | 3000 | `monitoring` |
| flower | `127.0.0.1:8104` | 5556 | `workers` |

A porta do host e a porta do container diferem de propósito. O Caddy já ocupa 80 e 443 no host, e a faixa 8100–8106 é a deste app na VPS compartilhada. Dentro do container o processo continua na porta que o Dockerfile expõe. O bind publicado é sempre `127.0.0.1`.

Dentro do container a API escuta em `0.0.0.0` para o proxy do Docker alcançar o processo. Quem publica a porta no host é o compose, e essa publicação é loopback.

## Túnel SSH

Na sua máquina, com as portas que for usar:

```bash
ssh -p PORTA -L 8100:127.0.0.1:8100 -L 8105:127.0.0.1:8105 deploy@HOST
```

Depois abra `http://127.0.0.1:8100` no navegador local. A API direta fica em `http://127.0.0.1:8105`.

## Setup na VPS

Ubuntu 24.04, Docker e o plugin Compose. UFW segue liberando só 22, 80 e 443. Não abra 8100–8106 no firewall.

O usuário `deploy` entra no grupo `docker` e só alcança `/home/bruce/apps`. A chave usada pelo GitHub Actions é exclusiva deste deploy. Não reutilize a chave pessoal.

```bash
sudo adduser --disabled-password --gecos "" deploy
sudo usermod -aG docker deploy
sudo mkdir -p /home/bruce/apps
sudo chown deploy:deploy /home/bruce/apps
```

A partir daqui, como `deploy`:

```bash
install -d -m 700 ~/.ssh
# Cole só a chave pública correspondente ao secret VPS_SSH_KEY.
nano ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys
```

O `git fetch` roda na VPS com uma deploy key de leitura, separada da chave que o GitHub Actions usa para entrar por SSH. Cadastre a deploy key no repositório. O clone é completo, sem `--depth`.

```bash
cd /home/bruce/apps
git clone git@github.com:brucewillism/AiTokenSuppressor.git AiTokenSuppressor
cd AiTokenSuppressor
```

Crie o `.env` neste diretório. O arquivo fica só na VPS.

```bash
touch .env
chmod 600 .env
```

O job recusa o deploy se o modo do `.env` não for `600`.

Antes do primeiro `docker compose` de produção, pare uma stack antiga que use os mesmos `container_name` (`ats-api`, `ats-redis`, `ats-frontend`). Dois projetos com o mesmo nome de container não sobem juntos.

Confira, fora do git, que o Postgres deste serviço é o banco `ats_db` com um role que não lê banco de outro serviço. O Redis desta stack usa senha e o prefixo de chaves `ats:` que a aplicação já grava. A rede Docker do projeto se chama `ai-token-suppressor`.

O compose de produção monta estas URLs do Redis para a API e para o Celery, a partir de `REDIS_PASSWORD`:

- banco 0 na API
- banco 1 no broker
- banco 2 no result backend

O host desses URLs é o serviço `redis` da rede Docker, não a porta publicada. `REDIS_PASSWORD` precisa ser URL-safe: letras e dígitos, sem `$`, `@`, `:` ou `/`. O Compose interpola `$`.

`SECRET_KEY` e `JWT_SECRET_KEY` precisam ter no mínimo 32 caracteres. É a regra que o processo já valida na subida.

`ATS_BASE_URL`, `EDITH_BASE_URL`, `JARVIS_BASE_URL` e `CONSUMO_ESPERTO_BASE_URL` são os endereços internos entre os serviços do ecossistema. Use `http://127.0.0.1:` mais a porta loopback de cada um. O compose injeta essas variáveis no container da API. O código da aplicação ainda não abre chamada nova a partir delas; o valor fica disponível no ambiente para a ponte de serviço.

`OLLAMA_BASE_URL`, quando existir, aponta para o loopback do host via `host.docker.internal`. Na VPS o padrão operacional é deixar a chamada a Ollama desligada. Ollama de servidor continua sendo da E.D.I.T.H.

O profile `litellm` só deve ser ligado com `LITELLM_IMAGE_TAG` numa tag fixa, nunca `latest` nem `main-latest`. O profile `monitoring` exige `GRAFANA_ADMIN_PASSWORD` no `.env` mesmo que o Grafana fique desligado, porque o Compose interpola o arquivo inteiro.

Profiles, se um dia houver RAM para eles:

```bash
docker compose -f docker-compose.prod.yml --profile workers up -d
docker compose -f docker-compose.prod.yml --profile monitoring up -d
docker compose -f docker-compose.prod.yml --profile litellm up -d
```

O workflow automático não passa `--profile`.

## Variáveis do `.env`

Só os nomes. Os valores ficam no arquivo da VPS.

Aplicação e autenticação:

- `APP_NAME`
- `APP_ENV`
- `APP_DEBUG`
- `APP_HOST`
- `APP_PORT`
- `SECRET_KEY`
- `API_KEY`
- `JWT_SECRET_KEY`
- `JWT_ALGORITHM`
- `JWT_EXPIRE_MINUTES`
- `ROOT_PATH`
- `CORS_ORIGINS`

Banco, Redis e fila:

- `DATABASE_URL`
- `DATABASE_POOL_SIZE`
- `DATABASE_MAX_OVERFLOW`
- `POSTGRES_USER`
- `REDIS_PASSWORD`
- `REDIS_URL`
- `REDIS_CACHE_TTL`
- `CELERY_BROKER_URL`
- `CELERY_RESULT_BACKEND`

Ollama e provedores:

- `OLLAMA_BASE_URL`
- `OLLAMA_MODEL`
- `OLLAMA_EMBED_MODEL`
- `OLLAMA_TIMEOUT`
- `OLLAMA_API_BASE`
- `GROQ_API_KEY`
- `OPENAI_API_KEY`
- `ANTHROPIC_API_KEY`
- `GEMINI_API_KEY`
- `DEEPSEEK_API_KEY`
- `OPENROUTER_API_KEY`

Proxy, compressão e limites:

- `PROXY_DEFAULT_STRATEGY`
- `PROXY_PIPELINE`
- `PROXY_USE_MEMORY`
- `PROXY_USE_OLLAMA`
- `PROXY_SKIP_OPTIMIZE`
- `PROXY_PROVIDER_FALLBACK`
- `LOW_MEMORY_MODE`
- `PROMETHEUS_ENABLED`
- `COMPRESS_AUTO_BALANCED_TOKENS`
- `DEFAULT_COMPRESSION_STRATEGY`
- `COMPRESS_LIGHTWEIGHT_TOKEN_THRESHOLD`
- `COMPRESS_SKIP_SEMANTIC_LOSS_BELOW_TOKENS`
- `TARGET_COMPRESSION_RATIO`
- `RATE_LIMIT_REQUESTS`
- `RATE_LIMIT_WINDOW`
- `MAX_PAYLOAD_SIZE_MB`
- `MAX_MESSAGES`
- `RAG_CHUNK_SIZE`
- `RAG_CHUNK_OVERLAP`
- `RAG_TOP_K`
- `MAX_CONTEXT_TOKENS`
- `SLIDING_WINDOW_SIZE`
- `COST_CLAUDE_INPUT`
- `COST_CLAUDE_OUTPUT`
- `COST_OPENAI_INPUT`
- `COST_OPENAI_OUTPUT`
- `COST_GEMINI_INPUT`
- `COST_GEMINI_OUTPUT`

Frontend, LiteLLM, Grafana e ecossistema:

- `VITE_API_URL`
- `VITE_API_KEY`
- `VITE_API_DIRECT_URL`
- `LITELLM_URL`
- `LITELLM_MASTER_KEY`
- `LITELLM_IMAGE_TAG`
- `GRAFANA_ADMIN_USER`
- `GRAFANA_ADMIN_PASSWORD`
- `EDITH_BASE_URL`
- `JARVIS_BASE_URL`
- `CONSUMO_ESPERTO_BASE_URL`
- `ATS_BASE_URL`

`GIT_SHA` não entra no `.env`. O workflow exporta o SHA na hora do `docker compose`, e a imagem da API e a do frontend recebem essa tag.

O compose exige, para interpolar, mesmo com os profiles opcionais desligados: `REDIS_PASSWORD`, `DATABASE_URL`, `SECRET_KEY`, `API_KEY`, `JWT_SECRET_KEY`, `VITE_API_KEY`, `LITELLM_IMAGE_TAG`, `GRAFANA_ADMIN_PASSWORD`.

`APP_NAME` com espaço precisa de aspas no `.env`. Sem aspas o Compose recusa a linha.

## Secrets no GitHub

No repositório, em Actions secrets:

| Secret | Uso |
|---|---|
| `VPS_HOST` | Hostname ou endereço da VPS. Não commite esse valor. |
| `VPS_USER` | `deploy` |
| `VPS_SSH_KEY` | Chave privada OpenSSH dedicada, com as quebras de linha reais. |
| `VPS_PORT` | Porta SSH. Opcional. Vazio significa 22. |
| `VPS_KNOWN_HOSTS` | Linha de host key conferida fora do pipeline. |

A host key vem de um `ssh-keyscan` que você confere com o fingerprint visto no console da VPS. Grave o resultado em `VPS_KNOWN_HOSTS`. O workflow usa `StrictHostKeyChecking=yes` e esse arquivo. Não use `StrictHostKeyChecking=no`.

O job automático só corre depois que o workflow `CI` termina com sucesso num push da `main`. O `CI` valida `docker-compose.prod.yml`. Enquanto o workflow de deploy não estiver na `main`, o `workflow_run` não dispara. O primeiro deploy, e qualquer rollback, é manual.

## Rollback

No GitHub: Actions → Deploy → Run workflow. No input `ref`, informe o SHA completo de 40 caracteres hexadecimais que já está no histórico da `main`. O job faz `git fetch` desse SHA, `git reset --hard` e sobe o compose de novo. Se o healthcheck não ficar saudável, o job falha e o concurrency impede outro deploy em paralelo.

`ref` vazio faz o deploy do SHA em que o workflow está rodando. Branch, tag curta e SHA abreviado são recusados. O SHA precisa conter `docker-compose.prod.yml`: o job faz reset para esse commit e sobe esse compose.

## Caddy

Este repositório não ganha site no Caddy. O bloco abaixo é o formato do ConsumoEsperto, único app com domínio e HTTPS neste host. Troque os nomes de exemplo pelas portas loopback reais daquele projeto.

```caddy
dominio.exemplo {
	reverse_proxy 127.0.0.1:PORTA
}
```

Front e API do ConsumoEsperto, quando forem hosts diferentes:

```caddy
dominio.exemplo {
	reverse_proxy 127.0.0.1:PORTA_FRONT
}

api.dominio.exemplo {
	reverse_proxy 127.0.0.1:PORTA_BACK
}
```

## O que conferir antes de confiar no automático

1. Usuário `deploy` no grupo `docker`, com `docker` sem sudo.
2. Clone em `/home/bruce/apps/AiTokenSuppressor`, remote SSH e deploy key de leitura.
3. `.env` com `chmod 600`, dono `deploy`, e os nomes da lista acima preenchidos.
4. Postgres `ats_db` no loopback do host, role exclusivo.
5. Secrets `VPS_HOST`, `VPS_USER`, `VPS_SSH_KEY`, `VPS_KNOWN_HOSTS` e, se a porta não for 22, `VPS_PORT`.
6. `curl` instalado na VPS. O job chama `http://127.0.0.1:8105/health` e `http://127.0.0.1:8100/health/live`.
7. Workflow `CI` verde na `main` depois do merge. Em seguida, um `workflow_dispatch` do SHA que deve subir.
