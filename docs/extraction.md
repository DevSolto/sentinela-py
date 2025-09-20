# Microserviço de Extração de Pessoas e Cidades

## Visão Geral

O pacote `sentinela.extraction` encapsula a lógica de extração mencionada no plano funcional: carregar notícias pendentes, aplicar NER e regras determinísticas, normalizar entidades e persistir relacionamentos em um banco relacional. A orquestração fica a cargo da classe `EntityExtractionService`, que recebe as dependências necessárias (repositórios Mongo, gravadores Postgres, motor NER e gazetteer) e processa lotes incrementais respeitando versões de pipeline.【F:sentinela/extraction/service.py†L31-L95】

## Componentes Principais

### Modelos e Protocolos

O módulo `models.py` define dataclasses imutáveis para representar documentos de notícia (`NewsDocument`), spans reconhecidos (`EntitySpan`), nomes normalizados (`NormalizedPersonName`) e ocorrências de pessoas e cidades com metadados completos. O arquivo também declara os protocolos `NewsRepository` e `ExtractionResultWriter`, que descrevem os contratos de integração com MongoDB e Postgres (ou outro armazenamento escolhido).【F:sentinela/extraction/models.py†L9-L127】

Esses protocolos permitem criar implementações específicas para o ambiente de produção sem acoplar o serviço à infraestrutura. O `NewsRepository` deve entregar lotes de notícias com `fetch_pending` e atualizar flags de versão via `mark_processed`/`mark_error`. O `ExtractionResultWriter` precisa garantir a existência do registro canônico da pessoa (`ensure_person`) e gravar cada ocorrência individual de pessoa e cidade nas tabelas de relacionamento.【F:sentinela/extraction/models.py†L100-L127】

### Normalização de Texto e Nomes

`normalization.py` remove boilerplates comuns das notícias, identifica menções a UFs por extenso ou siglas e aplica regras de capitalização/higienização em nomes de pessoas (remoção de títulos como "Dr." ou "Prefeito", tratamento de conectores e hífens). Também há utilitário para recuperar a frase onde o span ocorre, facilitando rastreabilidade posterior.【F:sentinela/extraction/normalization.py†L9-L142】

### Gazetteer de Cidades

`gazetteer.py` define a estrutura `CityRecord` (carregada a partir do catálogo do IBGE enriquecido com `alt_names`) e a classe `CityGazetteer`, um resolvedor em memória que normaliza variantes e seleciona candidatos com base em UF explicitada na notícia ou no contexto de estados mencionados. Quando múltiplos candidatos persistem, a resolução é marcada como `ambiguous` com a lista de hipóteses para revisão humana. O módulo ainda expõe `find_city_pattern_matches`, que captura padrões jornalísticos como “Cidade-UF”, “Cidade/UF”, “prefeito de X” e “município de X”.【F:sentinela/extraction/gazetteer.py†L12-L147】

### Interface de NER

`ner.py` contém o protocolo `NEREngine`, usado para integrar qualquer motor de reconhecimento de entidades compatível. Basta implementar o método `analyze(text)` retornando iteráveis de `EntitySpan` com rótulo, offsets, confiança e método (opcional).【F:sentinela/extraction/ner.py†L1-L12】

### Serviço de Extração

`EntityExtractionService` coordena todo o fluxo: lê o lote pendente respeitando `batch_size`, descarta notícias vazias, normaliza o texto e executa o NER. Em seguida, normaliza nomes de pessoas, garante o registro canônico via `result_writer`, captura a frase de contexto e grava cada ocorrência. Para cidades, combina spans do NER com os detectados por padrões determinísticos, separa UF quando presente ("Cidade-UF"/"Cidade/UF"), consulta o gazetteer com indícios de estado mencionados no texto e registra o status final (resolved/ambiguous/foreign) com hipóteses e confiança ajustada.【F:sentinela/extraction/service.py†L54-L175】

O método `process_next_batch` retorna um `ProcessedBatchResult` com totais processados, itens ignorados por falta de texto e lista de erros (URL + mensagem) para reprocessamento posterior.【F:sentinela/extraction/service.py†L54-L95】

## Fluxo de Processamento

1. `fetch_pending` devolve até `batch_size` documentos cujo `ner_done=false` ou versões desatualizadas.
2. Para cada notícia:
   - Combina título/corpo e normaliza o texto base.【F:sentinela/extraction/service.py†L97-L100】
   - Executa o motor NER e separa entidades de Pessoa/Local pelos rótulos configurados.【F:sentinela/extraction/service.py†L100-L105】
   - Normaliza nomes de pessoas, faz upsert canônico e registra ocorrências com frase e offsets.【F:sentinela/extraction/service.py†L106-L131】
   - Acrescenta cidades detectadas por padrões, resolve via gazetteer usando UF ou contexto, grava status/candidatos/confiança.【F:sentinela/extraction/service.py†L132-L175】
   - Atualiza o documento no Mongo com as versões e timestamp de processamento.【F:sentinela/extraction/service.py†L70-L84】
3. Em caso de exceção, grava o erro e continua com as demais notícias para garantir idempotência por lote.【F:sentinela/extraction/service.py†L85-L95】

## Preparando Dependências

1. **Repositório Mongo (`NewsRepository`)**: implemente `fetch_pending` buscando por `ner_done=false`/versões antigas, ordene por `_id` e limite pelo `batch_size`. Atualize `ner_done`, `ner_version`, `gazetteer_version`, `processed_at` em `mark_processed` e registre mensagens em `errors` para `mark_error`.
2. **Gravador Postgres (`ExtractionResultWriter`)**: use `ensure_person` para upsert na tabela `pessoas` (chaveada por `nome_canonico`). Nas ocorrências, persista `surface`, `spans`, `frase`, `metodo`, `confianca` e `status` nas tabelas `noticias_pessoas` e `noticias_cidades`, respeitando a unicidade `(url, start, end)`.
3. **Gazetteer**: carregue o catálogo do IBGE enriquecido com variantes (nome + `alt_names`) e instancie `CityGazetteer(cidades)`. É possível armazenar o catálogo em cache ou compartilhar a instância entre workers.【F:sentinela/extraction/gazetteer.py†L12-L122】
4. **Motor NER**: adapte seu pipeline SpaCy, Stanza ou outro sistema PT-BR retornando `EntitySpan`. O teste `FakeNER` demonstra como montar o objeto retornando entidades mockadas.【F:tests/test_entity_extraction_service.py†L36-L42】

## Como Utilizar no Código

O exemplo de teste de integração mostra o fluxo end-to-end com fakes em memória: cria-se um `NewsDocument`, injeta-se um `CityGazetteer`, `NEREngine` e repositórios/gravadores falsos, e então invoca-se `EntityExtractionService.process_next_batch()` para produzir ocorrências de pessoas e cidades persistidas no gravador de resultados.【F:tests/test_entity_extraction_service.py†L20-L109】

Em produção, o ciclo típico é:

```python
from sentinela.extraction import (
    CityGazetteer,
    CityRecord,
    EntityExtractionService,
)

# Dependências concretas implementadas pela aplicação
gazetteer = CityGazetteer(load_city_records())
service = EntityExtractionService(
    news_repository=MongoNewsRepository(...),
    result_writer=PostgresExtractionWriter(...),
    ner_engine=SpacyPortugueseNER(...),
    gazetteer=gazetteer,
    ner_version=os.environ["NER_VERSION"],
    gazetteer_version=os.environ["GAZETTEER_VERSION"],
    batch_size=int(os.environ.get("EXTRACTION_BATCH_SIZE", 500)),
)

result = service.process_next_batch()
print("Processadas", result.processed, "notícias")
```

O retorno `ProcessedBatchResult` permite alimentar métricas de observabilidade (processadas, vazias, erros) a cada execução de job ou worker.【F:sentinela/extraction/models.py†L92-L97】【F:sentinela/extraction/service.py†L54-L95】

## Boas Práticas Operacionais

- **Versionamento**: aumente `NER_VERSION`/`GAZETTEER_VERSION` sempre que atualizar modelo ou catálogo; o serviço só reprocessa notícias com versão anterior, garantindo reprocessamento incremental.【F:sentinela/extraction/service.py†L54-L84】
- **Idempotência**: derive a chave de unicidade das ocorrências (URL + span) no `ExtractionResultWriter` para evitar duplicatas, conforme indicado no plano.
- **Monitoramento**: registre métricas por lote a partir do `ProcessedBatchResult` e dos contadores de erros; use-as para alarmes e relatórios (ex.: taxa de ambiguidades).
- **Testes**: os testes unitários em `tests/` exemplificam regras de normalização, resolução por gazetteer e o fluxo end-to-end; adapte-os como base para testar implementações concretas ou regressões futuras.【F:tests/test_extraction_normalization.py†L1-L94】【F:tests/test_extraction_gazetteer.py†L1-L83】【F:tests/test_entity_extraction_service.py†L20-L109】

Com essas orientações, basta implementar as integrações concretas para Mongo/Postgres e acoplar o serviço a um agendador (cron, Celery, worker assíncrono) para operar o microserviço de cadastro de Pessoas e Cidades conforme os critérios de sucesso definidos.
