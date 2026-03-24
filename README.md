# VAIIIxBR deployment bundle v3

## O que está pronto
- `northflank/service/`: serviço principal da VAIIIxBR para Northflank.
- `northflank/news-worker/`: worker de notícias para Northflank.
- `colab/`: notebook e módulo do VaiiixBRxAprende para Google Colab.
- `shared/`: arquivos-base compartilhados.

## Fluxo recomendado
1. Suba `northflank/service` como **Service** no Northflank.
2. Suba `northflank/news-worker` como **Private Service** ou **Worker** HTTP.
3. Configure as mesmas variáveis de ambiente nos dois.
4. Use um repositório GitHub para armazenar:
   - `vaiiixbr/daily/YYYY-MM-DD/news_summary.json`
   - `vaiiixbr/artifacts/*`
5. Abra o notebook em `colab/VaiiixBRxAprende_Colab.ipynb`.
6. Treine no Colab e publique os artefatos de volta no GitHub.
7. O serviço principal consulta `vaiiixbr/artifacts/stats.json` para exibir o estado mais recente do aprendizado.

## Observações
- O service e o worker usam GitHub como armazenamento gratuito versionado.
- O Colab é para treino em lote, não para inferência contínua.
- Mantenha um único processo escrevendo por arquivo do GitHub para evitar conflito.
