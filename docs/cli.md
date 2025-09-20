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

## Visão geral

A chamada segue o padrão:

```bash
sentinela-cli <comando> [opções]
```

Todos os subcomandos compartilham o argumento `--log-level` para ajustar a verbosidade. Além disso, a variável de ambiente `SENTINELA_LOG_LEVEL` possui prioridade sobre a opção de linha de comando e aceita os mesmos valores (`DEBUG`, `INFO`, `WARNING`, `ERROR`).

Para que os comandos funcionem é necessário ter o MongoDB acessível e configurar as variáveis `MONGO_URI` e `MONGO_DATABASE`. Portais precisam estar cadastrados antes de executar tarefas de coleta ou listagem de artigos.

## Configuração de logs

```bash
export SENTINELA_LOG_LEVEL=DEBUG
sentinela-cli list-portals
```

No exemplo acima o nível `DEBUG` será aplicado mesmo que a opção `--log-level` não seja informada. Caso `--log-level` seja passado explicitamente, por exemplo `--log-level WARNING`, ele é usado apenas se `SENTINELA_LOG_LEVEL` estiver ausente.

## Subcomandos

### register-portal

Registra um novo portal a partir de um arquivo JSON. Uso básico:

```bash
sentinela-cli register-portal ./config/meu_portal.json
```

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
sentinela-cli list-portals
```

A saída mostra cada portal no formato `- <nome>: <base_url>`. Requer conexão com o banco e portais previamente cadastrados.

### collect

Coleta notícias para um portal em um intervalo de datas:

```bash
sentinela-cli collect NoticiasExemplo 2024-05-01 2024-05-03
```

Argumentos:

- `portal` (obrigatório): nome do portal cadastrado.
- `start_date` (obrigatório): data inicial no formato `YYYY-MM-DD`.
- `end_date` (opcional): data final no mesmo formato. Quando omitida, a data inicial é usada como limite final.

Ao concluir, o comando informa quantas novas notícias foram coletadas para o portal. Podem ocorrer exceções caso o portal não exista, o formato de data seja inválido ou haja problemas na coleta.

### list-articles

Lista artigos coletados previamente para um portal:

```bash
sentinela-cli list-articles NoticiasExemplo 2024-05-01 2024-05-03
```

Argumentos obrigatórios:

- `portal`: nome do portal.
- `start_date`: data inicial `YYYY-MM-DD`.
- `end_date`: data final `YYYY-MM-DD`.

Cada linha da saída contém um JSON com os campos `portal`, `titulo`, `url` e `publicado_em`. O comando depende de artigos já armazenados no MongoDB.

### collect-all

Varre todas as páginas configuradas para um portal:

```bash
sentinela-cli collect-all NoticiasExemplo --start-page 1 --max-pages 5 --min-date 2024-01-01
```

Argumentos:

- `portal` (obrigatório): nome do portal cadastrado.
- `--start-page` (opcional, padrão `1`): página inicial.
- `--max-pages` (opcional): limite máximo de páginas a processar.
- `--min-date` (opcional): data mínima no formato `YYYY-MM-DD`; artigos mais antigos são ignorados.

Ao terminar, informa o número de novas notícias coletadas e os limites utilizados. Pode falhar se o portal não existir, se o formato de data estiver incorreto ou se não houver acesso às páginas do portal.
