from __future__ import annotations

import datetime as dt
import hashlib
from pathlib import Path
from typing import Any, Mapping


def _escape_ics_text(value: str) -> str:
	text = value.replace("\\", "\\\\")
	text = text.replace(";", "\\;").replace(",", "\\,")
	text = text.replace("\n", "\\n")
	return text


def _parse_deadline_to_date(deadline: str) -> dt.date | None:
	value = str(deadline).strip()
	if value in {"", "无", "未提及", "长期有效", "按需执行"}:
		return None

	try:
		if len(value) == 10:
			return dt.datetime.strptime(value, "%Y-%m-%d").date()
		if len(value) == 7:
			month_start = dt.datetime.strptime(value, "%Y-%m").date()
			if month_start.month == 12:
				next_month = dt.date(month_start.year + 1, 1, 1)
			else:
				next_month = dt.date(month_start.year, month_start.month + 1, 1)
			return next_month - dt.timedelta(days=1)
		if len(value) == 4:
			return dt.date(int(value), 12, 31)
	except ValueError:
		return None

	return None


def _build_uid(doc_id: str, task_id: str, start_date: dt.date, end_date: dt.date) -> str:
	raw = f"{doc_id}|{task_id}|{start_date.isoformat()}|{end_date.isoformat()}"
	digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()  # noqa: S324
	return f"{digest[:16]}@docs-agent"


def build_ics_from_tasks(
	tasks: list[Mapping[str, Any]],
	doc_id: str,
	calendar_name: str = "Docs Agent Tasks",
) -> tuple[str, list[dict[str, Any]]]:
	"""Create ICS content from task list and return (ics_text, event_summaries)."""
	now_utc = dt.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
	lines = [
		"BEGIN:VCALENDAR",
		"VERSION:2.0",
		"PRODID:-//docs_agent//task_calendar//CN",
		"CALSCALE:GREGORIAN",
		"METHOD:PUBLISH",
		f"X-WR-CALNAME:{_escape_ics_text(calendar_name)}",
	]

	events: list[dict[str, Any]] = []

	for idx, task in enumerate(tasks, start=1):
		deadline_raw = str(task.get("deadline", ""))
		deadline_start_raw = str(task.get("deadline_start", ""))
		deadline_end_raw = str(task.get("deadline_end", ""))
		deadline_display = str(task.get("deadline_display", "")).strip() or deadline_raw

		start_date = _parse_deadline_to_date(deadline_start_raw) or _parse_deadline_to_date(deadline_raw)
		end_date = _parse_deadline_to_date(deadline_end_raw) or _parse_deadline_to_date(deadline_raw)
		if start_date is None and end_date is None:
			continue
		if start_date is None:
			start_date = end_date
		if end_date is None:
			end_date = start_date
		if start_date is None or end_date is None:
			continue
		if end_date < start_date:
			start_date, end_date = end_date, start_date

		task_id = str(task.get("task_id", f"task_{idx:03d}"))
		task_name = str(task.get("task_name", "待办事项"))
		owner = str(task.get("owner", "相关责任部门"))
		urgency_label = str(task.get("urgency", {}).get("label", "常规"))

		dtstart = start_date.strftime("%Y%m%d")
		dtend = (end_date + dt.timedelta(days=1)).strftime("%Y%m%d")
		summary = f"[{urgency_label}] {task_name}"
		description = (
			f"责任人: {owner}\\n"
			f"截止: {deadline_display}\\n"
			f"任务ID: {task_id}\\n"
			f"来源文档: {doc_id}"
		)
		uid = _build_uid(doc_id=doc_id, task_id=task_id, start_date=start_date, end_date=end_date)

		lines.extend(
			[
				"BEGIN:VEVENT",
				f"UID:{uid}",
				f"DTSTAMP:{now_utc}",
				f"DTSTART;VALUE=DATE:{dtstart}",
				f"DTEND;VALUE=DATE:{dtend}",
				f"SUMMARY:{_escape_ics_text(summary)}",
				f"DESCRIPTION:{_escape_ics_text(description)}",
				"END:VEVENT",
			]
		)

		events.append(
			{
				"task_id": task_id,
				"task_name": task_name,
				"deadline": deadline_display,
				"deadline_start": start_date.isoformat(),
				"deadline_end": end_date.isoformat(),
				"owner": owner,
				"uid": uid,
			}
		)

	lines.append("END:VCALENDAR")
	return "\r\n".join(lines) + "\r\n", events


def save_ics_file(ics_text: str, output_path: str | Path) -> Path:
	path = Path(output_path)
	path.parent.mkdir(parents=True, exist_ok=True)
	path.write_text(ics_text, encoding="utf-8")
	return path

