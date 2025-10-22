# Plano de rollout – Extração de Cidades

## Objetivo

Implantar de forma segura as melhorias de extração de cidades mantendo rastreabilidade e possibilidade de rollback rápido.

## Visão geral da estratégia

1. Utilizar a branch dedicada `feature/cities-extraction` para consolidar o desenvolvimento.
2. Abrir um Pull Request detalhado contra `main`, com descrição completa do escopo, checklist de testes e impacto esperado em dados.
3. Validar a funcionalidade em ambiente isolado (staging ou sandbox) antes de qualquer deploy em produção.
4. Controlar a ativação por meio de uma feature flag baseada em variável de ambiente (`EXTRACTION_CITIES_ENABLED`), ativando gradualmente conforme o plano acordado com o time de dados.

## Preparação e pré-requisitos

- **Checklist técnico**
  - Cobertura de testes atualizada (`pytest`, smoke tests de integração das APIs e workers).
  - Documentação revisada (CLI, catálogo de cidades, instruções operacionais) e publicada.
  - Cache de cidades (`municipios_br_<versao>.json`) regenerado e versionado conforme descrito em [Catálogo de Municípios](cidade_catalogo.md).
  - Scripts de migração ou seeds necessários validados em ambiente de teste.

- **Coordenação com o time de dados**
  - Agendar janela inicial de execução para processamento de um lote pequeno (ex.: 5% das notícias pendentes).
  - Definir responsáveis por monitorar métricas de acurácia (resoluções `resolved` vs `ambiguous`) e performance do worker.
  - Acordar canal de comunicação para incidentes (Slack `#dados-sentinela` ou equivalente) e sinal de pronto para rollback.

## Fluxo sugerido de implantação

1. **Branch e PR**
   - Atualize `feature/cities-extraction` com `main` e garanta histórico limpo (rebase se necessário).
   - Abra o PR com seções de resumo, testes executados, riscos conhecidos e plano de rollback.
   - Solicite revisão cruzada (engenharia + dados) antes do merge.

2. **Validação em ambiente isolado**
   - Deploy do branch em um ambiente staging/sandbox replicando integrações de Mongo/Postgres.
   - Executar `sentinela-extraction-worker` apontando para um conjunto controlado de notícias.
   - Comparar resultados com a versão anterior usando relatórios de dif (`resolved/ambiguous/foreign`) e análise manual de amostra.

3. **Feature flag / variável de ambiente**
   - Introduzir `EXTRACTION_CITIES_ENABLED` (default `false`) nos manifests ou `docker-compose`.
   - No worker/API, condicionar a execução do pipeline de cidades à flag (ativar por configuração sem redeploy quando possível).
   - Documentar a flag na tabela de variáveis operacionais do serviço de extração.

4. **Rollout gradual em produção**
   - Após aprovação do PR, realizar merge e gerar release.
   - Deploy em produção com a flag `EXTRACTION_CITIES_ENABLED=false` para validar integridade básica.
   - Ativar a flag apenas no ambiente isolado para smoke final e, em seguida, habilitar em produção durante a janela acordada (ex.: ativar para 25% das instâncias/filas, monitorar 30 min, aumentar para 100%).

5. **Monitoramento pós-deploy**
   - Acompanhar métricas de throughput, tempo médio por lote, contagem de ambiguidades e erros de gazetteer.
   - Validar logs de `sentinela-extraction-worker` procurando mensagens de erro (`ERROR`) ou volume atípico de ambiguidades.
   - Registrar resultados em dashboard compartilhado com o time de dados.

## Plano de rollback

- Desativar imediatamente `EXTRACTION_CITIES_ENABLED` caso sejam detectadas regressões graves.
- Reverter para o catálogo de cidades anterior (`municipios_br_<versao_antiga>.json`) mantendo o valor anterior de `CITY_CACHE_VERSION`.
- Se necessário, reprocessar notícias afetadas marcando as versões antigas via `ner_version`/`gazetteer_version`.
- Comunicar o time de dados com o status do rollback e abrir issue descrevendo causa raiz e ações corretivas.

## Aprovação final

O rollout é considerado completo quando:

- A feature está ativa em 100% dos ambientes produtivos.
- Métricas e logs estão dentro dos limites definidos em conjunto com o time de dados.
- Foi registrado *post-mortem* ou nota interna descrevendo resultados da implantação e próximos passos.

Documente assinaturas de aprovação (engenharia + dados) no PR correspondente para manter rastreabilidade.
