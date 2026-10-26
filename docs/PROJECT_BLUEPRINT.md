# DrugShield AI project blueprint

## Purpose

Build a web application that analyzes conversations created inside three local chat simulations styled after Instagram, Telegram, and WhatsApp. The application does not connect to real social accounts or collect live platform data.

The system flags evidence for human review. It does not identify real people or make enforcement decisions.

## End-to-end flow

1. Curate and label an authorized training dataset. The working target is at least 10,000 labeled examples; sample count alone does not establish quality.
2. Train and evaluate the text and image classifiers. Use OCR, QR decoding, and UPI/VPA candidate parsing as deterministic extraction steps; these steps do not need model training.
3. A user creates a conversation in one of the three simulations. No preloaded mock or fallback conversation is used as evidence.
4. The matching simulation collector sends each message and media reference to the backend using a shared event schema.
5. The backend preserves the submitted event in a raw evidence log, runs the relevant detectors, and records the detector version and findings.
6. The case service combines findings into an alert and links fictional accounts and identifiers in a graph.
7. The dashboard displays the report, evidence, graph, and review status.
8. A reviewer accepts, requests further review, or dismisses the alert. Only finalized, reviewed examples may be considered for a future training set.
9. A candidate model is retrained and evaluated offline. It becomes active only after validation and explicit version promotion.

## Data boundaries

- `data/training/` is reserved for authorized, labeled training data and a provenance manifest. The current repository does not contain a verified 10,000-example training dataset.
- Runtime simulation events are authored by a person using the chat simulations. They are not training data and must not silently fall back to seeded records.
- `data/runtime/raw/` and `data/runtime/processed/` are application-generated evidence and analysis outputs. They are not committed as sample training data.
- Novelty means an item differs from the known training corpus or entity store. Novelty is a separate signal, not a suspiciousness label.
- Training and evaluation partitions must be separated by source/conversation where possible to reduce leakage.

## Target project layout

```text
frontend/
  src/simulations/instagram/
  src/simulations/telegram/
  src/simulations/whatsapp/
  src/dashboard/
  src/cases/
  src/graph/
src/
  api/                    # HTTP routes, validation, authentication boundary
  ingestion/              # Three simulation collectors; shared event schema
  ai_pipeline/             # Text, OCR, QR, VPA, novelty, and orchestration
  cases/                   # Alert/report assembly and status transitions
  database/                # Relational case/evidence persistence and graph links
  review/                  # Decisions, audit history, feedback eligibility
  training/                # Dataset manifests, train/evaluate/promote workflows
data/
  training/                # Authorized labeled datasets only
  runtime/raw/             # Generated at runtime; ignored by Git
  runtime/processed/       # Generated at runtime; ignored by Git
models/
  registry/                # Versioned model metadata; large weights stored separately
tests/
  unit/ integration/       # No fixtures are loaded into training
docs/
```

## Existing components to reuse or adapt

- `config/settings.py`: retain general configuration; remove platform credentials and use local simulation settings.
- `config/constants.py`: retain only validated text labels, VPA patterns, and risk settings; remove live-platform, location, and identity-attribution rules.
- `src/ai_pipeline/nlp_classifier.py`: useful rules/lexicon baseline, but it is not evidence of a trained model. Replace or augment it with a model trained from the labeled dataset.
- `src/ai_pipeline/ocr_parser.py` and `src/ai_pipeline/qr_detector.py`: retain as candidate OCR and QR components; adapt their outputs to the shared event/evidence schema.
- `src/ai_pipeline/models/best.pt`: retained pending review of dataset provenance, label map, evaluation results, and license. Do not treat it as the project's validated model until those are documented. QR decoding does not require trained weights.
- `src/database/postgres_client.py` and `src/database/neo4j_client.py`: adapt for case/evidence records and the simulated entity graph, respectively; choose and document the local development configuration.
- `src/reporting/hasher.py` and `src/reporting/pdf_exporter.py`: retain for evidence integrity and report export, after adapting to the case schema.
- Existing unit tests: retain as a starting point, then rewrite around simulation events and validated model behavior. Test fixtures must remain separate from training data.

## Required new components

- Three chat simulation views and a dashboard with alert list, case report, evidence viewer, graph, and review controls.
- One local collector adapter per simulation, all producing the same validated event format.
- API routes for simulation events, alerts/cases, review decisions, and model/dataset status.
- A shared detection orchestrator that records text, OCR, QR, VPA, novelty, and model-version results.
- Case state transitions and an append-only human-review audit history.
- Dataset manifest, train/validation/test split tooling, metrics report, model registry, and a controlled promotion process.
- Database schema/migrations, configuration examples, and deployment setup for the web application.

## Out of scope

- Live platform crawlers/listeners, platform credentials, session files, and public invite/link scraping.
- Canary interactions, IP/device fingerprinting, real-person attribution, and external UPI owner resolution.
- Preloaded mock/fallback feeds or generated fallback evidence.
- Automatic production-model updates from one reviewer click.
