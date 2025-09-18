# Sentinela

Projeto Python modularizado para raspagem de dados em portais de notícia seguindo princípios SOLID e orientação a objetos. O projeto permite cadastrar portais com seletores CSS personalizados, coletar notícias em intervalos de datas e persistir o resultado em um banco MongoDB.

## Arquitetura

A solução foi organizada em camadas para favorecer separação de responsabilidades:

- **Domain**: entidades (`Portal`, `Article`), objetos de valor (`Selector`) e contratos de repositório.
- **Application**: serviços de caso de uso (`PortalRegistrationService`, `NewsCollectorService`).
- **Infrastructure**: implementação de scraping com Requests + BeautifulSoup, repositórios MongoDB e construção do container de dependências.
- **CLI**: interface de linha de comando para cadastro de portais, coleta e listagem de notícias.

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

## Cadastro de portal

Crie um arquivo JSON descrevendo o portal e seletores CSS necessários. Exemplo (`exemplo_portal.json`):

```json
{
  "name": "Noticias Exemplo",
  "base_url": "https://www.exemplo.com",
  "listing_path_template": "/arquivo/{date}",
  "date_format": "%Y-%m-%d",
  "headers": {
    "User-Agent": "Mozilla/5.0"
  },
  "selectors": {
    "listing_article": {"query": "article.card"},
    "listing_title": {"query": "h2 a"},
    "listing_url": {"query": "h2 a", "attribute": "href"},
    "listing_summary": {"query": "p.resumo"},
    "article_content": {"query": "div.conteudo"},
    "article_date": {"query": "time", "attribute": "datetime"}
  }
}
```

Registre o portal através da CLI:

```bash
sentinela register-portal exemplo_portal.json
```

## Coleta de notícias

Execute a coleta informando o portal e o intervalo de datas (formato `YYYY-MM-DD`). Se a data final for omitida, usa-se apenas a data inicial.

```bash
sentinela collect "Noticias Exemplo" 2024-05-01 2024-05-03
```

Os artigos coletados são salvos na coleção `articles`. O serviço evita duplicidade verificando URL + portal.

## Listar notícias

Para consultar artigos persistidos em um intervalo:

```bash
sentinela list-articles "Noticias Exemplo" 2024-05-01 2024-05-03
```

Cada linha da saída é um JSON com título, URL e data de publicação.

## Testes

Os testes (quando houver) podem ser executados com:

```bash
pytest
```

## Extensão

- Substitua `RequestsSoupScraper` por outra implementação de `Scraper` caso necessite Selenium ou outro motor.
- Crie uma implementação alternativa de repositório para persistir em outros bancos respeitando os contratos do domínio.

