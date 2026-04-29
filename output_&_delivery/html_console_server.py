from __future__ import annotations

import argparse
import asyncio
import copy
import cgi
import importlib
import json
import logging
import mimetypes
import re
import threading
import time
import traceback
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable, Mapping
from urllib.parse import parse_qs, urlparse

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
HTML_TEMPLATE_DIR = Path(__file__).resolve().parent / "html_templates"
TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"
DATA_WORKSPACE_DIR = PROJECT_ROOT / "data_workspace"
UI_JOB_ROOT = DATA_WORKSPACE_DIR / "ui_jobs"

import sys

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.logger_setup import get_log_session, get_logger, log_step, setup_logger, to_relative_path
from core_agent.orchestrator import Orchestrator
from main import LLM_MODEL_PRESETS, LLM_PROVIDER_ALIASES, LLM_PROVIDER_PRESETS, build_client, load_settings, save_cache

import email_gateway
import report_renderer


SUPPORTED_UPLOAD_SUFFIXES = {
    ".txt",
    ".docx",
    ".pdf",
    ".png",
    ".jpg",
    ".jpeg",
    ".bmp",
    ".tif",
    ".tiff",
    ".webp",
}
OCR_CANDIDATE_SUFFIXES = {
    ".pdf",
    ".png",
    ".jpg",
    ".jpeg",
    ".bmp",
    ".tif",
    ".tiff",
    ".webp",
}

PIPELINE_STEPS = [
    "正在识别与清洗文档排版...",
    "阅读智能体正在提取核心指令...",
    "审核智能体正在进行交叉验证...",
    "等待人工确认并执行下发...",
]
TERMINAL_JOB_STATUSES = {"success", "failed", "pending_approval"}
SSE_PUSH_INTERVAL_SECONDS = 1.0
SSE_STREAM_PUSH_INTERVAL_SECONDS = 0.12
STREAM_EVENT_HISTORY_LIMIT = 2400
STREAM_TOKEN_HEARTBEAT_STEP = 80
STREAM_TOKEN_BATCH_CHARS = 260
STREAM_STRUCTURAL_NOISE_RE = re.compile(r'^[\s{}\[\]":,]+$')
DEFAULT_UI_PORT = 1708

SUPPORTED_LLM_PROVIDERS = set(LLM_PROVIDER_PRESETS.keys())
UI_LLM_PROVIDERS = {"deepseek", "tongyi", "wenxin", "doubao", "kimi", "zhipu"}
SUPPORTED_EMAIL_FILE_TYPES = {"md", "html", "docx", "ics"}
DEFAULT_EMAIL_FILE_TYPES = ["md", "html", "docx", "ics"]
SUPPORTED_REPORT_LAYOUT = {"separate", "bundle"}
DEFAULT_REPORT_LAYOUTS = {
    "md": "separate",
    "html": "separate",
    "docx": "bundle",
}
EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")

JOBS: dict[str, "JobState"] = {}
JOBS_LOCK = threading.Lock()
RUN_LOCK = threading.Lock()
LOGGER = get_logger("html_console")
RAG_WARMUP_LOCK = threading.Lock()
RAG_WARMUP_STATUS = "idle"
RAG_WARMUP_DETAIL = ""


def _set_rag_warmup_state(status: str, detail: str = "") -> None:
    global RAG_WARMUP_STATUS, RAG_WARMUP_DETAIL  # noqa: PLW0603
    with RAG_WARMUP_LOCK:
        RAG_WARMUP_STATUS = str(status or "idle")
        RAG_WARMUP_DETAIL = str(detail or "")


def _get_rag_warmup_state() -> tuple[str, str]:
    with RAG_WARMUP_LOCK:
        return RAG_WARMUP_STATUS, RAG_WARMUP_DETAIL


def _start_rag_warmup_thread() -> None:
    status, _ = _get_rag_warmup_state()
    if status in {"running", "done", "skipped"}:
        return

    _set_rag_warmup_state("running", "warming")

    def _worker() -> None:
        try:
            settings_path = PROJECT_ROOT / "config" / "settings.yaml"
            settings = load_settings(settings_path)
            rag_cfg = settings.get("rag", {}) if isinstance(settings.get("rag"), Mapping) else {}
            if not bool(rag_cfg.get("enabled", True)):
                _set_rag_warmup_state("skipped", "rag_disabled")
                return

            paths_cfg = settings.get("paths", {}) if isinstance(settings.get("paths"), Mapping) else {}
            rag_db_dir = PROJECT_ROOT / str(paths_cfg.get("rag_db_dir", "data_workspace/rag_db"))

            tools_dir = PROJECT_ROOT / "tools_&_rag"
            if str(tools_dir) not in sys.path:
                sys.path.insert(0, str(tools_dir))

            rag_module = importlib.import_module("rag_retriever")
            RAGRetriever = getattr(rag_module, "RAGRetriever")

            retriever = RAGRetriever(
                db_dir=rag_db_dir,
                top_k=int(rag_cfg.get("top_k", 3)),
                enabled=True,
                rag_settings=rag_cfg,
            )
            prewarm_ok = retriever.prewarm_reranker() if hasattr(retriever, "prewarm_reranker") else False
            _set_rag_warmup_state("done", "reranker_ready" if prewarm_ok else "vector_ready")
            log_step(
                LOGGER,
                "startup",
                "UIConsole",
                "RAGWarmupDone",
                (
                    f"vector_ready={retriever.ready} rerank_enabled={getattr(retriever, 'rerank_enabled', False)} "
                    f"reranker_prewarmed={prewarm_ok}"
                ),
            )
        except Exception as exc:  # pylint: disable=broad-except
            _set_rag_warmup_state("failed", str(exc))
            LOGGER.warning(
                "STEP=startup | AGENT=UIConsole | ACTION=RAGWarmupFailed | DETAILS=error=%s",
                exc,
            )

    threading.Thread(target=_worker, name="docs_agent_rag_warmup", daemon=True).start()


@dataclass
class JobState:
    job_id: str
    mode: str
    llm_provider: str
    llm_model: str
    email_file_types: list[str]
    report_layouts: dict[str, str]
    api_key: str
    recipient_emails: list[str]
    created_at: str
    status: str = "queued"
    progress: int = 0
    step_index: int = 0
    step_text: str = "等待任务开始..."
    file_id: str = ""
    file_name: str = ""
    file_percent: int = 0
    step_detail: str = ""
    message: str = ""
    error: str = ""
    error_code: str = ""
    log_file: str = ""
    artifacts: dict[str, str] = field(default_factory=dict)
    reports: list[dict[str, Any]] = field(default_factory=list)
    drafts: list[dict[str, Any]] = field(default_factory=list)
    draft_cache_map: dict[str, str] = field(default_factory=dict)
    draft_source_map: dict[str, str] = field(default_factory=dict)
    bundle_reports: dict[str, str] = field(default_factory=dict)
    approval_locked: bool = False
    email_result: dict[str, Any] | None = None
    stream_seq: int = 0
    stream_events: list[dict[str, Any]] = field(default_factory=list)


class JobProgressLogHandler(logging.Handler):
    def __init__(self, job_id: str) -> None:
        super().__init__(level=logging.INFO)
        self.job_id = job_id

    def emit(self, record: logging.LogRecord) -> None:
        message = record.getMessage()
        if "ACTION=ReaderStart" in message:
            _update_job_step(self.job_id, 2, "阅读智能体正在提取核心指令...")
        elif "ACTION=ReviewerStart" in message:
            _update_job_step(self.job_id, 3, "审核智能体正在进行交叉验证...")
        elif "ACTION=RenderFromJsonStart" in message or "ACTION=BundleSendStart" in message:
            _update_job_step(self.job_id, 4, "正在生成排版与投递邮件...")


def _json_bytes(payload: Mapping[str, Any]) -> bytes:
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


def _classify_error(exc: Exception) -> tuple[str, str]:
    text = str(exc)
    lower = text.lower()

    if (
        "api key" in lower
        or "http 401" in lower
        or "http 402" in lower
        or "request rejected" in lower
        or "unauthorized" in lower
        or "forbidden" in lower
    ):
        return "auth_rejected", "模型调用被拒绝，请检查秘钥或余额。"

    if "timeout" in lower or "connection" in lower or "network" in lower:
        return "network_error", "网络波动导致请求失败，请点击重试。"

    if "recipient_email" in lower or "email" in lower:
        return "email_error", text

    return "runtime_error", text


def _get_job(job_id: str) -> JobState | None:
    with JOBS_LOCK:
        return JOBS.get(job_id)


def _save_job(job: JobState) -> None:
    with JOBS_LOCK:
        JOBS[job.job_id] = job


def _update_job(job_id: str, **kwargs: Any) -> None:
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if not job:
            return
        for key, value in kwargs.items():
            setattr(job, key, value)


def _append_stream_event(
    job_id: str,
    *,
    node: str,
    event: str,
    content: str,
    doc_id: str = "",
    agent: str = "",
    file_id: str = "",
    file_name: str = "",
    meta: Mapping[str, Any] | None = None,
) -> None:
    node_name = str(node or "system").strip().lower() or "system"
    agent_name = str(agent or node_name.title()).strip() or node_name.title()
    event_name = str(event or "token").strip().lower() or "token"
    text = str(content or "")
    if not text and event_name == "token":
        return

    doc_identity = str(doc_id or file_id or file_name).strip()

    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if not job:
            return

        job.stream_seq += 1
        payload: dict[str, Any] = {
            "seq": int(job.stream_seq),
            "ts": datetime.now().isoformat(timespec="seconds"),
            "node": node_name,
            "agent": agent_name,
            "event": event_name,
            "content": text,
            "text": text,
            "doc_id": doc_identity,
            "file_id": str(file_id or "").strip(),
            "file_name": str(file_name or "").strip(),
        }
        if isinstance(meta, Mapping) and meta:
            flattened_meta = dict(meta)
            payload["meta"] = flattened_meta
            for key in ("tokens", "token_count", "usage_tokens", "current", "total", "percent", "message"):
                if key in flattened_meta:
                    payload[key] = flattened_meta[key]

        job.stream_events.append(payload)
        overflow = len(job.stream_events) - STREAM_EVENT_HISTORY_LIMIT
        if overflow > 0:
            del job.stream_events[:overflow]


def _get_stream_events_since(job_id: str, last_seq: int) -> tuple[list[dict[str, Any]], int]:
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if not job:
            return [], last_seq

        threshold = max(0, int(last_seq))
        updates = [dict(item) for item in job.stream_events if int(item.get("seq", 0)) > threshold]
        latest_seq = int(job.stream_seq)
        return updates, latest_seq


def _update_job_step(job_id: str, step_index: int, text: str) -> None:
    bounded = max(1, min(4, step_index))
    progress = int((bounded / 4) * 92)
    _update_job(job_id, step_index=bounded, step_text=text, progress=progress)


def _update_job_file_progress(
    job_id: str,
    *,
    file_id: str,
    file_name: str = "",
    file_percent: int | float | None = None,
    step_detail: str = "",
) -> None:
    payload: dict[str, Any] = {
        "file_id": str(file_id).strip(),
        "step_detail": str(step_detail).strip(),
    }
    if file_name:
        payload["file_name"] = str(file_name).strip()
    if file_percent is not None:
        bounded = max(0, min(100, int(round(float(file_percent)))))
        payload["file_percent"] = bounded
    _update_job(job_id, **payload)


def _estimate_stream_token_units(text: str) -> int:
    cleaned = str(text or "").strip()
    if not cleaned:
        return 0
    return max(1, int(round(len(cleaned) / 2)))


def _is_structural_stream_noise(text: str) -> bool:
    candidate = str(text or "")
    if not candidate.strip():
        return True
    return bool(STREAM_STRUCTURAL_NOISE_RE.fullmatch(candidate))


def _build_stream_sink(
    *,
    job_id: str,
    default_doc_id: str,
    file_id: str,
    file_name: str,
    node_allowlist: set[str] | None = None,
) -> Callable[[Mapping[str, Any]], None]:
    allowed_nodes = set(node_allowlist) if node_allowlist else {"reader", "reviewer", "dispatcher"}
    token_units = 0
    last_heartbeat = 0
    token_buffer: list[str] = []
    token_buffer_chars = 0

    def _emit_token_heartbeat(node: str, agent: str, doc_identity: str, *, force: bool) -> None:
        nonlocal last_heartbeat
        if token_units <= 0:
            return
        if force:
            if token_units == last_heartbeat:
                return
        elif token_units - last_heartbeat < STREAM_TOKEN_HEARTBEAT_STEP:
            return

        last_heartbeat = token_units
        _append_stream_event(
            job_id,
            node=node,
            event="token_update",
            content=f"token_count={token_units}",
            doc_id=doc_identity,
            agent=agent,
            file_id=file_id,
            file_name=file_name,
            meta={"token_count": token_units, "tokens": token_units},
        )

    def _flush_token_buffer(node: str, agent: str, doc_identity: str) -> None:
        nonlocal token_buffer, token_buffer_chars
        if not token_buffer:
            return
        merged = "".join(token_buffer)
        token_buffer = []
        token_buffer_chars = 0
        if _is_structural_stream_noise(merged):
            return
        _append_stream_event(
            job_id,
            node=node,
            event="token",
            content=merged,
            doc_id=doc_identity,
            agent=agent,
            file_id=file_id,
            file_name=file_name,
        )

    def _stream_sink(payload: Mapping[str, Any]) -> None:
        nonlocal token_units, token_buffer_chars

        if not isinstance(payload, Mapping):
            return

        node = str(payload.get("node", "")).strip().lower()
        if node not in allowed_nodes:
            return

        origin_doc_identity = str(payload.get("doc_id", "")).strip()
        doc_identity = default_doc_id or origin_doc_identity or file_name
        agent_name = {"reader": "Reader", "reviewer": "Reviewer", "dispatcher": "Dispatcher"}.get(node, node.title())
        event_name = str(payload.get("event", "token")).strip().lower() or "token"
        content = str(payload.get("content", ""))
        meta_payload = payload.get("meta") if isinstance(payload.get("meta"), Mapping) else None
        if origin_doc_identity and origin_doc_identity != doc_identity:
            merged_meta = dict(meta_payload) if isinstance(meta_payload, Mapping) else {}
            merged_meta.setdefault("origin_doc_id", origin_doc_identity)
            meta_payload = merged_meta

        if event_name == "token":
            if _is_structural_stream_noise(content):
                return
            token_units += _estimate_stream_token_units(content)
            token_buffer.append(content)
            token_buffer_chars += len(content)
            if token_buffer_chars >= STREAM_TOKEN_BATCH_CHARS:
                _flush_token_buffer(node, agent_name, doc_identity)
            _emit_token_heartbeat(node, agent_name, doc_identity, force=False)
            return

        _flush_token_buffer(node, agent_name, doc_identity)
        _append_stream_event(
            job_id,
            node=node,
            event=event_name,
            content=content,
            doc_id=doc_identity,
            agent=agent_name,
            file_id=file_id,
            file_name=file_name,
            meta=meta_payload,
        )
        if event_name in {"stage_done", "error"}:
            _emit_token_heartbeat(node, agent_name, doc_identity, force=True)

    return _stream_sink


def _build_job_payload(job: JobState) -> dict[str, Any]:
    return {
        "job_id": job.job_id,
        "status": job.status,
        "llm_provider": job.llm_provider,
        "llm_model": job.llm_model,
        "email_file_types": list(job.email_file_types),
        "report_layouts": dict(job.report_layouts),
        "recipient_emails": list(job.recipient_emails),
        "progress": job.progress,
        "step_index": job.step_index,
        "step_text": job.step_text,
        "file_id": job.file_id,
        "file_name": job.file_name,
        "file_percent": job.file_percent,
        "step_detail": job.step_detail,
        "message": job.message,
        "error": job.error,
        "error_code": job.error_code,
        "log_file": job.log_file,
        "drafts": copy.deepcopy(job.drafts),
        "approval_locked": job.approval_locked,
        "reports": copy.deepcopy(job.reports),
        "bundle_reports": dict(job.bundle_reports),
        "email_result": copy.deepcopy(job.email_result) if isinstance(job.email_result, Mapping) else job.email_result,
        "stream_seq": int(job.stream_seq),
        "created_at": job.created_at,
    }


def _normalize_llm_provider(raw_provider: str) -> str:
    key = str(raw_provider).strip()
    if not key:
        return "deepseek"
    candidate = LLM_PROVIDER_ALIASES.get(key.lower(), key.lower())
    return candidate if candidate in SUPPORTED_LLM_PROVIDERS else "deepseek"


def _resolve_requested_llm_provider(raw_provider: str) -> str:
    key = str(raw_provider).strip()
    candidate = LLM_PROVIDER_ALIASES.get(key.lower(), key.lower()) if key else "deepseek"
    if candidate not in UI_LLM_PROVIDERS or candidate not in LLM_PROVIDER_PRESETS:
        raise ValueError(f"unsupported llm_provider: {raw_provider}")
    return candidate


def _normalize_model_name(raw_model: Any) -> str:
    model_name = str(raw_model or "").strip()
    if re.search(r"[\r\n;]", model_name):
        return ""
    return model_name


def _get_provider_default_model(provider: str) -> str:
    preset = LLM_PROVIDER_PRESETS.get(provider, {})
    return str(preset.get("default_model") or preset.get("model") or "").strip()


def _build_llm_models_payload() -> dict[str, Any]:
    providers: list[dict[str, Any]] = []
    for provider in sorted(UI_LLM_PROVIDERS):
        preset = LLM_PROVIDER_PRESETS.get(provider, {})
        if not preset:
            continue
        models = [dict(item) for item in LLM_MODEL_PRESETS.get(provider, [])]
        default_model = _get_provider_default_model(provider)
        if default_model and not any(str(item.get("value", "")).strip() == default_model for item in models):
            models.insert(0, {"value": default_model, "label": default_model, "recommended": True})
        providers.append(
            {
                "value": provider,
                "label": str(preset.get("display_name") or provider),
                "defaultModel": default_model,
                "models": models,
                "supportsCustomModel": True,
            }
        )
    return {
        "providers": providers,
        "notes": {
            "customModel": "如果账号使用企业专属模型、区域模型或火山方舟 ep- 接入点，请填写自定义模型并用测试连接确认。",
            "test": "测试连接会发起一次小请求，用于确认 API Key、模型名和 JSON 兼容性。",
        },
    }


def _build_settings_for_job(api_key: str, llm_provider: str, job_root: Path, model_name: str = "") -> dict[str, Any]:
    settings_path = PROJECT_ROOT / "config" / "settings.yaml"
    settings = load_settings(settings_path)
    settings = copy.deepcopy(settings)

    provider = _resolve_requested_llm_provider(llm_provider)
    normalized_model = _normalize_model_name(model_name)

    llm_cfg = settings.setdefault("llm", {})
    llm_cfg["provider"] = provider
    providers_cfg = llm_cfg.setdefault("providers", {})
    provider_cfg = providers_cfg.get(provider, {}) if isinstance(providers_cfg.get(provider), Mapping) else {}
    provider_cfg = dict(provider_cfg)
    provider_cfg["api_key"] = api_key.strip()
    provider_cfg["api_key_env"] = ""
    if normalized_model:
        provider_cfg["model"] = normalized_model
    providers_cfg[provider] = provider_cfg

    deepseek_cfg = settings.setdefault("deepseek", {})
    deepseek_cfg["api_key"] = api_key.strip()
    deepseek_cfg["api_key_env"] = ""

    paths_cfg = settings.setdefault("paths", {})
    paths_cfg["processed_cache_dir"] = str(job_root / "processed_cache")
    paths_cfg["final_reports_dir"] = str(job_root / "final_reports")

    return settings


def _normalize_email_file_types(raw_values: list[str] | str | None) -> list[str]:
    if raw_values is None:
        return []

    values = raw_values if isinstance(raw_values, list) else [str(raw_values)]
    parsed: list[str] = []
    for raw in values:
        for token in str(raw).replace("\n", ",").split(","):
            item = token.strip().lower()
            if not item or item not in SUPPORTED_EMAIL_FILE_TYPES:
                continue
            if item in parsed:
                continue
            parsed.append(item)
    return parsed


def _normalize_report_layout(raw_value: Any) -> str:
    value = str(raw_value or "").strip().lower()
    return value if value in SUPPORTED_REPORT_LAYOUT else "separate"


def _parse_report_layouts(form: cgi.FieldStorage) -> dict[str, str]:
    layouts: dict[str, str] = {}
    for fmt, default_mode in DEFAULT_REPORT_LAYOUTS.items():
        layouts[fmt] = _normalize_report_layout(form.getfirst(f"report_layout_{fmt}", default_mode))
    return layouts


def _normalize_recipient_emails(raw_values: Any) -> list[str]:
    if raw_values is None:
        return []

    if isinstance(raw_values, list):
        values = raw_values
    else:
        values = [raw_values]

    emails: list[str] = []
    for raw in values:
        segments = str(raw).replace("\r", "\n").replace(",", "\n").split("\n")
        for segment in segments:
            email = str(segment).strip()
            if not email or email in emails:
                continue
            if EMAIL_PATTERN.fullmatch(email):
                emails.append(email)
    return emails


def _resolve_parallel_workers(settings: Mapping[str, Any], source_count: int) -> int:
    app_cfg = settings.get("app", {}) if isinstance(settings.get("app"), Mapping) else {}
    raw = app_cfg.get("max_parallel_tasks", app_cfg.get("max_parallel_docs", 10))
    try:
        requested = int(raw)
    except (TypeError, ValueError):
        requested = 10
    return max(1, min(source_count, max(1, requested)))


def _resolve_ocr_workers(settings: Mapping[str, Any], source_count: int) -> int:
    ingestion_cfg = settings.get("ingestion", {}) if isinstance(settings.get("ingestion"), Mapping) else {}
    ocr_cfg = ingestion_cfg.get("ocr", {}) if isinstance(ingestion_cfg.get("ocr"), Mapping) else {}
    app_cfg = settings.get("app", {}) if isinstance(settings.get("app"), Mapping) else {}
    fallback = app_cfg.get("max_parallel_tasks", app_cfg.get("max_parallel_docs", 10))
    raw = ocr_cfg.get("max_parallel_files", fallback)
    try:
        requested = int(raw)
    except (TypeError, ValueError):
        requested = 10
    return max(1, min(source_count, max(1, requested)))


def _first_non_empty_value(*values: Any) -> Any:
    for value in values:
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        return value
    return None


def _extract_critic_fields(draft_output: Mapping[str, Any]) -> tuple[Any, str]:
    critic_eval = draft_output.get("critic_evaluation", {})
    if not isinstance(critic_eval, Mapping):
        critic_eval = {}

    pipeline_meta = draft_output.get("pipeline_meta", {})
    if not isinstance(pipeline_meta, Mapping):
        pipeline_meta = {}

    critic_dimensions = pipeline_meta.get("critic_dimensions", {})
    if not isinstance(critic_dimensions, Mapping):
        critic_dimensions = {}

    real_score = _first_non_empty_value(
        critic_eval.get("total_score"),
        critic_eval.get("critic_final_score"),
        pipeline_meta.get("critic_final_score"),
        critic_dimensions.get("total_score"),
    )
    real_feedback = str(
        _first_non_empty_value(
            critic_eval.get("critic_feedback"),
            critic_eval.get("feedback"),
            pipeline_meta.get("critic_feedback"),
        )
        or ""
    )
    return real_score, real_feedback


_TASK_SCORE_KEYS = (
    "score",
    "confidence",
    "total_score",
    "critic_score",
    "critic_final_score",
    "ai_score",
    "quality_score",
)


def _normalize_score(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, str) and not value.strip():
        return None
    try:
        score = int(round(float(value)))
    except (TypeError, ValueError):
        return None
    return max(0, min(100, score))


def _extract_task_score(item: Mapping[str, Any]) -> int | None:
    for key in _TASK_SCORE_KEYS:
        score = _normalize_score(item.get(key))
        if score is not None:
            return score
    return None


def _fallback_task_scores(task_count: int, fallback_score: Any) -> list[Any]:
    total_score = _normalize_score(fallback_score)
    if total_score is None:
        return [fallback_score] * task_count
    if task_count <= 1:
        return [total_score] * task_count

    offsets = (-2, 2, -3, 3)
    return [max(0, min(100, total_score + offsets[index % len(offsets)])) for index in range(task_count)]


def _extract_task_feedback(item: Mapping[str, Any], fallback_feedback: str) -> str:
    return str(
        _first_non_empty_value(
            item.get("critic_feedback"),
            item.get("criticFeedback"),
            item.get("feedback"),
            fallback_feedback,
        )
        or ""
    )


def _build_draft_payload(draft_token: str, source_file: Path, cache_path: Path, draft_output: Mapping[str, Any]) -> dict[str, Any]:
    real_score, real_feedback = _extract_critic_fields(draft_output)

    tasks_raw = draft_output.get("tasks", []) if isinstance(draft_output.get("tasks"), list) else []
    task_items = [item for item in tasks_raw if isinstance(item, Mapping)]
    fallback_scores = _fallback_task_scores(len(task_items), real_score)
    tasks_payload: list[dict[str, Any]] = []
    for index, item in enumerate(task_items):
        task_score = _extract_task_score(item)
        tasks_payload.append(
            {
                "task_id": str(item.get("task_id", "")).strip(),
                "task_name": str(item.get("task_name", "")).strip(),
                "owner": str(item.get("owner", "")).strip(),
                "deadline": str(item.get("deadline", "")).strip(),
                "deadline_display": str(item.get("deadline_display", "")).strip(),
                "score": task_score if task_score is not None else fallback_scores[index],
                "criticFeedback": _extract_task_feedback(item, real_feedback),
            }
        )

    return {
        "draft_token": draft_token,
        "doc_id": str(draft_output.get("doc_id", source_file.stem)),
        "title": str(draft_output.get("title", source_file.stem)),
        "source_file": source_file.name,
        "cache_path": to_relative_path(cache_path),
        "status": str(draft_output.get("status", "pending_approval")),
        "task_count": len(tasks_payload),
        "tasks": tasks_payload,
        "draft_json": draft_output,
    }


def _read_json_body(handler: BaseHTTPRequestHandler) -> dict[str, Any]:
    content_length_raw = handler.headers.get("Content-Length", "0")
    try:
        content_length = int(content_length_raw)
    except ValueError as exc:
        raise ValueError("invalid Content-Length") from exc

    if content_length <= 0:
        raise ValueError("request body is empty")

    raw = handler.rfile.read(content_length)
    try:
        payload = json.loads(raw.decode("utf-8"))
    except Exception as exc:  # pylint: disable=broad-except
        raise ValueError("request body must be valid JSON") from exc

    if not isinstance(payload, dict):
        raise ValueError("JSON payload must be an object")
    return payload


async def _run_llm_connection_test(api_key: str, provider: str, model_name: str) -> dict[str, Any]:
    settings = _build_settings_for_job(
        api_key=api_key,
        llm_provider=provider,
        job_root=UI_JOB_ROOT / "_llm_test",
        model_name=model_name,
    )
    client = build_client(settings, model_name=model_name)
    response = await client.chat_completion(
        messages=[
            {
                "role": "system",
                "content": "Return a tiny JSON object only.",
            },
            {
                "role": "user",
                "content": '{"ping":"ok"}',
            },
        ],
        response_format={"type": "json_object"},
        temperature=0,
        max_tokens=32,
    )
    content = client.get_message_content(response)
    return {
        "provider": provider,
        "model": client.config.model,
        "endpoint": client.endpoint,
        "jsonMode": client.config.request_json_mode,
        "sample": content[:120],
    }


def _classify_llm_test_error(error: Exception) -> tuple[str, str]:
    text = str(error)
    lower = text.lower()
    if "401" in lower or "unauthorized" in lower or "invalid api key" in lower:
        return "auth_failed", "API Key 无效或认证失败。"
    if "403" in lower or "forbidden" in lower or "permission" in lower:
        return "permission_denied", "API Key 没有调用该模型的权限。"
    if "404" in lower or "model_not_found" in lower or "not found" in lower:
        return "model_not_found", "模型名不可用，或当前账号/区域没有开通该模型。"
    if "response_format" in lower or "json_object" in lower:
        return "response_format_unsupported", "该模型可能不支持 JSON response_format，请改用兼容模型或自定义模型。"
    if "429" in lower or "rate limit" in lower or "too many requests" in lower:
        return "rate_limited", "请求被限流，请稍后重试或检查额度。"
    if "timeout" in lower or "timed out" in lower:
        return "timeout", "请求超时，请检查网络、厂商服务状态或模型可用性。"
    return "request_failed", f"测试请求失败：{text[:300]}"


def _normalize_paste_filename(raw_name: str, index: int) -> str:
    cleaned = re.sub(r"[\\/:*?\"<>|]+", "_", str(raw_name or "").strip())
    cleaned = re.sub(r"\s+", "_", cleaned)
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    if not cleaned:
        now = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"paste_notice_{now}_{index:02d}.txt"
    return cleaned if cleaned.lower().endswith(".txt") else f"{cleaned}.txt"


def _create_files_from_pastes(upload_dir: Path, pasted_texts: list[str], pasted_names: list[str] | None = None) -> list[Path]:
    saved: list[Path] = []
    names = pasted_names if isinstance(pasted_names, list) else []

    for idx, raw_text in enumerate(pasted_texts, start=1):
        normalized = str(raw_text).strip()
        if not normalized:
            continue

        suggested_name = names[idx - 1] if idx - 1 < len(names) else ""
        filename = _normalize_paste_filename(suggested_name, idx)
        out_file = upload_dir / filename

        counter = 1
        while out_file.exists():
            out_file = upload_dir / f"{out_file.stem}_{counter}{out_file.suffix}"
            counter += 1

        out_file.write_text(normalized, encoding="utf-8")
        saved.append(out_file)

    return saved


def _normalize_crawl_count(raw_value: Any) -> int:
    try:
        parsed = int(str(raw_value).strip())
    except Exception:  # pylint: disable=broad-except
        return 5
    return max(1, min(20, parsed))


def _resolve_crawler_text_files(crawler_result: Mapping[str, Any]) -> list[Path]:
    text_files: list[Path] = []
    raw_paths = crawler_result.get("text_files", []) if isinstance(crawler_result.get("text_files"), list) else []
    for item in raw_paths:
        candidate = str(item).strip()
        if not candidate:
            continue
        path = Path(candidate)
        resolved = path if path.is_absolute() else PROJECT_ROOT / candidate
        if resolved.exists() and resolved.is_file():
            text_files.append(resolved)
    return text_files


def _save_uploaded_files(form: cgi.FieldStorage, upload_dir: Path) -> list[Path]:
    saved: list[Path] = []
    file_field = form["files"] if "files" in form else []
    items = file_field if isinstance(file_field, list) else [file_field]

    for item in items:
        if not isinstance(item, cgi.FieldStorage):
            continue

        filename = Path(str(item.filename or "")).name
        if not filename:
            continue

        suffix = Path(filename).suffix.lower()
        if suffix not in SUPPORTED_UPLOAD_SUFFIXES:
            continue

        raw_bytes = item.file.read() if item.file else b""
        if not raw_bytes:
            continue

        target = upload_dir / filename
        counter = 1
        while target.exists():
            target = upload_dir / f"{target.stem}_{counter}{target.suffix}"
            counter += 1

        target.write_bytes(raw_bytes)
        saved.append(target)

    return saved


def _register_artifact(job_id: str, token: str, file_path: Path) -> str:
    relative = to_relative_path(file_path)
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if not job:
            return ""
        job.artifacts[token] = relative
    return f"/api/jobs/{job_id}/artifacts/{token}"


def _register_bundle_reports(job_id: str, bundle_paths: Mapping[str, Path]) -> dict[str, str]:
    bundle_urls: dict[str, str] = {}
    for fmt, file_path in bundle_paths.items():
        if not isinstance(file_path, Path) or not file_path.exists():
            continue
        token = f"bundle_{fmt}_{uuid.uuid4().hex[:8]}"
        url = _register_artifact(job_id, token, file_path)
        if url:
            bundle_urls[fmt] = url
    return bundle_urls


def _prepare_logger_for_job() -> str:
    settings_file = PROJECT_ROOT / "config" / "settings.yaml"
    loaded = yaml.safe_load(settings_file.read_text(encoding="utf-8")) or {}
    if not isinstance(loaded, dict):
        loaded = {}

    app_cfg = loaded.get("app", {}) if isinstance(loaded.get("app"), Mapping) else {}
    logging_cfg = loaded.get("logging", {}) if isinstance(loaded.get("logging"), Mapping) else {}

    setup_logger(
        log_level=str(app_cfg.get("log_level", "INFO")),
        log_file=str(logging_cfg.get("file", "")) or None,
        log_dir=str(logging_cfg.get("dir", "log")),
        config_file=str(logging_cfg.get("config_file", "log/logging.yaml")),
        force_reconfigure=True,
    )

    session = get_log_session()
    return to_relative_path(session.log_file) if session is not None else ""


async def _process_job_async(
    job_id: str,
    api_key: str,
    llm_provider: str,
    model_name: str,
    report_layouts: dict[str, str],
    mode: str,
    source_files: list[Path],
    input_tab: str,
    crawl_url: str,
    crawl_count: int,
    crawl_keyword: str,
) -> None:
    _update_job(job_id, status="running", message="任务已启动")
    _update_job_step(job_id, 1, PIPELINE_STEPS[0])
    _update_job_file_progress(
        job_id,
        file_id="__job__",
        file_name="总体任务",
        file_percent=2,
        step_detail="任务已启动，等待分发文件...",
    )

    with RUN_LOCK:
        log_file = _prepare_logger_for_job()
        _update_job(job_id, log_file=log_file)

        job_root = UI_JOB_ROOT / job_id
        cache_dir = job_root / "processed_cache"
        final_reports_dir = job_root / "final_reports"
        report_dir = final_reports_dir / "reports"
        for folder in (cache_dir, final_reports_dir, report_dir):
            folder.mkdir(parents=True, exist_ok=True)

        if llm_provider not in LLM_PROVIDER_PRESETS:
            raise ValueError(f"unsupported llm_provider: {llm_provider}")

        settings = _build_settings_for_job(
            api_key=api_key,
            llm_provider=llm_provider,
            job_root=job_root,
            model_name=model_name,
        )

        warmup_status, warmup_detail = _get_rag_warmup_state()
        if warmup_status == "running":
            _update_job_file_progress(
                job_id,
                file_id="__job__",
                file_name="总体任务",
                file_percent=4,
                step_detail="模型与向量检索组件预热中，正在准备并行流水线...",
            )
        elif warmup_status == "failed":
            LOGGER.warning(
                "STEP=ui.pipeline | AGENT=UIConsole | ACTION=RAGWarmupState | DETAILS=status=failed reason=%s",
                warmup_detail,
            )

        progress_handler = JobProgressLogHandler(job_id=job_id)
        docs_logger = logging.getLogger("docs_agent")
        docs_logger.addHandler(progress_handler)

        effective_source_files = list(source_files)
        normalized_input_tab = str(input_tab or "upload").strip().lower()
        crawl_runtime: dict[str, Any] = {}
        if normalized_input_tab == "crawl":
            target_url = str(crawl_url).strip()
            if not target_url:
                raise ValueError("全网抓取模式缺少目标链接 crawl_url。")

            keyword_text = str(crawl_keyword or "").strip()
            crawl_limit = max(1, int(crawl_count or 1))
            crawl_output_dir = job_root / "uploads" / "crawled"
            crawl_output_dir.mkdir(parents=True, exist_ok=True)

            crawl_runtime = {
                "target_url": target_url,
                "keyword_text": keyword_text,
                "crawl_limit": crawl_limit,
                "crawl_output_dir": crawl_output_dir,
            }
            effective_source_files = []

            _update_job(
                job_id,
                message="正在启动网页抓取，请稍候...",
            )
            _update_job_step(job_id, 1, "正在驱动无头浏览器抓取目标网站...")
            _update_job_file_progress(
                job_id,
                file_id="__crawl__",
                file_name="网页抓取阶段",
                file_percent=10,
                step_detail="正在驱动无头浏览器抓取目标网站...",
            )
            log_step(
                LOGGER,
                "ui.pipeline",
                "UIConsole",
                "CrawlDispatchStart",
                f"job_id={job_id} url={target_url} count={crawl_limit} keyword={keyword_text or 'none'}",
            )

        if not effective_source_files and normalized_input_tab != "crawl":
            raise RuntimeError("未检测到可处理的输入文件。")

        planned_sources = len(effective_source_files)
        if planned_sources <= 0 and normalized_input_tab == "crawl":
            planned_sources = max(1, int(crawl_runtime.get("crawl_limit", 1)))
        total_sources = max(1, planned_sources)

        reports: list[dict[str, Any]] = []
        drafts: list[dict[str, Any]] = []
        draft_cache_map: dict[str, str] = {}
        draft_source_map: dict[str, str] = {}
        draft_outputs: list[Mapping[str, Any]] = []

        per_doc_formats: set[str] = {"html"}
        if total_sources <= 1 or str(report_layouts.get("md", "separate")).strip().lower() == "separate":
            per_doc_formats.add("md")
        if total_sources <= 1 or str(report_layouts.get("docx", "bundle")).strip().lower() == "separate":
            per_doc_formats.add("docx")

        prep_started = time.perf_counter()
        _update_job_file_progress(
            job_id,
            file_id="__job__",
            file_name="总体任务",
            file_percent=6,
            step_detail="正在初始化编排器与检索引擎...",
        )
        shared_draft_client = build_client(settings, model_name=model_name)
        draft_orchestrator_worker = Orchestrator(client=shared_draft_client, settings=settings, project_root=PROJECT_ROOT)
        ocr_worker_count = _resolve_ocr_workers(settings=settings, source_count=total_sources)
        ocr_limit = asyncio.Semaphore(ocr_worker_count)
        prep_elapsed = round(time.perf_counter() - prep_started, 2)
        log_step(
            LOGGER,
            "ui.pipeline",
            "UIConsole",
            "DraftRuntimeReady",
            (
                f"job_id={job_id} elapsed_sec={prep_elapsed} per_doc_formats={sorted(per_doc_formats)} "
                f"ocr_workers={ocr_worker_count}"
            ),
        )

        async def _process_single_source(index: int, source_file: Path) -> dict[str, Any]:
            doc_started = time.perf_counter()
            file_progress_id = source_file.name
            log_step(
                LOGGER,
                "ui.pipeline",
                "UIConsole",
                "DocumentStart",
                f"job_id={job_id} file={to_relative_path(source_file)} index={index}/{total_sources}",
            )
            _update_job(
                job_id,
                message=f"正在处理第 {index}/{total_sources} 份文件：{source_file.name}",
            )
            _update_job_step(job_id, 1, PIPELINE_STEPS[0])
            _update_job_file_progress(
                job_id,
                file_id=file_progress_id,
                file_name=source_file.name,
                file_percent=8,
                step_detail="已进入识别与清洗阶段",
            )

            _stream_sink = _build_stream_sink(
                job_id=job_id,
                default_doc_id=source_file.name,
                file_id=file_progress_id,
                file_name=source_file.name,
                node_allowlist={"reader", "reviewer", "dispatcher"},
            )

            source_suffix = source_file.suffix.lower()
            is_ocr_candidate = source_suffix in OCR_CANDIDATE_SUFFIXES

            parse_start_message = "正在解析文档结构..."
            if is_ocr_candidate:
                parse_start_message = "正在执行OCR识别与版面重建..."

            _append_stream_event(
                job_id,
                node="reader",
                event="stage_start",
                content=parse_start_message,
                doc_id=source_file.name,
                agent="Reader",
                file_id=file_progress_id,
                file_name=source_file.name,
            )
            _update_job_file_progress(
                job_id,
                file_id=file_progress_id,
                file_name=source_file.name,
                file_percent=12,
                step_detail=parse_start_message,
            )

            from ingestion.router import route_document  # pylint: disable=import-outside-toplevel

            async def _parse_source_doc() -> Mapping[str, Any]:
                if is_ocr_candidate:
                    async with ocr_limit:
                        return await asyncio.to_thread(route_document, file_path=source_file, settings=settings)
                return await asyncio.to_thread(route_document, file_path=source_file, settings=settings)

            parse_task = asyncio.create_task(_parse_source_doc())
            parse_heartbeat_round = 0
            while not parse_task.done():
                await asyncio.sleep(2.0)
                parse_heartbeat_round += 1
                if parse_heartbeat_round % 2 != 0:
                    continue
                heartbeat_text = "OCR处理中，请稍候..." if is_ocr_candidate else "文档识别处理中，请稍候..."
                _update_job_file_progress(
                    job_id,
                    file_id=file_progress_id,
                    file_name=source_file.name,
                    file_percent=min(20, 12 + parse_heartbeat_round),
                    step_detail=heartbeat_text,
                )
                _append_stream_event(
                    job_id,
                    node="reader",
                    event="file_parse_progress",
                    content=heartbeat_text,
                    doc_id=source_file.name,
                    agent="Reader",
                    file_id=file_progress_id,
                    file_name=source_file.name,
                )

            parsed_doc = await parse_task
            parsed_meta = parsed_doc.get("metadata", {}) if isinstance(parsed_doc.get("metadata"), Mapping) else {}
            parser_name_hint = str(parsed_meta.get("parser", "unknown"))
            parse_done_message = "文档识别完成，进入阅读抽取"
            if parser_name_hint == "ocr_parser":
                parse_done_message = "OCR识别完成，进入阅读抽取"

            _update_job_file_progress(
                job_id,
                file_id=file_progress_id,
                file_name=source_file.name,
                file_percent=20,
                step_detail=parse_done_message,
            )
            _append_stream_event(
                job_id,
                node="reader",
                event="file_parse_done",
                content=parse_done_message,
                doc_id=source_file.name,
                agent="Reader",
                file_id=file_progress_id,
                file_name=source_file.name,
            )

            output = await draft_orchestrator_worker.generate_draft_plan(parsed_doc=parsed_doc, stream_callback=_stream_sink)
            _update_job_step(job_id, 2, PIPELINE_STEPS[1])
            _update_job_file_progress(
                job_id,
                file_id=file_progress_id,
                file_name=source_file.name,
                file_percent=42,
                step_detail="已完成阅读智能体抽取，进入审核阶段",
            )
            _update_job_step(job_id, 3, PIPELINE_STEPS[2])
            _update_job_file_progress(
                job_id,
                file_id=file_progress_id,
                file_name=source_file.name,
                file_percent=72,
                step_detail="交叉审核完成，正在生成报告",
            )

            pipeline_meta = output.get("pipeline_meta", {}) if isinstance(output.get("pipeline_meta"), Mapping) else {}
            parser_name = str(pipeline_meta.get("parser", parser_name_hint or "unknown"))
            router_strategy = str(pipeline_meta.get("router_strategy", "unknown"))

            cache_path = await asyncio.to_thread(save_cache, output=output, settings=settings, file_tag="agent")
            rendered_paths = await asyncio.to_thread(
                report_renderer.render_selected_reports_from_json,
                json_path=cache_path,
                output_dir=report_dir,
                template_dir=TEMPLATE_DIR,
                include_formats=sorted(per_doc_formats),
            )
            _update_job_file_progress(
                job_id,
                file_id=file_progress_id,
                file_name=source_file.name,
                file_percent=92,
                step_detail="报告渲染完成，准备汇总结果",
            )

            return {
                "index": index,
                "source_file": source_file,
                "file_progress_id": file_progress_id,
                "output": output,
                "cache_path": cache_path,
                "rendered_paths": rendered_paths,
                "parser_name": parser_name,
                "router_strategy": router_strategy,
                "elapsed_sec": round(time.perf_counter() - doc_started, 2),
            }

        try:
            doc_results: list[dict[str, Any]] = []
            worker_count = _resolve_parallel_workers(settings=settings, source_count=total_sources)
            completed_count = 0

            if normalized_input_tab == "crawl":
                from ingestion.web_crawler import run_crawler  # pylint: disable=import-outside-toplevel

                loop = asyncio.get_running_loop()
                crawl_limit = max(1, int(crawl_runtime.get("crawl_limit", 1)))
                target_url = str(crawl_runtime.get("target_url", "")).strip()
                keyword_text = str(crawl_runtime.get("keyword_text", "")).strip()
                crawl_output_dir_raw = crawl_runtime.get("crawl_output_dir")
                crawl_output_dir = crawl_output_dir_raw if isinstance(crawl_output_dir_raw, Path) else job_root / "uploads" / "crawled"
                crawl_output_dir.mkdir(parents=True, exist_ok=True)

                crawl_seen_files: set[str] = set()
                crawl_progress_floor = 0
                crawl_progress_ceiling = 100
                crawl_last_percent = 0
                scheduled_tasks: dict[str, asyncio.Task[dict[str, Any]]] = {}
                limit = asyncio.Semaphore(worker_count)

                def _resolve_discovered_source(raw_source: str) -> Path | None:
                    normalized = str(raw_source or "").strip()
                    if not normalized:
                        return None
                    candidate = Path(normalized)
                    if not candidate.is_absolute():
                        candidate = crawl_output_dir / candidate
                    if not candidate.exists() or not candidate.is_file():
                        return None
                    return candidate

                async def _run_with_limit(index: int, source_file: Path) -> dict[str, Any]:
                    async with limit:
                        return await _process_single_source(index=index, source_file=source_file)

                def _schedule_discovered_source(raw_source: str, parser_hint: str = "") -> None:
                    if len(effective_source_files) >= crawl_limit:
                        return

                    source_path = _resolve_discovered_source(raw_source)
                    if source_path is None:
                        return

                    source_name = source_path.name
                    if source_name in crawl_seen_files:
                        return

                    if len(effective_source_files) >= crawl_limit:
                        return

                    crawl_seen_files.add(source_name)
                    effective_source_files.append(source_path)

                    waiting_detail = "已抓取，等待识别"
                    if str(parser_hint).strip().lower() == "ocr":
                        waiting_detail = "已抓取，等待OCR识别"

                    _update_job_file_progress(
                        job_id,
                        file_id=source_name,
                        file_name=source_name,
                        file_percent=0,
                        step_detail=waiting_detail,
                    )
                    _append_stream_event(
                        job_id,
                        node="reader",
                        event="crawl_file_found",
                        content=f"发现可解析文件：{source_name}",
                        doc_id=source_name,
                        agent="Reader",
                        file_id=source_name,
                        file_name=source_name,
                        meta={
                            "discovered_file": source_name,
                            "parser_hint": str(parser_hint).strip(),
                            "source": "crawler",
                        },
                    )

                    source_index = len(effective_source_files)
                    scheduled_tasks[source_name] = asyncio.create_task(
                        _run_with_limit(index=source_index, source_file=source_path)
                    )

                def _crawl_progress_sink(payload: Mapping[str, Any]) -> None:
                    nonlocal crawl_last_percent
                    if not isinstance(payload, Mapping):
                        return

                    total_raw = payload.get("total", 0)
                    current_raw = payload.get("current", 0)
                    percent_raw = payload.get("percent")
                    stage_name = str(payload.get("stage", "progress")).strip().lower() or "progress"
                    message = str(payload.get("message", payload.get("detail", ""))).strip() or "网页抓取处理中..."
                    discovered_file = str(payload.get("discovered_file", "")).strip()
                    parser_hint = str(payload.get("parser_hint", "")).strip()

                    try:
                        total = max(0, int(total_raw))
                    except (TypeError, ValueError):
                        total = 0

                    try:
                        current = max(0, int(current_raw))
                    except (TypeError, ValueError):
                        current = 0

                    mapped_percent = crawl_last_percent
                    if percent_raw is not None:
                        try:
                            mapped_percent = int(round(float(percent_raw)))
                        except (TypeError, ValueError):
                            mapped_percent = crawl_last_percent
                    elif total > 0:
                        mapped_percent = int(round((current / float(total)) * 100.0))

                    if stage_name == "done":
                        mapped_percent = 100

                    mapped_percent = max(crawl_progress_floor, min(crawl_progress_ceiling, mapped_percent))
                    mapped_percent = max(crawl_last_percent, mapped_percent)
                    crawl_last_percent = mapped_percent

                    detail_suffix = f"（{current}/{total}）" if total > 0 else ""
                    detail_text = f"{message}{detail_suffix}"
                    event_name = "crawler_done" if stage_name == "done" else "crawler_progress"

                    _update_job_file_progress(
                        job_id,
                        file_id="__crawl__",
                        file_name="网页抓取阶段",
                        file_percent=mapped_percent,
                        step_detail=detail_text,
                    )
                    _append_stream_event(
                        job_id,
                        node="reader",
                        event=event_name,
                        content=message,
                        doc_id="__crawl__",
                        agent="Reader",
                        file_id="__crawl__",
                        file_name="网页抓取阶段",
                        meta={
                            "current": current,
                            "total": total,
                            "percent": mapped_percent,
                            "message": message,
                            "stage": stage_name,
                        },
                    )

                    if discovered_file:
                        loop.call_soon_threadsafe(_schedule_discovered_source, discovered_file, parser_hint)

                log_step(
                    LOGGER,
                    "ui.pipeline",
                    "UIConsole",
                    "ParallelDraftStart",
                    f"job_id={job_id} workers={worker_count} files={crawl_limit}",
                )

                crawl_result = await asyncio.to_thread(
                    run_crawler,
                    settings,
                    crawl_output_dir,
                    crawl_limit,
                    None,
                    target_url,
                    True,
                    keyword_text or None,
                    _crawl_progress_sink,
                )

                # Allow scheduled callbacks from crawler thread to flush into the event loop.
                await asyncio.sleep(0)

                resolved_sources = _resolve_crawler_text_files(crawl_result if isinstance(crawl_result, Mapping) else {})
                for source in resolved_sources:
                    parser_hint = "ocr" if source.suffix.lower() in OCR_CANDIDATE_SUFFIXES else "text"
                    _schedule_discovered_source(source.name, parser_hint)

                await asyncio.sleep(0)

                if not effective_source_files:
                    failed_reason = "未抓取到可解析网页正文。"
                    failed_items = crawl_result.get("failed_items", []) if isinstance(crawl_result, Mapping) else []
                    if isinstance(failed_items, list) and failed_items:
                        first_item = failed_items[0] if isinstance(failed_items[0], Mapping) else {}
                        failed_reason = str(first_item.get("reason", failed_reason)).strip() or failed_reason

                    _update_job_file_progress(
                        job_id,
                        file_id="__crawl__",
                        file_name="网页抓取阶段",
                        file_percent=100,
                        step_detail=f"抓取结束，但无可解析结果：{failed_reason}",
                    )
                    raise RuntimeError(f"网页抓取未产出可解析公文。{failed_reason}")

                _update_job(
                    job_id,
                    message=f"网页抓取完成，已获取 {len(effective_source_files)} 份公文，解析任务并行处理中。",
                )
                _update_job_file_progress(
                    job_id,
                    file_id="__crawl__",
                    file_name="网页抓取阶段",
                    file_percent=100,
                    step_detail=f"抓取完成，获取 {len(effective_source_files)} 份公文",
                )
                _update_job_step(job_id, 1, PIPELINE_STEPS[0])
                log_step(
                    LOGGER,
                    "ui.pipeline",
                    "UIConsole",
                    "CrawlDispatchDone",
                    f"job_id={job_id} files={len(effective_source_files)}",
                )

                if scheduled_tasks:
                    for done in asyncio.as_completed(list(scheduled_tasks.values())):
                        result = await done
                        doc_results.append(result)
                        completed_count += 1
                        _update_job(
                            job_id,
                            message=f"已完成 {completed_count}/{len(effective_source_files)} 份文件，正在汇总结果...",
                        )
                        done_source = result.get("source_file")
                        done_name = done_source.name if isinstance(done_source, Path) else str(result.get("file_progress_id", ""))
                        _update_job_file_progress(
                            job_id,
                            file_id=str(result.get("file_progress_id", done_name)),
                            file_name=done_name or "文档",
                            file_percent=100,
                            step_detail="该文件已完成",
                        )

                log_step(
                    LOGGER,
                    "ui.pipeline",
                    "UIConsole",
                    "ParallelDraftDone",
                    f"job_id={job_id} workers={worker_count} files={len(doc_results)}",
                )

            elif worker_count <= 1:
                for index, source_file in enumerate(effective_source_files, start=1):
                    result = await _process_single_source(index=index, source_file=source_file)
                    doc_results.append(result)
                    completed_count += 1
                    _update_job(job_id, message=f"已完成 {completed_count}/{total_sources} 份文件，正在汇总结果...")
                    _update_job_file_progress(
                        job_id,
                        file_id=str(result.get("file_progress_id", source_file.name)),
                        file_name=source_file.name,
                        file_percent=100,
                        step_detail="该文件已完成",
                    )
            else:
                log_step(
                    LOGGER,
                    "ui.pipeline",
                    "UIConsole",
                    "ParallelDraftStart",
                    f"job_id={job_id} workers={worker_count} files={total_sources}",
                )
                limit = asyncio.Semaphore(worker_count)

                async def _run_with_limit(index: int, source_file: Path) -> dict[str, Any]:
                    async with limit:
                        return await _process_single_source(index=index, source_file=source_file)

                tasks = [
                    asyncio.create_task(_run_with_limit(index=index, source_file=source_file))
                    for index, source_file in enumerate(effective_source_files, start=1)
                ]
                try:
                    for done in asyncio.as_completed(tasks):
                        result = await done
                        doc_results.append(result)
                        completed_count += 1
                        _update_job(job_id, message=f"已完成 {completed_count}/{total_sources} 份文件，正在汇总结果...")
                        done_source = result.get("source_file")
                        done_name = done_source.name if isinstance(done_source, Path) else str(result.get("file_progress_id", ""))
                        _update_job_file_progress(
                            job_id,
                            file_id=str(result.get("file_progress_id", done_name)),
                            file_name=done_name or "文档",
                            file_percent=100,
                            step_detail="该文件已完成",
                        )
                finally:
                    for task in tasks:
                        if not task.done():
                            task.cancel()
                    await asyncio.gather(*tasks, return_exceptions=True)

                log_step(
                    LOGGER,
                    "ui.pipeline",
                    "UIConsole",
                    "ParallelDraftDone",
                    f"job_id={job_id} workers={worker_count} files={len(doc_results)}",
                )

            for item in sorted(doc_results, key=lambda result: int(result.get("index", 0))):
                output = item["output"]
                source_file = item["source_file"]
                cache_path = item["cache_path"]
                parser_name = item["parser_name"]
                router_strategy = item["router_strategy"]
                rendered_paths = item["rendered_paths"]
                draft_outputs.append(output)

                html_path = rendered_paths.get("html")
                md_path = rendered_paths.get("md")
                docx_path = rendered_paths.get("docx")

                base_token = uuid.uuid4().hex[:10]
                html_url = _register_artifact(job_id, f"{base_token}_html", html_path) if isinstance(html_path, Path) and html_path.exists() else ""
                md_url = _register_artifact(job_id, f"{base_token}_md", md_path) if isinstance(md_path, Path) and md_path.exists() else ""
                docx_url = _register_artifact(job_id, f"{base_token}_docx", docx_path) if isinstance(docx_path, Path) and docx_path.exists() else ""

                reports.append(
                    {
                        "doc_id": str(output.get("doc_id", source_file.stem)),
                        "title": str(output.get("title", source_file.stem)),
                        "task_count": len(output.get("tasks", [])) if isinstance(output.get("tasks"), list) else 0,
                        "html_url": html_url,
                        "md_url": md_url,
                        "docx_url": docx_url,
                        "ics_url": "",
                        "parser": parser_name,
                        "strategy": router_strategy,
                    }
                )

                draft_token = uuid.uuid4().hex[:12]
                cache_relative = to_relative_path(cache_path)
                draft_cache_map[draft_token] = cache_relative
                draft_source_map[draft_token] = to_relative_path(source_file)
                drafts.append(
                    _build_draft_payload(
                        draft_token=draft_token,
                        source_file=source_file,
                        cache_path=cache_path,
                        draft_output=output,
                    )
                )

                log_step(
                    LOGGER,
                    "ui.pipeline",
                    "UIConsole",
                    "DocumentDone",
                    (
                        f"job_id={job_id} doc_id={output.get('doc_id')} parser={parser_name} "
                        f"cache={to_relative_path(cache_path)} elapsed_sec={item.get('elapsed_sec', 0)}"
                    ),
                )

        finally:
            docs_logger.removeHandler(progress_handler)

        if not reports:
            raise RuntimeError("未生成任何报告草稿，请检查输入文件格式。")

        bundle_formats = [fmt for fmt, layout in report_layouts.items() if layout == "bundle"]
        bundle_reports: dict[str, str] = {}
        if len(draft_outputs) > 1 and bundle_formats:
            bundle_paths = await asyncio.to_thread(
                report_renderer.render_bundle_reports,
                data_items=draft_outputs,
                output_dir=report_dir,
                template_dir=TEMPLATE_DIR,
                bundle_formats=bundle_formats,
            )
            bundle_reports = _register_bundle_reports(job_id, bundle_paths)

        _update_job_step(job_id, 4, PIPELINE_STEPS[3])
        _update_job_file_progress(
            job_id,
            file_id="__job__",
            file_name="总体任务",
            file_percent=78,
            step_detail="草稿已生成，等待人工确认",
        )
        _update_job(
            job_id,
            status="pending_approval",
            progress=78,
            step_index=4,
            step_text="草稿已生成，等待人工确认",
            message="请先完成人工确认（含邮箱）再执行最终下发。",
            reports=reports,
            bundle_reports=bundle_reports,
            drafts=drafts,
            approval_locked=False,
            draft_cache_map=draft_cache_map,
            draft_source_map=draft_source_map,
            email_result=None,
        )
        log_step(
            LOGGER,
            "ui.pipeline",
            "UIConsole",
            "DraftPendingApproval",
            f"job_id={job_id} drafts={len(drafts)} reports={len(reports)} mode={mode}",
        )


def _process_job(
    job_id: str,
    api_key: str,
    llm_provider: str,
    model_name: str,
    email_file_types: list[str],
    report_layouts: dict[str, str],
    mode: str,
    source_files: list[Path],
    input_tab: str,
    crawl_url: str,
    crawl_count: int,
    crawl_keyword: str,
) -> None:
    try:
        asyncio.run(
            _process_job_async(
                job_id=job_id,
                api_key=api_key,
                llm_provider=llm_provider,
                model_name=model_name,
                report_layouts=report_layouts,
                mode=mode,
                source_files=source_files,
                input_tab=input_tab,
                crawl_url=crawl_url,
                crawl_count=crawl_count,
                crawl_keyword=crawl_keyword,
            )
        )
    except Exception as exc:  # pylint: disable=broad-except
        code, user_message = _classify_error(exc)
        _update_job(
            job_id,
            status="failed",
            progress=100,
            error=user_message,
            error_code=code,
            message="任务失败",
            file_id="__job__",
            file_name="总体任务",
            file_percent=100,
            step_detail=user_message,
        )
        for node_name in ("reader", "reviewer", "dispatcher"):
            _append_stream_event(
                job_id,
                node=node_name,
                event="error",
                content=f"任务失败：{user_message}",
                doc_id="__job__",
                agent=node_name.title(),
                file_id="__job__",
                file_name="总体任务",
            )
        LOGGER.exception(
            "STEP=ui.pipeline | AGENT=UIConsole | ACTION=JobFailed | DETAILS=job_id=%s error=%s trace=%s",
            job_id,
            exc,
            traceback.format_exc(),
        )


async def _process_single_approved_item(
    *,
    job_id: str,
    index: int,
    item: Mapping[str, Any],
    settings: Mapping[str, Any],
    orchestrator_worker: Orchestrator,
    report_dir: Path,
    draft_cache_map: Mapping[str, str],
    draft_source_map: Mapping[str, str],
) -> dict[str, Any]:
    draft_token = str(item.get("draft_token", "")).strip()
    if not draft_token or draft_token not in draft_cache_map:
        raise ValueError(f"invalid draft_token: {draft_token}")

    draft_json = item.get("draft_json")
    if not isinstance(draft_json, Mapping):
        raise ValueError(f"draft_json must be object for token={draft_token}")

    source_relative = str(draft_source_map.get(draft_token, "")).strip()
    source_file_name = Path(source_relative).name if source_relative else f"审批文档_{index}"
    _update_job_file_progress(
        job_id,
        file_id=source_file_name,
        file_name=source_file_name,
        file_percent=84,
        step_detail="已接收人工确认，开始执行下发",
    )

    approved_payload = dict(draft_json)
    approved_payload["status"] = "approved"
    approval = approved_payload.get("approval", {}) if isinstance(approved_payload.get("approval"), Mapping) else {}
    approval_payload = dict(approval)
    approval_payload["required"] = True
    approval_payload["approved_at"] = datetime.now().isoformat(timespec="seconds")
    approved_payload["approval"] = approval_payload

    _stream_sink = _build_stream_sink(
        job_id=job_id,
        default_doc_id=source_file_name,
        file_id=source_file_name,
        file_name=source_file_name,
        node_allowlist={"reader", "reviewer", "dispatcher"},
    )

    result = await orchestrator_worker.execute_dispatch_plan(
        draft_output=approved_payload,
        generate_calendar=True,
        save_calendar=True,
        dispatch_owner=None,
        stream_callback=_stream_sink,
    )

    cache_relative = str(draft_cache_map[draft_token]).strip()
    cache_path = PROJECT_ROOT / cache_relative
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    per_doc_formats = {"md", "html", "docx"}

    rendered_paths = await asyncio.to_thread(
        report_renderer.render_selected_reports_from_json,
        json_path=cache_path,
        output_dir=report_dir,
        template_dir=TEMPLATE_DIR,
        include_formats=sorted(per_doc_formats),
        section_index=index,
    )
    html_path = rendered_paths.get("html")
    md_path = rendered_paths.get("md")
    docx_path = rendered_paths.get("docx")

    calendar = result.get("calendar", {}) if isinstance(result.get("calendar"), Mapping) else {}
    ics_relative = str(calendar.get("ics_file", "")).strip()
    ics_path = (PROJECT_ROOT / ics_relative) if ics_relative else None

    base_token = uuid.uuid4().hex[:10]
    html_url = _register_artifact(job_id, f"{base_token}_html", html_path) if isinstance(html_path, Path) and html_path.exists() else ""
    md_url = _register_artifact(job_id, f"{base_token}_md", md_path) if isinstance(md_path, Path) and md_path.exists() else ""
    docx_url = _register_artifact(job_id, f"{base_token}_docx", docx_path) if isinstance(docx_path, Path) and docx_path.exists() else ""
    ics_url = ""
    if ics_path and ics_path.exists():
        ics_url = _register_artifact(job_id, f"{base_token}_ics", ics_path)

    source_file_name = source_file_name or str(result.get("doc_id", ""))
    report_payload = {
        "doc_id": str(result.get("doc_id", source_file_name)),
        "title": str(result.get("title", source_file_name)),
        "task_count": len(result.get("tasks", [])) if isinstance(result.get("tasks"), list) else 0,
        "html_url": html_url,
        "md_url": md_url,
        "docx_url": docx_url,
        "ics_url": ics_url,
        "parser": "approved_draft",
        "strategy": "human_approved_dispatch",
    }

    locked_draft_payload = _build_draft_payload(
        draft_token=draft_token,
        source_file=Path(source_relative) if source_relative else Path(f"{result.get('doc_id', 'unknown')}.txt"),
        cache_path=cache_path,
        draft_output=result,
    )
    locked_draft_payload["status"] = "approved"

    _update_job_file_progress(
        job_id,
        file_id=source_file_name,
        file_name=source_file_name,
        file_percent=100,
        step_detail="该文件已完成下发",
    )

    return {
        "index": index,
        "final_output": result,
        "report": report_payload,
        "locked_draft": locked_draft_payload,
    }


async def _execute_approval_job_async(job_id: str, modified_drafts: list[dict[str, Any]], recipient_emails: list[str]) -> None:
    # 1. 必须在所有逻辑开始前，先获取并验证 job 实例
    current_job = _get_job(job_id)
    if not current_job:
        return

    # 2. 现在可以安全定义模式相关的文案变量
    is_email = (current_job.mode == "email")
    step_desc = "正在执行下发..." if is_email else "正在完成最终解析..."
    msg_desc = "正在生成日历并准备发送邮件..." if is_email else "正在固化任务数据并生成最终产物..."

    # 3. 执行第一次状态更新
    _update_job(
        job_id,
        status="running",
        progress=84,
        step_index=4,
        step_text=f"已接收人工确认，{step_desc}",
        file_id="__job__",
        file_name="总体任务",
        file_percent=84,
        step_detail=f"审批已提交，{step_desc}",
        message=msg_desc,
    )

    with RUN_LOCK:
        log_file = _prepare_logger_for_job()
        _update_job(job_id, log_file=log_file)

        job_root = UI_JOB_ROOT / job_id
        if current_job is None:
            raise RuntimeError("job not found during approval stage")

        job_root = UI_JOB_ROOT / job_id
        cache_dir = job_root / "processed_cache"
        final_reports_dir = job_root / "final_reports"
        report_dir = final_reports_dir / "reports"
        for folder in (cache_dir, final_reports_dir, report_dir):
            folder.mkdir(parents=True, exist_ok=True)

        settings = _build_settings_for_job(
            api_key=current_job.api_key,
            llm_provider=current_job.llm_provider,
            job_root=job_root,
            model_name=current_job.llm_model,
        )
        shared_approval_client = build_client(settings, model_name=current_job.llm_model)
        approval_orchestrator_worker = Orchestrator(client=shared_approval_client, settings=settings, project_root=PROJECT_ROOT)

        reports: list[dict[str, Any]] = []
        final_outputs: list[Mapping[str, Any]] = []
        approved_drafts_locked: list[dict[str, Any]] = []
        draft_cache_map = dict(current_job.draft_cache_map)
        draft_source_map = dict(current_job.draft_source_map)
        report_layouts = dict(current_job.report_layouts or DEFAULT_REPORT_LAYOUTS)

        doc_results: list[dict[str, Any]] = []
        approval_items = [(index, item) for index, item in enumerate(modified_drafts, start=1) if isinstance(item, Mapping)]
        if approval_items:
            approval_worker_count = _resolve_parallel_workers(settings=settings, source_count=len(approval_items))
            log_step(
                LOGGER,
                "ui.pipeline",
                "UIConsole",
                "ParallelApprovalStart",
                f"job_id={job_id} workers={approval_worker_count} files={len(approval_items)}",
            )

            limit = asyncio.Semaphore(approval_worker_count)

            async def _run_with_limit(index: int, item: Mapping[str, Any]) -> dict[str, Any]:
                async with limit:
                    return await _process_single_approved_item(
                        job_id=job_id,
                        index=index,
                        item=item,
                        settings=settings,
                        orchestrator_worker=approval_orchestrator_worker,
                        report_dir=report_dir,
                        draft_cache_map=draft_cache_map,
                        draft_source_map=draft_source_map,
                    )

            tasks = [asyncio.create_task(_run_with_limit(index=index, item=item)) for index, item in approval_items]
            try:
                for done in asyncio.as_completed(tasks):
                    doc_results.append(await done)
            finally:
                for task in tasks:
                    if not task.done():
                        task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)

            log_step(
                LOGGER,
                "ui.pipeline",
                "UIConsole",
                "ParallelApprovalDone",
                f"job_id={job_id} workers={approval_worker_count} files={len(doc_results)}",
            )

        ordered_doc_results = sorted(doc_results, key=lambda result: int(result.get("index", 0)))
        for result_item in ordered_doc_results:
            final_outputs.append(result_item["final_output"])
            reports.append(result_item["report"])
            approved_drafts_locked.append(result_item["locked_draft"])

        if not reports:
            raise RuntimeError("no approved drafts were provided")

        bundle_formats = [fmt for fmt, layout in report_layouts.items() if layout == "bundle"]
        bundle_reports: dict[str, str] = {}
        if len(final_outputs) > 1 and bundle_formats:
            bundle_paths = await asyncio.to_thread(
                report_renderer.render_bundle_reports,
                data_items=final_outputs,
                output_dir=report_dir,
                template_dir=TEMPLATE_DIR,
                bundle_formats=bundle_formats,
            )
            bundle_reports = _register_bundle_reports(job_id, bundle_paths)

        email_result: dict[str, Any] | None = None
        if current_job.mode == "email":
            targets = recipient_emails if recipient_emails else list(current_job.recipient_emails)
            if not targets:
                raise ValueError("recipient_emails is required for email mode")

            send_results: list[dict[str, Any]] = []
            for recipient in targets:
                send_result = await asyncio.to_thread(
                    email_gateway.send_formal_reports_bundle,
                    recipient_email=recipient,
                    reports_dir=report_dir,
                    cache_dir=cache_dir,
                    attachment_types=current_job.email_file_types,
                    report_layouts=report_layouts,
                    settings=settings,
                )
                send_results.append(send_result)

            attachment_count = 0
            if send_results and isinstance(send_results[0], Mapping):
                attachment_count = int(send_results[0].get("attachment_count", 0))

            email_result = {
                "status": "sent",
                "to": "；".join(targets),
                "recipient_count": len(targets),
                "attachment_count": attachment_count,
                "results": send_results,
            }
        final_msg = "人工确认后的任务已完成下发。" if current_job.mode == "email" else "人工确认完成，最终产物已就绪。"
        _update_job(
            job_id,
            status="success",
            progress=100,
            step_index=4,
            step_text="处理完成",
            file_id="__job__",
            file_name="总体任务",
            file_percent=100,
            step_detail="人工确认后的任务已全部完成",
            message=final_msg,
            reports=reports,
            bundle_reports=bundle_reports,
            drafts=approved_drafts_locked,
            approval_locked=True,
            email_result=email_result,
        )

        log_step(
            LOGGER,
            "ui.pipeline",
            "UIConsole",
            "ApprovalDispatchDone",
            f"job_id={job_id} reports={len(reports)} email_sent={email_result is not None}",
        )


def _execute_approval_job(job_id: str, modified_drafts: list[dict[str, Any]], recipient_emails: list[str]) -> None:
    job = _get_job(job_id)
    if job is None:
        return

    try:
        asyncio.run(_execute_approval_job_async(job_id=job_id, modified_drafts=modified_drafts, recipient_emails=recipient_emails))
    except Exception as exc:  # pylint: disable=broad-except
        code, user_message = _classify_error(exc)
        _update_job(
            job_id,
            status="failed",
            progress=100,
            error=user_message,
            error_code=code,
            message="审批下发失败",
            file_id="__job__",
            file_name="总体任务",
            file_percent=100,
            step_detail=user_message,
        )
        _append_stream_event(
            job_id,
            node="dispatcher",
            event="error",
            content=f"审批下发失败：{user_message}",
            doc_id="__job__",
            agent="Dispatcher",
            file_id="__job__",
            file_name="总体任务",
        )
        LOGGER.exception(
            "STEP=ui.pipeline | AGENT=UIConsole | ACTION=ApproveFailed | DETAILS=job_id=%s error=%s trace=%s",
            job_id,
            exc,
            traceback.format_exc(),
        )


class UIConsoleHandler(BaseHTTPRequestHandler):
    server_version = "DocAgentUI/1.0"

    def end_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        super().end_headers()

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(200, "ok")
        self.end_headers()

    def _set_headers(self, status: HTTPStatus = HTTPStatus.OK, content_type: str = "application/json; charset=utf-8") -> None:
        self.send_response(status.value)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

    def _send_json(self, payload: Mapping[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        self._set_headers(status=status)
        self.wfile.write(_json_bytes(payload))

    def _send_file(self, file_path: Path) -> None:
        if not file_path.exists() or not file_path.is_file():
            self._send_json({"error": "file not found"}, status=HTTPStatus.NOT_FOUND)
            return

        content_type = mimetypes.guess_type(str(file_path))[0] or "application/octet-stream"
        if content_type.startswith("text/") or content_type in {"application/javascript", "application/json"}:
            content_type = f"{content_type}; charset=utf-8"
        self.send_response(HTTPStatus.OK.value)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(file_path.stat().st_size))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(file_path.read_bytes())

    def _serve_index(self) -> None:
        index_file = HTML_TEMPLATE_DIR / "index.html"
        self._send_file(index_file)

    def _serve_static(self, filename: str) -> None:
        safe_name = Path(filename).name
        file_path = HTML_TEMPLATE_DIR / safe_name
        self._send_file(file_path)

    def _handle_create_job(self) -> None:
        ctype, _ = cgi.parse_header(self.headers.get("Content-Type", ""))
        if ctype != "multipart/form-data":
            self._send_json({"error": "content type must be multipart/form-data"}, status=HTTPStatus.BAD_REQUEST)
            return

        form = cgi.FieldStorage(
            fp=self.rfile,
            headers=self.headers,
            environ={
                "REQUEST_METHOD": "POST",
                "CONTENT_TYPE": self.headers.get("Content-Type", ""),
            },
        )

        api_key = str(form.getfirst("api_key", "")).strip()
        try:
            llm_provider = _resolve_requested_llm_provider(str(form.getfirst("llm_provider", "deepseek")))
        except ValueError as exc:
            self._send_json(
                {
                    "error": str(exc),
                    "error_code": "unsupported_llm_provider",
                },
                status=HTTPStatus.BAD_REQUEST,
            )
            return
        model_name = _normalize_model_name(form.getfirst("model", ""))
        mode = str(form.getfirst("mode", "preview")).strip().lower()
        input_tab = str(form.getfirst("input_tab", "upload")).strip().lower()
        if input_tab not in {"upload", "paste", "crawl"}:
            input_tab = "upload"
        pasted_text_values = [str(item).strip() for item in form.getlist("pasted_text") if str(item).strip()]
        pasted_text_names = [str(item).strip() for item in form.getlist("pasted_text_name")]
        crawl_url = str(form.getfirst("crawl_url", "")).strip()
        crawl_keyword = str(form.getfirst("crawl_keyword", "")).strip()
        crawl_count = _normalize_crawl_count(form.getfirst("crawl_count", "5"))
        requested_email_file_types = _normalize_email_file_types(form.getlist("email_file_types"))
        report_layouts = _parse_report_layouts(form)

        if not api_key:
            self._send_json(
                {
                    "error": "api_key is required",
                    "error_code": "missing_api_key",
                },
                status=HTTPStatus.BAD_REQUEST,
            )
            return

        if mode not in {"preview", "email"}:
            mode = "preview"

        if mode == "email" and not requested_email_file_types:
            self._send_json(
                {
                    "error": "at least one email file type is required in email mode",
                    "error_code": "missing_email_file_types",
                },
                status=HTTPStatus.BAD_REQUEST,
            )
            return

        email_file_types = requested_email_file_types if requested_email_file_types else list(DEFAULT_EMAIL_FILE_TYPES)

        job_id = uuid.uuid4().hex
        upload_dir = UI_JOB_ROOT / job_id / "uploads"
        upload_dir.mkdir(parents=True, exist_ok=True)

        files = _save_uploaded_files(form=form, upload_dir=upload_dir)
        pasted_files = _create_files_from_pastes(
            upload_dir=upload_dir,
            pasted_texts=pasted_text_values,
            pasted_names=pasted_text_names,
        )
        files.extend(pasted_files)

        is_crawl_mode = input_tab == "crawl"
        if is_crawl_mode and not crawl_url:
            self._send_json(
                {
                    "error": "crawl_url is required when input_tab is crawl",
                    "error_code": "missing_crawl_url",
                },
                status=HTTPStatus.BAD_REQUEST,
            )
            return

        if not is_crawl_mode and not files:
            self._send_json(
                {
                    "error": "at least one file or pasted text is required",
                    "error_code": "missing_input",
                },
                status=HTTPStatus.BAD_REQUEST,
            )
            return

        source_count = 1 if is_crawl_mode else len(files)
        source_label = "网页抓取" if is_crawl_mode else f"{source_count} 份输入"

        job = JobState(
            job_id=job_id,
            mode=mode,
            llm_provider=llm_provider,
            llm_model=model_name,
            email_file_types=email_file_types,
            report_layouts=report_layouts,
            api_key=api_key,
            recipient_emails=[],
            created_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            message=f"已接收{source_label}，模型={llm_provider}，来源={input_tab or 'upload'}，排队处理中",
        )
        _save_job(job)

        worker = threading.Thread(
            target=_process_job,
            args=(
                job_id,
                api_key,
                llm_provider,
                model_name,
                email_file_types,
                report_layouts,
                mode,
                files,
                input_tab,
                crawl_url,
                crawl_count,
                crawl_keyword,
            ),
            daemon=True,
        )
        worker.start()

        accepted_files = [file.name for file in files]
        if is_crawl_mode and not accepted_files:
            accepted_files = ["(crawler)"]

        self._send_json(
            {
                "job_id": job_id,
                "status": job.status,
                "message": job.message,
                "llm_provider": llm_provider,
                "llm_model": model_name,
                "email_file_types": email_file_types,
                "report_layouts": report_layouts,
                "input_tab": input_tab,
                "input_files": accepted_files,
            },
            status=HTTPStatus.ACCEPTED,
        )

    def _handle_get_job(self, job_id: str) -> None:
        job = _get_job(job_id)
        if job is None:
            self._send_json({"error": "job not found"}, status=HTTPStatus.NOT_FOUND)
            return

        payload = _build_job_payload(job)
        self._send_json(payload)

    def _write_sse_event(self, event: str, payload: Mapping[str, Any]) -> None:
        self.wfile.write(f"event: {event}\n".encode("utf-8"))
        data = json.dumps(payload, ensure_ascii=False)
        for line in (data.splitlines() or [data]):
            self.wfile.write(f"data: {line}\n".encode("utf-8"))
        self.wfile.write(b"\n")
        self.wfile.flush()

    def _handle_job_events(self, job_id: str, from_seq: int = 0) -> None:
        if _get_job(job_id) is None:
            self._send_json({"error": "job not found"}, status=HTTPStatus.NOT_FOUND)
            return

        self.send_response(HTTPStatus.OK.value)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "keep-alive")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()

        last_snapshot = ""
        last_stream_seq = max(0, int(from_seq))
        try:
            while True:
                job = _get_job(job_id)
                if job is None:
                    self._write_sse_event("job", {"job_id": job_id, "status": "failed", "error": "job not found"})
                    return

                payload = _build_job_payload(job)
                snapshot = json.dumps(payload, ensure_ascii=False, sort_keys=True)
                had_updates = False
                if snapshot != last_snapshot:
                    self._write_sse_event("job", payload)
                    last_snapshot = snapshot
                    had_updates = True

                stream_updates, last_stream_seq = _get_stream_events_since(job_id, last_stream_seq)
                for event_payload in stream_updates:
                    self._write_sse_event("stream", event_payload)
                if stream_updates:
                    had_updates = True

                status = str(job.status).strip().lower()
                if status in TERMINAL_JOB_STATUSES:
                    return

                if stream_updates:
                    time.sleep(SSE_STREAM_PUSH_INTERVAL_SECONDS)
                elif had_updates:
                    time.sleep(min(SSE_PUSH_INTERVAL_SECONDS, 0.25))
                else:
                    time.sleep(SSE_PUSH_INTERVAL_SECONDS)
        except (BrokenPipeError, ConnectionResetError):
            return
        except Exception as exc:  # pylint: disable=broad-except
            LOGGER.warning(
                "STEP=ui.pipeline | AGENT=UIConsole | ACTION=SSEStreamError | DETAILS=job_id=%s error=%s",
                job_id,
                exc,
            )
            return

    def _handle_approve_task(self) -> None:
        try:
            payload = _read_json_body(self)
        except ValueError as exc:
            self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
            return

        job_id = str(payload.get("job_id", "")).strip()
        drafts = payload.get("drafts")
        recipient_emails = _normalize_recipient_emails(payload.get("recipient_emails", []))
        if not job_id:
            self._send_json({"error": "job_id is required"}, status=HTTPStatus.BAD_REQUEST)
            return
        if not isinstance(drafts, list) or not drafts:
            self._send_json({"error": "drafts is required and must be a non-empty array"}, status=HTTPStatus.BAD_REQUEST)
            return
        # 修改后（增加 job.mode 判断）：
        job = _get_job(job_id)
        if job and job.mode == "email" and not recipient_emails:
            self._send_json({
                "error": "recipient_emails is required and must contain valid email(s)",
                "error_code": "missing_recipient_emails",
            }, status=HTTPStatus.BAD_REQUEST)
            return

        job = _get_job(job_id)
        if job is None:
            self._send_json({"error": "job not found"}, status=HTTPStatus.NOT_FOUND)
            return
        if job.status != "pending_approval":
            self._send_json(
                {
                    "error": f"job status is '{job.status}', cannot approve now",
                    "error_code": "invalid_job_status",
                },
                status=HTTPStatus.CONFLICT,
            )
            return

        worker = threading.Thread(
            target=_execute_approval_job,
            args=(job_id, [item for item in drafts if isinstance(item, dict)], recipient_emails),
            daemon=True,
        )
        worker.start()

        _update_job(job_id, approval_locked=True, recipient_emails=recipient_emails)

        self._send_json(
            {
                "job_id": job_id,
                "status": "running",
                "message": "已接收人工确认，正在执行下发。",
            },
            status=HTTPStatus.ACCEPTED,
        )

    def _handle_get_artifact(self, job_id: str, token: str) -> None:
        job = _get_job(job_id)
        if job is None:
            self._send_json({"error": "job not found"}, status=HTTPStatus.NOT_FOUND)
            return

        relative = job.artifacts.get(token)
        if not relative:
            self._send_json({"error": "artifact not found"}, status=HTTPStatus.NOT_FOUND)
            return

        target = PROJECT_ROOT / relative
        self._send_file(target)

    def _handle_health(self) -> None:
        self._send_json({"status": "ok", "time": datetime.now().isoformat(timespec="seconds")})

    def _handle_llm_models(self) -> None:
        self._send_json(_build_llm_models_payload())

    def _handle_llm_test(self) -> None:
        try:
            payload = _read_json_body(self)
        except ValueError as exc:
            self._send_json({"ok": False, "error": str(exc), "error_code": "invalid_payload"}, status=HTTPStatus.BAD_REQUEST)
            return

        api_key = str(payload.get("api_key", "")).strip()
        if not api_key:
            self._send_json({"ok": False, "error": "api_key is required", "error_code": "missing_api_key"}, status=HTTPStatus.BAD_REQUEST)
            return

        try:
            provider = _resolve_requested_llm_provider(str(payload.get("provider", "deepseek")))
        except ValueError as exc:
            self._send_json({"ok": False, "error": str(exc), "error_code": "unsupported_llm_provider"}, status=HTTPStatus.BAD_REQUEST)
            return

        model_name = _normalize_model_name(payload.get("model", ""))
        try:
            result = asyncio.run(_run_llm_connection_test(api_key=api_key, provider=provider, model_name=model_name))
        except Exception as exc:  # pylint: disable=broad-except
            error_code, message = _classify_llm_test_error(exc)
            self._send_json(
                {
                    "ok": False,
                    "provider": provider,
                    "model": model_name or _get_provider_default_model(provider),
                    "error": message,
                    "error_code": error_code,
                    "detail": str(exc)[:500],
                },
                status=HTTPStatus.BAD_REQUEST,
            )
            return

        self._send_json(
            {
                "ok": True,
                "message": "模型连接测试通过。",
                **result,
            }
        )

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path

        if path in {"/", "/index.html"}:
            self._serve_index()
            return

        if path.startswith("/static/"):
            filename = path.split("/", 2)[-1]
            self._serve_static(filename)
            return

        if path == "/api/health":
            self._handle_health()
            return

        if path == "/api/llm/models":
            self._handle_llm_models()
            return

        if path.startswith("/api/jobs/"):
            parts = [item for item in path.split("/") if item]
            if len(parts) == 4 and parts[3] == "events":
                query = parse_qs(parsed.query)
                from_seq_raw = str(query.get("from_seq", ["0"])[0]).strip()
                try:
                    from_seq = max(0, int(from_seq_raw))
                except ValueError:
                    from_seq = 0
                self._handle_job_events(parts[2], from_seq=from_seq)
                return
            if len(parts) == 3:
                self._handle_get_job(parts[2])
                return
            if len(parts) == 5 and parts[3] == "artifacts":
                self._handle_get_artifact(parts[2], parts[4])
                return

        if path == "/api/log_tail":
            query = parse_qs(parsed.query)
            rel_path = str(query.get("path", [""])[0]).strip()
            if not rel_path:
                self._send_json({"error": "missing path"}, status=HTTPStatus.BAD_REQUEST)
                return
            target = PROJECT_ROOT / rel_path
            if not target.exists():
                self._send_json({"error": "log not found"}, status=HTTPStatus.NOT_FOUND)
                return
            lines = target.read_text(encoding="utf-8", errors="ignore").splitlines()
            self._send_json({"path": rel_path, "tail": lines[-80:]})
            return

        self._send_json({"error": "not found"}, status=HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/jobs":
            self._handle_create_job()
            return

        if path == "/api/llm/test":
            self._handle_llm_test()
            return

        if path in {"/approve_task", "/api/approve_task"}:
            self._handle_approve_task()
            return

        self._send_json({"error": "not found"}, status=HTTPStatus.NOT_FOUND)

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
        LOGGER.info("HTTP %s - %s", self.address_string(), format % args)


def run_server(host: str, port: int) -> None:
    if not HTML_TEMPLATE_DIR.exists():
        raise FileNotFoundError(f"html template directory not found: {HTML_TEMPLATE_DIR}")

    UI_JOB_ROOT.mkdir(parents=True, exist_ok=True)

    setup_logger(force_reconfigure=True)
    _start_rag_warmup_thread()
    bind_port = int(port)
    if bind_port < 1 or bind_port > 65535:
        raise ValueError(f"invalid ui port: {bind_port}")

    try:
        server = ThreadingHTTPServer((host, bind_port), UIConsoleHandler)
    except OSError as exc:
        winerror = getattr(exc, "winerror", None)
        errno = getattr(exc, "errno", None)
        LOGGER.error(
            "STEP=startup | AGENT=UIConsole | ACTION=BindFailed | DETAILS=host=%s port=%s winerror=%s errno=%s reason=%s",
            host,
            bind_port,
            winerror,
            errno,
            exc,
        )
        raise RuntimeError(
            "UI 服务无法绑定固定端口。"
            f"host={host}, port={bind_port}, detail={exc}. "
            "当前模式已禁用自动端口切换，请释放该端口或显式指定 --ui-port。"
        ) from exc

    bound_host, bound_port = server.server_address[:2]
    startup_url = f"http://{bound_host}:{bound_port}"
    log_step(LOGGER, "startup", "UIConsole", "ServerStart", f"url={startup_url}")
    print(f"[docs_agent] Frontend console is ready at: {startup_url}")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        log_step(LOGGER, "shutdown", "UIConsole", "ServerStop", "")
        server.server_close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Lightweight HTML console for docs_agent")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host")
    parser.add_argument("--port", type=int, default=DEFAULT_UI_PORT, help="Bind port")
    args = parser.parse_args()

    run_server(host=args.host, port=args.port)
