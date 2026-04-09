from __future__ import annotations

import datetime as dt
import re
from typing import Any, Mapping


URGENT_KEYWORDS: dict[str, int] = {
	"立即": 16,
	"立刻": 16,
	"尽快": 12,
	"务必": 10,
	"严禁": 12,
	"必须": 9,
	"刻不容缓": 18,
	"从严": 8,
	"限期": 10,
}


def _parse_deadline(deadline: str, today: dt.date) -> tuple[dt.date | None, str]:
	value = str(deadline).strip()
	if value in {"长期有效", "按需执行", "未提及", "无", ""}:
		return None, value or "未提及"

	full = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", value)
	if full:
		year, month, day = map(int, full.groups())
		return dt.date(year, month, day), value

	month_only = re.match(r"^(\d{4})-(\d{2})$", value)
	if month_only:
		year, month = map(int, month_only.groups())
		# For month-level deadlines, use the month-end as the conservative due date.
		if month == 12:
			next_month = dt.date(year + 1, 1, 1)
		else:
			next_month = dt.date(year, month + 1, 1)
		return next_month - dt.timedelta(days=1), value

	only_year = re.match(r"^(\d{4})$", value)
	if only_year:
		year = int(only_year.group(1))
		return dt.date(year, 12, 31), value

	return None, value


def _keyword_score(text: str) -> int:
	score = 0
	for keyword, weight in URGENT_KEYWORDS.items():
		count = text.count(keyword)
		score += count * weight
	return min(score, 40)


def _deadline_score(deadline_date: dt.date | None, deadline_text: str, today: dt.date) -> int:
	if deadline_date is None:
		if deadline_text in {"长期有效", "按需执行"}:
			return 8
		return 0

	days_left = (deadline_date - today).days
	if days_left <= 0:
		return 65
	if days_left <= 1:
		return 55
	if days_left <= 3:
		return 45
	if days_left <= 7:
		return 35
	if days_left <= 15:
		return 22
	if days_left <= 30:
		return 12
	return 4


def evaluate_task_urgency(task: Mapping[str, Any], today: dt.date | None = None) -> dict[str, Any]:
	reference = today or dt.date.today()
	deadline_start = str(task.get("deadline_start", "")).strip()
	if deadline_start in {"", "无", "未提及"}:
		deadline_raw = str(task.get("deadline", "未提及"))
	else:
		deadline_raw = deadline_start
	deadline_date, deadline_text = _parse_deadline(deadline_raw, reference)

	if deadline_date is None:
		return {
			"score": 0,
			"level": "NONE",
			"color": "gray",
			"label": "长效制度",
			"days_left": None,
			"reference_date": reference.isoformat(),
		}

	text_for_keywords = "\n".join(
		[
			str(task.get("task_name", "")),
			str(task.get("action_suggestion", "")),
			" ".join(str(item) for item in task.get("deliverables", [])) if isinstance(task.get("deliverables"), list) else "",
		]
	)

	date_score = _deadline_score(deadline_date, deadline_text, reference)
	kw_score = _keyword_score(text_for_keywords)
	total_score = min(100, date_score + kw_score)

	if total_score >= 70:
		level = "HIGH"
		color = "red"
		label = "特急"
	elif total_score >= 40:
		level = "MEDIUM"
		color = "yellow"
		label = "紧急"
	else:
		level = "LOW"
		color = "green"
		label = "常规"

	return {
		"score": total_score,
		"level": level,
		"color": color,
		"label": label,
		"days_left": (deadline_date - reference).days if deadline_date else None,
		"reference_date": reference.isoformat(),
	}


def annotate_tasks_with_urgency(tasks: list[dict[str, Any]], today: dt.date | None = None) -> list[dict[str, Any]]:
	annotated: list[dict[str, Any]] = []
	for task in tasks:
		item = dict(task)
		item["urgency"] = evaluate_task_urgency(item, today=today)
		annotated.append(item)

	return sorted(
		annotated,
		key=lambda task: int(task.get("urgency", {}).get("score", 0)),
		reverse=True,
	)


def summarize_urgency(tasks: list[Mapping[str, Any]]) -> dict[str, int]:
	count = {"HIGH": 0, "MEDIUM": 0, "LOW": 0, "NONE": 0}
	for task in tasks:
		level = str(task.get("urgency", {}).get("level", "LOW")).upper()
		if level not in count:
			continue
		count[level] += 1
	return count

