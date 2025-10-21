# Catálogo de Municípios Brasileiros

Este catálogo provê uma listagem confiável e versionada de todos os municípios brasileiros.

## Fontes de Dados

| Papel | Fonte | SLA observado | Campos mínimos | Limitações conhecidas |
| --- | --- | --- | --- | --- |
| Primária | [IBGE Localidades API](https://servicodados.ibge.gov.br/api/docs/localidades) | 24x7, monitorado por _status_ público; operações rápidas (&lt; 5 s) para o endpoint `/municipios`. | `id`, `nome`, `microrregiao.mesorregiao.UF.sigla`, `microrregiao.mesorregiao.UF.nome`, `microrregiao.mesorregiao.UF.regiao.nome`. | Ausência de lat/long; indisponibilidade eventual em janelas de manutenção.
| Secundária (fallback) | [BrasilAPI](https://brasilapi.com.br/docs#tag/IBGE) | Mantida pela comunidade, resposta típica em &lt; 2 s. | `codigo_ibge`, `nome`, `estado`, `latitude`, `longitude`, `siafi_id`, `ddd`. | Disponibilidade "best effort"; pode divergir nos metadados de UF.

Os dois provedores cobrem o conjunto completo de 5.570 municípios brasileiros. Quando a fonte primária retorna erro ou formato inesperado, acionamos automaticamente o fallback e registramos a fonte efetiva nos metadados do cache.

> **Nota**: o arquivo `municipios_br_v1.json` versionado no repositório contém um subconjunto representativo (capitais) para permitir testes em ambientes sem acesso externo. Em ambientes com acesso à internet, execute o builder para publicar o catálogo completo.

## Campos disponibilizados

Cada entrada no catálogo normalizado contém os campos obrigatórios abaixo:

* `ibge_id` – código oficial do IBGE em formato de string.
* `name` – nome oficial do município.
* `uf` – sigla da unidade federativa.
* `state` – nome da unidade federativa (enriquecido via IBGE ou tabela local).
* `region` – macrorregião brasileira correspondente.

Campos opcionais podem aparecer conforme a fonte ativa (por exemplo `mesoregion`, `microregion`, `latitude`, `longitude`, `capital`, `siafi_id`, `ddd`, `timezone`).

## Limpeza e validação

O construtor do cache elimina registros sem `ibge_id` ou `name`, remove duplicados por código IBGE e ordena os resultados para garantir reprodutibilidade. O arquivo JSON gravado inclui metadados com `version`, `source`, `primary_source`, `downloaded_at`, `record_count` e `checksum` SHA-256 calculado sobre os dados.

## Procedimento de atualização

1. Ajuste a constante `CITY_CACHE_VERSION` caso deseje publicar nova versão.
2. Execute `python -m sentinela.services.publications.city_matching.build_cache --source ibge --version <nova_versao> --refresh`.
3. Substitua o arquivo `sentinela/data/municipios_br_<versao>.json` no repositório.
4. Confirme a integridade do cache com o teste rápido `tests/services/publications/city_matching/test_catalogo.py` (ou `pytest -k city_catalog`).

Os metadados permitem auditoria da origem e data de download de cada release do catálogo.
