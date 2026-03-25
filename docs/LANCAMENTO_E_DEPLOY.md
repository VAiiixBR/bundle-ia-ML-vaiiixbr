# Lançamento e deploy

## Fluxo recomendado
- usar branch dedicada no GitHub Desktop para isolar mudanças
- sincronizar a branch antes do push
- abrir pull request antes de consolidar na principal
- fazer deploy controlado no Northflank
- usar serviço contínuo para o dashboard e job agendado quando a tarefa for periódica

## Mapeamento sugerido
### Northflank
- `vaiiixbr_standard`: serviço contínuo
- `newsworker`: serviço contínuo ou job agendado, conforme custo e frequência desejada
- tarefas periódicas de coleta/reprocessamento: job com schedule

### Colab
- usar para treino/exportação de artefatos
- publicar `stats.json` versionado
- não tratar Colab como servidor estável de produção

## Release checklist
1. atualizar contratos
2. rodar testes locais
3. validar dashboard e auditoria
4. publicar branch
5. abrir pull request
6. realizar deploy
7. fazer smoke tests pós-deploy
