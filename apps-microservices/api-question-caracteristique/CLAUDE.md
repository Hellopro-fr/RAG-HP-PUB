# api-question-caracteristique

API for the QC (Quality/Categorization) pipeline: generates questions, characteristics, values, enrichment, equivalences, and product characterization for categories.

## Tech Stack

- **Language:** Python 3.10
- **Framework:** FastAPI + Uvicorn
- **LLM:** via `common_utils.grpc_clients` (gRPC ChatRequest)
- **External API:** HelloPro API client for category data
- **Shared libs:** `common_utils`, `grpc-stubs`

## Build / Run

- **Port:** 8540 (shares Dockerfile pattern with api-chat-llm)
- **Run:** `uvicorn main:app --host 0.0.0.0 --port 8540`
- **Docker build:** installs protobuf compiler, generates gRPC stubs

## Folder Structure

```
api-question-caracteristique/
  main.py                                # FastAPI app
  app/
    core/
      credentials.py                     # Settings
      api_client.py                      # HelloProAPIClient
      question_generator.py              # QuestionGenerator (steps 1-2)
      caracteristique_generator.py       # CaracteristiqueGenerator (steps 3-4)
      enrichissement_generator.py        # EnrichissementGenerator (step 5)
      equivalence_generator.py           # EquivalenceGenerator (step 6)
      caracterisation_produit.py         # CaracterisationProduitGenerator (step 7)
      ConnexionManager.py                # WebSocket manager
      utils.py                           # Shared utilities
    router/
      question_caracteristique.py        # All generation endpoints
    schemas/
      question_caracteristique.py        # RequestProcessus, ApiResponse
    utils/
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/generate/question1` | Generate level-1 questions |
| `POST` | `/generate/question2aN` | Generate level-2-to-N questions |
| `POST` | `/generate/list_caracteristiques` | Generate characteristic list |
| `POST` | `/generate/info_caracteristiques` | Generate characteristic info (1-by-1) |
| `POST` | `/generate/enrichissement` | Enrich characteristics via questions |
| `GET` | `/` | Health check |

## Conventions

- 7-step pipeline: question1 -> question2aN -> list_carac -> info_carac -> enrichissement -> equivalence -> caracterisation.
- Each generator class follows the same pattern: init with API client, generate, close.
- Route path determines which step to execute (parsed from `request.url.path`).

## Dependencies on Other Services

- **LLM service** (via gRPC)
- **HelloPro external API** (category data)
