"""Local FastAPI boundary for the fictional chat simulations.

Run with: uvicorn src.api.app:app --host 127.0.0.1 --port 8000
This development API binds to loopback by default and does not collect live
platform data.
"""

from __future__ import annotations

import hashlib
from functools import lru_cache
import json
import logging
import mimetypes
import os
import shutil
import sqlite3
import tempfile
import time
import uuid
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool
from starlette.middleware.trustedhost import TrustedHostMiddleware

from src.ai_pipeline.message_analyzer import analyze_message
from src.ai_pipeline.risk_policy import evaluate_for_human_review
from config.settings import (
    CORS_ORIGINS as CONFIG_CORS_ORIGINS,
    DATABASE_PATH,
    MAX_ATTACHMENT_BYTES,
    MAX_ATTACHMENTS_PER_MESSAGE,
    MAX_TOTAL_ATTACHMENT_BYTES,
    PROJECT_ROOT,
    RUNTIME_DIR,
    APP_ENV,
    ALLOWED_HOSTS,
    DATA_ENCRYPTION_KEY,
    SESSION_COOKIE_NAME,
    SESSION_TTL_SECONDS,
    MAX_REQUEST_BYTES,
)
from src.database.case_store import CaseStore
from src.reporting.hasher import sha256_json
from src.security.auth import Principal, check_login, get_current_user, issue_token, require_roles, validate_configuration, optional_simulation_user
from src.security.crypto import DataCipher
from src.cases.state_machine import (
    state_machine,
    STATE_ACTIVE_HONEYPOT_READY,
    STATE_HONEYPOT_ENGAGED,
    STATE_INVOICE_SENT,
    STATE_TARGET_GEO_LOCATED,
    STATE_DISPATCH_INITIATED,
)
from src.ingestion.smart_honeypot_bot import buyer_bot

logger = logging.getLogger(__name__)

RUNTIME_ROOT = (PROJECT_ROOT / RUNTIME_DIR).resolve()
RAW_ROOT = RUNTIME_ROOT / "raw"
REPORTS_ROOT = RUNTIME_ROOT / "reports"
if not DATABASE_PATH.is_absolute():
    DATABASE_PATH = (PROJECT_ROOT / DATABASE_PATH).resolve()
MAX_ATTACHMENTS = MAX_ATTACHMENTS_PER_MESSAGE
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
validate_configuration()
data_cipher = DataCipher.from_environment(DATA_ENCRYPTION_KEY)
store = CaseStore(DATABASE_PATH, cipher=data_cipher)
METRICS = {"requests": 0, "errors": 0, "client_errors": 0,
           "analysis_failures": 0, "analysis_seconds_total": 0.0}
for directory in (RAW_ROOT, REPORTS_ROOT, RUNTIME_ROOT / "tmp"):
    directory.mkdir(parents=True, exist_ok=True)
store.migrate_attachments(RAW_ROOT)


class SimulationEvent(BaseModel):
    schema_version: Literal[1] = 1
    channel: Literal["instagram", "telegram", "whatsapp"]
    message_id: str = Field(min_length=1, max_length=160)
    conversation_id: str = Field(min_length=1, max_length=160)
    sender_id: str = Field(min_length=1, max_length=160)
    sender_display_name: str = Field(min_length=1, max_length=120)
    recipient_id: str = Field(min_length=1, max_length=160)
    recipient_display_name: str = Field(min_length=1, max_length=120)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    text: str = Field(default="", max_length=20000)


class ReviewRequest(BaseModel):
    action: Literal["accept", "further_review", "dismiss"]
    note: str = Field(default="", max_length=4000)


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=1, max_length=256)


app = FastAPI(
    title="DrugShield Simulation Analysis API",
    version="0.1.0",
    docs_url="/docs" if APP_ENV != "production" else None,
    redoc_url=None,
    description=(
        "Local analysis service for user-authored fictional chat simulations. "
        "Model output is evidence for human review, not a determination of wrongdoing."
    ),
)
allowed_origins = list(CONFIG_CORS_ORIGINS)
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Authorization"],
)
if APP_ENV == "production":
    from starlette.middleware.httpsredirect import HTTPSRedirectMiddleware
    app.add_middleware(HTTPSRedirectMiddleware)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=list(ALLOWED_HOSTS))

from src.api.routes_honeypot import router as honeypot_router
app.include_router(honeypot_router)


@app.middleware("http")
async def security_and_request_middleware(request: Request, call_next):
    origin = request.headers.get("origin")
    if request.method in {"POST", "PUT", "PATCH", "DELETE"} and origin and origin not in allowed_origins:
        return JSONResponse(status_code=403, content={"detail": "Origin is not allowed"})
    try:
        content_length = int(request.headers.get("content-length", "0"))
    except ValueError:
        return JSONResponse(status_code=400, content={"detail": "Invalid Content-Length"})
    if content_length > MAX_REQUEST_BYTES:
        return JSONResponse(status_code=413, content={"detail": "Request exceeds configured size limit"})
    started = time.perf_counter()
    response = await call_next(request)
    duration_ms = round((time.perf_counter() - started) * 1000, 2)
    METRICS["requests"] += 1
    if response.status_code >= 500:
        METRICS["errors"] += 1
    elif response.status_code >= 400:
        METRICS["client_errors"] += 1
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Cache-Control"] = "no-store"
    response.headers["Content-Security-Policy"] = "default-src 'self' 'unsafe-inline' 'unsafe-eval' data: blob: ws: http:; frame-ancestors 'none'"
    if APP_ENV == "production":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    request_id = str(uuid.uuid4())
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Request-Duration-Ms"] = str(duration_ms)
    logger.info("request_id=%s method=%s path=%s status=%s duration_ms=%s",
                request_id, request.method, request.url.path, response.status_code, duration_ms)
    return response


@app.get("/api/v1/health")
def health() -> Dict[str, str]:
    return {"status": "ok", "mode": "local_simulation_only"}


@app.get("/api/v1/ready")
def readiness() -> Dict[str, str]:
    store.ping()
    return {"status": "ready", "database": "ok", "encryption": "configured"}


@app.post("/api/v1/auth/token")
def login(payload: LoginRequest, request: Request, response: Response) -> Dict[str, Any]:
    remote = request.client.host if request.client else "unknown"
    principal = check_login(payload.username, payload.password, remote)
    token = issue_token(principal)
    response.set_cookie(
        SESSION_COOKIE_NAME, token, max_age=SESSION_TTL_SECONDS, httponly=True,
        secure=APP_ENV == "production", samesite="strict", path="/",
    )
    return {"authenticated": True, "expires_in": SESSION_TTL_SECONDS,
            "user": {"username": principal.username, "roles": sorted(principal.roles)}}


@app.post("/api/v1/auth/logout")
def logout(response: Response) -> Dict[str, str]:
    response.delete_cookie(SESSION_COOKIE_NAME, path="/", httponly=True,
                           secure=APP_ENV == "production", samesite="strict")
    return {"status": "logged_out"}


@app.get("/api/v1/auth/me")
def who_am_i(principal: Principal = Depends(get_current_user)) -> Dict[str, Any]:
    return {"username": principal.username, "roles": sorted(principal.roles)}


@app.get("/api/v1/metrics")
def metrics(_: Principal = Depends(require_roles("admin"))) -> Dict[str, Any]:
    return {**METRICS, "database": "ok" if store.ping() else "unavailable"}


@app.get("/api/v1/models")
def model_status(_: Principal = Depends(require_roles("admin"))) -> Dict[str, Any]:
    model_files = {
        "nlp_drug_topic": PROJECT_ROOT / "models" / "registry" / "nlp_drug_topic.joblib",
        "image_analysis": PROJECT_ROOT / "models" / "registry" / "image_analysis.joblib",
    }
    metrics_files = {
        "nlp_drug_topic": PROJECT_ROOT / "models" / "registry" / "nlp_drug_topic.metrics.json",
        "image_analysis": PROJECT_ROOT / "models" / "registry" / "image_analysis.metrics.json",
    }
    models: Dict[str, Any] = {}
    for name, path in model_files.items():
        metrics_path = metrics_files[name]
        metrics = None
        if metrics_path.is_file():
            try:
                metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                metrics = {"status": "metrics_unreadable"}
        models[name] = {
            "status": "available" if path.is_file() else "not_trained",
            "artifact_bytes": path.stat().st_size if path.is_file() else None,
            "metrics": metrics,
        }
    return {"models": models, "decision_scope": "human_review_evidence_only"}


@app.post("/api/v1/simulation-events")
async def receive_simulation_event(
    event_json: str = Form(...),
    files: Optional[List[UploadFile]] = File(default=None),
    _: Principal = Depends(optional_simulation_user),
) -> Dict[str, Any]:
    """Persist and analyze one newly-authored simulation message and images."""
    try:
        payload = json.loads(event_json)
        if hasattr(SimulationEvent, "model_validate"):
            event = SimulationEvent.model_validate(payload)
        else:  # Pydantic v1 compatibility
            event = SimulationEvent.parse_obj(payload)
    except (json.JSONDecodeError, ValueError, TypeError) as exc:
        raise HTTPException(status_code=422, detail=f"Invalid event JSON: {exc}") from exc

    existing_event = store.event_exists(event.channel, event.conversation_id, event.message_id)
    if existing_event:
        raise HTTPException(
            status_code=409,
            detail={"error": "duplicate_message", "event_id": existing_event},
        )

    uploaded_files = files or []
    if len(uploaded_files) > MAX_ATTACHMENTS:
        raise HTTPException(status_code=413, detail=f"At most {MAX_ATTACHMENTS} images are allowed per message")
    if not event.text.strip() and not uploaded_files:
        raise HTTPException(status_code=422, detail="A message must include text or at least one image")

    event_id = str(uuid.uuid4())
    validated_uploads = []
    total_upload_bytes = 0
    expected_formats = {
        "image/jpeg": "JPEG",
        "image/png": "PNG",
        "image/webp": "WEBP",
    }
    for upload in uploaded_files:
        content_type = (upload.content_type or "").casefold()
        if content_type not in ALLOWED_IMAGE_TYPES:
            raise HTTPException(status_code=415, detail="Unsupported image type")
        content = await upload.read(MAX_ATTACHMENT_BYTES + 1)
        if not content:
            raise HTTPException(status_code=422, detail="Empty image attachment")
        if len(content) > MAX_ATTACHMENT_BYTES:
            raise HTTPException(status_code=413, detail="Image attachment exceeds the configured size limit")
        total_upload_bytes += len(content)
        if total_upload_bytes > MAX_TOTAL_ATTACHMENT_BYTES:
            raise HTTPException(status_code=413, detail="Combined attachments exceed the configured size limit")
        try:
            from PIL import Image
            with Image.open(BytesIO(content)) as image:
                if image.format != expected_formats[content_type]:
                    raise ValueError("Image bytes do not match the declared media type")
                if image.width * image.height > 25_000_000:
                    raise ValueError("Image dimensions exceed the allowed pixel count")
                image.verify()
        except Exception as exc:
            raise HTTPException(status_code=415, detail="Attachment is not a supported, safe image") from exc
        validated_uploads.append((upload, content, content_type))

    event_dir = RAW_ROOT / event_id
    event_dir.mkdir(parents=True, exist_ok=False)
    attachment_records: List[Dict[str, Any]] = []
    image_paths: List[Path] = []
    temp_dir = Path(tempfile.mkdtemp(prefix="drugshield-analysis-"))
    try:
        for index, (upload, content, content_type) in enumerate(validated_uploads):
            digest = hashlib.sha256(content).hexdigest()
            extension = mimetypes.guess_extension(content_type) or ".img"
            attachment_id = digest[:24]
            storage_path = event_dir / f"{digest}{extension}.enc"
            storage_path.write_bytes(data_cipher.encrypt_bytes(content, "attachment"))
            temporary_image = temp_dir / f"{index}{extension}"
            temporary_image.write_bytes(content)
            image_paths.append(temporary_image)
            attachment_records.append({
                "attachment_id": attachment_id,
                "filename": Path(upload.filename or "attachment").name[:180],
                "content_type": content_type,
                "bytes": len(content),
                "sha256": digest,
                "storage_path": str(storage_path.resolve()),
                "analysis_path": str(temporary_image.resolve()),
            })

        event_dict = _model_to_dict(event)
        event_dict["attachments"] = attachment_records
        try:
            analysis_started = time.perf_counter()
            analysis = await run_in_threadpool(analyze_message, event.text, image_paths)
            METRICS["analysis_seconds_total"] += time.perf_counter() - analysis_started
        except Exception:
            logger.exception("Analysis failed for simulation event %s", event_id)
            METRICS["analysis_failures"] += 1
            analysis = {"status": "analysis_failed", "error_code": "analysis_failed"}
    finally:
        import shutil
        shutil.rmtree(temp_dir, ignore_errors=True)

    policy = evaluate_for_human_review(analysis) if analysis.get("status") != "analysis_failed" else {
        "review_required": True,
        "triage_status": "analysis_failed",
        "reasons": [{"signal": "analysis_failure_manual_review", "source": "analysis_pipeline"}],
        "thresholds": {},
        "policy_note": "Analysis failed; the message needs operator attention, not an inferred clean result.",
    }
    attachment_public = [
        {key: value for key, value in item.items() if key not in {"storage_path", "analysis_path"}}
        for item in attachment_records
    ]
    public_analysis = _hide_local_paths(analysis, attachment_records)
    public_policy = _hide_local_paths(policy, attachment_records)
    for item in attachment_records:
        item.pop("analysis_path", None)
    graph = _build_evidence_graph(event, attachment_public, public_analysis)
    report: Dict[str, Any] = {
        "schema_version": 1,
        "event_id": event_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "pending_review" if policy["review_required"] else policy["triage_status"],
        "decision_scope": "evidence_for_human_review_only",
        "summary": {
            "channel": event.channel,
            "conversation_id": event.conversation_id,
            "message_id": event.message_id,
            "timestamp": event.timestamp.isoformat(),
            "sender_id": event.sender_id,
            "sender_display_name": event.sender_display_name,
            "recipient_id": event.recipient_id,
            "recipient_display_name": event.recipient_display_name,
            "message_text": event.text,
            "review_required": bool(policy["review_required"]),
            "reason_count": len(policy["reasons"]),
        },
        "attachments": attachment_public,
        "analysis": public_analysis,
        "review_policy": public_policy,
        "graph": graph,
        "model_versions": _model_versions(),
    }
    case_id = str(uuid.uuid4()) if policy["review_required"] else None
    report_hash = sha256_json(report) if case_id else None
    if report_hash:
        report["integrity"] = {"algorithm": "sha256", "digest": report_hash}
    try:
        store.save_event_and_case(
            event_id=event_id,
            channel=event.channel,
            conversation_id=event.conversation_id,
            message_id=event.message_id,
            event=event_dict,
            analysis=analysis,
            case_id=case_id,
            report=report if case_id else None,
            report_sha256=report_hash,
        )
    except sqlite3.IntegrityError as exc:
        shutil.rmtree(event_dir, ignore_errors=True)
        if store.event_exists(event.channel, event.conversation_id, event.message_id):
            raise HTTPException(status_code=409, detail={"error": "duplicate_message"}) from exc
        logger.exception("Persistence integrity failure for simulation event %s", event_id)
        raise HTTPException(status_code=500, detail="Failed to persist simulation event") from exc
    except Exception as exc:
        shutil.rmtree(event_dir, ignore_errors=True)
        logger.exception("Persistence failed for simulation event %s", event_id)
        raise HTTPException(status_code=500, detail="Failed to persist simulation event") from exc

    # State machine threat accumulation and smart bot engagement
    # Strictly accumulate threat flags when the message is INCOMING from the target/seller
    # (i.e. not outgoing from the analyst/investigator)
    is_analyst_sender = str(event.sender_id).lower().startswith("analyst:")
    target_entity_id = event.conversation_id if not is_analyst_sender else str(event.recipient_id)

    smart_bot_data = None
    state_res = None

    if not is_analyst_sender:
        threat_record = {
            "id": event_id,
            "sender_id": target_entity_id,
            "chat_id": event.conversation_id,
            "threat_score": float(analysis.get("text_analysis", {}).get("risk_score") or (0.4 if policy.get("review_required") else 0.0)),
            "flagged_status": bool(policy.get("review_required")),
            "extracted_entities": {
                "narcotics_detected": analysis.get("text_analysis", {}).get("detected_slangs", []),
            },
            "nlp_analysis": {"solicitation_intent": bool(policy.get("review_required"))}
        }
        state_res = state_machine.evaluate_threat_event(threat_record)
        current_state = state_res.get("current_state")
        sim_url = "http://127.0.0.1:8090/api/send" if event.channel == "whatsapp" else "http://127.0.0.1:8001/api/send"

        if current_state == STATE_ACTIVE_HONEYPOT_READY:
            smart_bot_data = buyer_bot.engage_target(
                entity_id=target_entity_id,
                chat_id=event.conversation_id,
                platform=event.channel,
                simulation_post_url=sim_url
            )
        elif current_state in (STATE_HONEYPOT_ENGAGED, STATE_INVOICE_SENT, STATE_TARGET_GEO_LOCATED, STATE_DISPATCH_INITIATED):
            # Dynamic two-way conversational loop: target replies during active honeypot
            smart_bot_data = buyer_bot.handle_target_reply(
                entity_id=target_entity_id,
                chat_id=event.conversation_id,
                message_text=event.text,
                platform=event.channel,
                simulation_post_url=sim_url
            )
    else:
        # Analyst outgoing message - do not accumulate threat against analyst
        state_res = state_machine.get_entity_state(target_entity_id)

    honeypot_link = smart_bot_data.get("invoice_url") if smart_bot_data else None
    bot_response = smart_bot_data.get("dispatched_message") if smart_bot_data else None

    return {
        "event_id": event_id,
        "case_id": case_id,
        "review_required": bool(policy["review_required"]),
        "triage_status": policy["triage_status"],
        "analysis": public_analysis,
        "report_url": f"/api/v1/cases/{case_id}" if case_id else None,
        "report_sha256": report_hash,
        "state_machine": state_res,
        "smart_bot": smart_bot_data,
        "bot_response": bot_response,
        "honeypot_link": honeypot_link,
    }


@app.get("/api/v1/cases")
def list_cases(status: Optional[str] = None, limit: int = 100,
               _: Principal = Depends(require_roles("reviewer", "admin"))) -> Dict[str, Any]:
    allowed = {"pending_review", "further_review", "accepted", "dismissed"}
    if status is not None and status not in allowed:
        raise HTTPException(status_code=422, detail="Unsupported case status")
    if not 1 <= limit <= 500:
        raise HTTPException(status_code=422, detail="limit must be between 1 and 500")
    cases = store.list_cases(status=status, limit=limit)
    return {"cases": cases, "count": len(cases)}


@app.get("/api/v1/cases/{case_id}")
def get_case(case_id: str, _: Principal = Depends(require_roles("reviewer", "admin"))) -> Dict[str, Any]:
    case = store.get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    return case


@app.get("/api/v1/graph")
def evidence_graph(status: Optional[str] = None, limit: int = 500,
                   _: Principal = Depends(require_roles("reviewer", "admin"))) -> Dict[str, Any]:
    """Aggregate the fictional participants and candidate links in evidence cases."""
    allowed = {"pending_review", "further_review", "accepted", "dismissed"}
    if status is not None and status not in allowed:
        raise HTTPException(status_code=422, detail="Unsupported case status")
    if not 1 <= limit <= 500:
        raise HTTPException(status_code=422, detail="limit must be between 1 and 500")
    cases = store.list_cases(status=status, limit=limit)
    nodes: Dict[str, Dict[str, Any]] = {}
    edges: Dict[tuple, Dict[str, Any]] = {}
    for item in cases:
        case = store.get_case(item["case_id"])
        if not case:
            continue
        graph = case["report"].get("graph", {})
        for node in graph.get("nodes", []):
            nodes.setdefault(node["id"], node)
        for edge in graph.get("edges", []):
            key = (edge.get("source"), edge.get("target"), edge.get("type"))
            edges.setdefault(key, edge)
    return {"nodes": list(nodes.values()), "edges": list(edges.values()), "case_count": len(cases)}


@app.get("/api/v1/cases/{case_id}/attachments/{attachment_id}")
def get_case_attachment(case_id: str, attachment_id: str,
                        _: Principal = Depends(require_roles("reviewer", "admin"))) -> Response:
    attachment = store.get_attachment(case_id, attachment_id)
    if not attachment:
        raise HTTPException(status_code=404, detail="Attachment not found for this case")
    path = Path(attachment["storage_path"]).resolve()
    if not path.is_relative_to(RAW_ROOT.resolve()) or not path.is_file():
        raise HTTPException(status_code=404, detail="Stored attachment is unavailable")
    try:
        content = data_cipher.decrypt_bytes(path.read_bytes(), "attachment")
    except Exception as exc:
        logger.exception("Evidence decryption failed for case %s", case_id)
        raise HTTPException(status_code=500, detail="Evidence is unavailable") from exc
    from urllib.parse import quote
    return Response(content, media_type=attachment["content_type"], headers={
        "Content-Disposition": "attachment; filename*=UTF-8''" + quote(attachment["filename"]),
        "Cache-Control": "no-store",
        "X-Content-Type-Options": "nosniff",
    })


@app.post("/api/v1/cases/{case_id}/review")
def review_case(case_id: str, request: ReviewRequest,
                principal: Principal = Depends(require_roles("reviewer", "admin"))) -> Dict[str, Any]:
    try:
        case = store.add_review(case_id, principal.username, request.action, request.note)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    return case


def _model_to_dict(model: BaseModel) -> Dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump(mode="json")
    return json.loads(model.json())


def _hide_local_paths(value: Any, attachments: List[Dict[str, Any]]) -> Any:
    path_to_id = {}
    for item in attachments:
        for path_key in ("storage_path", "analysis_path"):
            if item.get(path_key):
                path_to_id[str(Path(item[path_key]).resolve()).casefold()] = item["attachment_id"]
    if isinstance(value, list):
        return [_hide_local_paths(item, attachments) for item in value]
    if not isinstance(value, dict):
        return value
    safe: Dict[str, Any] = {}
    for key, item in value.items():
        if key in {"image_path", "source_image"} and isinstance(item, str):
            attachment_id = path_to_id.get(str(Path(item).resolve()).casefold())
            if attachment_id:
                safe["attachment_id"] = attachment_id
            continue
        if key == "source" and isinstance(item, str):
            attachment_id = path_to_id.get(str(Path(item).resolve()).casefold())
            if attachment_id:
                safe["attachment_id"] = attachment_id
                continue
        safe[key] = _hide_local_paths(item, attachments)
    return safe


def _build_evidence_graph(
    event: SimulationEvent, attachments: List[Dict[str, Any]], analysis: Dict[str, Any]
) -> Dict[str, Any]:
    """Create a small explicit graph of simulation evidence, not identity claims."""
    nodes = [
        {"id": event.sender_id, "type": "fictional_participant", "label": event.sender_display_name},
        {"id": event.recipient_id, "type": "fictional_participant", "label": event.recipient_display_name},
        {"id": event.message_id, "type": "message", "label": "Simulation message"},
    ]
    edges = [
        {"source": event.sender_id, "target": event.message_id, "type": "sent"},
        {"source": event.message_id, "target": event.recipient_id, "type": "addressed_to"},
    ]
    for attachment in attachments:
        nodes.append({
            "id": attachment["attachment_id"],
            "type": "attachment",
            "label": attachment["filename"],
        })
        edges.append({"source": event.message_id, "target": attachment["attachment_id"], "type": "includes"})
    for candidate in analysis.get("vpa_candidates", []):
        identifier = str(candidate.get("candidate", ""))
        if not identifier:
            continue
        candidate_id = "vpa:" + hashlib.sha256(identifier.casefold().encode("utf-8")).hexdigest()[:20]
        nodes.append({"id": candidate_id, "type": "candidate_vpa", "label": identifier})
        edges.append({
            "source": event.message_id,
            "target": candidate_id,
            "type": "contains_candidate_identifier",
            "verified": False,
        })
    return {"nodes": nodes, "edges": edges}


@lru_cache(maxsize=1)
def _model_versions() -> Dict[str, Any]:
    """Snapshot artifact fingerprints once per API process for case provenance."""
    registry = PROJECT_ROOT / "models" / "registry"
    result: Dict[str, Any] = {}
    for name in ("nlp_drug_topic", "image_analysis"):
        path = registry / f"{name}.joblib"
        metrics_path = registry / f"{name}.metrics.json"
        metrics = None
        if metrics_path.is_file():
            try:
                metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                metrics = {"status": "metrics_unreadable"}
        digest = None
        if path.is_file():
            hasher = hashlib.sha256()
            with path.open("rb") as handle:
                for block in iter(lambda: handle.read(1024 * 1024), b""):
                    hasher.update(block)
            digest = hasher.hexdigest()
        result[name] = {
            "available": path.is_file(),
            "sha256": digest,
            "metrics_summary": {
                key: metrics.get(key)
                for key in ("task", "source_dataset", "trained_at_utc", "limitations")
            } if isinstance(metrics, dict) else None,
        }
    return result


# ---------------------------------------------------------
# Static File & Dashboard Serving
# ---------------------------------------------------------
FRONTEND_DIR = (PROJECT_ROOT / "frontend").resolve()

@app.get("/", response_class=FileResponse)
def index_page():
    cmd_center = FRONTEND_DIR / "command_center.html"
    if cmd_center.is_file():
        return FileResponse(cmd_center)
    dash = FRONTEND_DIR / "dashboard.html"
    if dash.is_file():
        return FileResponse(dash)
    raise HTTPException(status_code=404, detail="Dashboard not found")

@app.get("/dashboard.html", response_class=FileResponse)
@app.get("/command_center.html", response_class=FileResponse)
def command_center_page():
    cmd_center = FRONTEND_DIR / "command_center.html"
    if cmd_center.is_file():
        return FileResponse(cmd_center)
    dash = FRONTEND_DIR / "dashboard.html"
    if dash.is_file():
        return FileResponse(dash)
    raise HTTPException(status_code=404, detail="Command Center not found")

from fastapi.staticfiles import StaticFiles
if FRONTEND_DIR.is_dir():
    app.mount("/frontend", StaticFiles(directory=str(FRONTEND_DIR)), name="frontend")
