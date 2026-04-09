from __future__ import annotations

from dataclasses import dataclass
from html import escape as html_escape
import json
import logging
import smtplib
from email.header import Header
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr
from pathlib import Path
from typing import Any, Mapping

import yaml
from premailer import transform

from config.logger_setup import to_relative_path


LOGGER = logging.getLogger("docs_agent.email_gateway")
PROJECT_ROOT = Path(__file__).resolve().parent.parent
ICS_MIME_TYPE = "text/calendar; charset=utf-8; method=PUBLISH"
SUPPORTED_BUNDLE_ATTACHMENT_TYPES = {"md", "html", "docx", "ics"}
DEFAULT_BUNDLE_ATTACHMENT_TYPES = ["md", "html", "docx", "ics"]
SUPPORTED_REPORT_LAYOUTS = {"separate", "bundle"}
ATTACHMENT_TYPE_DISPLAY = {
	"md": "Markdown",
	"html": "HTML",
	"docx": "Word",
	"ics": "ICS",
}


@dataclass
class EmailAttachment:
	file_path: Path
	mime_type: str = "application/octet-stream"
	filename: str = ""


def _safe_text(value: Any, fallback: str = "") -> str:
	text = str(value).strip() if value is not None else ""
	return text or fallback


def _load_settings_from_file(settings_path: Path) -> dict[str, Any]:
	if not settings_path.exists():
		raise FileNotFoundError(f"settings file not found: {settings_path}")
	loaded = yaml.safe_load(settings_path.read_text(encoding="utf-8")) or {}
	if not isinstance(loaded, dict):
		raise ValueError("settings.yaml must contain a YAML object at top level.")
	return loaded


def _resolve_settings(
	settings: Mapping[str, Any] | None = None,
	settings_path: str | Path | None = None,
) -> dict[str, Any]:
	if settings is not None:
		return dict(settings)

	path = Path(settings_path) if settings_path else PROJECT_ROOT / "config" / "settings.yaml"
	if not path.is_absolute():
		path = PROJECT_ROOT / path
	return _load_settings_from_file(path)


def _resolve_recipient(owner: str, contacts: Mapping[str, Any]) -> str:
	owner_text = _safe_text(owner)
	if owner_text and owner_text in contacts:
		return _safe_text(contacts.get(owner_text))

	for key, value in contacts.items():
		key_text = _safe_text(key)
		if not key_text or key_text == "默认":
			continue
		if key_text in owner_text or owner_text in key_text:
			return _safe_text(value)

	return _safe_text(contacts.get("默认"))


def inline_css_for_email(html_content: str) -> str:
	"""Convert <style> rules into inline style attributes for better email compatibility."""
	try:
		return transform(
			html_content,
			remove_classes=False,
			keep_style_tags=False,
			disable_leftover_css=False,
		)
	except Exception as exc:  # pylint: disable=broad-except
		LOGGER.warning("STEP=email.gateway | AGENT=EmailGateway | ACTION=InlineCssFallback | DETAILS=reason=%s", exc.__class__.__name__)
		return html_content


def prepare_email_html_from_file(report_html_path: Path) -> str:
	html_content = report_html_path.read_text(encoding="utf-8")
	return inline_css_for_email(html_content)


def _resolve_attachment_path(path_value: str | Path) -> Path:
	path = Path(path_value)
	return path if path.is_absolute() else PROJECT_ROOT / path


def build_attachments_from_agent_output(
	agent_output: Mapping[str, Any],
	extra_attachments: list[EmailAttachment] | None = None,
) -> list[EmailAttachment]:
	"""Build attachment list and auto-include .ics calendar when available."""
	attachments: list[EmailAttachment] = []
	seen: set[str] = set()

	for item in extra_attachments or []:
		path = _resolve_attachment_path(item.file_path)
		key = str(path).lower()
		if key in seen:
			continue
		seen.add(key)
		mime = item.mime_type
		if path.suffix.lower() == ".ics" and mime == "application/octet-stream":
			mime = ICS_MIME_TYPE
		attachments.append(EmailAttachment(file_path=path, mime_type=mime, filename=item.filename))

	calendar = agent_output.get("calendar", {}) if isinstance(agent_output.get("calendar"), Mapping) else {}
	ics_file = str(calendar.get("ics_file", "")).strip()
	event_count_raw = calendar.get("event_count", 0)
	try:
		event_count = int(event_count_raw)
	except (TypeError, ValueError):
		event_count = 0

	candidate_path: Path | None = None
	if ics_file:
		candidate_path = _resolve_attachment_path(ics_file)
	elif event_count > 0:
		doc_id = str(agent_output.get("doc_id", "")).strip()
		if doc_id:
			candidate_path = PROJECT_ROOT / "data_workspace" / "final_reports" / f"{doc_id}.ics"

	if candidate_path and candidate_path.exists():
		key = str(candidate_path).lower()
		if key not in seen:
			seen.add(key)
			attachments.append(
				EmailAttachment(
					file_path=candidate_path,
					mime_type=ICS_MIME_TYPE,
					filename=candidate_path.name,
				)
			)

	return attachments


def build_email_payload(
	subject: str,
	html_content: str,
	to_addresses: list[str],
	attachments: list[EmailAttachment] | None = None,
	plain_text: str = "",
	agent_output: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
	"""Build a transport-agnostic payload. Actual SMTP/API sending can consume this payload."""
	items = build_attachments_from_agent_output(agent_output=agent_output, extra_attachments=attachments) if agent_output else (attachments or [])
	normalized_attachments: list[dict[str, str]] = []
	for item in items:
		abs_path = _resolve_attachment_path(item.file_path)
		mime = item.mime_type
		if abs_path.suffix.lower() == ".ics" and mime == "application/octet-stream":
			mime = ICS_MIME_TYPE
		normalized_attachments.append(
			{
				"path": to_relative_path(abs_path),
				"filename": item.filename.strip() or abs_path.name,
				"mime_type": mime,
				"disposition": "attachment",
			}
		)

	return {
		"subject": subject,
		"to": [addr.strip() for addr in to_addresses if addr.strip()],
		"html": inline_css_for_email(html_content),
		"text": plain_text.strip(),
		"attachments": normalized_attachments,
	}


def _attach_binary_file(message: MIMEMultipart, file_path: Path, filename: str = "") -> None:
	payload = MIMEApplication(file_path.read_bytes())
	attach_name = _safe_text(filename, fallback=file_path.name)
	payload.add_header("Content-Disposition", f"attachment; filename=\"{attach_name}\"")
	message.attach(payload)


def send_report(
	owner: str,
	report_html_path: str | Path,
	source_file_path: str | Path,
	ics_file_path: str | Path | None = None,
	subject: str = "",
	settings: Mapping[str, Any] | None = None,
	settings_path: str | Path | None = None,
) -> dict[str, Any]:
	"""Send rendered report email with HTML body and attachments (ics + source file)."""
	cfg = _resolve_settings(settings=settings, settings_path=settings_path)
	email_cfg = cfg.get("email", {}) if isinstance(cfg.get("email"), Mapping) else {}
	contacts = cfg.get("contacts", {}) if isinstance(cfg.get("contacts"), Mapping) else {}

	smtp_server = _safe_text(email_cfg.get("smtp_server"))
	smtp_port = int(email_cfg.get("smtp_port", 465))
	sender_email = _safe_text(email_cfg.get("sender_email"))
	sender_name = _safe_text(email_cfg.get("sender_name"), fallback="公文速阅智能体")
	auth_code = _safe_text(email_cfg.get("auth_code"))
	timeout_seconds = int(email_cfg.get("timeout_seconds", 30))

	if not smtp_server or not sender_email or not auth_code:
		raise ValueError("email settings incomplete: smtp_server/sender_email/auth_code are required")

	recipient = _resolve_recipient(owner=owner, contacts=contacts)
	if not recipient:
		raise ValueError(f"No recipient matched for owner='{owner}', and contacts.默认 is empty")

	html_path = _resolve_attachment_path(report_html_path)
	if not html_path.exists():
		raise FileNotFoundError(f"HTML report not found: {html_path}")
	html_text = inline_css_for_email(html_path.read_text(encoding="utf-8"))

	source_path = _resolve_attachment_path(source_file_path)
	if not source_path.exists():
		raise FileNotFoundError(f"Source document not found: {source_path}")

	ics_path: Path | None = None
	if ics_file_path:
		candidate = _resolve_attachment_path(ics_file_path)
		if candidate.exists():
			ics_path = candidate

	subject_text = _safe_text(subject, fallback=f"[公文速阅] {_safe_text(owner, fallback='任务提醒')}")
	message = MIMEMultipart("mixed")
	message["From"] = formataddr((sender_name, sender_email))
	message["To"] = recipient
	message["Subject"] = str(Header(subject_text, "utf-8"))
	message.attach(MIMEText(html_text, "html", "utf-8"))

	attachments: list[str] = []
	if ics_path is not None:
		_attach_binary_file(message=message, file_path=ics_path, filename=ics_path.name)
		attachments.append(to_relative_path(ics_path))

	_attach_binary_file(message=message, file_path=source_path, filename=source_path.name)
	attachments.append(to_relative_path(source_path))

	LOGGER.info(
		"STEP=email.gateway | AGENT=EmailGateway | ACTION=SendStart | DETAILS=owner=%s to=%s subject=%s html=%s",
		_safe_text(owner, fallback="默认"),
		recipient,
		subject_text,
		to_relative_path(html_path),
	)

	with smtplib.SMTP_SSL(smtp_server, smtp_port, timeout=timeout_seconds) as smtp:
		smtp.login(sender_email, auth_code)
		smtp.sendmail(sender_email, [recipient], message.as_string())

	LOGGER.info(
		"STEP=email.gateway | AGENT=EmailGateway | ACTION=SendDone | DETAILS=to=%s attachments=%s",
		recipient,
		attachments,
	)

	return {
		"status": "sent",
		"owner": _safe_text(owner, fallback="默认"),
		"to": recipient,
		"subject": subject_text,
		"html": to_relative_path(html_path),
		"attachments": attachments,
	}


def _load_notice_summaries(cache_dir: Path) -> list[dict[str, Any]]:
	def _normalize_deadline(task: Mapping[str, Any]) -> str:
		deadline_display = _safe_text(task.get("deadline_display"))
		if deadline_display:
			return deadline_display

		deadline = _safe_text(task.get("deadline"))
		if deadline:
			return deadline

		start = _safe_text(task.get("deadline_start"))
		end = _safe_text(task.get("deadline_end"))
		if start and end:
			return start if start == end else f"{start} 至 {end}"
		if start:
			return start
		if end:
			return end
		return "未提及"

	items: list[dict[str, Any]] = []
	for json_file in sorted(cache_dir.glob("*.agent.json")):
		try:
			payload = json.loads(json_file.read_text(encoding="utf-8"))
		except Exception:  # pylint: disable=broad-except
			continue

		if not isinstance(payload, Mapping):
			continue

		title = _safe_text(payload.get("title"), fallback=_safe_text(payload.get("doc_id"), fallback=json_file.stem))
		summary_raw = _safe_text(payload.get("summary"), fallback="未提及")
		summary = " ".join(line.strip() for line in summary_raw.splitlines() if line.strip())
		if len(summary) > 220:
			summary = f"{summary[:220].rstrip()}..."

		tasks_raw = payload.get("tasks") if isinstance(payload.get("tasks"), list) else []
		tasks: list[dict[str, str]] = []
		for task in tasks_raw:
			if not isinstance(task, Mapping):
				continue
			description_raw = _safe_text(
				task.get("task_name"),
				fallback=_safe_text(task.get("action_suggestion"), fallback="未提取任务描述"),
			)
			description = " ".join(line.strip() for line in description_raw.splitlines() if line.strip())
			if len(description) > 140:
				description = f"{description[:140].rstrip()}..."
			tasks.append(
				{
					"description": description or "未提取任务描述",
					"deadline": _normalize_deadline(task),
				}
			)

		items.append(
			{
				"title": title,
				"summary": summary or "未提及",
				"tasks": tasks,
			}
		)

	return items


def _build_formal_bundle_body(
	notices: list[dict[str, Any]],
	attachment_count: int,
	attachment_breakdown: str,
) -> tuple[str, str]:
	if not notices:
		notices = [
			{
				"title": "未识别通知标题",
				"summary": "未提取到核心摘要",
				"tasks": [{"description": "未提取任务描述", "deadline": "未提及"}],
			}
		]

	html_notice_rows: list[str] = []
	for item in notices:
		title = html_escape(_safe_text(item.get("title"), fallback="未识别通知标题"))
		summary = html_escape(_safe_text(item.get("summary"), fallback="未提及"))
		tasks = item.get("tasks") if isinstance(item.get("tasks"), list) else []
		if not tasks:
			tasks = [{"description": "未提取任务描述", "deadline": "未提及"}]

		task_rows = "\n".join(
			f"<li><strong>任务简述：</strong>{html_escape(_safe_text(task.get('description'), fallback='未提取任务描述'))}"
			f"<br/><strong>Deadline：</strong>{html_escape(_safe_text(task.get('deadline'), fallback='未提及'))}</li>"
			for task in tasks
			if isinstance(task, Mapping)
		)
		if not task_rows:
			task_rows = "<li><strong>任务简述：</strong>未提取任务描述<br/><strong>Deadline：</strong>未提及</li>"

		html_notice_rows.append(
			f"<li><strong>通知标题：</strong>{title}<br/><strong>核心摘要：</strong>{summary}<br/><strong>任务清单：</strong><ul>{task_rows}</ul></li>"
		)

	html_rows = "\n".join(html_notice_rows)
	html_body = (
		"<p>您好：</p>"
		"<p>现将本次公文速阅结果报送如下，请审阅。</p>"
		"<p><strong>通知概览</strong></p>"
		f"<ol>{html_rows}</ol>"
		f"<p>本邮件附件共 {attachment_count} 份（{attachment_breakdown}）。</p>"
		"<p>此致<br/>敬礼</p>"
		"<p>公文速阅智能体</p>"
	)

	text_lines = [
		"您好：",
		"",
		"现将本次公文速阅结果报送如下，请审阅。",
		"",
		"通知概览：",
	]
	for idx, item in enumerate(notices, start=1):
		title = _safe_text(item.get("title"), fallback="未识别通知标题")
		summary = _safe_text(item.get("summary"), fallback="未提及")
		tasks = item.get("tasks") if isinstance(item.get("tasks"), list) else []
		if not tasks:
			tasks = [{"description": "未提取任务描述", "deadline": "未提及"}]

		text_lines.append(f"{idx}. 通知标题：{title}")
		text_lines.append(f"   核心摘要：{summary}")
		text_lines.append("   任务清单：")
		for t_idx, task in enumerate(tasks, start=1):
			if not isinstance(task, Mapping):
				continue
			description = _safe_text(task.get("description"), fallback="未提取任务描述")
			deadline = _safe_text(task.get("deadline"), fallback="未提及")
			text_lines.append(f"     {idx}.{t_idx} 任务简述：{description}")
			text_lines.append(f"          Deadline：{deadline}")
	text_lines.extend(
		[
			"",
			f"本邮件附件共 {attachment_count} 份（{attachment_breakdown}）。",
			"",
			"此致",
			"敬礼",
			"",
			"公文速阅智能体",
		]
	)

	return html_body, "\n".join(text_lines)


def _normalize_bundle_attachment_types(attachment_types: list[str] | None) -> list[str]:
	if not attachment_types:
		return list(DEFAULT_BUNDLE_ATTACHMENT_TYPES)

	normalized: list[str] = []
	for item in attachment_types:
		key = str(item).strip().lower()
		if key not in SUPPORTED_BUNDLE_ATTACHMENT_TYPES:
			continue
		if key in normalized:
			continue
		normalized.append(key)

	return normalized or list(DEFAULT_BUNDLE_ATTACHMENT_TYPES)


def _build_attachment_breakdown(type_counts: Mapping[str, int], ordered_types: list[str]) -> str:
	parts: list[str] = []
	for key in ordered_types:
		label = ATTACHMENT_TYPE_DISPLAY.get(key, key.upper())
		parts.append(f"{int(type_counts.get(key, 0))} 份 {label}")
	return " + ".join(parts)


def _normalize_report_layouts(report_layouts: Mapping[str, Any] | None) -> dict[str, str]:
	layouts = {"md": "separate", "html": "separate", "docx": "bundle"}
	if not isinstance(report_layouts, Mapping):
		return layouts
	for fmt in layouts:
		value = str(report_layouts.get(fmt, "separate")).strip().lower()
		layouts[fmt] = value if value in SUPPORTED_REPORT_LAYOUTS else "separate"
	return layouts


def _pick_latest_bundle_file(reports_dir: Path, suffix: str) -> Path | None:
	candidates = sorted(reports_dir.glob(f"公文速阅报告_*.{suffix}"), key=lambda item: item.stat().st_mtime, reverse=True)
	return candidates[0] if candidates else None


def send_formal_reports_bundle(
	recipient_email: str,
	reports_dir: str | Path | None = None,
	cache_dir: str | Path | None = None,
	subject: str = "公文速阅报告报送",
	attachment_types: list[str] | None = None,
	report_layouts: Mapping[str, Any] | None = None,
	settings: Mapping[str, Any] | None = None,
	settings_path: str | Path | None = None,
) -> dict[str, Any]:
	"""Send one formal bundle email with report attachments and readable notice summaries."""
	cfg = _resolve_settings(settings=settings, settings_path=settings_path)
	email_cfg = cfg.get("email", {}) if isinstance(cfg.get("email"), Mapping) else {}

	smtp_server = _safe_text(email_cfg.get("smtp_server"))
	smtp_port = int(email_cfg.get("smtp_port", 465))
	sender_email = _safe_text(email_cfg.get("sender_email"))
	sender_name = _safe_text(email_cfg.get("sender_name"), fallback="公文速阅智能体")
	auth_code = _safe_text(email_cfg.get("auth_code"))
	timeout_seconds = int(email_cfg.get("timeout_seconds", 30))

	if not smtp_server or not sender_email or not auth_code:
		raise ValueError("email settings incomplete: smtp_server/sender_email/auth_code are required")

	receiver = _safe_text(recipient_email)
	if not receiver:
		raise ValueError("recipient_email is required")

	resolved_reports_dir = _resolve_attachment_path(reports_dir or (PROJECT_ROOT / "data_workspace" / "final_reports" / "reports"))
	resolved_cache_dir = _resolve_attachment_path(cache_dir or (PROJECT_ROOT / "data_workspace" / "processed_cache"))
	resolved_final_reports_dir = resolved_reports_dir.parent
	selected_types = _normalize_bundle_attachment_types(attachment_types)
	report_layout_mode = _normalize_report_layouts(report_layouts)

	md_files: list[Path] = []
	html_files: list[Path] = []
	docx_files: list[Path] = []
	if "md" in selected_types:
		if report_layout_mode.get("md") == "bundle":
			bundle = _pick_latest_bundle_file(resolved_reports_dir, "md")
			md_files = [bundle] if bundle else sorted(resolved_reports_dir.glob("*.report.md"))
		else:
			md_files = sorted(resolved_reports_dir.glob("*.report.md"))

	if "html" in selected_types:
		if report_layout_mode.get("html") == "bundle":
			bundle = _pick_latest_bundle_file(resolved_reports_dir, "html")
			html_files = [bundle] if bundle else sorted(resolved_reports_dir.glob("*.report.html"))
		else:
			html_files = sorted(resolved_reports_dir.glob("*.report.html"))

	if "docx" in selected_types:
		if report_layout_mode.get("docx") == "bundle":
			bundle = _pick_latest_bundle_file(resolved_reports_dir, "docx")
			docx_files = [bundle] if bundle else sorted(resolved_reports_dir.glob("*.docx"))
		else:
			docx_files = sorted(resolved_reports_dir.glob("*.docx"))
	ics_files = sorted(resolved_final_reports_dir.glob("*.ics")) if "ics" in selected_types else []
	attachments = md_files + html_files + docx_files + ics_files

	if not attachments:
		raise ValueError("No selected attachments found for the current email file type choices")

	notices = _load_notice_summaries(resolved_cache_dir)
	type_counts = {
		"md": len(md_files),
		"html": len(html_files),
		"docx": len(docx_files),
		"ics": len(ics_files),
	}
	attachment_breakdown = _build_attachment_breakdown(type_counts=type_counts, ordered_types=selected_types)
	html_body, text_body = _build_formal_bundle_body(
		notices=notices,
		attachment_count=len(attachments),
		attachment_breakdown=attachment_breakdown,
	)

	message = MIMEMultipart("mixed")
	message["From"] = formataddr((sender_name, sender_email))
	message["To"] = receiver
	message["Subject"] = str(Header(_safe_text(subject, fallback="公文速阅报告报送"), "utf-8"))

	alt = MIMEMultipart("alternative")
	alt.attach(MIMEText(text_body, "plain", "utf-8"))
	alt.attach(MIMEText(inline_css_for_email(html_body), "html", "utf-8"))
	message.attach(alt)

	attachment_names: list[str] = []
	for file_path in attachments:
		if file_path.suffix.lower() == ".ics":
			payload = MIMEText(file_path.read_text(encoding="utf-8"), "calendar", "utf-8")
			payload.replace_header("Content-Type", ICS_MIME_TYPE)
		else:
			payload = MIMEApplication(file_path.read_bytes())
		payload.add_header("Content-Disposition", "attachment", filename=("utf-8", "", file_path.name))
		message.attach(payload)
		attachment_names.append(file_path.name)

	LOGGER.info(
		"STEP=email.gateway | AGENT=EmailGateway | ACTION=BundleSendStart | DETAILS=to=%s reports_dir=%s cache_dir=%s selected_types=%s",
		receiver,
		to_relative_path(resolved_reports_dir),
		to_relative_path(resolved_cache_dir),
		selected_types,
	)

	with smtplib.SMTP_SSL(smtp_server, smtp_port, timeout=timeout_seconds) as smtp:
		smtp.login(sender_email, auth_code)
		smtp.sendmail(sender_email, [receiver], message.as_string())

	LOGGER.info(
		"STEP=email.gateway | AGENT=EmailGateway | ACTION=BundleSendDone | DETAILS=to=%s attachments=%s",
		receiver,
		len(attachment_names),
	)

	return {
		"status": "sent",
		"to": receiver,
		"subject": _safe_text(subject, fallback="公文速阅报告报送"),
		"attachment_count": len(attachment_names),
		"attachment_types_selected": selected_types,
		"report_layouts": report_layout_mode,
		"attachment_type_counts": type_counts,
		"ics_count": len(ics_files),
		"attachments": attachment_names,
		"notice_count": len(notices),
	}
