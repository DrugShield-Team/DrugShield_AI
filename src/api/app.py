"""Local FastAPI boundary for the fictional chat simulations.

Run with: uvicorn src.api.app:app --host 127.0.0.1 --port 8000
This development API binds to loopback by default and does not collect live
platform data.
"""

from __future__ import annotations

import hashlib
from functools import lru_cache
import json
import mimetypes
import uuid
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from src.ai_pipeline.message_analyzer import analyze_message
from src.ai_pipeline.risk_policy import evaluate_for_human_review
from config.settings import (
    CORS_ORIGINS as CONFIG_CORS_ORIGINS,
    DATABASE_PATH,
    MAX_ATTACHMENT_BYTES,
    MAX_ATTACHMENTS_PER_MESSAGE,
    PROJECT_ROOT,
    RUNTIME_DIR,
)
from src.database.case_store import CaseStore
from src.reporting.hasher import sha256_json

RUNTIME_ROOT = (PROJECT_ROOT / RUNTIME_DIR).resolve()
RAW_ROOT = RUNTIME_ROOT / "raw"
REPORTS_ROOT = RUNTIME_ROOT / "reports"
if not DATABASE_PATH.is_absolute():
    DATABASE_PATH = (PROJECT_ROOT / DATABASE_PATH).resolve()
MAX_ATTACHMENTS = MAX_ATTACHMENTS_PER_MESSAGE
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
store = CaseStore(DATABASE_PATH)


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
    reviewer_id: str = Field(min_length=1, max_length=160)
    action: Literal["accept", "further_review", "dismiss"]
    note: str = Field(default="", max_length=4000)


app = FastAPI(
    title="DrugShield Simulation Analysis API",
    version="0.1.0",
    description=(
        "Local analysis service for user-authored fictional chat simulations. "
        "Model output is evidence for human review, not a determination of wrongdoing."
    ),
)
allowed_origins = list(CONFIG_CORS_ORIGINS)
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


@app.get("/api/v1/health")
def health() -> Dict[str, str]:
    return {"status": "ok", "mode": "local_simulation_only"}


@app.get("/api/v1/models")
def model_status() -> Dict[str, Any]:
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
    event_dir = RAW_ROOT / event_id
    event_dir.mkdir(parents=True, exist_ok=True)
    attachment_records: List[Dict[str, Any]] = []
    image_paths: List[Path] = []
    for upload in uploaded_files:
        content_type = (upload.content_type or "").casefold()
        if content_type not in ALLOWED_IMAGE_TYPES:
            raise HTTPException(status_code=415, detail=f"Unsupported image type: {content_type or 'unknown'}")
        content = await upload.read(MAX_ATTACHMENT_BYTES + 1)
        if not content:
            raise HTTPException(status_code=422, detail="Empty image attachment")
        if len(content) > MAX_ATTACHMENT_BYTES:
            raise HTTPException(status_code=413, detail="Image attachment exceeds the configured size limit")
        try:
            from PIL import Image
            with Image.open(BytesIO(content)) as image:
                image.verify()
        except Exception as exc:
            raise HTTPException(status_code=415, detail="Attachment is not a readable image") from exc

        digest = hashlib.sha256(content).hexdigest()
        extension = mimetypes.guess_extension(content_type) or ".img"
        attachment_id = digest[:24]
        storage_path = event_dir / f"{digest}{extension}"
        storage_path.write_bytes(content)
        image_paths.append(storage_path)
        attachment_records.append({
            "attachment_id": attachment_id,
            "filename": Path(upload.filename or "attachment").name[:180],
            "content_type": content_type,
            "bytes": len(content),
            "sha256": digest,
            "storage_path": str(storage_path.resolve()),
        })

    event_dict = _model_to_dict(event)
    event_dict["attachments"] = attachment_records
    try:
        analysis = await run_in_threadpool(analyze_message, event.text, image_paths)
    except Exception as exc:
        # Preserve the raw event for diagnosis, but never invent a fallback result.
        analysis = {"status": "analysis_failed", "error": str(exc)}

    policy = evaluate_for_human_review(analysis) if analysis.get("status") != "analysis_failed" else {
        "review_required": True,
        "triage_status": "analysis_failed",
        "reasons": [{"signal": "analysis_failure_manual_review", "source": "analysis_pipeline"}],
        "thresholds": {},
        "policy_note": "Analysis failed; the message needs operator attention, not an inferred clean result.",
    }
    attachment_public = [
        {key: value for key, value in item.items() if key != "storage_path"}
        for item in attachment_records
    ]
    public_analysis = _hide_local_paths(analysis, attachment_records)
    public_policy = _hide_local_paths(policy, attachment_records)
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
    try:
        store.save_event(event_id, event.channel, event.conversation_id, event.message_id, event_dict, analysis)
        case_id = None
        report_path = None
        report_hash = None
        if policy["review_required"]:
            case_id = str(uuid.uuid4())
            report_path = REPORTS_ROOT / f"{case_id}.json"
            REPORTS_ROOT.mkdir(parents=True, exist_ok=True)
            report_hash = sha256_json(report)
            report["integrity"] = {"algorithm": "sha256", "digest": report_hash}
            report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            store.create_case(case_id, event_id, report, report_hash)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to persist simulation event: {exc}") from exc

    return {
        "event_id": event_id,
        "case_id": case_id,
        "review_required": bool(policy["review_required"]),
        "triage_status": policy["triage_status"],
        "analysis": public_analysis,
        "report_url": f"/api/v1/cases/{case_id}" if case_id else None,
        "report_sha256": report_hash,
    }


@app.get("/api/v1/cases")
def list_cases(status: Optional[str] = None, limit: int = 100) -> Dict[str, Any]:
    allowed = {"pending_review", "further_review", "accepted", "dismissed"}
    if status is not None and status not in allowed:
        raise HTTPException(status_code=422, detail="Unsupported case status")
    if not 1 <= limit <= 500:
        raise HTTPException(status_code=422, detail="limit must be between 1 and 500")
    cases = store.list_cases(status=status, limit=limit)
    return {"cases": cases, "count": len(cases)}


@app.get("/api/v1/cases/{case_id}")
def get_case(case_id: str) -> Dict[str, Any]:
    case = store.get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    return case


@app.get("/api/v1/graph")
def evidence_graph(status: Optional[str] = None, limit: int = 500) -> Dict[str, Any]:
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
def get_case_attachment(case_id: str, attachment_id: str) -> FileResponse:
    attachment = store.get_attachment(case_id, attachment_id)
    if not attachment:
        raise HTTPException(status_code=404, detail="Attachment not found for this case")
    path = Path(attachment["storage_path"]).resolve()
    if not path.is_relative_to(RAW_ROOT.resolve()) or not path.is_file():
        raise HTTPException(status_code=404, detail="Stored attachment is unavailable")
    return FileResponse(path, media_type=attachment["content_type"], filename=attachment["filename"])


@app.post("/api/v1/cases/{case_id}/review")
def review_case(case_id: str, request: ReviewRequest) -> Dict[str, Any]:
    try:
        case = store.add_review(case_id, request.reviewer_id, request.action, request.note)
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
    path_to_id = {
        str(Path(item["storage_path"]).resolve()).casefold(): item["attachment_id"]
        for item in attachments
    }
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
