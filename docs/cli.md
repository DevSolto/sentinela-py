# sentinela-cli

O utilitário de linha de comando `sentinela-cli` fornece acesso direto aos casos de uso do coletor Sentinela. O entrypoint é exposto pelo próprio pacote e registrado em `pyproject.toml`, na seção `[project.scripts].sentinela-cli`, permitindo a execução do comando após a instalação com `pip install -e .`.

## Índice

1. [Visão geral](#visão-geral)
2. [Configuração de logs](#configuração-de-logs)
3. [Subcomandos](#subcomandos)
   1. [register-portal](#register-portal)
   2. [list-portals](#list-portals)
   3. [collect](#collect)
   4. [list-articles](#list-articles)
   5. [collect-all](#collect-all)
   6. [report-articles](#report-articles)
   7. [extract-cities](#extract-cities)

## Visão geral

A chamada segue o padrão:

```bash
sentinela-cli <comando> [opções]
```

> **Nota**: se o comando `sentinela-cli` não estiver disponível no ambiente virtual,
> execute `pip install -e .` (ou `pip install -e . --no-build-isolation` em ambientes
> restritos) para registrar os scripts de console, ou utilize `python -m sentinela.cli`
> como alternativa direta.

Todos os subcomandos compartilham o argumento `--log-level` para ajustar a verbosidade. Além disso, a variável de ambiente `SENTINELA_LOG_LEVEL` possui prioridade sobre a opção de linha de comando e aceita os mesmos valores (`DEBUG`, `INFO`, `WARNING`, `ERROR`). Quando ambos são informados, a variável de ambiente prevalece. O utilitário carrega variáveis definidas em um arquivo `.env` automaticamente via `python-dotenv`.

### Pré-requisitos

- Python 3.11+ com o pacote `sentinela` instalado (`pip install -e .`).
- Banco MongoDB acessível com as variáveis `MONGO_URI` e `MONGO_DATABASE` preenchidas.
- Portais cadastrados previamente para executar tarefas de coleta ou listagem de artigos.

### Variáveis de ambiente relevantes

| Nome | Função | Valor padrão |
| --- | --- | --- |
| `MONGO_URI` | String de conexão com o MongoDB. | `mongodb://localhost:27017` |
| `MONGO_DATABASE` | Nome do banco de dados MongoDB. | `sentinela` |
| `SENTINELA_LOG_LEVEL` | Define o nível de log global (`DEBUG`, `INFO`, `WARNING`, `ERROR`). Tem precedência sobre `--log-level`. | `INFO` |

> **Dica**: utilize um arquivo `.env` na raiz do projeto para centralizar as variáveis de ambiente durante o desenvolvimento local.

## Configuração de logs

```bash
export SENTINELA_LOG_LEVEL=DEBUG
sentinela-cli list-portals
```

No exemplo acima o nível `DEBUG` será aplicado mesmo que a opção `--log-level` não seja informada. Caso `--log-level` seja passado explicitamente, por exemplo `--log-level WARNING`, ele é usado apenas se `SENTINELA_LOG_LEVEL` estiver ausente.

Os logs seguem o formato `%(asctime)s %(levelname)s %(name)s - %(message)s`, gerando saídas como:

```text
2024-05-18 10:32:11 INFO sentinela.services.news.collector - Iniciando coleta para portal=NoticiasExemplo start=2024-05-01 end=2024-05-03
2024-05-18 10:32:13 INFO sentinela.services.news.collector - 12 notícias baixadas; 12 novas, 0 duplicadas
```

Redirecione a saída (`> logs/coleta.log`) quando precisar consolidar registros para auditoria.

## Subcomandos

### register-portal

Registra um novo portal a partir de um arquivo JSON. Uso básico:

```bash
sentinela-cli register-portal ./config/meu_portal.json [--log-level DEBUG]
```

Argumentos:

| Nome | Tipo | Obrigatório | Descrição |
| --- | --- | --- | --- |
| `path` | Caminho | Sim | Caminho para o arquivo JSON com seletores e metadados do portal. |
| `--log-level` | String | Não | Altera o nível de log somente para esta execução. |

O arquivo deve conter a seguinte estrutura mínima:

```json
{
  "name": "Noticias Exemplo",
  "base_url": "https://www.exemplo.com",
  "listing_path_template": "/arquivo/{date}",
  "selectors": {
    "listing_article": {"query": "article.card"},
    "listing_title": {"query": "h2 a"},
    "listing_url": {"query": "h2 a", "attribute": "href"},
    "article_content": {"query": "div.conteudo"},
    "article_date": {"query": "time", "attribute": "datetime"}
  },
  "headers": {
    "User-Agent": "Mozilla/5.0"
  },
  "date_format": "%Y-%m-%d"
}
```

Campos dentro de `selectors` aceitam os blocos opcionais `listing_summary` (resumo) e qualquer seletor deve informar `query` e, quando necessário, `attribute`. Após uma execução bem-sucedida, a mensagem `Portal '<nome>' cadastrado com sucesso.` é exibida. Exceções comuns incluem JSON inválido ou falhas de conexão ao MongoDB.

### list-portals

Lista os portais registrados:

```bash
sentinela-cli list-portals [--log-level DEBUG]
```

Saída esperada:

```text
- Noticias Exemplo: https://www.exemplo.com
```

Requer conexão com o banco e portais previamente cadastrados. Combine com `--log-level DEBUG` para depurar chamadas ao repositório.

### collect

Coleta notícias para um portal em um intervalo de datas:

```bash
sentinela-cli collect NoticiasExemplo 2024-05-01 2024-05-03 --log-level INFO
```

Argumentos:

| Nome | Tipo | Obrigatório | Descrição |
| --- | --- | --- | --- |
| `portal` | String | Sim | Nome do portal cadastrado. |
| `start_date` | Data (`YYYY-MM-DD`) | Sim | Data inicial da coleta. |
| `end_date` | Data (`YYYY-MM-DD`) | Não | Data final (usa `start_date` se omitida). |
| `--log-level` | String | Não | Define o nível de log da execução. |

Ao concluir, o comando informa quantas novas notícias foram coletadas para o portal. Podem ocorrer exceções caso o portal não exista, o formato de data seja inválido ou haja problemas na coleta.

### list-articles

Lista artigos coletados previamente para um portal:

```bash
sentinela-cli list-articles NoticiasExemplo 2024-05-01 2024-05-03 > artigos.jsonl
```

Argumentos obrigatórios:

- `portal`: nome do portal.
- `start_date`: data inicial `YYYY-MM-DD`.
- `end_date`: data final `YYYY-MM-DD`.

Cada linha da saída contém um JSON com os campos `portal`, `titulo`, `url` e `publicado_em`. O comando depende de artigos já armazenados no MongoDB.

### collect-all

Varre todas as páginas configuradas para um portal:

```bash
sentinela-cli collect-all NoticiasExemplo --start-page 1 --max-pages 5 --min-date 2024-01-01 --log-level DEBUG
```

Argumentos:

| Nome | Tipo | Obrigatório | Descrição |
| --- | --- | --- | --- |
| `portal` | String | Sim | Nome do portal cadastrado. |
| `--start-page` | Inteiro | Não (padrão `1`) | Página inicial. |
| `--max-pages` | Inteiro | Não | Limite máximo de páginas a processar; varre tudo quando omitido. |
| `--min-date` | Data (`YYYY-MM-DD`) | Não | Ignora artigos mais antigos do que a data informada. |
| `--log-level` | String | Não | Sobrescreve o nível de log na chamada. |

Ao terminar, informa o número de novas notícias coletadas e os limites utilizados. Pode falhar se o portal não existir, se o formato de data estiver incorreto ou se não houver acesso às páginas do portal.

### report-articles

Gera um relatório CSV com os dados principais dos artigos, incluindo o texto completo, e as cidades mencionadas em cada um. Caso um artigo cite múltiplas cidades, ele aparece uma vez por cidade; se não houver menção, o campo `cidade` fica vazio.

```bash
sentinela-cli report-articles NoticiasExemplo 2024-05-01 2024-05-31 --output relatorios/maio.csv
```

Argumentos:

| Nome | Tipo | Obrigatório | Descrição |
| --- | --- | --- | --- |
| `portal` | String | Sim | Nome do portal/blog cadastrado para filtrar os artigos. |
| `start_date` | Data (`YYYY-MM-DD`) | Sim | Data inicial do intervalo. |
| `end_date` | Data (`YYYY-MM-DD`) | Sim | Data final do intervalo. |
| `--output` | Caminho | Não | Local do arquivo CSV a ser gerado (padrão: `relatorio_<portal>.csv` no diretório atual). |
| `--log-level` | String | Não | Ajusta a verbosidade da execução. |

O relatório possui as colunas `portal`, `titulo`, `url`, `conteudo`, `publicado_em`, `resumo`, `classificacao`, `cidade`, `cidade_id`, `uf`, `ocorrencias` e `fontes`. Quando um artigo contém múltiplas cidades, cada linha terá a mesma informação do artigo com a cidade correspondente. Se o artigo não mencionar nenhuma cidade, uma única linha é gerada com os campos `cidade`, `cidade_id`, `uf`, `ocorrencias` e `fontes` vazios.

O diretório de saída é criado automaticamente quando informado via `--output`. Utilize a opção com caminhos absolutos ou relativos (`./relatorios/maio.csv`) para separar relatórios por portal ou período.

### Exemplo completo

O fluxo abaixo registra um portal, executa uma coleta e lista artigos enquanto grava logs em arquivo:

```bash
export MONGO_URI="mongodb://localhost:27017"
export MONGO_DATABASE="sentinela"
sentinela-cli register-portal ./config/meu_portal.json --log-level INFO
sentinela-cli collect NoticiasExemplo 2024-05-01 2024-05-03 --log-level DEBUG | tee logs/collect.log
sentinela-cli list-articles NoticiasExemplo 2024-05-01 2024-05-03 > artigos_202405.jsonl
```

O arquivo `logs/collect.log` conterá os mesmos registros exibidos no terminal, facilitando auditoria posterior.

### extract-cities

O subcomando `extract-cities` executa o job de extração de cidades diretamente na coleção `articles` do MongoDB utilizando o catálogo descrito em [`docs/cidade_catalogo.md`](./cidade_catalogo.md). Ele está disponível tanto via `sentinela-cli extract-cities` quanto pelo script legado `sentinela-extract-cities` registrado em `pyproject.toml`.

#### Pré-requisitos

- Variáveis `MONGO_URI` e `MONGO_DATABASE` apontando para a instância que armazena a coleção `articles`.
- Arquivo de cache `sentinela/data/municipios_br_<versao>.json` correspondente à constante `CITY_CACHE_VERSION`.
- Opcional: defina `SENTINELA_LOG_LEVEL=DEBUG` para acompanhar o processamento em detalhes.

#### Argumentos disponíveis

| Opção | Tipo | Obrigatório | Descrição |
| --- | --- | --- | --- |
| `--portal` | String | Não | Restringe o processamento a um único portal (`portal_name`). |
| `--batch-size` | Inteiro | Não (padrão `100`) | Quantidade de documentos buscados por página. |
| `--only-missing` | Flag | Não | Processa apenas artigos sem hash de extração registrado. |
| `--force` | Flag | Não | Reprocessa artigos mesmo com hash idêntico (ignora cache). |
| `--dry-run` | Flag | Não | Executa a extração sem persistir alterações (somente logs). |
| `--metrics-file` | Caminho | Não | Exporta o resumo final em JSON para o arquivo informado. |
| `--log-level` | String | Não | Ajusta o nível de log da execução atual. |

#### Processar todos os portais

```bash
export MONGO_URI="mongodb://localhost:27017"
export MONGO_DATABASE="sentinela"
sentinela-cli extract-cities --only-missing --batch-size 200 --metrics-file metrics.json
```

O comando acima percorre todas as notícias cadastradas, atualiza o campo `cities` quando necessário e salva um resumo agregado em `metrics.json` (contendo campos como `processed`, `updated` e `ambiguous`). Utilize `--dry-run` para validar o impacto antes de persistir as alterações.

#### Processar apenas um portal

```bash
sentinela-cli extract-cities --portal diario-oficial --only-missing --batch-size 100
```

Quando `--portal` é informado, somente artigos cujo `portal_name` coincide com o valor fornecido são analisados. Esse modo é útil para reprocessar um portal específico após ajustes de catálogo ou gazetteer, evitando reprocessamentos desnecessários nos demais portais. Os logs exibem o total escaneado e atualizado dentro do recorte informado.
