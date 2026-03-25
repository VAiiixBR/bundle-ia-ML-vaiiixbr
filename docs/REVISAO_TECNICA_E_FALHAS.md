# Revisão técnica e análise de falhas

## Falhas prioritárias tratadas neste bundle

### 1. Auditoria fraca no dashboard
Sintoma:
- operador vê o sinal, mas não entende claramente por que não houve entrada

Impacto:
- baixa confiabilidade operacional
- difícil depuração

Ação:
- rota `/audit`
- aba clicável `Auditoria`
- motivos positivos e bloqueios em separado

### 2. Contrato instável entre backend e frontend
Sintoma:
- frontend mostra dados resumidos demais ou inconsistentes

Impacto:
- divergência entre log, decisão e dashboard

Ação:
- schema mínimo obrigatório para preços e decisão

### 3. Risco de dados externos faltantes
Sintoma:
- ausência de artefatos do aprendizado ou notícias

Impacto:
- dashboard quebra ou opera com informação incompleta

Ação:
- fallback seguro com defaults
- healthcheck com indicação explícita de dependências

### 4. Falta de padronização de release
Sintoma:
- atualização simultânea dos 3 módulos sem validação central

Impacto:
- regressões cruzadas

Ação:
- checklist de lançamento
- testes de contrato
- bundle único versionado

### 5. Logs sem granularidade suficiente
Sintoma:
- difícil explicar diferença entre watchlist, entrada e bloqueio

Impacto:
- difícil treinar, corrigir ou comparar resultados

Ação:
- adicionar `verdict`, `blockers`, `positives`, `cooldown_remaining`, `position_open`

## Falhas futuras a monitorar
- drift entre `news_score` e `final_signal`
- thresholds excessivamente otimistas
- dashboard desatualizado versus retorno do motor
- artefatos do Colab sobrescritos sem versionamento
- uso de segredo/env divergente entre ambientes
