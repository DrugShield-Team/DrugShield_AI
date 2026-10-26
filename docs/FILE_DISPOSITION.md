# Repository file disposition

This is a review plan for the current repository snapshot. It distinguishes files to keep, adapt, replace, and remove from the active project. The out-of-scope files under `src/` listed in the removal section were deleted on 2026-10-25; the remaining listed files are still present.

## Keep and adapt

| Current path | Disposition | Why |
|---|---|---|
| `config/settings.py` | Adapt | Keep local configuration; remove Telegram credentials/session settings. |
| `config/constants.py` | Prune | Keep only detection labels, VPA patterns, and calibrated risk settings. |
| `src/ai_pipeline/nlp_classifier.py` | Adapt | Reuse its lexicon logic as a baseline; it is not a trained model. |
| `src/ai_pipeline/ocr_parser.py` | Keep/adapt | Candidate image-text extraction component. |
| `src/ai_pipeline/qr_detector.py` | Keep/adapt | Decode QR payloads as evidence only; no QR risk score or trained QR model. |
| `src/ai_pipeline/train_yolo.py` | Removed | The legacy script downloaded a third-party dataset and embedded a Roboflow API key; image training will use the reviewed project dataset workflow. |
| `src/ai_pipeline/models/best.pt` | Hold pending provenance | Do not load as a validated project model until its training data, labels, license, and evaluation are documented. |
| `src/ai_pipeline/models/qr_detector.pt` | Removed | QR decoding will use a QR decoder library; no trained QR model is required for payload decoding. |
| `src/database/postgres_client.py`, `neo4j_client.py` | Keep/adapt | Candidate case storage and graph persistence. |
| `src/reporting/hasher.py`, `pdf_exporter.py` | Keep/adapt | Useful for evidence integrity and case report export. |
| `tests/test_nlp.py`, `test_ocr.py`, `test_graph.py`, `test_qr_pipeline.py` | Keep/rewrite | Keep test coverage, but remove dependencies on generated files and legacy processing entry points. Test examples must never enter model training. |
| `.gitignore` | Update | Ignore runtime evidence, local secrets, caches, and downloaded model/data artifacts. |
| `requirements.txt` | Prune | Remove unused live-ingestion and desktop-notification dependencies; add only dependencies required by the chosen web UI/API. |

## Replace with simulation-only components

| Current path | Disposition | Replacement |
|---|---|---|
| `main.py` | Replace | Web API application entry point. |
| `process_data.py` | Replace | Event-based detection orchestrator invoked by simulation collectors. |
| `src/ingestion/` live platform modules | Remove from active project | Local simulation collector adapters for all three channels. |
| Current `README.md` | Rewrite | State simulation-only scope, setup, data boundaries, and project status. |
| Current static JSON feeds | Remove | No preloaded feed; simulations submit user-authored events. |

## Remove from active project

The following files remain recommended for removal because they implement obsolete test assumptions or store static output/sample evidence outside the `src/` cleanup completed above:

- `tests/test_canary.py`, `tests/test_dynamic_qr.py`, `tests/test_pipeline.py` (obsolete canary, generated scenario, or prepopulated-output assumptions)
- Static feed/output files: `data.json`, `data/mock_demo_data.json`, `data/raw/ingested_raw_data.json`, `data/processed/processed_data.json`, `data/qr_deep_intel.json`
- Sample evidence assets: `data/raw/sample_hidden.jpg`, `data/raw/sample_image.jpg`, `data/raw/sample_menu.jpg`, `data/forensic_cache/test_fixtures/test_suspect_flyer_upi.jpg`

## Missing inputs and files

- No verified 10,000+ labeled training dataset is present in the repository.
- No dataset provenance/label manifest is present.
- No frontend, simulation pages, dashboard, case review workflow, or simulation API exists yet.
- No complete model evaluation or model-version promotion workflow exists yet.

Create `data/training/` only for authorized labeled datasets plus their manifest. Do not put generated simulation conversations, fallback records, or test fixtures there.
