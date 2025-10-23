# Visão Conceitual da Solução Sentinela

Este documento descreve, em alto nível, o fluxo completo da plataforma Sentinela —
desde o cadastro de portais até a disponibilização de notícias enriquecidas com
informações extraídas automaticamente. O objetivo é apresentar a sequência de
passos executados pelos serviços, sem entrar em detalhes de implementação.

## Componentes principais

- **Serviço de Portais**: concentra o cadastro dos portais e seus seletores de
  raspagem, garantindo unicidade de nomes e oferecendo uma API para consulta
  dessas configurações.
- **Serviço de Coleta de Notícias**: coordena a raspagem diária ou paginada,
  aplica deduplicação e envia as notícias coletadas para persistência.
- **Serviço de Publicações**: recebe os artigos, armazena-os e expõe consultas
  públicas, inclusive enriquecimentos provenientes da extração.
- **Serviço de Extração**: consome filas de notícias pendentes para rodar
  modelos de reconhecimento de entidades (NER) e normalizar cidades com base em
  um gazetteer.

## Fluxo ponta a ponta

1. **Cadastro de portais**  
   Operadores registram novos portais informando URL base, template de listagem
   e seletores CSS. O `PortalRegistrationService` impede duplicidades ao
   consultar o repositório antes de persistir o cadastro.

2. **Recuperação de configurações**  
   Quando uma coleta é iniciada, o serviço de notícias pede os dados do portal
   à API de portais via `PortalServiceClient`, reconstruindo a entidade
   `Portal` com os seletores originais.

3. **Disparo da coleta**  
   A coleta pode ser acionada por CLI ou via rotas REST (`POST /collect` e
   `/collect/stream`). A aplicação FastAPI converte o payload em datas e delega
   ao `NewsCollectorService`.

4. **Raspagem e normalização**  
   Para cada dia do intervalo, o `NewsCollectorService` solicita ao
   `RequestsSoupScraper` que abra a listagem, siga os links de cada artigo e
   normalize título, conteúdo, resumo e data conforme os seletores cadastrados.

5. **Deduplicação e persistência**  
   URLs repetidas dentro do intervalo são filtradas em memória antes de enviar
   os artigos ao `ArticleSink`. Na implementação padrão, o
   `PublicationsAPISink` empacota os artigos e chama a rota `/articles/batch`
   do serviço de publicações, que retorna apenas os itens aceitos.

6. **Notificação para extração**  
   Sempre que novos artigos são coletados, o serviço de notícias chama
   `notify_news_ready`, que insere `NewsDocument` na fila compartilhada
   (`PendingNewsQueue`) para processamento assíncrono.

7. **Processamento de entidades**  
   O serviço de extração inicializa `EntityExtractionService` com modelos de
   NER e gazetteer configuráveis. O worker busca lotes na fila através do
   `QueueNewsRepository`, executa a extração e registra pessoas e cidades no
   `ExtractionResultStoreWriter` (ou outro backend configurado).

8. **Disponibilização dos resultados**  
   O serviço de publicações agrega notícias e enriquecimentos. Suas rotas REST
   entregam tanto o conteúdo bruto (`/articles`) quanto entidades enriquecidas
   (`/enriched/articles`), permitindo construir dashboards ou integrações
   externas.

## Resumo conceitual

Em termos conceituais, a solução pode ser vista como um pipeline dirigido por
configuração:

1. Os portais definem **como** raspar;  
2. A coleta executa **quando e o que** raspar;  
3. A publicação guarda **o que foi encontrado**;  
4. A extração enriquece **o que pode ser conhecido** a partir do texto.

Essa separação garante flexibilidade para substituir motores de raspagem,
backends de armazenamento ou modelos de extração sem interromper o fluxo geral
nem duplicar regras de negócio entre os serviços.
