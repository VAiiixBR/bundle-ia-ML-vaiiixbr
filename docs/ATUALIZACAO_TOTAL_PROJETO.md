# Atualização total do projeto VAIIIxBR

Este pacote foi revisado para reduzir erros de sintaxe, digitação e inconsistências de execução em Python.

## O que foi ajustado

### VAIII padrão
- `app.py` revisado para evitar duplicação entre `/status` e `/audit`
- import do contrato robusto para execução como pacote ou por `uvicorn app:app --reload`
- `load_dotenv()` opcional para ler `.env` localmente
- uso da branch do GitHub no download de artefatos
- `health` agora informa também o modo atual do trader
- `DummyTrader` e `DummyResearchEngine` alinhados ao estado inicial esperado (`UNINITIALIZED`)

### Contrato e auditoria
- normalização mais segura de `bool`, `int` e `float`
- bloqueio explícito para estado neutro/não inicializado
- thresholds centralizados para entrada confirmada e watchlist
- dashboard e auditoria continuam compatíveis com o contrato anterior

### Newsworker
- `run_demo()` agora aceita diretório de saída e retorna o caminho do artefato
- gravação usando `parents=True` para evitar falhas de diretório

### VAIIIxAprende
- tipagem do `thresholds` corrigida
- gravação robusta do `stats.json` com `parents=True`

### Testes
- novo teste de rotas: `/health`, `/status`, `/audit`
- testes anteriores mantidos

### Ferramenta nova
- `scripts/python_sanity_check.py`
- verifica sintaxe Python e procura usos suspeitos de `true`, `false` e `null` em arquivos `.py`

## Como atualizar o projeto inteiro

1. Faça backup do repositório atual.
2. Substitua os diretórios abaixo pelos deste pacote:
   - `vaiiixbr_standard/`
   - `newsworker/`
   - `vaiiixaprende/`
   - `tests/`
   - `scripts/`
   - `docs/`
3. Instale dependências.
4. Rode o sanity check:
   ```bash
   python scripts/python_sanity_check.py .
   ```
5. Rode os testes:
   ```bash
   pytest
   ```
6. Suba localmente:
   ```bash
   uvicorn app:app --reload
   ```
7. Valide no navegador:
   - `/health`
   - `/status`
   - `/audit`
   - `/`

## Ordem de liberação recomendada
- primeiro o serviço principal
- depois o newsworker
- depois o vaiiixaprende/Colab
- por fim o deploy integrado
