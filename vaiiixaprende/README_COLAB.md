# VAIIIxAprende no Colab

## Função
Gerar artefatos leves e reutilizáveis para o serviço principal.

## Saída mínima
- `stats.json`
- versionamento de thresholds
- timestamp de atualização

## Recomendações operacionais
- não depender de sessão contínua para servir API
- usar o Colab para treino e exportação de artefatos
- publicar artefatos versionados no GitHub/armazenamento acessível ao serviço principal
- manter compatibilidade de schema com `vaiiixbr_standard/contract.py`
