# CLI de Enriquecimento Geográfico

O comando `sentinela-geo-enrichment` executa o pipeline completo de enriquecimento
geográfico para um artigo e produz um payload compatível com `GeoOutput`. Ele
reaproveita o catálogo de municípios versionado e as mesmas regras de sinalização
utilizadas pela extração automática, permitindo validar casos manualmente ou
integrar o serviço a outras rotinas.

## Pré-requisitos

* Python 3.10+ com as dependências do projeto instaladas.
* Arquivo `sentinela/data/municipios_br_<versao>.json` gerado pelo builder de
  catálogo ou um catálogo customizado compatível.

## Uso básico

```
sentinela-geo-enrichment enrich caminho/para/artigo.json --pretty
```

O arquivo do artigo deve conter os campos textuais (`title`, `body` ou
`content`). O resultado é impresso em JSON e inclui as cidades mencionadas, a
cidade primária selecionada, detalhes de desambiguação e metadados do catálogo.

Para gravar o resultado em disco, use a opção `--output`:

```
sentinela-geo-enrichment enrich artigo.json --output resultado.json --pretty
```

## Opções relevantes

* `--catalog`: usa um catálogo alternativo em JSON. Aceita o mesmo formato do
  arquivo versionado ou uma lista simples de cidades.
* `--catalog-version`: força a versão a ser carregada via `load_city_catalog`.
* `--ensure-complete`: baixa automaticamente o catálogo completo quando a cópia
  local contiver apenas a amostra reduzida.
* `--id-field` / `--fallback-id`: definem quais campos do artigo serão usados
  para determinar `article_id` no resultado.
* `--include-extraction`: adiciona ao JSON final os dados brutos de extração
  (campos processados, matches e metadados de hashing).
* `--log-level`: ajusta a verbosidade dos logs de execução.

Execute `sentinela-geo-enrichment enrich --help` para consultar a lista completa
de opções e exemplos de uso.【F:sentinela/services/publications/geo_cli.py†L33-L193】

