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

## Política de versionamento

A constante `CITY_CACHE_VERSION` (definida em `sentinela/services/publications/city_matching/config.py`) identifica a versão ativa do catálogo. Utilize o padrão `v<numero>` (por exemplo, `v1`, `v2`...) e incremente:

- **Major (`v2`, `v3`, ...)** quando houver mudanças estruturais no payload que exijam ajustes em consumidores ou reprocessamentos completos.
- **Minor (`v1.1`, `v1.2`, ...)** para ajustes compatíveis (adição de campos, correções de metadados) que não quebram integração. Embora o código atual leia apenas `vN`, é recomendável manter o padrão `vN` no repositório e incluir o sufixo `.1`, `.2` nos metadados (`metadata.version`) quando a mudança for interna.

Mantenha as versões antigas no repositório até concluir o rollout para permitir rollback imediato. Arquivos ficam nomeados como `municipios_br_<versao>.json` dentro de `sentinela/data/`.

## Regeneração do cache passo a passo

1. Ajuste `CITY_CACHE_VERSION` para a nova versão planejada e confirme se existe um arquivo alvo (`sentinela/data/municipios_br_<versao>.json`).
2. Limpe caches locais antigos removendo `sentinela/data/municipios_br_*.json` temporários e garanta que a pasta `data/tmp` (se usada) esteja vazia.
3. Execute o builder com fonte e versão desejadas:
   ```bash
   python -m sentinela.services.publications.city_matching.build_cache --source ibge --version <nova_versao> --refresh
   ```
   Use `--source brasilapi` para publicar um fallback em caso de indisponibilidade do IBGE.
4. Revise o arquivo gerado verificando `metadata.version`, `record_count`, `primary_source` e `checksum`. Compare o checksum com a execução anterior para identificar alterações significativas.
5. Rode os testes de integridade:
   ```bash
   pytest tests/services/publications/city_matching/test_build_cache.py
   ```
   ou `pytest -k city_catalog` para a suíte reduzida.
6. Atualize a documentação (este arquivo) e o `CHANGELOG` ou notas de release internas descrevendo fontes, diferenças e impactos esperados.
7. Commits devem citar a versão publicada no título (ex.: `chore: atualiza catálogo de municípios para v2`).

Os metadados permitem auditoria da origem e data de download de cada release do catálogo e são essenciais para o controle de versão em produção. Guarde o arquivo anterior em um local acessível para rollback rápido caso as validações posteriores apontem regressões.
