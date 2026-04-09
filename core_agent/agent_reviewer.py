from __future__ import annotations

import json
import logging
import re
from typing import Any, Callable, Mapping, Protocol


REVIEWER_PLAIN_TEXT_MAX_CHARS = 14000
REVIEWER_RAG_CONTEXT_MAX_CHARS = 1800
REVIEWER_DRAFT_JSON_MAX_CHARS = 8000


class ReviewerClientProtocol(Protocol):
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


class ReviewerAgent:
	"""Second-pass reviewer for consistency checks and timeline sanity."""

	def __init__(
		self,
		client: ReviewerClientProtocol,
		json_retry_times: int = 2,
		max_output_tokens: int = 2600,
	) -> None:
		self.client = client
		self.json_retry_times = max(0, json_retry_times)
		self.max_output_tokens = max(500, int(max_output_tokens))
		self.logger = logging.getLogger("docs_agent.agent_reviewer")

	async def review(
		self,
		reader_output: Mapping[str, Any],
		parsed_doc: Mapping[str, Any],
		rag_context: str = "",
		critic_feedback: str = "",
		stream_callback: Callable[[str], Any] | None = None,
	) -> dict[str, Any]:
		feedback_text = str(critic_feedback or "").strip()
		attempt_temperature = 0.2 if feedback_text else 0
		self.logger.info(
			"STEP=pipeline.reviewer | AGENT=Reviewer | ACTION=ReviewStart | DETAILS=doc_id=%s input_tasks=%s plain_text_chars=%s feedback_chars=%s",
			reader_output.get("doc_id", "unknown"),
			len(reader_output.get("tasks", [])) if isinstance(reader_output.get("tasks"), list) else 0,
			len(str(parsed_doc.get("plain_text", ""))),
			len(feedback_text),
		)
		system_prompt = (
			"You are Reviewer Agent. Review and correct the extracted JSON from Reader Agent.\n"
			"Rules:\n"
			"1) Output valid JSON only.\n"
			"2) Keep same schema as input and preserve factual grounding.\n"
			"3) Do not fabricate missing evidence. Unknown values must stay as '未提及' or '无'.\n"
			"4) Check timeline consistency: notification tasks should prefer concrete deadlines if present; "
			"policy/regulation documents may use '长期有效' or '按需执行'.\n"
			"5) Risk definition must focus on business logic gaps (e.g., task exists but no deadline; "
			"deliverable unclear; standard not specified).\n"
			"6) Treat contact info in source (emails/phones/urls) as valid by default; do NOT label them as placeholders.\n"
			"7) Do NOT treat minor OCR typos, layout breaks, or isolated garbled chars as major risks.\n"
			"8) Keep source_anchor.block_id unchanged unless obviously invalid.\n"
			"9) Keep language concise and actionable.\n"
			"10) For ranged deadlines, keep and preserve three fields: deadline_start, deadline_end, deadline_display. "
			"Do not collapse a date range into a single start date.\n"
			"11) Keep output compact: short summary, concise task descriptions, and no redundant wording.\n"
			"12) If you receive Critic feedback, your JSON MUST include a field called rework_thought before tasks, "
			"briefly explaining how feedback was addressed.\n"
		)

		plain_text = str(parsed_doc.get("plain_text", ""))[:REVIEWER_PLAIN_TEXT_MAX_CHARS]
		rag_context_text = str(rag_context or "")[:REVIEWER_RAG_CONTEXT_MAX_CHARS]
		reader_json = json.dumps(reader_output, ensure_ascii=False, separators=(",", ":"))[:REVIEWER_DRAFT_JSON_MAX_CHARS]
		if feedback_text:
			user_prompt = (
				"Raw document excerpt:\n"
				f"{plain_text}\n\n"
				"RAG context (may be empty):\n"
				f"{rag_context_text or '无'}\n\n"
				"Previous draft JSON:\n"
				f"{reader_json}\n\n"
				"Critic feedback from previous round (must be fully addressed):\n"
				f"{feedback_text}\n\n"
				"Task: strictly follow the feedback above, re-check against raw document, "
				"and output the full corrected JSON only."
			)
		else:
			user_prompt = (
				"Raw document excerpt:\n"
				f"{plain_text}\n\n"
				"RAG context (may be empty):\n"
				f"{rag_context_text or '无'}\n\n"
				"Reader output JSON to review:\n"
				f"{reader_json}\n\n"
				"Return corrected JSON only."
			)

		messages: list[dict[str, str]] = [
			{"role": "system", "content": system_prompt},
			{"role": "user", "content": user_prompt},
		]

		max_attempts = self.json_retry_times + 1
		for attempt in range(1, max_attempts + 1):
			finish_reason = "unknown"
			try:
				self.logger.info(
					"STEP=pipeline.reviewer | AGENT=Reviewer | ACTION=LLMAttemptStart | DETAILS=attempt=%s/%s max_tokens=%s temperature=%s",
					attempt,
					max_attempts,
					self.max_output_tokens,
					attempt_temperature,
				)
				resp = await self.client.chat_completion(
					messages=messages,
					response_format={"type": "json_object"},
					temperature=attempt_temperature,
					max_tokens=self.max_output_tokens,
					stream=bool(stream_callback),
					stream_callback=stream_callback,
				)
				finish_reason = self._extract_finish_reason(resp)
				content = self.client.get_message_content(resp)
				candidate = self._parse_json_relaxed(content, allow_truncated_repair=(finish_reason == "length"))
				if not isinstance(candidate, dict):
					raise ValueError("Reviewer output must be JSON object.")
				if finish_reason == "length":
					self.logger.warning(
						"STEP=pipeline.reviewer | AGENT=Reviewer | ACTION=LengthTruncated | DETAILS=attempt=%s/%s content_chars=%s",
						attempt,
						max_attempts,
						len(content),
					)
				merged = self._merge_with_fallback(candidate, reader_output)
				cleaned = self._post_review_cleanup(merged, critic_feedback=feedback_text)
				self.logger.info(
					"STEP=pipeline.reviewer | AGENT=Reviewer | ACTION=ReviewDone | DETAILS=tasks=%s risks=%s questions=%s",
					len(cleaned.get("tasks", [])) if isinstance(cleaned.get("tasks"), list) else 0,
					len(cleaned.get("risks_or_unclear_points", [])) if isinstance(cleaned.get("risks_or_unclear_points"), list) else 0,
					len(cleaned.get("follow_up_questions", [])) if isinstance(cleaned.get("follow_up_questions"), list) else 0,
				)
				return cleaned
			except Exception as exc:  # pylint: disable=broad-except
				self.logger.warning(
					"Reviewer failed attempt %s/%s: %s",
					attempt,
					max_attempts,
					exc,
				)
				if attempt >= max_attempts:
					break
				retry_hint = "Previous output invalid. Return corrected JSON object only."
				if finish_reason == "length":
					retry_hint = (
						"Previous output was truncated by max_tokens. Return concise JSON only: "
						"no prose, short fields, max 8 tasks."
					)
				messages.append(
					{
						"role": "user",
						"content": (
							retry_hint
							+ (
								" Include rework_thought before tasks and keep it under 120 Chinese chars."
								if feedback_text
								else ""
							)
						),
					}
				)

		self.logger.warning("STEP=pipeline.reviewer | AGENT=Reviewer | ACTION=FallbackToReaderOutput")
		fallback_cleaned = self._post_review_cleanup(dict(reader_output), critic_feedback=feedback_text)
		return fallback_cleaned

	@staticmethod
	def _merge_with_fallback(candidate: Mapping[str, Any], fallback: Mapping[str, Any]) -> dict[str, Any]:
		merged = dict(fallback)
		for key, value in candidate.items():
			if value is None:
				continue
			if isinstance(value, str) and not value.strip():
				continue
			if isinstance(value, (list, dict)) and not value:
				continue
			merged[key] = value
		return merged

	@staticmethod
	def _extract_finish_reason(response_json: Mapping[str, Any]) -> str:
		choices = response_json.get("choices") if isinstance(response_json, Mapping) else None
		if isinstance(choices, list) and choices and isinstance(choices[0], Mapping):
			reason = choices[0].get("finish_reason")
			if isinstance(reason, str) and reason.strip():
				return reason.strip().lower()
		return "unknown"

	@classmethod
	def _parse_json_relaxed(cls, raw_content: str, allow_truncated_repair: bool = True) -> dict[str, Any]:
		text = str(raw_content or "").strip()
		if not text:
			raise ValueError("Reviewer output is empty.")

		try:
			parsed = json.loads(text)
			if isinstance(parsed, dict):
				return parsed
			raise ValueError("Top-level JSON must be an object.")
		except json.JSONDecodeError:
			pass

		cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE | re.DOTALL).strip()
		left = cleaned.find("{")
		right = cleaned.rfind("}")
		if left != -1 and right != -1 and right > left:
			candidate = cleaned[left : right + 1]
			try:
				parsed = json.loads(candidate)
				if isinstance(parsed, dict):
					return parsed
			except json.JSONDecodeError:
				pass

		if allow_truncated_repair and left != -1:
			repaired = cls._repair_truncated_json(cleaned[left:])
			if repaired:
				parsed = json.loads(repaired)
				if isinstance(parsed, dict):
					return parsed

		raise ValueError("Reviewer output is not valid JSON object.")

	@staticmethod
	def _repair_truncated_json(raw_text: str) -> str | None:
		text = str(raw_text or "").strip()
		if not text:
			return None

		left = text.find("{")
		if left == -1:
			return None
		source = text[left:]

		chars: list[str] = []
		depth = 0
		in_string = False
		escape = False

		for ch in source:
			chars.append(ch)
			if in_string:
				if escape:
					escape = False
				elif ch == "\\":
					escape = True
				elif ch == '"':
					in_string = False
				continue

			if ch == '"':
				in_string = True
			elif ch == "{":
				depth += 1
			elif ch == "}":
				depth = max(0, depth - 1)
				if depth == 0:
					break

		repaired = "".join(chars).strip()
		if not repaired:
			return None

		if in_string:
			trailing_backslashes = 0
			for ch in reversed(repaired):
				if ch == "\\":
					trailing_backslashes += 1
				else:
					break
			if trailing_backslashes % 2 == 1:
				repaired += "\\"
			repaired += '"'

		if depth > 0:
			repaired += "}" * depth

		repaired = re.sub(r",\s*([}\]])", r"\1", repaired)
		return repaired if "}" in repaired else None

	@staticmethod
	def _sanitize_text(text: Any) -> str:
		value = str(text).strip()
		value = re.sub(r"(?<![A-Za-z0-9_])p\d{3,6}(?![A-Za-z0-9_])", "原文相关段落", value, flags=re.IGNORECASE)
		return re.sub(r"\s+", " ", value)

	def _is_false_positive_risk(self, risk: str) -> bool:
		text = risk.strip()
		if not text:
			return True

		# Do not over-doubt contact information validity.
		if any(keyword in text for keyword in ["占位符", "placeholder", "疑似占位"]):
			if any(keyword in text for keyword in ["邮箱", "电话", "网址", "网站", "联系方式"]):
				return True

		# Ignore minor parsing/OCR artifacts as major risks.
		if any(keyword in text for keyword in ["OCR", "ocr", "乱码", "排版", "错别字", "识别残缺", "解析错误"]):
			if not any(keyword in text for keyword in ["关键字段缺失", "无法识别关键信息", "任务不可判定"]):
				return True

		return False

	def _derive_business_risks(self, data: Mapping[str, Any]) -> list[str]:
		tasks = data.get("tasks", [])
		doc_type = str(data.get("doc_type", ""))
		risks: list[str] = []

		if isinstance(tasks, list):
			if doc_type == "事务性通知":
				missing_deadline = [
					t for t in tasks if str(t.get("deadline", "")).strip() in {"未提及", "无", "按需执行", "长期有效", ""}
				]
				if missing_deadline:
					risks.append("部分事务性任务缺少明确截止时间，建议补充时间节点以便催办执行。")

			vague_deliverables = [
				t
				for t in tasks
				if any(str(item).strip() in {"未提及", "无"} for item in t.get("deliverables", []) if isinstance(t.get("deliverables"), list))
			]
			if vague_deliverables:
				risks.append("部分任务交付物描述仍不够明确，建议补充载体格式与提交路径。")

		return risks

	@staticmethod
	def _parse_full_date(value: Any) -> str | None:
		text = str(value).strip()
		iso_match = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})$", text)
		if iso_match:
			year, month, day = map(int, iso_match.groups())
			return f"{year:04d}-{month:02d}-{day:02d}"
		cn_match = re.match(r"^(\d{4})年(\d{1,2})月(\d{1,2})日?$", text)
		if cn_match:
			year, month, day = map(int, cn_match.groups())
			return f"{year:04d}-{month:02d}-{day:02d}"
		dot_match = re.match(r"^(\d{4})\.(\d{1,2})\.(\d{1,2})$", text)
		if dot_match:
			year, month, day = map(int, dot_match.groups())
			return f"{year:04d}-{month:02d}-{day:02d}"
		return None

	@classmethod
	def _extract_date_range(cls, text: Any) -> tuple[str | None, str | None]:
		value = str(text).strip()
		if not value:
			return None, None

		iso_range = re.search(
			r"(\d{4})-(\d{1,2})-(\d{1,2})\s*[至到~\-]\s*(\d{4})-(\d{1,2})-(\d{1,2})",
			value,
		)
		if iso_range:
			a = tuple(map(int, iso_range.groups()[:3]))
			b = tuple(map(int, iso_range.groups()[3:]))
			return f"{a[0]:04d}-{a[1]:02d}-{a[2]:02d}", f"{b[0]:04d}-{b[1]:02d}-{b[2]:02d}"

		cn_range_same_year = re.search(
			r"(\d{4})年(\d{1,2})月(\d{1,2})日?\s*[至到~\-]\s*(\d{1,2})月(\d{1,2})日?",
			value,
		)
		if cn_range_same_year:
			year, sm, sd, em, ed = map(int, cn_range_same_year.groups())
			return f"{year:04d}-{sm:02d}-{sd:02d}", f"{year:04d}-{em:02d}-{ed:02d}"

		cn_range_full = re.search(
			r"(\d{4})年(\d{1,2})月(\d{1,2})日?\s*[至到~\-]\s*(\d{4})年(\d{1,2})月(\d{1,2})日?",
			value,
		)
		if cn_range_full:
			a = tuple(map(int, cn_range_full.groups()[:3]))
			b = tuple(map(int, cn_range_full.groups()[3:]))
			return f"{a[0]:04d}-{a[1]:02d}-{a[2]:02d}", f"{b[0]:04d}-{b[1]:02d}-{b[2]:02d}"

		return None, None

	def _normalize_task_deadlines(self, tasks: list[Any]) -> list[dict[str, Any]]:
		normalized: list[dict[str, Any]] = []
		for raw in tasks:
			if not isinstance(raw, Mapping):
				continue
			item = dict(raw)
			deadline = str(item.get("deadline", "未提及")).strip() or "未提及"
			display = str(item.get("deadline_display", "")).strip()
			start = self._parse_full_date(item.get("deadline_start", ""))
			end = self._parse_full_date(item.get("deadline_end", ""))

			range_start, range_end = self._extract_date_range(display or deadline)
			if not start:
				start = range_start
			if not end:
				end = range_end

			single = self._parse_full_date(deadline)
			if single and not start and not end:
				start = single
				end = single

			if start and not end:
				end = start
			if end and not start:
				start = end

			if not display or display in {"无", "未提及"}:
				if start and end and start != end:
					display = f"{start}至{end}"
				elif start:
					display = start
				else:
					display = deadline

			if deadline in {"", "无"}:
				deadline = display or "未提及"
			elif start and end and start != end:
				deadline = display

			item["deadline"] = deadline
			item["deadline_start"] = start or "无"
			item["deadline_end"] = end or "无"
			item["deadline_display"] = display or "未提及"
			normalized.append(item)

		return normalized

	def _build_default_rework_thought(self, critic_feedback: str) -> str:
		feedback = self._sanitize_text(critic_feedback)
		if not feedback:
			return "已按 Critic 扣分项逐条复核并完成修正。"
		if len(feedback) > 140:
			feedback = feedback[:140].rstrip() + "..."
		return f"已依据 Critic 反馈完成本轮修正：{feedback}"

	@staticmethod
	def _reorder_output_fields(data: Mapping[str, Any]) -> dict[str, Any]:
		preferred_order = [
			"doc_id",
			"doc_type",
			"title",
			"document_no",
			"publish_date",
			"issuing_department",
			"summary",
			"rework_thought",
			"tasks",
			"risks_or_unclear_points",
			"follow_up_questions",
		]
		ordered: dict[str, Any] = {}
		for key in preferred_order:
			if key in data:
				ordered[key] = data[key]
		for key, value in data.items():
			if key not in ordered:
				ordered[key] = value
		return ordered

	def _post_review_cleanup(self, data: Mapping[str, Any], critic_feedback: str = "") -> dict[str, Any]:
		cleaned = dict(data)

		raw_tasks = cleaned.get("tasks")
		if isinstance(raw_tasks, list):
			cleaned["tasks"] = self._normalize_task_deadlines(raw_tasks)

		raw_risks = cleaned.get("risks_or_unclear_points")
		risks_input = raw_risks if isinstance(raw_risks, list) else []
		filtered_risks: list[str] = []
		for item in risks_input:
			text = self._sanitize_text(item)
			if self._is_false_positive_risk(text):
				continue
			if text and text not in filtered_risks:
				filtered_risks.append(text)

		for item in self._derive_business_risks(cleaned):
			if item not in filtered_risks:
				filtered_risks.append(item)

		cleaned["risks_or_unclear_points"] = filtered_risks[:4]

		raw_questions = cleaned.get("follow_up_questions")
		questions_input = raw_questions if isinstance(raw_questions, list) else []
		cleaned["follow_up_questions"] = [
			self._sanitize_text(item)
			for item in questions_input
			if self._sanitize_text(item)
		][:4]

		if critic_feedback.strip():
			rework_text = self._sanitize_text(cleaned.get("rework_thought", ""))
			if not rework_text:
				rework_text = self._build_default_rework_thought(critic_feedback)
			cleaned["rework_thought"] = rework_text[:220]
		else:
			cleaned.pop("rework_thought", None)

		cleaned = self._reorder_output_fields(cleaned)
		self.logger.debug(
			"STEP=pipeline.reviewer | AGENT=Reviewer | ACTION=PostCleanup | DETAILS=tasks=%s risks=%s questions=%s",
			len(cleaned.get("tasks", [])) if isinstance(cleaned.get("tasks"), list) else 0,
			len(cleaned.get("risks_or_unclear_points", [])) if isinstance(cleaned.get("risks_or_unclear_points"), list) else 0,
			len(cleaned.get("follow_up_questions", [])) if isinstance(cleaned.get("follow_up_questions"), list) else 0,
		)

		return cleaned

