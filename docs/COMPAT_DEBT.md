# Dívida de compatibilidade — AI Token Suppressor (ATS)

Registro exigido pelo contrato do ecossistema v1.2, §13. Cada ponte lista o que é, por que existe, o que precisa acontecer para sair, a métrica e a data-alvo.

Fonte: `docs/ECOSYSTEM_CONTRACT.md` (SHA-256 `379ba1462c31185f7cf8c4e9e417eb20c8a51bff545f22491bc7add1bf01b8ec`), aprovado em 11/10/2026. Este arquivo só documenta a dívida. Não altera o `contract_version` que o serviço reporta.

## Pontes que se aplicam a este repositório

| Ponte | Por que existe | Para sair | Métrica | Data-alvo |
|---|---|---|---|---|
| ATS em modo serviço (§11.2) | O modo canônico da v1.2 é a biblioteca `ats_core` em processo na E.D.I.T.H. Este repositório ainda é o serviço HTTP que clientes chamam hoje: `POST /compress` e `POST /optimize` (`backend/app/api/routes/optimize.py`), proxy `GET /v1/models`, `POST /v1/chat/completions` e `POST /v1/messages` (`backend/app/api/routes/proxy.py`, montado em `backend/app/main.py`), mais `POST /stream/compress` (`backend/app/api/routes/advanced.py`). O estado fica no Postgres próprio (role `ats`; nome padrão `ai_token_suppressor` em `backend/app/core/config.py` e `.env.example`; o nome de contrato `ats_db` aparece no comentário de deploy compartilhado do `.env.example`) e no Redis com prefixo `ats:` (`ats:cache:`, `ats:embed:`, `ats:compress:`, `ats:response:`, `ats:stats:` em `backend/app/services/cache_service.py`; `ats:mem:l1:` e `ats:mem:l3:` em `backend/app/services/hierarchical_memory_service.py`). | A E.D.I.T.H. importa `ats_core` e executa `TokenSuppressor().compress(...)` no processo dela (§11.2). As chamadas HTTP a `/compress`, `/optimize`, `/stream/compress` e `/v1/*` ficam em zero por tempo contínuo, e só então o Postgres próprio e o Redis `ats:` deste serviço podem ser retirados. Enquanto a ponte existir, o contrato exige HMAC §9, §8 no proxy `/v1/*` e Redis com senha — isso ainda não está implementado e fica fora deste registro. | `ats_mode` e a contagem de chamadas HTTP ao ATS | 2027-03-31 |

## Pontes da §13 que não se aplicam aqui

Conferidas no código em 11/10/2026. Não entram na tabela acima.

| Ponte da §13 | Repositórios no contrato | Por que não entra neste registro |
|---|---|---|
| Auth `X-Edith-*` | edith, consumo-esperto | Nenhuma ocorrência de `X-Edith-*` no código da aplicação. A autenticação local é `X-API-Key` ou Bearer da `API_KEY` do ATS (`backend/app/core/security.py`), esquema próprio, não a ponte do §9.8. |
| Bearer `edith_*` entre serviços | edith, jarvis, consumo-esperto | Nenhum emissor ou receptor de `Bearer edith_*`. |
| HMAC do SDK no tool server do Arman | arman, edith | Este repositório não hospeda o tool server do Arman. |
| Header `X-Eco-Deadline` de v1 | edith, consumo-esperto | Nenhum leitor de `X-Eco-Deadline` no código. A menção existe só no texto do contrato. |
| Envelope sintetizado (ausência de `X-Eco-*`) | edith, consumo-esperto | Nenhum código sintetiza envelope nem marca `envelope_synthesized`. |

## Outras cópias do contrato neste repositório

- `docs/ECOSYSTEM_CONTRACT.md` é a cópia canônica, substituída por completo pela v1.2.
- `00-CONTRATO-COMPARTILHADO.md` (raiz) é o patch v1→v1.1, não uma segunda cópia integral. Permanece no lugar; a instrução desta publicação foi apontar cópias extras em vez de apagá-las.
- `.cursor/rules/ecosystem-contract.mdc` é um lembrete operacional para agentes. Ainda descreve a v1 e `contract_version: "1"`. Não foi alterado: o serviço só declara `"1.2"` depois de passar nos vetores do §9.7 (§12).
