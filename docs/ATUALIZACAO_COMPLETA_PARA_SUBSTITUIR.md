# Atualização completa do projeto VAIIIxBR

## O que está neste pacote
- `app.py`: entrada principal para rodar o serviço com `uvicorn app:app --reload`
- `worker_app.py`: entrada principal para rodar o newsworker com `uvicorn worker_app:app --reload`
- `vaiiixbr_standard/`: backend principal do VAIIIxBR
- `newsworker/`: geração e exposição do snapshot de notícias
- `vaiiixaprende/`: geração de `stats.json`
- `tests/`: testes da API principal, worker, contrato e artefatos
- `requirements.txt`: dependências completas
- `.env.example`: modelo de configuração

## Como substituir o projeto atual
1. Faça backup da pasta atual.
2. Apague o conteúdo da pasta antiga do projeto.
3. Copie todo o conteúdo deste pacote para a pasta do projeto.
4. Crie `.env` a partir de `.env.example`.
5. Instale dependências:
   `pip install -r requirements.txt`
6. Rode o sanity check:
   `python scripts/python_sanity_check.py .`
7. Rode os testes:
   `pytest`
8. Suba a API principal:
   `uvicorn app:app --reload`
9. Suba o newsworker em outro terminal:
   `uvicorn worker_app:app --reload`

## Comandos principais
### API principal
`uvicorn app:app --reload`

### Newsworker
`uvicorn worker_app:app --reload`

### Gerar stats do aprendizado
`python -m vaiiixaprende.colab_artifacts`

### Gerar snapshot local do worker
`python -m newsworker.worker`

## Endpoints principais
### Serviço principal
- `/`
- `/health`
- `/status`
- `/audit`
- `/decision`

### Newsworker
- `/health`
- `/latest`
- `/run-demo`

## Resultado esperado
- `/health` do principal responde `ok`
- `/status` inclui `audit`
- dashboard abre em `/`
- worker responde em `/health` e `/latest`
- `pytest` passa
