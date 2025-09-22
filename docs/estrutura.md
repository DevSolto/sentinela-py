# Documentação da Estrutura do Projeto

## Visão Geral

O Sentinela é um coletor modular de notícias com arquitetura em camadas. O diretório `sentinela` concentra o código-fonte da biblioteca, enquanto a raiz do repositório contém arquivos de configuração e documentação para distribuição do pacote Python.

## Estrutura de Diretórios

| Caminho | Descrição |
| --- | --- |
| `README.md` | Guia introdutório explicando objetivo, arquitetura geral e instruções de uso da API. |
| `pyproject.toml` | Declaração do pacote Python, dependências (FastAPI, Pydantic, Requests, BeautifulSoup, PyMongo etc.) e metadados para build com Poetry/setuptools. |
| `docs/estrutura.md` | Este documento com a descrição detalhada dos componentes. |
| `sentinela/` | Pacote principal com módulos da aplicação. |
| `sentinela.egg-info/` | Artefatos gerados pelo processo de build/install (metadados para distribuição). |

## Pacote `sentinela`

### `sentinela/__init__.py`
Reexporta entidades (`Article`, `Portal`, `PortalSelectors`, `Selector`) e serviços (`NewsCollectorService`, `PortalRegistrationService`) para facilitar importações externas. Também expõe os builders `build_portals_container` e `build_news_container`, além do shim legado `build_container`.【F:sentinela/__init__.py†L1-L18】

### `sentinela/api.py`
Define a API REST usando FastAPI. Inclui modelos Pydantic que representam payloads de portais, seletores e artigos, além das rotas:

- `POST /portals`: cadastra um portal ao transformar o payload em objeto `Portal` e delegar ao serviço de registro.
- `GET /portals`: lista portais registrados convertendo entidades em respostas JSON.
- `POST /collect`: executa a coleta de artigos em um intervalo de datas usando o serviço de coleta e retorna artigos gerados.
- `GET /articles`: consulta artigos persistidos por portal e período.

O módulo também cria a aplicação (`create_app`), mapeia entidades para DTOs de resposta, converte exceções de domínio em `HTTPException` e expõe uma função `run` para subir o servidor com Uvicorn.【F:sentinela/api.py†L1-L164】【F:sentinela/api.py†L166-L189】

### `sentinela/cli.py`
Implementa a interface de linha de comando com `argparse`. Os subcomandos disponíveis são:

- `register-portal <arquivo.json>`: carrega um JSON e cadastra um portal.
- `list-portals`: imprime os portais disponíveis.
- `collect <portal> <data_inicial> [data_final]`: solicita coleta de notícias para o intervalo fornecido.
- `list-articles <portal> <data_inicial> <data_final>`: lista artigos armazenados em formato JSON.

O arquivo inclui utilitários para parse de datas (`_parse_date`) e conversão do JSON em objetos de domínio (`_load_portal_from_json`, `_build_selector`). As dependências são montadas por `build_portals_container` e `build_news_container`, garantindo que cada serviço carregue apenas o necessário.【F:sentinela/cli.py†L1-L117】

### `sentinela/container.py`
Mantém um shim para compatibilidade retroativa, delegando a criação das dependências para `build_portals_container` e `build_news_container`. Retorna um objeto `Container` agregando os serviços principais para código legado.【F:sentinela/container.py†L1-L26】

### `sentinela/application/services.py`
Contém a camada de aplicação (casos de uso):

- `PortalRegistrationService`: valida duplicidade e delega persistência de portais ao `PortalRepository`.
- `NewsCollectorService`: coordena repositórios e o scraper para coletar artigos em um período, evitando duplicados e armazenando novos registros. Também fornece método para listar artigos no intervalo solicitado convertendo datas para `datetime`.

Ambos os serviços dependem apenas das interfaces de repositório e do componente de scraping, mantendo regras de negócio isoladas.【F:sentinela/application/services.py†L1-L63】【F:sentinela/application/services.py†L65-L96】

### `sentinela/domain/entities/`
As entidades do domínio foram divididas em arquivos individuais para facilitar evolução e documentação:

- `selector.py`: define `Selector`, especificando a consulta CSS e, opcionalmente, o atributo HTML a ser lido durante a raspagem.【F:sentinela/domain/entities/selector.py†L1-L15】
- `portal_selectors.py`: agrupa os seletores necessários para listar artigos, extrair detalhes e, se disponível, o resumo apresentado na listagem (`PortalSelectors`).【F:sentinela/domain/entities/portal_selectors.py†L1-L23】
- `portal.py`: descreve `Portal`, com URLs base, template parametrizado por data, cabeçalhos e método `listing_url_for` para montar a URL diária.【F:sentinela/domain/entities/portal.py†L1-L35】
- `article.py`: encapsula `Article`, contendo dados normalizados do conteúdo coletado, incluindo resumo opcional e metadados brutos.【F:sentinela/domain/entities/article.py†L1-L21】

Essas classes permanecem o modelo central consumido pelas demais camadas.

### `sentinela/domain/ports/`
Contém as portas que integram o domínio com serviços externos:

- `portal_gateway.py`: `PortalGateway` define como buscar configurações de portais em serviços remotos.【F:sentinela/domain/ports/portal_gateway.py†L1-L15】
- `article_sink.py`: `ArticleSink` descreve a publicação de artigos coletados para destinos externos.【F:sentinela/domain/ports/article_sink.py†L1-L14】

### `sentinela/domain/repositories/`
Reúne os contratos de persistência utilizados pela aplicação:

- `portal_repository.py`: operações de cadastro e consulta de portais (`PortalRepository`).【F:sentinela/domain/repositories/portal_repository.py†L1-L19】
- `article_repository.py`: escrita e consulta por período de artigos (`ArticleRepository`).【F:sentinela/domain/repositories/article_repository.py†L1-L24】
- `article_read_repository.py`: acesso somente leitura aos artigos persistidos (`ArticleReadRepository`).【F:sentinela/domain/repositories/article_read_repository.py†L1-L16】

### `sentinela/infrastructure/database.py`
Concentra configuração de acesso ao MongoDB:

- Função `get_env` para ler variáveis de ambiente com fallback e validação.
- `MongoSettings`: dataclass com URI e nome do banco, com fábrica `from_env`.
- `MongoClientFactory`: cria clientes compartilhados e retorna instâncias de banco a partir das configurações.

Serve de base para os repositórios concretos da camada de infraestrutura.【F:sentinela/infrastructure/database.py†L1-L40】

### `sentinela/infrastructure/repositories.py`
Implementa os repositórios MongoDB concretos:

- `MongoPortalRepository`: converte entidades `Portal` para documentos Mongo e vice-versa, oferecendo operações de inserir, buscar por nome e listar todos. A serialização inclui todos os seletores associados ao portal.【F:sentinela/infrastructure/repositories.py†L1-L71】
- `MongoArticleRepository`: cria índices para unicidade e ordenação, insere lotes de artigos (`save_many`), verifica duplicatas (`exists`) e consulta artigos por período (`list_by_period`) convertendo os documentos para objetos `Article` ao retornar.【F:sentinela/infrastructure/repositories.py†L73-L150】

### `sentinela/infrastructure/scraper.py`
Define a abstração de scraping (`Scraper`) e a implementação padrão `RequestsSoupScraper`, responsável por:

1. Montar a URL da listagem diária via `Portal.listing_url_for`.
2. Requisitar a página de listagem com Requests, parsear com BeautifulSoup e iterar pelos elementos dos artigos.
3. Extrair título, URL e resumo via seletores configurados.
4. Buscar a página individual de cada notícia, extrair conteúdo e data de publicação e convertê-la para `datetime`.
5. Retornar uma lista de entidades `Article` preenchidas com metadados adicionais (URL de origem e seletores usados).

Inclui utilitários privados para normalizar URLs (`_extract_url`), extrair valores com ou sem atributo (`_extract_value`) e interpretar datas (`_parse_datetime`).【F:sentinela/infrastructure/scraper.py†L1-L88】【F:sentinela/infrastructure/scraper.py†L90-L116】

### `sentinela/application/__init__.py`, `sentinela/domain/__init__.py`, `sentinela/infrastructure/__init__.py`
Arquivos vazios ou mínimos para declarar os pacotes Python correspondentes.

### `sentinela/ portais.json`
Exemplo de configuração de portal em JSON que pode ser reutilizado pelo CLI. Mostra estrutura esperada com seletores e cabeçalhos padrão.【F:sentinela/ portais.json†L1-L16】

## Fluxo de Dependências

1. **Entrada**: API (`sentinela/api.py`) ou CLI (`sentinela/cli.py`) recebem comandos externos.
2. **Containers**: API/CLI criam `PortalsContainer` ou `NewsContainer` conforme a funcionalidade, isolando dependências por domínio.
3. **Serviços de Aplicação**: orquestram regras de negócio com base nas entidades do domínio.
4. **Infraestrutura**: repositórios manipulam MongoDB e o scraper coleta HTML, convertendo dados em entidades.
5. **Persistência/Resposta**: artigos são salvos e retornados a quem iniciou o fluxo.

Essa arquitetura permite substituir componentes (ex.: outro scraper ou banco) sem alterar API/CLI ou serviços, graças às interfaces definidas no domínio.
