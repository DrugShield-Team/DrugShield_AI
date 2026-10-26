# DrugShield AI

DrugShield AI is a **local, simulation-only decision-support prototype**. It analyzes messages and image attachments created in fictional Instagram-, Telegram-, and WhatsApp-style chats. It does not connect to live platform accounts or collect real-user conversations.

The backend now exposes a common event API for the three simulations. Each new event is stored, text and image/QR evidence is analyzed, and configured review triggers create an evidence case for a human reviewer. VPA-like strings and pill/capsule detections are candidates only; neither is verification or proof of illicit activity.

## Run the local API

Use Python 3.11 or later, then install the repository dependencies:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python main.py
```

The API binds to `127.0.0.1:8000`. Interactive endpoint documentation is at `http://127.0.0.1:8000/docs`. Runtime database, uploaded evidence, and report files are written under `data/runtime/` and are ignored by Git.

### Configure authentication and encryption

The API fails closed if its authentication secret, data-encryption key, or user
accounts are missing. It does not ship with a default account.

1. Copy .env.example to .env.
2. Generate secrets in PowerShell:

   python -c "import secrets; print(secrets.token_urlsafe(48))"

   python -c "import base64,secrets; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())"

   Use the first value for DRUGSHIELD_AUTH_SECRET and the second for
   DRUGSHIELD_DATA_ENCRYPTION_KEY. Keep both outside Git and store a protected
   copy of the encryption key separately from backups.
3. Create a password hash:

   python -m src.security.manage_users reviewer1 reviewer

   Copy the printed JSON object into DRUGSHIELD_USERS_JSON as a JSON array. In
   .env, use single quotes around this whole JSON value so Compose does not treat
   the password-hash dollar signs as variable references.
   Create separate simulator, reviewer, and admin accounts as needed. Never put
   a plain-text password in .env.
4. Run python main.py. Authenticate with username and password at
   /api/v1/auth/token. The API sets an HttpOnly cookie. Browser clients must send
   credentialed requests and must not store credentials or tokens in localStorage.

Roles: simulator can submit messages; reviewer can read cases and evidence and
record decisions; admin can do those actions plus read model status and metrics.
Set exact browser origins in DRUGSHIELD_CORS_ORIGINS.

### Run the hardened local container

After setting secrets and account JSON in .env, build and run with:

   docker compose up --build

The API is published only at 127.0.0.1:8000. Runtime state is stored in a Docker
named volume. The container uses an unprivileged account, a read-only root
filesystem, a temporary filesystem for analysis, and drops Linux capabilities.
This is still a local container profile, not a complete public deployment.

Retention preview:

   python scripts/retention_cleanup.py

Create a runtime backup:

   python scripts/backup_runtime.py

For the Docker named volume, run the tools inside the container instead:

   docker compose exec api python scripts/retention_cleanup.py
   docker compose exec api python scripts/backup_runtime.py

## Simulation event contract

`POST /api/v1/simulation-events` accepts `multipart/form-data`:

- `event_json`: JSON with `schema_version`, `channel`, `message_id`, `conversation_id`, `sender_id`, `sender_display_name`, `recipient_id`, `recipient_display_name`, optional ISO `timestamp`, and `text`.
- `files`: zero or more JPEG, PNG, or WebP image attachments (maximum five; each size is controlled by `MAX_ATTACHMENT_BYTES`).

Example `event_json`:

```json
{
  "schema_version": 1,
  "channel": "instagram",
  "message_id": "message-001",
  "conversation_id": "conversation-001",
  "sender_id": "participant-a",
  "sender_display_name": "Fictional sender",
  "recipient_id": "participant-b",
  "recipient_display_name": "Fictional recipient",
  "timestamp": "2026-10-26T12:00:00Z",
  "text": "Message text"
}
```

The response includes `event_id`, optional `case_id`, `review_required`, `analysis`, and a case URL. Duplicate `(channel, conversation_id, message_id)` submissions return HTTP 409. The `channel` must be `instagram`, `telegram`, or `whatsapp`.

## Analysis and case endpoints

- `GET /api/v1/health` ? local API health
- `GET /api/v1/models` ? model artifact and metrics status
- `POST /api/v1/simulation-events` ? ingest and analyze a newly sent simulation message
- `GET /api/v1/cases` ? dashboard case list; optional `status` and `limit`
- `GET /api/v1/graph` ? aggregated fictional participants, messages, attachments, and candidate VPA links
- `GET /api/v1/cases/{case_id}` ? evidence report, model fingerprints, graph, and review history
- `GET /api/v1/cases/{case_id}/attachments/{attachment_id}` ? retrieve an evidence image
- `POST /api/v1/cases/{case_id}/review` ? submit `accept`, `further_review`, or `dismiss`

Review decisions are recorded in an append-only history table. They do not trigger immediate or automatic model retraining.

## Current detector scope and limits

- **Text classifier:** predicts drug-related topic from CardiffNLP X-Sensitive labels. It does not predict dealing or suspicious intent. Its English test recall was low, and it has not been validated on Hinglish or these simulations.
- **Reviewed slang matcher:** spots terms from the reviewed CSV. A match is a review signal, not proof or a complete contextual interpretation.
- **Image models:** the supplied drug/lookalike dataset is very small and showed poor test specificity. The pill model detects capsule/tablet shape, not illicitness. These outputs are evidence candidates only.
- **QR decoder:** attempts to decode QR payloads. Decoded text is sent through text analysis; VPA candidates are extracted from message and QR text.
- **OCR:** intentionally not wired. The supplied image datasets lack paired text transcriptions; provide an OCR dataset before training or implementing the agreed OCR component.
- **Thresholds:** values in `.env.example` are provisional development settings, not calibrated suspiciousness probabilities. Triggered cases are sent for human review; untriggered messages are labeled `no_threshold_trigger`, not ?clean.?
- **Frontend/dashboard:** the friend?s frontend is not in this checkout yet. This API provides the event and case endpoints for it to connect; pull the frontend here before implementing component-specific integration.

## Hinglish and simulation evaluation

`data/evaluation/hinglish_simulation_messages.csv` is an empty reviewed-data template. Add real fictional messages with reviewed `drug_related_label` values (0/1), keeping related messages/conversations out of any training split. Then run:

```powershell
python ml/evaluate_nlp_classifier.py
```

The evaluator reports overall and channel/language metrics; it will refuse to score an empty or single-class file. It does not invent data or modify the model.

## Train the supplied image baseline

With the original dataset ZIPs available locally:

```powershell
python ml/train_image_classifier.py --drug-zip "PATH_TO_DRUG_DETECTION.zip" --pill-zip "PATH_TO_PILLS.zip"
```

The outputs are `models/registry/image_analysis.joblib` and `image_analysis.metrics.json`. Keep the drug-class and pill-shape tasks separate. Inspect held-out metrics before using either result as an alert trigger.

## Safety and deployment boundary

The API requires configured authentication and encrypts event payloads, analysis
output, reports, review notes, and uploaded images at rest. Case and evidence
access is role-restricted, review identity comes from the authenticated account,
and request logs omit message contents.

It provides readiness checks, basic process-local metrics, request IDs, security
headers, explicit origin/host checks, retention and backup utilities, and a
hardened Docker configuration. See docs/SECURITY_OPERATIONS.md for operational
details and limitations.

This remains a local simulation decision-support prototype, not a production
investigation system. The Instagram-, Telegram-, and WhatsApp-style frontends are
present in the repository, but their current Node service endpoints have not yet
been integrated with this FastAPI authentication and evidence-storage boundary.
Do not expose those Node services beyond the local machine until they are secured
and connected to this API. Browser login integration still needs to be completed.
Model thresholds also need validation. Docker Compose binds to loopback and is
not an internet deployment. Public deployment still needs a TLS reverse proxy,
managed secrets, off-host backups, durable monitoring and alerting, tested
restoration, and a security/privacy review. Human review is required for every
evidence case.
