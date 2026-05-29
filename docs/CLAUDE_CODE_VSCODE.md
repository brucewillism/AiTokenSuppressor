# Claude Code (VS Code / Cursor) + AI Token Suppressor

A extensão **Claude Code** usa a API Anthropic (`POST /v1/messages`), não OpenAI. O ATS expõe esse endpoint com compressão antes do LLM.

## URL base

```
http://SEU_IP:8100
```

(Não inclua `/v1` no `ANTHROPIC_BASE_URL` — o cliente acrescenta `/v1/messages`.)

## Autenticação

Use a **API_KEY do ATS** (não `sk-ant-...`):

| Header | Valor |
|--------|--------|
| `x-api-key` | `ats-super-api-key` |
| ou `Authorization` | `Bearer ats-super-api-key` |

## VS Code / Cursor — `settings.json`

```json
{
  "claudeCode.environmentVariables": [
    { "name": "ANTHROPIC_BASE_URL", "value": "http://191.252.210.60:8100" },
    { "name": "ANTHROPIC_API_KEY", "value": "ats-super-api-key" },
    { "name": "ANTHROPIC_AUTH_TOKEN", "value": "ats-super-api-key" }
  ],
  "claudeCode.disableLoginPrompt": true
}
```

Reinicie o VS Code / Cursor após alterar.

## `~/.claude/settings.json` (CLI)

```json
{
  "env": {
    "ANTHROPIC_BASE_URL": "http://191.252.210.60:8100",
    "ANTHROPIC_API_KEY": "ats-super-api-key"
  }
}
```

## VPS — `.env` do ATS

Chaves dos provedores ficam no servidor:

```env
API_KEY=ats-super-api-key
ANTHROPIC_API_KEY=sk-ant-...
PROXY_DEFAULT_STRATEGY=fast
PROXY_USE_OLLAMA=false
PROXY_USE_MEMORY=false
```

## Teste curl

```bash
curl -s http://191.252.210.60:8100/v1/messages \
  -H "x-api-key: ats-super-api-key" \
  -H "Content-Type: application/json" \
  -H "anthropic-version: 2023-06-01" \
  -d '{
    "model": "claude-3-5-sonnet-20241022",
    "max_tokens": 256,
    "messages": [{"role": "user", "content": "Diga olá em uma frase."}]
  }'
```

Headers de compressão na resposta: `X-ATS-Tokens-Before`, `X-ATS-Tokens-After`, `X-ATS-Tokens-Saved`.

## Cursor (chat nativo)

Continua a usar **Override OpenAI Base URL**: `http://191.252.210.60:8100/v1` — fluxo diferente do Claude Code.
