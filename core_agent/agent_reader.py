from __future__ import annotations

import json
import logging
import re
from typing import Any, Callable, Iterable, Mapping, Protocol

from config.prompt_templates import build_reader_system_prompt, build_reader_user_prompt


class ReaderClientProtocol(Protocol):
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


class ReaderOutputError(RuntimeError):
	"""Raised when Reader Agent cannot produce valid JSON output."""


INTERNAL_BLOCK_PATTERN = re.compile(r"(?<![A-Za-z0-9_])p\d{3,6}(?![A-Za-z0-9_])", flags=re.IGNORECASE)


def _is_missing(value: Any) -> bool:
	if value is None:
		return True
	text = str(value).strip()
	return text == "" or text.lower() == "null"


def _normalize_string(value: Any, fallback: str = "未提及") -> str:
	if _is_missing(value):
		return fallback
	return str(value).strip()


class ReaderAgent:
	def __init__(
		self,
		client: ReaderClientProtocol,
		summary_target_chars: int = 250,
		json_retry_times: int = 2,
		max_output_tokens: int = 2600,
	) -> None:
		self.client = client
		self.summary_target_chars = summary_target_chars
		self.json_retry_times = max(0, json_retry_times)
		self.max_output_tokens = max(800, int(max_output_tokens))
		self.logger = logging.getLogger("docs_agent.agent_reader")

	async def extract(
		self,
		parsed_doc: Mapping[str, Any],
		stream_callback: Callable[[str], Any] | None = None,
	) -> dict[str, Any]:
		doc_id = str(parsed_doc.get("doc_id", ""))
		if not doc_id:
			raise ValueError("parsed_doc.doc_id is required.")

		plain_text = str(parsed_doc.get("plain_text", ""))
		source_blocks_raw = parsed_doc.get("blocks", [])
		source_blocks = source_blocks_raw if isinstance(source_blocks_raw, list) else []
		self.logger.info(
			"STEP=pipeline.reader | AGENT=Reader | ACTION=ExtractStart | DETAILS=doc_id=%s blocks=%s plain_text_chars=%s",
			doc_id,
			len(source_blocks),
			len(plain_text),
		)

		system_prompt = build_reader_system_prompt(self.summary_target_chars)
		user_prompt = build_reader_user_prompt(doc_id, plain_text, source_blocks)

		messages: list[dict[str, str]] = [
			{"role": "system", "content": system_prompt},
			{"role": "user", "content": user_prompt},
		]

		max_attempts = self.json_retry_times + 1
		last_error: Exception | None = None
		last_raw_content = ""
		length_truncated_seen = False

		for attempt in range(1, max_attempts + 1):
			finish_reason = "unknown"
			attempt_max_tokens = min(self.max_output_tokens + (600 if length_truncated_seen else 0), 4200)
			self.logger.info(
				"STEP=pipeline.reader | AGENT=Reader | ACTION=LLMAttemptStart | DETAILS=doc_id=%s attempt=%s/%s max_tokens=%s",
				doc_id,
				attempt,
				max_attempts,
				attempt_max_tokens,
			)
			response_json = await self.client.chat_completion(
				messages=messages,
				response_format={"type": "json_object"},
				temperature=0,
				max_tokens=attempt_max_tokens,
				stream=bool(stream_callback),
				stream_callback=stream_callback,
			)
			raw_content = self.client.get_message_content(response_json)
			last_raw_content = raw_content
			finish_reason = self._extract_finish_reason(response_json)
			if finish_reason == "length":
				length_truncated_seen = True
				self.logger.warning(
					"STEP=pipeline.reader | AGENT=Reader | ACTION=LengthTruncated | DETAILS=doc_id=%s attempt=%s/%s content_chars=%s",
					doc_id,
					attempt,
					max_attempts,
					len(raw_content),
				)

			try:
				result = self._parse_json_relaxed(raw_content, allow_truncated_repair=(finish_reason == "length"))
				result = self._normalize_result(
					result=result,
					doc_id=doc_id,
					plain_text=plain_text,
					source_blocks=source_blocks,
				)
				self._validate_result(result)
				self.logger.info(
					"STEP=pipeline.reader | AGENT=Reader | ACTION=ExtractDone | DETAILS=doc_id=%s tasks=%s risks=%s questions=%s",
					doc_id,
					len(result.get("tasks", [])) if isinstance(result.get("tasks"), list) else 0,
					len(result.get("risks_or_unclear_points", [])) if isinstance(result.get("risks_or_unclear_points"), list) else 0,
					len(result.get("follow_up_questions", [])) if isinstance(result.get("follow_up_questions"), list) else 0,
				)
				return result
			except Exception as exc:  # pylint: disable=broad-except
				last_error = exc
				self.logger.warning(
					"Reader output invalid (attempt %s/%s): %s",
					attempt,
					max_attempts,
					exc,
				)
				if attempt >= max_attempts:
					break
				retry_hint = (
					"Your previous output was invalid. "
					f"Error: {exc}. Return corrected compact JSON only, with no markdown fences."
				)
				if finish_reason == "length":
					retry_hint = (
						"Your previous output was truncated by max_tokens. "
						"Return compact JSON only, no prose, no markdown, no repetition. "
						"Keep at most 6 tasks, each quote <= 45 Chinese chars, risks <= 4, follow_up_questions <= 4."
					)
				messages.append({"role": "assistant", "content": raw_content[:5000]})
				messages.append(
					{
						"role": "user",
						"content": retry_hint,
					}
				)

		# Last-chance repair step for malformed/truncated JSON.
		if last_error is not None and last_raw_content:
			try:
				self.logger.warning(
					"STEP=pipeline.reader | AGENT=Reader | ACTION=RepairAttemptStart | DETAILS=doc_id=%s reason=%s",
					doc_id,
					last_error,
				)
				repair_prompt = (
					"Repair the malformed JSON below. Return one valid JSON object only, keep fields compact, "
					"do not add explanations.\n\n"
					f"Malformed JSON:\n{last_raw_content[:12000]}"
				)
				repair_resp = await self.client.chat_completion(
					messages=[
						{"role": "system", "content": "You are a JSON repair assistant."},
						{"role": "user", "content": repair_prompt},
					],
					response_format={"type": "json_object"},
					temperature=0,
					max_tokens=max(self.max_output_tokens, 3200),
					stream=False,
					stream_callback=None,
				)
				repaired_content = self.client.get_message_content(repair_resp)
				repaired = self._parse_json_relaxed(repaired_content, allow_truncated_repair=True)
				repaired = self._normalize_result(
					result=repaired,
					doc_id=doc_id,
					plain_text=plain_text,
					source_blocks=source_blocks,
				)
				self._validate_result(repaired)
				self.logger.info(
					"STEP=pipeline.reader | AGENT=Reader | ACTION=RepairAttemptDone | DETAILS=doc_id=%s tasks=%s",
					doc_id,
					len(repaired.get("tasks", [])) if isinstance(repaired.get("tasks"), list) else 0,
				)
				return repaired
			except Exception:  # pylint: disable=broad-except
				self.logger.exception("STEP=pipeline.reader | AGENT=Reader | ACTION=RepairAttemptFailed | DETAILS=doc_id=%s", doc_id)
				pass

		fallback = self._build_minimal_fallback_result(
			doc_id=doc_id,
			plain_text=plain_text,
			source_blocks=source_blocks,
			reason=last_error,
		)
		try:
			self._validate_result(fallback)
		except Exception as fallback_exc:  # pylint: disable=broad-except
			raise ReaderOutputError(
				f"Reader Agent failed to output valid JSON: {last_error}; fallback_build_error={fallback_exc}"
			) from fallback_exc

		self.logger.warning(
			"STEP=pipeline.reader | AGENT=Reader | ACTION=FallbackOutputUsed | DETAILS=doc_id=%s reason=%s tasks=%s",
			doc_id,
			last_error,
			len(fallback.get("tasks", [])),
		)
		return fallback

		raise ReaderOutputError(f"Reader Agent failed to output valid JSON: {last_error}")

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
			raise ValueError("Reader output is empty.")
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
				try:
					parsed = json.loads(repaired)
					if isinstance(parsed, dict):
						return parsed
				except json.JSONDecodeError:
					pass

		raise ValueError("No valid JSON object found in Reader output.")

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

	def _build_minimal_fallback_result(
		self,
		doc_id: str,
		plain_text: str,
		source_blocks: Iterable[Mapping[str, Any]],
		reason: Exception | None,
	) -> dict[str, Any]:
		title = "未提及"
		for line in str(plain_text).splitlines():
			cleaned = self._sanitize_human_text(line)
			if cleaned and cleaned != "未提及":
				title = cleaned[:80]
				break
		if title == "未提及":
			title = self._sanitize_human_text(doc_id)[:80] or "未提及"

		doc_type = self._infer_doc_type(doc_type="", title=title, plain_text=plain_text)
		deadline_display = "长期有效" if doc_type == "管理办法/规章制度" else "未提及"
		task_name = f"{title}执行落实"

		block_id = "p0001"
		quote = title
		for index, block in enumerate(source_blocks, start=1):
			if not isinstance(block, Mapping):
				continue
			candidate_id = str(block.get("block_id", "")).strip()
			if re.match(r"^p\d{3,6}$", candidate_id, flags=re.IGNORECASE):
				block_id = candidate_id
			else:
				block_id = f"p{index:04d}"
			text = self._sanitize_human_text(str(block.get("text", "")))
			if text and text != "未提及":
				quote = text[:100]
			break

		owner = self._sanitize_human_text(
			self._infer_owner(task_text=task_name, title=title, plain_text=plain_text, doc_type=doc_type)
		)
		deliverables = ["未提及"]
		action_suggestion = self._normalize_action_suggestion(
			task_name=task_name,
			action_text="未提及",
			deliverables=deliverables,
			deadline_display=deadline_display,
		)

		minimal_task = {
			"task_id": "task_001",
			"task_name": task_name,
			"owner": owner,
			"deadline": deadline_display,
			"deadline_start": "无",
			"deadline_end": "无",
			"deadline_display": deadline_display,
			"deliverables": deliverables,
			"action_suggestion": action_suggestion,
			"source_anchor": {
				"block_id": block_id,
				"quote": quote,
			},
		}

		summary = self._enforce_summary_format(
			summary=title,
			title=title,
			tasks=[minimal_task],
		)

		error_text = self._sanitize_human_text(str(reason or "未知错误"))
		return {
			"doc_id": doc_id,
			"doc_type": doc_type,
			"title": title,
			"document_no": "未提及",
			"publish_date": "未提及",
			"issuing_department": "未提及",
			"summary": summary,
			"tasks": [minimal_task],
			"risks_or_unclear_points": [
				f"Reader 输出解析失败（{error_text}），已自动降级生成最小草稿，请人工复核后再下发。"
			],
			"follow_up_questions": [
				"请补充该任务的明确截止时间与交付物规格。"
			],
		}

	@staticmethod
	def _normalize_date_literal(raw_value: str, plain_text: str) -> str:
		value = raw_value.strip()
		if value in {"无", "未提及", "长期有效", "按需执行"}:
			return value

		cn_full = re.match(r"^(\d{4})年(\d{1,2})月(\d{1,2})日?$", value)
		if cn_full:
			year, month, day = map(int, cn_full.groups())
			return f"{year:04d}-{month:02d}-{day:02d}"

		cn_month = re.match(r"^(\d{4})年(\d{1,2})月$", value)
		if cn_month:
			year, month = map(int, cn_month.groups())
			return f"{year:04d}-{month:02d}"

		hyphen_full = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})$", value)
		if hyphen_full:
			year, month, day = map(int, hyphen_full.groups())
			full_date_re = re.compile(rf"{year}\s*年\s*{month}\s*月\s*{day}\s*日?")
			month_re = re.compile(rf"{year}\s*年\s*{month}\s*月")
			if day == 1 and not full_date_re.search(plain_text) and month_re.search(plain_text):
				return f"{year:04d}-{month:02d}"
			return f"{year:04d}-{month:02d}-{day:02d}"

		hyphen_month = re.match(r"^(\d{4})-(\d{1,2})$", value)
		if hyphen_month:
			year, month = map(int, hyphen_month.groups())
			return f"{year:04d}-{month:02d}"

		only_year = re.match(r"^(\d{4})$", value)
		if only_year:
			return value

		return value

	@staticmethod
	def _infer_doc_type(doc_type: str, title: str, plain_text: str) -> str:
		value = doc_type.strip()
		if any(keyword in value for keyword in ["管理办法", "规章", "制度", "细则", "条例"]):
			return "管理办法/规章制度"
		if any(keyword in value for keyword in ["通知", "公告", "通告", "函"]):
			return "事务性通知"

		joined = f"{title}\n{plain_text[:1200]}"
		if any(keyword in joined for keyword in ["管理办法", "规章制度", "本办法", "制度建设", "解释权"]):
			return "管理办法/规章制度"
		if any(keyword in joined for keyword in ["通知", "报送", "提交", "截止", "请于"]):
			return "事务性通知"
		return "其他"

	@staticmethod
	def _infer_owner(task_text: str, title: str, plain_text: str, doc_type: str) -> str:
		candidates = [
			"各学院团委",
			"各学院",
			"各部门",
			"各单位",
			"参赛团队",
			"参赛队",
			"全体教职工",
			"全体学生",
			"相关院校",
			"起草单位",
		]

		joined = f"{task_text}\n{title}\n{plain_text[:2500]}"
		for keyword in candidates:
			if keyword in joined:
				return keyword

		if "大赛" in title:
			return "参赛团队"
		if doc_type == "管理办法/规章制度":
			return "相关职能部门"
		return "相关责任部门"

	@staticmethod
	def _sanitize_human_text(text: Any) -> str:
		value = _normalize_string(text, fallback="未提及")
		value = INTERNAL_BLOCK_PATTERN.sub("原文相关段落", value)
		value = re.sub(r"\s+", " ", value).strip()
		return value

	def _enforce_summary_format(self, summary: str, title: str, tasks: list[dict[str, Any]]) -> str:
		markers = ["【核心主旨】：", "【关键动作】：", "【涉及范围】："]
		cleaned = self._sanitize_human_text(summary)

		if all(marker in cleaned for marker in markers):
			formatted = cleaned
		else:
			core = self._sanitize_human_text(title)
			action_items = [self._sanitize_human_text(task.get("task_name", "")) for task in tasks[:3]]
			action_items = [item for item in action_items if item and item not in {"无", "未提及"}]
			actions = "；".join(action_items) if action_items else "按原文要求推进落实"
			owners = [self._sanitize_human_text(task.get("owner", "")) for task in tasks]
			unique_owners = []
			for owner in owners:
				if owner and owner not in {"无", "未提及"} and owner not in unique_owners:
					unique_owners.append(owner)
			scope = "、".join(unique_owners[:4]) if unique_owners else "相关责任部门"
			formatted = (
				f"【核心主旨】：{core}\n"
				f"【关键动作】：{actions}\n"
				f"【涉及范围】：{scope}"
			)

		if len(formatted) > self.summary_target_chars:
			formatted = formatted[: self.summary_target_chars].rstrip()
		return formatted

	def _normalize_deliverable_item(self, item: str, task_name: str, action_suggestion: str) -> str:
		text = self._sanitize_human_text(item)
		if text in {"", "无", "未提及"}:
			return ""

		context = f"{task_name}\n{action_suggestion}"
		if "（" in text and "）" in text:
			return text

		if "参赛作品" in text:
			if any(keyword in context for keyword in ["演示", "答辩", "10分钟"]):
				return f"{text}（含文档与10分钟内演示视频）"
			return f"{text}（含作品说明与必要附件）"

		if ("上推" in text or "作品数据" in text or "填报" in text) and any(
			keyword in context for keyword in ["平台", "填报", "国赛"]
		):
			return f"{text}（通过国赛平台填报）"

		if text in {"邮件", "发送邮件"}:
			if any(keyword in context for keyword in ["主题", "联系人", "正文"]):
				return "邮件（主题规范，正文含联系人信息）"
			return "邮件（按通知要求发送）"

		if "压缩包" in text:
			if "命名" in context:
				return f"{text}（按指定规则命名）"
			return text

		if "文档" in text and any(keyword in context.lower() for keyword in ["docx", "word"]):
			return f"{text}（Word .docx格式）"

		if "视频" in text and any(keyword in context.lower() for keyword in ["mp4", "1080", "16:9"]):
			return f"{text}（MP4，1080P，16:9）"

		if "照片" in text and any(keyword in context for keyword in ["JPG", "PNG", "DPI"]):
			return f"{text}（JPG/PNG，分辨率不低于300DPI）"

		return text

	def _normalize_deliverables(
		self,
		deliverables: list[Any],
		task_name: str,
		action_suggestion: str,
	) -> list[str]:
		normalized_items: list[str] = []
		for raw in deliverables:
			item = self._normalize_deliverable_item(str(raw), task_name, action_suggestion)
			if not item:
				continue
			if item not in normalized_items:
				normalized_items.append(item)

		if not normalized_items:
			return ["未提及"]
		return normalized_items

	@staticmethod
	def _parse_full_date(value: str) -> str | None:
		text = str(value).strip()
		if not text or text in {"无", "未提及"}:
			return None

		iso_match = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})$", text)
		if iso_match:
			year, month, day = map(int, iso_match.groups())
			return f"{year:04d}-{month:02d}-{day:02d}"

		dot_match = re.match(r"^(\d{4})\.(\d{1,2})\.(\d{1,2})$", text)
		if dot_match:
			year, month, day = map(int, dot_match.groups())
			return f"{year:04d}-{month:02d}-{day:02d}"

		cn_match = re.match(r"^(\d{4})年(\d{1,2})月(\d{1,2})日?$", text)
		if cn_match:
			year, month, day = map(int, cn_match.groups())
			return f"{year:04d}-{month:02d}-{day:02d}"

		return None

	@staticmethod
	def _extract_date_range(text: str) -> tuple[str | None, str | None]:
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
			start = f"{a[0]:04d}-{a[1]:02d}-{a[2]:02d}"
			end = f"{b[0]:04d}-{b[1]:02d}-{b[2]:02d}"
			return start, end

		cn_range_full = re.search(
			r"(\d{4})年(\d{1,2})月(\d{1,2})日?\s*[至到~\-]\s*(\d{4})年(\d{1,2})月(\d{1,2})日?",
			value,
		)
		if cn_range_full:
			a = tuple(map(int, cn_range_full.groups()[:3]))
			b = tuple(map(int, cn_range_full.groups()[3:]))
			start = f"{a[0]:04d}-{a[1]:02d}-{a[2]:02d}"
			end = f"{b[0]:04d}-{b[1]:02d}-{b[2]:02d}"
			return start, end

		cn_range_same_year = re.search(
			r"(\d{4})年(\d{1,2})月(\d{1,2})日?\s*[至到~\-]\s*(\d{1,2})月(\d{1,2})日?",
			value,
		)
		if cn_range_same_year:
			year, sm, sd, em, ed = map(int, cn_range_same_year.groups())
			start = f"{year:04d}-{sm:02d}-{sd:02d}"
			end = f"{year:04d}-{em:02d}-{ed:02d}"
			return start, end

		return None, None

	def _normalize_deadline_fields(
		self,
		task: Mapping[str, Any],
		plain_text: str,
		doc_type: str,
	) -> tuple[str, str, str, str]:
		deadline_raw = _normalize_string(task.get("deadline"), fallback="未提及")
		deadline = self._normalize_date_literal(deadline_raw, plain_text)

		if doc_type == "管理办法/规章制度" and deadline in {"未提及", "无"}:
			deadline = "长期有效"
		elif doc_type == "管理办法/规章制度":
			if deadline not in {"长期有效", "按需执行"} and not re.match(r"^\d{4}-\d{2}-\d{2}$", deadline):
				deadline = "按需执行"
		elif deadline == "无":
			deadline = "未提及"

		start_raw = _normalize_string(task.get("deadline_start"), fallback="")
		end_raw = _normalize_string(task.get("deadline_end"), fallback="")
		display_raw = _normalize_string(task.get("deadline_display"), fallback="")

		start = self._parse_full_date(self._normalize_date_literal(start_raw, plain_text))
		end = self._parse_full_date(self._normalize_date_literal(end_raw, plain_text))

		range_start, range_end = self._extract_date_range(deadline_raw)
		if not range_start and not range_end:
			range_start, range_end = self._extract_date_range(deadline)

		if not start:
			start = range_start
		if not end:
			end = range_end

		single_date = self._parse_full_date(deadline)
		if single_date and not start and not end:
			start = single_date
			end = single_date

		if start and not end:
			end = start
		if end and not start:
			start = end

		display = self._sanitize_human_text(display_raw) if display_raw not in {"", "无", "未提及"} else ""
		if not display:
			if start and end and start != end:
				display = f"{start}至{end}"
			elif start:
				display = start
			else:
				display = deadline

		if start and end and start != end:
			deadline = display
		elif deadline in {"未提及", "无"} and start:
			deadline = start

		return deadline, (start or "无"), (end or "无"), (display or "未提及")

	def _normalize_action_suggestion(
		self,
		task_name: str,
		action_text: str,
		deliverables: list[str],
		deadline_display: str,
	) -> str:
		text = self._sanitize_human_text(action_text)
		if re.search(r"^\s*1[\.、]", text) and re.search(r"[；;]\s*2[\.、]", text):
			return text

		deli_text = "；".join(deliverables[:2]) if deliverables else "按通知要求准备材料"
		core_action = text if text not in {"", "无", "未提及"} else f"落实{task_name}执行动作"

		step1 = f"确认{task_name}的执行范围与责任分工"
		step2 = f"按要求完成关键动作：{core_action}"
		if deadline_display not in {"", "无", "未提及", "长期有效", "按需执行"}:
			step3 = f"围绕交付物（{deli_text}）在{deadline_display}前提交并留痕反馈"
		else:
			step3 = f"围绕交付物（{deli_text}）完成提交并按制度节奏跟踪反馈"

		return f"1. {step1}；2. {step2}；3. {step3}。"

	def _normalize_result(
		self,
		result: Mapping[str, Any],
		doc_id: str,
		plain_text: str,
		source_blocks: Iterable[Mapping[str, Any]],
	) -> dict[str, Any]:
		normalized: dict[str, Any] = {}
		normalized["doc_id"] = _normalize_string(result.get("doc_id"), fallback=doc_id)
		normalized["title"] = self._sanitize_human_text(result.get("title", "未提及"))
		normalized["document_no"] = _normalize_string(result.get("document_no"), fallback="未提及")

		publish_date_raw = _normalize_string(result.get("publish_date"), fallback="未提及")
		normalized["publish_date"] = self._normalize_date_literal(publish_date_raw, plain_text)
		normalized["issuing_department"] = _normalize_string(
			result.get("issuing_department"),
			fallback="未提及",
		)

		doc_type_raw = _normalize_string(result.get("doc_type"), fallback="")
		normalized["doc_type"] = self._infer_doc_type(
			doc_type=doc_type_raw,
			title=normalized["title"],
			plain_text=plain_text,
		)

		source_block_ids = [str(block.get("block_id", "")).strip() for block in source_blocks]
		source_block_ids = [block_id for block_id in source_block_ids if block_id]

		raw_tasks = result.get("tasks")
		tasks_input = raw_tasks if isinstance(raw_tasks, list) else []
		normalized_tasks: list[dict[str, Any]] = []
		doc_type_decision = normalized["doc_type"]
		self.logger.info(
			"STEP=pipeline.reader | AGENT=Reader | ACTION=NormalizeStart | DETAILS=doc_id=%s inferred_doc_type=%s input_tasks=%s",
			doc_id,
			doc_type_decision,
			len(tasks_input),
		)

		for index, task in enumerate(tasks_input, start=1):
			if not isinstance(task, Mapping):
				continue

			task_name = self._sanitize_human_text(task.get("task_name", "未提及"))
			action_suggestion_raw = self._sanitize_human_text(task.get("action_suggestion", "未提及"))
			owner = _normalize_string(task.get("owner"), fallback="")
			if owner in {"", "无", "未提及"}:
				owner = self._infer_owner(
					task_text=f"{task_name}\n{action_suggestion_raw}",
					title=normalized["title"],
					plain_text=plain_text,
					doc_type=normalized["doc_type"],
				)
			owner = self._sanitize_human_text(owner)

			deadline, deadline_start, deadline_end, deadline_display = self._normalize_deadline_fields(
				task=task,
				plain_text=plain_text,
				doc_type=normalized["doc_type"],
			)

			deliverables_raw = task.get("deliverables")
			deliverables = (
				deliverables_raw if isinstance(deliverables_raw, list) else []
			)
			normalized_deliverables = self._normalize_deliverables(
				deliverables=deliverables,
				task_name=task_name,
				action_suggestion=action_suggestion_raw,
			)

			action_suggestion = self._normalize_action_suggestion(
				task_name=task_name,
				action_text=action_suggestion_raw,
				deliverables=normalized_deliverables,
				deadline_display=deadline_display,
			)

			source_anchor_raw = task.get("source_anchor")
			source_anchor = source_anchor_raw if isinstance(source_anchor_raw, Mapping) else {}
			block_id = _normalize_string(source_anchor.get("block_id"), fallback="")
			if not re.match(r"^p\d{3,6}$", block_id, flags=re.IGNORECASE):
				if source_block_ids:
					block_id = source_block_ids[min(index - 1, len(source_block_ids) - 1)]
				else:
					block_id = f"p{index:04d}"

			quote = self._sanitize_human_text(source_anchor.get("quote", "未提及"))

			normalized_tasks.append(
				{
					"task_id": _normalize_string(task.get("task_id"), fallback=f"task_{index:03d}"),
					"task_name": task_name,
					"owner": owner,
					"deadline": deadline,
					"deadline_start": deadline_start,
					"deadline_end": deadline_end,
					"deadline_display": deadline_display,
					"deliverables": normalized_deliverables,
					"action_suggestion": action_suggestion,
					"source_anchor": {
						"block_id": block_id,
						"quote": quote,
					},
				}
			)

		normalized["tasks"] = normalized_tasks

		raw_risks = result.get("risks_or_unclear_points")
		risks_input = raw_risks if isinstance(raw_risks, list) else []
		normalized["risks_or_unclear_points"] = [
			self._sanitize_human_text(item)
			for item in risks_input
			if self._sanitize_human_text(item) not in {"", "无"}
		]

		raw_questions = result.get("follow_up_questions")
		questions_input = raw_questions if isinstance(raw_questions, list) else []
		normalized["follow_up_questions"] = [
			self._sanitize_human_text(item)
			for item in questions_input
			if self._sanitize_human_text(item) not in {"", "无"}
		]

		raw_summary = _normalize_string(result.get("summary"), fallback=normalized["title"])
		normalized["summary"] = self._enforce_summary_format(
			summary=raw_summary,
			title=normalized["title"],
			tasks=normalized_tasks,
		)

		self.logger.info(
			"STEP=pipeline.reader | AGENT=Reader | ACTION=NormalizeDone | DETAILS=doc_id=%s normalized_tasks=%s summary_chars=%s",
			doc_id,
			len(normalized_tasks),
			len(normalized["summary"]),
		)

		return normalized

	def _validate_result(self, result: Mapping[str, Any]) -> None:
		required_top = [
			"doc_id",
			"doc_type",
			"title",
			"document_no",
			"publish_date",
			"issuing_department",
			"summary",
			"tasks",
			"risks_or_unclear_points",
			"follow_up_questions",
		]
		missing_top = [key for key in required_top if key not in result]
		if missing_top:
			raise ValueError(f"Missing required keys: {missing_top}")

		summary = result.get("summary")
		if not isinstance(summary, str) or not summary.strip():
			raise ValueError("summary must be non-empty string.")
		for marker in ["【核心主旨】：", "【关键动作】：", "【涉及范围】："]:
			if marker not in summary:
				raise ValueError("summary must include all required structured markers.")

		if INTERNAL_BLOCK_PATTERN.search(summary):
			raise ValueError("summary cannot contain internal block ID labels.")

		tasks = result.get("tasks")
		if not isinstance(tasks, list):
			raise ValueError("tasks must be an array.")
		if not tasks:
			raise ValueError("tasks cannot be empty.")

		for index, task in enumerate(tasks, start=1):
			if not isinstance(task, Mapping):
				raise ValueError(f"task[{index}] must be an object.")

			for key in [
				"task_name",
				"owner",
				"deadline",
				"deadline_start",
				"deadline_end",
				"deadline_display",
				"deliverables",
				"action_suggestion",
				"source_anchor",
			]:
				if key not in task:
					raise ValueError(f"task[{index}] missing required key: {key}")

			owner = task.get("owner")
			if not isinstance(owner, str) or not owner.strip():
				raise ValueError(f"task[{index}].owner must be non-empty string.")

			deadline = task.get("deadline")
			if not isinstance(deadline, str) or not deadline.strip():
				raise ValueError(f"task[{index}].deadline must be non-empty string.")

			for key in ["deadline_start", "deadline_end", "deadline_display"]:
				value = task.get(key)
				if not isinstance(value, str) or not value.strip():
					raise ValueError(f"task[{index}].{key} must be non-empty string.")

			deliverables = task.get("deliverables")
			if not isinstance(deliverables, list) or not deliverables:
				raise ValueError(f"task[{index}].deliverables must be a non-empty array.")

			source_anchor = task.get("source_anchor")
			if not isinstance(source_anchor, Mapping):
				raise ValueError(f"task[{index}].source_anchor must be an object.")
			block_id = source_anchor.get("block_id")
			if not isinstance(block_id, str) or not re.match(r"^p\d{3,6}$", block_id, flags=re.IGNORECASE):
				raise ValueError(f"task[{index}].source_anchor.block_id is required.")

			for key in ["task_name", "owner", "action_suggestion"]:
				value = task.get(key)
				if isinstance(value, str) and INTERNAL_BLOCK_PATTERN.search(value):
					raise ValueError(f"task[{index}].{key} cannot contain internal block ID labels.")

			action = str(task.get("action_suggestion", ""))
			if not re.search(r"^\s*1[\.、]", action):
				raise ValueError(f"task[{index}].action_suggestion must be checklist style.")

		for field in ["risks_or_unclear_points", "follow_up_questions"]:
			items = result.get(field)
			if not isinstance(items, list):
				raise ValueError(f"{field} must be an array.")
			for idx, item in enumerate(items, start=1):
				if not isinstance(item, str):
					raise ValueError(f"{field}[{idx}] must be string.")
				if INTERNAL_BLOCK_PATTERN.search(item):
					raise ValueError(f"{field}[{idx}] cannot contain internal block ID labels.")

