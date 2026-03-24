# VAIIIxBR Northflank Ready

Versão atualizada para rodar de forma profissional no Northflank, com foco no plano Sandbox:

- API FastAPI pública
- worker embutido opcional no mesmo serviço (`VAIII_EMBEDDED_WORKER=true`)
- dashboard responsivo em `/dashboard`
- endpoints `/health`, `/status`, `/metrics`, `/signals`, `/paper-trades`
- paper trading persistido em SQLite
- estratégia e coleta de dados reais via brapi

## Subida rápida

```bash
python -m pip install -r requirements.txt
uvicorn main_api:app --host 0.0.0.0 --port 8000
```

## Variáveis principais

```env
VAIII_ASSET=ITUB4
VAIII_POLL_SECONDS=60
VAIII_EMBEDDED_WORKER=true
VAIII_PAPER_INITIAL_CASH=50
BRAPI_TOKEN=
```

## Rotas

- `/` JSON simples de status
- `/dashboard` painel web para celular
- `/health` saúde do serviço
- `/status` último estado processado
- `/metrics` métricas de sinais e paper trading
- `/signals` histórico recente de sinais
- `/paper-trades` histórico recente de trades

## Modo recomendado para Sandbox

Use apenas o serviço web com `VAIII_EMBEDDED_WORKER=true`. Assim a API e a automação rodam no mesmo container.

## Worker separado

Se quiser uma arquitetura mais robusta fora do Sandbox, mantenha `main_worker.py` para rodar em um segundo serviço.


## Melhorias incluídas na versão atual
- saída automática por perda de sinal (`signal_loss`) para evitar segurar posição sem confirmação
- medição de ganho/perda real em valor financeiro e em percentual do ativo
- métricas de precisão da predição no paper trading
- dashboard ampliado com posição aberta, PnL líquido e retorno total
