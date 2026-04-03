# graph-rag-llm-extractor-processor
RabbitMQ consumer that extracts structured product characteristics from raw text using LLM APIs (DeepSeek, OpenAI, Gemini, Anthropic).

## Tech Stack
- **Language:** Python 3.10
- **Messaging:** aio_pika (async RabbitMQ)
- **LLM SDKs:** openai, google-genai, anthropic (multi-provider)
- **Observability:** Prometheus metrics

## Build & Run
```bash
pip install -r requirements.txt
python -m app.main
```
- **Docker port:** 8561 (Prometheus only)
- Build is Docker-only

## Folder Structure
```
app/
  main.py                    # Entrypoint
  config.py                  # pydantic-settings (LLM provider config, queues)
  core/
    processor.py             # LLM extraction logic
    prompts.py               # Prompt templates for structured extraction
  messaging/consumer.py      # RabbitMQ consumer
  messaging/publisher.py     # Publishes extracted data downstream
  infrastructure/llm_client.py  # Multi-provider LLM client
```

## Conventions
- Default LLM provider: DeepSeek (`deepseek-chat`)
- Supports 4 providers: DeepSeek, OpenAI, Gemini, Anthropic
- Concurrency: `MAX_CONCURRENCY=10` parallel LLM requests
- Prompt templates in `core/prompts.py`

## API Endpoints
- None (RabbitMQ consumer only)

## Dependencies
- **Input:** `graph_rag_llm_extraction_queue` (exchange: `graph_rag_product_extracted`, key: `graph_rag.product.extracted`)
- **Output:** `graph_rag_normalization` (key: `graph_rag.normalization.pending`)
- **Upstream:** produit-processor
- **Downstream:** normalize-unite-processor
