from __future__ import annotations

import datetime as dt
import json
import logging
import re
from collections import OrderedDict
from typing import Any, Callable, Mapping, Protocol


class DispatcherClientProtocol(Protocol):
	async def chat_completion(
		self,
		messages: list[dict[str, str]],
		response_format: Mapping[str, Any] | None = None,
		temperature: float | None = None,
		max_tokens: int | None = None,
		stream: bool = False,
		stream_callback: Callable[[str], Any] | None = None,
	) -> dict[str, Any]:
		...

	def get_message_content(self, response_json: Mapping[str, Any]) -> str:
		...


class DispatcherAgent:
	"""Generate communication-oriented outputs for reminders and distribution."""

	def __init__(self, client: DispatcherClientProtocol, json_retry_times: int = 1) -> None:
		self.client = client
		self.json_retry_times = max(0, json_retry_times)
		self.logger = logging.getLogger("docs_agent.agent_dispatcher")

	async def dispatch(
		self,
		reviewed_output: Mapping[str, Any],
		target_owner: str | None = None,
		stream_callback: Callable[[str], Any] | None = None,
	) -> dict[str, Any]:
		title = str(reviewed_output.get("title", "公文任务"))
		summary = str(reviewed_output.get("summary", ""))
		tasks_raw = reviewed_output.get("tasks", [])
		tasks = tasks_raw if isinstance(tasks_raw, list) else []
		self.logger.info(
			"STEP=pipeline.dispatcher | AGENT=Dispatcher | ACTION=DispatchStart | DETAILS=doc_id=%s target_owner=%s task_count=%s",
			reviewed_output.get("doc_id", "unknown"),
			target_owner or "ALL",
			len(tasks),
		)
		owner_groups = self._group_tasks_by_owner(tasks, target_owner=target_owner)
		self.logger.info(
			"STEP=pipeline.dispatcher | AGENT=Dispatcher | ACTION=GroupByOwner | DETAILS=owner_groups=%s owners=%s",
			len(owner_groups),
			list(owner_groups.keys()),
		)
		tasks_text = json.dumps(tasks, ensure_ascii=False, indent=2)
		grouped_body = self._build_grouped_email_body(
			title=title,
			summary=summary,
			owner_groups=owner_groups,
			target_owner=target_owner,
		)
		follow_up_tips = self._build_follow_up_tips(owner_groups)

		system_prompt = (
			"You are Dispatcher Agent. Create concise and polite dispatch messages.\n"
			"Return JSON only with keys: email_subject, email_body_markdown, "
			"instant_message, follow_up_tips.\n"
			"No null values.\n"
			"Email body must group tasks by owner using clear sections such as '【致 XXX】'. "
			"Do not mix tasks for different owners in one ungrouped list."
		)
		user_prompt = (
			f"Document title: {title}\n\n"
			f"Summary:\n{summary}\n\n"
			f"Target owner filter: {target_owner or '无（发送全体）'}\n\n"
			f"Tasks:\n{tasks_text}\n\n"
			"Write high-EQ reminder copy for responsible owners."
		)

		messages: list[dict[str, str]] = [
			{"role": "system", "content": system_prompt},
			{"role": "user", "content": user_prompt},
		]

		max_attempts = self.json_retry_times + 1
		for attempt in range(1, max_attempts + 1):
			try:
				self.logger.info(
					"STEP=pipeline.dispatcher | AGENT=Dispatcher | ACTION=LLMAttemptStart | DETAILS=attempt=%s/%s",
					attempt,
					max_attempts,
				)
				resp = await self.client.chat_completion(
					messages=messages,
					response_format={"type": "json_object"},
					temperature=0.3,
					stream=bool(stream_callback),
					stream_callback=stream_callback,
				)
				content = self.client.get_message_content(resp)
				payload = json.loads(content)
				if not isinstance(payload, dict):
					raise ValueError("Dispatcher output must be JSON object.")
				normalized = self._normalize(
					payload=payload,
					reviewed_output=reviewed_output,
					grouped_body=grouped_body,
					fallback_tips=follow_up_tips,
					target_owner=target_owner,
				)
				self.logger.info(
					"STEP=pipeline.dispatcher | AGENT=Dispatcher | ACTION=DispatchDone | DETAILS=subject_len=%s body_len=%s tips=%s",
					len(str(normalized.get("email_subject", ""))),
					len(str(normalized.get("email_body_markdown", ""))),
					len(normalized.get("follow_up_tips", [])) if isinstance(normalized.get("follow_up_tips"), list) else 0,
				)
				return normalized
			except Exception as exc:  # pylint: disable=broad-except
				self.logger.warning(
					"Dispatcher failed attempt %s/%s: %s",
					attempt,
					max_attempts,
					exc,
				)
				if attempt >= max_attempts:
					break

		self.logger.warning("STEP=pipeline.dispatcher | AGENT=Dispatcher | ACTION=FallbackResponse")
		return self._fallback(reviewed_output, grouped_body=grouped_body, fallback_tips=follow_up_tips, target_owner=target_owner)

	@staticmethod
	def _group_tasks_by_owner(tasks: list[Any], target_owner: str | None = None) -> OrderedDict[str, list[dict[str, Any]]]:
		groups: OrderedDict[str, list[dict[str, Any]]] = OrderedDict()
		target = (target_owner or "").strip()

		for item in tasks:
			if not isinstance(item, Mapping):
				continue
			owner = str(item.get("owner", "相关责任部门")).strip() or "相关责任部门"
			if target:
				if target not in owner and owner not in target:
					continue
			groups.setdefault(owner, []).append(dict(item))

		if target and not groups:
			return OrderedDict()

		if not target and not groups:
			groups["相关责任部门"] = []

		return groups

	@staticmethod
	def _format_task_line(index: int, task: Mapping[str, Any]) -> str:
		name = str(task.get("task_name", "待办事项"))
		deadline = str(task.get("deadline_display") or task.get("deadline", "未提及"))
		urgency = str(task.get("urgency", {}).get("label", "常规"))
		deliverables = task.get("deliverables", [])
		deli_text = "；".join(str(item) for item in deliverables) if isinstance(deliverables, list) else "未提及"
		return f"{index}. [{urgency}] {name}（截止：{deadline}；交付物：{deli_text}）"

	def _build_grouped_email_body(
		self,
		title: str,
		summary: str,
		owner_groups: OrderedDict[str, list[dict[str, Any]]],
		target_owner: str | None,
	) -> str:
		lines: list[str] = [f"### {title}", "", summary, ""]

		if target_owner and not owner_groups:
			lines.extend([
				f"未匹配到责任人“{target_owner}”对应的任务，请检查责任人名称或取消筛选。",
			])
			return "\n".join(lines)

		for owner, tasks in owner_groups.items():
			lines.append(f"【致 {owner}】：")
			if not tasks:
				lines.append("- 当前未识别到明确任务。")
				lines.append("")
				continue
			for idx, task in enumerate(tasks, start=1):
				lines.append(f"- {self._format_task_line(idx, task)}")
			lines.append("")

		lines.append("如需协调支持，请及时反馈。")
		return "\n".join(lines)

	@staticmethod
	def _parse_concrete_date(deadline: str) -> dt.date | None:
		value = str(deadline).strip()
		match = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", value)
		if match:
			year, month, day = map(int, match.groups())
			try:
				return dt.date(year, month, day)
			except ValueError:
				return None

		range_match = re.match(r"^(\d{4}-\d{2}-\d{2})\s*至\s*(\d{4}-\d{2}-\d{2})$", value)
		if range_match:
			try:
				return dt.datetime.strptime(range_match.group(1), "%Y-%m-%d").date()
			except ValueError:
				return None

		return None

	@staticmethod
	def _is_periodic_deadline(deadline: str) -> bool:
		value = str(deadline).strip()
		if not value:
			return False
		periodic_patterns = [
			r"每年",
			r"每月",
			r"每周",
			r"每季度",
			r"每学期",
			r"年度",
			r"季度",
			r"学期",
			r"定期",
			r"常态",
		]
		return any(re.search(pattern, value) for pattern in periodic_patterns)

	def _build_follow_up_tips(self, owner_groups: OrderedDict[str, list[dict[str, Any]]]) -> list[str]:
		all_tasks = [task for tasks in owner_groups.values() for task in tasks]
		if not all_tasks:
			return ["未匹配到可发送任务，请检查责任人筛选条件。"]

		non_concrete_values = {"长期有效", "按需执行", "未提及", "无", ""}
		deadlines = [str(task.get("deadline", "")).strip() for task in all_tasks]
		periodic_flags = [self._is_periodic_deadline(value) for value in deadlines]
		concrete_dates = [
			self._parse_concrete_date(deadline)
			for deadline in deadlines
		]
		concrete_dates = [date for date in concrete_dates if date is not None]

		if not concrete_dates:
			if all(value in non_concrete_values or is_periodic for value, is_periodic in zip(deadlines, periodic_flags)):
				if any(periodic_flags):
					return ["长期制度，无需定期催办", "存在周期性任务，建议按制度周期例行检查。"]
				return ["长期制度，无需定期催办"]
			return ["部分任务缺少明确截止时间，建议先补全时间节点后再安排催办。"]

		today = dt.date.today()
		nearest = min(concrete_dates)
		days_left = (nearest - today).days

		tips: list[str] = []
		if days_left <= 0:
			tips.append("存在到期或逾期任务，建议立即提醒并当日复核进展。")
		elif days_left <= 2:
			tips.append("建议从现在起每日提醒一次，直至截止。")
		elif days_left <= 7:
			tips.append("建议在截止前3天和前1天各提醒一次。")
		else:
			tips.append("建议在截止前7天、3天、1天分层提醒。")

		if any(value in non_concrete_values for value in deadlines) or any(periodic_flags):
			tips.append("存在长期或周期任务，可按制度节奏例行跟踪，无需按日期催办。")

		return tips[:3]

	@staticmethod
	def _looks_grouped(body: str) -> bool:
		return "【致 " in body

	def _normalize(
		self,
		payload: Mapping[str, Any],
		reviewed_output: Mapping[str, Any],
		grouped_body: str,
		fallback_tips: list[str],
		target_owner: str | None,
	) -> dict[str, Any]:
		email_subject = str(payload.get("email_subject", "")).strip()
		email_body = str(payload.get("email_body_markdown", "")).strip()
		instant_message = str(payload.get("instant_message", "")).strip()

		if not email_subject:
			title = str(reviewed_output.get("title", "公文任务通知"))
			email_subject = f"[公文催办] {title}"
		if target_owner and target_owner not in email_subject:
			email_subject = f"[{target_owner}] {email_subject}"

		if not email_body or not self._looks_grouped(email_body):
			email_body = grouped_body

		if not instant_message:
			instant_message = "请相关责任人关注分组任务并按期落实。"

		return {
			"email_subject": email_subject,
			"email_body_markdown": email_body,
			"instant_message": instant_message,
			"follow_up_tips": fallback_tips,
		}

	def _fallback(
		self,
		reviewed_output: Mapping[str, Any],
		grouped_body: str,
		fallback_tips: list[str],
		target_owner: str | None,
	) -> dict[str, Any]:
		title = str(reviewed_output.get("title", "公文任务通知"))
		subject = f"[公文催办] {title}"
		if target_owner:
			subject = f"[{target_owner}] {subject}"

		return {
			"email_subject": subject,
			"email_body_markdown": grouped_body,
			"instant_message": f"请关注《{title}》相关任务，按时完成并反馈进展。",
			"follow_up_tips": fallback_tips,
		}

