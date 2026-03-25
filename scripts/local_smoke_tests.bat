@echo off
setlocal

echo Executando smoke tests locais...
python -m pytest tests -q
if %errorlevel% neq 0 (
  echo Falha nos testes.
  exit /b 1
)

echo Testes concluídos com sucesso.
pause
