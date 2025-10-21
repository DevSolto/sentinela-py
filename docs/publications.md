# API de Publicações

## Visão Geral
O microserviço de publicações expõe rotas FastAPI para consultar tanto os artigos coletados quanto os resultados de enriquecimento gerados pela pipeline de extração. As rotas são registradas em `include_routes`, que publica `/articles` para listagem básica e `/enriched/articles` para recuperar pessoas e cidades reconhecidas por URL.【F:sentinela/services/publications/api.py†L146-L204】

## Fluxo de Enriquecimento
Quando a pipeline de extração identifica novas cidades, o `MongoArticleCitiesWriter` sincroniza o campo `cities` diretamente no documento do artigo, preservando a lista atualizada usada pelos filtros de consulta.【F:sentinela/services/publications/infrastructure/mongo_article_cities_writer.py†L10-L23】 Os resultados completos (pessoas, cidades, candidatos e metadados de versão) ficam disponíveis via `GET /enriched/articles`, que serializa cada ocorrência através de `map_enriched`.【F:sentinela/services/publications/api.py†L74-L170】

Além das entidades enriquecidas, os artigos persistem a classificação atribuída durante ingestão ou processamento. O repositório Mongo garante que `classification` seja serializado juntamente com o resumo, conteúdo e metadados cronológicos, permitindo reexpor esse valor nas respostas públicas.【F:sentinela/services/publications/infrastructure/mongo_article_repository.py†L70-L92】

## Novidades no `GET /articles`
A resposta de `/articles` agora inclui o campo `classification`, refletindo o rótulo mais recente associado ao artigo, além do portal, título, conteúdo, cidades e datas. Esse valor é preenchido pelo mapeamento `map_article_response`, que converte a entidade de domínio em `ArticleResponse` antes de devolvê-la ao cliente.【F:sentinela/services/publications/api.py†L186-L214】

Também é possível restringir os resultados por cidade informando o parâmetro opcional `city`. O serviço de aplicação encaminha o filtro diretamente ao repositório de leitura, que aproveita o índice `{cities: 1, published_at: 1}` para aplicar o critério na consulta MongoDB sem pós-processamento em memória.【F:sentinela/services/publications/application/query_service.py†L16-L30】【F:sentinela/services/publications/infrastructure/mongo_article_read_repository.py†L20-L42】 Basta realizar chamadas no formato:

```http
GET /articles?portal=diario-oficial&start_date=2024-05-01&end_date=2024-05-31&city=Campinas
```

O parâmetro `city` é opcional; omiti-lo mantém o comportamento anterior, retornando todas as cidades vinculadas ao portal e período informado.

## Catálogo de municípios versionado

Para garantir consistência na resolução de localidades, o módulo de publicações agora depende do catálogo versionado descrito em [`docs/cidade_catalogo.md`](./cidade_catalogo.md). O script `python -m sentinela.services.publications.city_matching.build_cache` gera o arquivo `sentinela/data/municipios_br_<versao>.json`, enriquecido com metadados de origem, checksum e data de download. A função `load_city_catalog(version)` oferece acesso simples ao JSON durante o carregamento do _gazetteer_ ou outras rotinas que necessitem do mapeamento de municípios.
