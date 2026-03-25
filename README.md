# VAIIIxBR - pacote completo corrigido

Pacote integrado com:
- VAIII padrão
- newsworker
- vaiiixaprende
- dashboard com auditoria
- testes automatizados
- wrappers de execução local

## Instalação
```bash
pip install -r requirements.txt
```

## Testes
```bash
pytest
```

## Rodar API principal
```bash
uvicorn app:app --reload
```

## Rodar newsworker
```bash
uvicorn worker_app:app --reload
```
