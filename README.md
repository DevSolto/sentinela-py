# Sentinela

Projeto Python modularizado para raspagem de dados em portais de notícia seguindo princípios SOLID e orientação a objetos. O projeto permite cadastrar portais com seletores CSS personalizados, coletar notícias em intervalos de datas e persistir o resultado em um banco MongoDB.

## Arquitetura

A solução foi organizada em camadas para favorecer separação de responsabilidades:

- **Domain**: entidades (`Portal`, `Article`), objetos de valor (`Selector`) e contratos de repositório.
- **Application**: serviços de caso de uso (`PortalRegistrationService`, `NewsCollectorService`).
- **Infrastructure**: implementação de scraping com Requests + BeautifulSoup, repositórios MongoDB e construção do container de dependências.
- **API**: camada REST construída com FastAPI expondo operações de cadastro de portais, coleta e consulta de notícias.

Essa separação facilita a substituição de componentes (por exemplo, outro banco de dados ou motor de scraping) sem alterar as camadas superiores.

## Requisitos

- Python 3.11+
- MongoDB acessível (padrão `mongodb://localhost:27017` e banco `sentinela`)
- Dependências Python listadas em `pyproject.toml`

Configure a conexão com MongoDB através das variáveis de ambiente:

```bash
export MONGO_URI="mongodb://localhost:27017"
export MONGO_DATABASE="sentinela"
```

## Instalação

Crie um ambiente virtual e instale o pacote em modo editável:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

## CLI (`sentinela-cli`)

Após a instalação, o utilitário de linha de comando `sentinela-cli` fica disponível para registrar portais, executar coletas e consultar artigos diretamente do terminal. Execute `sentinela-cli --help` para visualizar o índice de comandos ou use `sentinela-cli <comando> --help` para conhecer os parâmetros de cada subcomando.

| Comando | Objetivo | Argumentos principais |
| --- | --- | --- |
| `register-portal <arquivo.json>` | Cadastra um portal a partir de um arquivo JSON. | Caminho para o arquivo de configuração contendo seletores e metadados obrigatórios. |
| `list-portals` | Lista portais cadastrados. | — |
| `collect <portal> <data_inicial> [data_final]` | Coleta notícias em um intervalo de datas. | Datas no formato `YYYY-MM-DD`; `data_final` é opcional e assume `data_inicial` quando ausente. |
| `list-articles <portal> <data_inicial> <data_final>` | Lista artigos coletados previamente. | Datas obrigatórias no formato `YYYY-MM-DD`. |
| `collect-all <portal> [--start-page N] [--max-pages N] [--min-date AAAA-MM-DD]` | Percorre todas as páginas configuradas para um portal. | Flags opcionais controlam limites de paginação e data mínima. |

Todos os comandos aceitam a flag `--log-level` (`DEBUG`, `INFO`, `WARNING`, `ERROR`) e respeitam a variável de ambiente `SENTINELA_LOG_LEVEL`, útil para padronizar o nível de log em pipelines de CI/CD. O formato padrão de saída é `%(asctime)s %(levelname)s %(name)s - %(message)s`, conforme configurado em `sentinela/cli.py`. Um trecho típico dos logs ao rodar `collect` é apresentado abaixo:

```text
2024-05-18 10:32:11 INFO sentinela.services.news.collector - Iniciando coleta para portal=NoticiasExemplo start=2024-05-01 end=2024-05-03
2024-05-18 10:32:13 INFO sentinela.services.news.collector - 12 notícias baixadas; 12 novas, 0 duplicadas
12 novas notícias coletadas para 'NoticiasExemplo'.
```

Consulte a [documentação detalhada](docs/cli.md) para instruções completas, exemplos de uso e variáveis de ambiente suportadas.

## Executando a API

## Serviço de Extração

O microserviço de extração (`sentinela.services.extraction`) consome notícias publicadas para identificar pessoas e cidades mencionadas. Após instalar o pacote execute um dos comandos abaixo:

```bash
sentinela-extraction-api   # expõe rotas REST (/enqueue, /process, /results)
sentinela-extraction-worker # executa processamento contínuo por lotes
```

Configure `NER_VERSION`, `GAZETTEER_VERSION` e `EXTRACTION_GAZETTEER_PATH` para controlar reprocessamentos e catálogo de cidades. A coleta de notícias (`sentinela-news-api`) notifica automaticamente o worker usando o `PendingNewsQueue`, e os resultados ficam disponíveis na API de publicações via `/enriched/articles`.


Após instalar o pacote, inicie a API REST com o comando:

```bash
sentinela-api
```

O serviço utiliza o FastAPI e fica disponível por padrão em `http://127.0.0.1:8000`. A documentação interativa pode ser acessada em `http://127.0.0.1:8000/docs`.

### Cadastro de portal (`POST /portals`)

Envie o corpo JSON com a configuração do portal:

```bash
curl -X POST http://127.0.0.1:8000/portals \
  -H "Content-Type: application/json" \
  -d '{
        "name": "Noticias Exemplo",
        "base_url": "https://www.exemplo.com",
        "listing_path_template": "/arquivo/{date}",
        "selectors": {
          "listing_article": {"query": "article.card"},
          "listing_title": {"query": "h2 a"},
          "listing_url": {"query": "h2 a", "attribute": "href"},
          "listing_summary": {"query": "p.resumo"},
          "article_content": {"query": "div.conteudo"},
          "article_date": {"query": "time", "attribute": "datetime"}
        }
      }'
```

### Listagem de portais (`GET /portals`)

```bash
curl http://127.0.0.1:8000/portals
```

### Coleta de notícias (`POST /collect`)

```bash
curl -X POST http://127.0.0.1:8000/collect \
  -H "Content-Type: application/json" \
  -d '{"portal": "Noticias Exemplo", "start_date": "2024-05-01", "end_date": "2024-05-03"}'
```

### Consulta de artigos (`GET /articles`)

```bash
curl "http://127.0.0.1:8000/articles?portal=Noticias%20Exemplo&start_date=2024-05-01&end_date=2024-05-03"
```

As respostas são retornadas em JSON, incluindo o conteúdo completo e a data de publicação das notícias.

## Rollout da extração de cidades

O plano operacional detalhado para implantar as melhorias de extração de cidades, incluindo estratégia de branch (`feature/cities-extraction`), PR, validação em ambiente isolado, feature flag e rollback está documentado em [docs/rollout_cities_extraction.md](docs/rollout_cities_extraction.md).

## Testes

Os testes (quando houver) podem ser executados com:

```bash
pytest
```

## Extensão

- Substitua `RequestsSoupScraper` por outra implementação de `Scraper` caso necessite Selenium ou outro motor.
- Crie uma implementação alternativa de repositório para persistir em outros bancos respeitando os contratos do domínio.

