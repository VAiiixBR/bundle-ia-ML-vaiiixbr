# Plano concreto, estável e profissional

## 1. Meta
Transformar o conjunto VAIIIxBR + Newsworker + VAIIIxAprende em um padrão único de operação, revisão e lançamento.

## 2. Arquitetura alvo

### Serviço 1 — VAIIIxBR padrão
Responsabilidades:
- receber candles/sinais
- calcular decisão híbrida
- executar paper trading
- expor `/health`, `/status`, `/decision`, `/audit`, `/dashboard`
- manter auditoria clara do motivo de entrada ou bloqueio

### Serviço 2 — Newsworker
Responsabilidades:
- pesquisar notícias de ITUB4
- classificar viés de preço
- gerar resumo padronizado
- publicar artefatos JSON consumíveis pelo serviço principal

### Serviço 3 — VAIIIxAprende
Responsabilidades:
- treinar/ajustar artefatos a partir de histórico e sinais
- gerar `stats.json`, pesos, thresholds e insights auxiliares
- publicar saídas reutilizáveis pelo serviço principal

## 3. Contrato entre módulos

### Saída do Newsworker
Arquivo: `news_snapshot.json`
Campos mínimos:
- `symbol`
- `timestamp`
- `headline_count`
- `summary`
- `price_bias`
- `news_price_score`
- `confidence_adjustment_hint`
- `last_price`
- `reference_entry_price`
- `reference_stop_price`
- `reference_take_price`
- `reference_trailing_stop_price`

### Saída do VAIIIxAprende
Arquivo: `stats.json`
Campos mínimos:
- `samples`
- `positive_rate`
- `model_version`
- `updated_at`
- `feature_set`
- `thresholds`

### Saída do VAIIIxBR
Campos mínimos por decisão:
- `symbol`
- `timestamp`
- `last_price`
- `entry_price`
- `stop_price`
- `take_price`
- `trailing_stop_price`
- `decision`
- `metrics`
- `audit`

## 4. Revisão técnica por área

### 4.1 Dashboard
Problema identificado:
- visão operacional sem auditoria suficiente

Correção:
- adicionar aba clicável de auditoria
- mostrar preço atual, entrada, stop e alvo
- separar fatores positivos e bloqueios
- manter linguagem objetiva e técnica

### 4.2 Logs
Problema identificado:
- logs pouco claros para explicar não entrada

Correção:
- adotar JSONL com schema único
- incluir `verdict`, `status`, `final_confidence`, `hybrid_score`, `blockers`, `positives`

### 4.3 Integração
Problema identificado:
- risco de retorno inconsistente entre serviços

Correção:
- congelar contrato de payload
- testar contrato com suíte automatizada antes de release

### 4.4 Deploy
Problema identificado:
- risco de regressão ao publicar alterações simultâneas

Correção:
- branch por release
- checklist obrigatório
- smoke tests após deploy

## 5. Fluxo operacional recomendado
1. Newsworker roda continuamente ou em agenda para gerar snapshot de notícias.
2. VAIIIxAprende atualiza artefatos quando houver novas amostras relevantes.
3. VAIIIxBR consome o snapshot mais recente e os artefatos do aprendizado.
4. Dashboard expõe o estado operacional e a auditoria.
5. Todos os serviços registram logs com o mesmo `correlation_id` quando possível.

## 6. Estratégia de estabilidade
- travar ativo em ITUB4
- travar modo inicial em paper trading
- limitar mudanças simultâneas no mesmo release
- validar retorno do trader antes de atualizar frontend
- manter fallback seguro se faltar artefato externo

## 7. Estratégia de depuração
- todos os serviços devem ter `healthcheck`
- todo retorno crítico deve ter timestamps
- logs devem informar claramente: entrou, quase entrou ou não entrou
- se não entrou, o bloqueio deve ser textual e numérico

## 8. Lançamento padrão
### Branch sugerida
`release/integracao-vaiiixbr-v1`

### Ordem
1. Atualizar código local
2. Rodar testes
3. Commit granular
4. Push da branch
5. Pull request
6. Deploy controlado no Northflank
7. Testes pós-deploy
8. Marcar release como padrão

## 9. Critérios de aprovação
- `/health` responde nos 3 blocos aplicáveis
- dashboard mostra auditoria
- contrato de payload validado
- logs legíveis
- sem quebra do padrão ITUB4/R$50/paper trading
- bundle documentado e reproduzível
