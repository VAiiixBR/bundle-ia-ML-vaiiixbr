# VAIIIxBR Bundle Integrado

Bundle técnico para padronizar a próxima fase do ecossistema:
- `vaiiixbr_standard`: serviço principal do VAIIIxBR focado em ITUB4
- `newsworker`: serviço de pesquisa e enriquecimento de notícias
- `vaiiixaprende`: núcleo de aprendizado/treino no Colab
- `docs`: arquitetura, plano de lançamento e revisão técnica
- `scripts`: automação local e deploy assistido
- `tests`: testes mínimos de contrato entre os três blocos
- `config`: modelos de configuração

## Objetivo
Consolidar um padrão único de integração, auditoria, logs, dashboard e fluxo de lançamento.

## Estado esperado do sistema
1. O `newsworker` coleta, limpa e resume notícias de ITUB4.
2. O `vaiiixaprende` transforma histórico + notícias em artefatos de aprendizado.
3. O `vaiiixbr_standard` consome artefatos e decisões, opera em paper trading e expõe dashboard/auditoria.

## Princípios fixos
- Ativo único: `ITUB4`
- Ambiente inicial: `paper trading`
- Caixa inicial padrão: `R$50`
- Dashboard com auditoria clicável
- Logs padronizados e auditáveis
- Integração pensando no conjunto completo do projeto

## Como usar este bundle
1. Leia `docs/PLANO_CONCRETO_INTEGRACAO.md`
2. Ajuste `config/.env.example`
3. Aplique os arquivos do patch em cada repositório/serviço correspondente
4. Rode os testes de `tests/`
5. Faça o deploy usando GitHub Desktop + Northflank

## Observação
Este bundle foi montado como base profissional de atualização. Ele não altera sua instância remota diretamente; entrega a estrutura, os contratos, os arquivos de referência e os testes para estabilizar o lançamento.
