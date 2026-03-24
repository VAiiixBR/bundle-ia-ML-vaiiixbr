# VAIIIxBR na Northflank

Esta pasta prepara a VAIIIxBR para deploy com dois serviços usando o mesmo repositório e o mesmo Dockerfile.

## 1) Build
- Build type: Dockerfile
- Dockerfile location: `/Dockerfile`
- Build context: `/`

## 2) Serviço Web (dashboard + API)
- Resource type: Deployment service
- Public port: `8000`
- Start command override:
  `uvicorn main_api:app --host 0.0.0.0 --port $PORT`
- Runtime variables: use o arquivo `runtime.env.example`
- Volume: monte um volume persistente em `/app/data`

## 3) Serviço Worker (loop da VAIIIxBR)
- Resource type: Deployment service
- Start command override:
  `python main_worker.py`
- Runtime variables: use o mesmo conjunto do serviço web
- Volume: monte o MESMO volume persistente em `/app/data` se quiser compartilhar estado e base SQLite

## 4) Persistência
A aplicação está configurada para gravar SQLite e estado do worker em:
- `/app/data/vaiiixbr.db`
- `/app/data/worker_state.json`

## 5) Endpoints do serviço web
- `/health`
- `/status`
- `/signals`
- `/paper-trades`
- `/`

## 6) Checklist
- Adicione `BRAPI_TOKEN` como secret/runtime variable
- Confirme que `PORT=8000`
- Exponha a porta `8000`
- Monte volume persistente em `/app/data`
- Faça deploy do web service
- Faça deploy do worker service
- Abra a URL pública do web service no celular
