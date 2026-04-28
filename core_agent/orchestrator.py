from __future__ import annotations

import asyncio
import logging
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Mapping

from config.logger_setup import to_relative_path
from core_agent.agent_critic import CriticAgent
from core_agent.agent_dispatcher import DispatcherAgent
from core_agent.agent_reader import ReaderAgent
from core_agent.agent_reviewer import ReviewerAgent
from core_agent.security_filter import SecurityFilter


PROJECT_ROOT = Path(__file__).resolve().parent.parent
TOOLS_RAG_DIR = PROJECT_ROOT / "tools_&_rag"
if str(TOOLS_RAG_DIR) not in sys.path:
	sys.path.insert(0, str(TOOLS_RAG_DIR))

from calendar_builder import build_ics_from_tasks, save_ics_file  # noqa: E402  pylint: disable=wrong-import-position
from rag_retriever import RAGRetriever  # noqa: E402  pylint: disable=wrong-import-position
from urgency_engine import annotate_tasks_with_urgency, summarize_urgency  # noqa: E402  pylint: disable=wrong-import-position


class Orchestrator:
	"""Reader -> Reviewer -> Dispatcher pipeline with security and utility tools."""

	@staticmethod
	def _task_sort_key(task: Mapping[str, Any]) -> tuple[int, str]:
		task_id = str(task.get("task_id", "")).strip()
		match = re.search(r"(\d+)", task_id)
		if match:
			return int(match.group(1)), task_id
		return 10**9, task_id

	@staticmethod
	def _safe_int(value: Any, default: int = 0) -> int:
		try:
			return int(float(value))
		except (TypeError, ValueError):
			return default

	@staticmethod
	def _parse_full_date(value: str) -> str | None:
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
	def _extract_date_range(cls, text: str) -> tuple[str | None, str | None]:
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

	@classmethod
	def _normalize_task_deadline_fields(cls, task: dict[str, Any]) -> dict[str, Any]:
		deadline = str(task.get("deadline", "未提及")).strip() or "未提及"
		display = str(task.get("deadline_display", "")).strip()
		start = cls._parse_full_date(str(task.get("deadline_start", "")).strip())
		end = cls._parse_full_date(str(task.get("deadline_end", "")).strip())

		range_start, range_end = cls._extract_date_range(display or deadline)
		if not start:
			start = range_start
		if not end:
			end = range_end

		single = cls._parse_full_date(deadline)
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

		task["deadline"] = deadline
		task["deadline_start"] = start or "无"
		task["deadline_end"] = end or "无"
		task["deadline_display"] = display or "未提及"
		return task

	def __init__(self, client: Any, settings: Mapping[str, Any], project_root: Path | None = None) -> None:
		self.client = client
		self.settings = settings
		self.project_root = project_root or PROJECT_ROOT
		self.logger = logging.getLogger("docs_agent.orchestrator")
		self.orchestrator_cfg = settings.get("orchestrator", {}) if isinstance(settings.get("orchestrator"), Mapping) else {}
		self.security_cfg = settings.get("security_filter", {}) if isinstance(settings.get("security_filter"), Mapping) else {}
		self.calendar_cfg = settings.get("calendar", {}) if isinstance(settings.get("calendar"), Mapping) else {}
		critic_cfg_raw = settings.get("critic")
		if not isinstance(critic_cfg_raw, Mapping):
			orchestrator_critic_cfg = self.orchestrator_cfg.get("critic") if isinstance(self.orchestrator_cfg.get("critic"), Mapping) else {}
			critic_cfg_raw = orchestrator_critic_cfg
		self.critic_cfg = critic_cfg_raw if isinstance(critic_cfg_raw, Mapping) else {}

		reader_cfg = settings.get("reader", {}) if isinstance(settings.get("reader"), Mapping) else {}
		reviewer_cfg = settings.get("reviewer", {}) if isinstance(settings.get("reviewer"), Mapping) else {}
		dispatcher_cfg = settings.get("dispatcher", {}) if isinstance(settings.get("dispatcher"), Mapping) else {}

		self.reader = ReaderAgent(
			client=client,
			summary_target_chars=int(reader_cfg.get("summary_target_words", 250)),
			json_retry_times=int(reader_cfg.get("json_retry_times", 3)),
			max_output_tokens=int(reader_cfg.get("max_output_tokens", 2600)),
		)
		self.reviewer = ReviewerAgent(
			client=client,
			json_retry_times=int(reviewer_cfg.get("json_retry_times", 2)),
			max_output_tokens=int(reviewer_cfg.get("max_output_tokens", 2600)),
		)
		self.dispatcher = DispatcherAgent(
			client=client,
			json_retry_times=int(dispatcher_cfg.get("json_retry_times", 1)),
		)

		self.critic_enabled = bool(self.critic_cfg.get("enabled", True))
		self.critic_score_threshold = max(0, min(100, int(self.critic_cfg.get("score_threshold", 85))))
		self.critic_max_rework_loops = max(1, int(self.critic_cfg.get("max_rework_loops", 2)))
		self.critic = CriticAgent(
			client=client,
			score_threshold=self.critic_score_threshold,
			json_retry_times=int(self.critic_cfg.get("json_retry_times", 2)),
			max_output_tokens=int(self.critic_cfg.get("max_output_tokens", 1800)),
		)

		security_cfg = settings.get("security_filter", {})
		patterns = security_cfg.get("patterns") if isinstance(security_cfg, Mapping) else None
		self.security_filter = SecurityFilter(patterns=patterns)

		paths_cfg = settings.get("paths", {}) if isinstance(settings.get("paths"), Mapping) else {}
		rag_cfg = settings.get("rag", {}) if isinstance(settings.get("rag"), Mapping) else {}
		rag_db_dir = self.project_root / str(paths_cfg.get("rag_db_dir", "data_workspace/rag_db"))
		self.rag_retriever = RAGRetriever(
			db_dir=rag_db_dir,
			top_k=int(rag_cfg.get("top_k", 3)),
			enabled=bool(rag_cfg.get("enabled", True)),
			rag_settings=rag_cfg,
		)

		app_cfg = settings.get("app", {}) if isinstance(settings.get("app"), Mapping) else {}
		configured_parallel = app_cfg.get(
			"max_parallel_tasks",
			app_cfg.get("max_parallel_docs", self.orchestrator_cfg.get("max_parallel_tasks", 10)),
		)
		self.max_parallel_tasks = max(1, self._safe_int(configured_parallel, 10))
		self._llm_semaphore = asyncio.Semaphore(self.max_parallel_tasks)

	def _normalize_tasks_with_urgency(self, tasks: Any) -> list[dict[str, Any]]:
		task_list: list[dict[str, Any]] = []
		if isinstance(tasks, list):
			for item in tasks:
				if not isinstance(item, Mapping):
					continue
				task_list.append(self._normalize_task_deadline_fields(dict(item)))

		tasks_with_urgency = annotate_tasks_with_urgency(task_list)
		return sorted(tasks_with_urgency, key=self._task_sort_key)

	async def _run_llm_call(self, call_coro: Any) -> Any:
		"""Limit concurrent LLM requests to reduce provider-side throttling risk."""
		async with self._llm_semaphore:
			return await call_coro

	async def _emit_stream_event(self, stream_callback: Callable[[Mapping[str, Any]], Any] | None, payload: Mapping[str, Any]) -> None:
		if stream_callback is None:
			return
		try:
			result = stream_callback(dict(payload))
			if asyncio.iscoroutine(result):
				await result
		except Exception as exc:  # pylint: disable=broad-except
			self.logger.warning(
				"STEP=pipeline.orchestrator | AGENT=Orchestrator | ACTION=StreamCallbackError | DETAILS=error=%s",
				exc,
			)

	def _build_node_stream_callback(
		self,
		stream_callback: Callable[[Mapping[str, Any]], Any] | None,
		node: str,
		extra_payload: Mapping[str, Any] | None = None,
	) -> Callable[[str], Any] | None:
		if stream_callback is None:
			return None

		def _on_chunk(chunk: str) -> Any:
			payload: dict[str, Any] = {
				"event": "token",
				"node": node,
				"content": chunk,
			}
			if isinstance(extra_payload, Mapping):
				payload.update(dict(extra_payload))
			return self._emit_stream_event(
				stream_callback,
				payload,
			)

		return _on_chunk

	async def generate_draft_plan(
		self,
		parsed_doc: Mapping[str, Any] | None = None,
		source_file: str | Path | None = None,
		stream_callback: Callable[[Mapping[str, Any]], Any] | None = None,
	) -> dict[str, Any]:
		"""Generate draft plan (Parser -> Reader -> Reviewer), waiting for human approval."""
		if parsed_doc is None:
			if source_file is None:
				raise ValueError("Either parsed_doc or source_file must be provided.")
			from ingestion.router import route_document

			parsed_doc = await asyncio.to_thread(route_document, file_path=source_file, settings=self.settings)

		metadata = parsed_doc.get("metadata", {}) if isinstance(parsed_doc.get("metadata"), Mapping) else {}
		stream_doc_id = str(parsed_doc.get("doc_id", "")).strip() or "unknown_doc"
		parser_name = str(metadata.get("parser", "")).strip() or "unknown"
		router_meta = metadata.get("router", {}) if isinstance(metadata.get("router"), Mapping) else {}
		router_strategy = str(router_meta.get("strategy", "")).strip() or "unknown"

		self.logger.info(
			"STEP=pipeline.orchestrator | AGENT=Orchestrator | ACTION=DraftStart | DETAILS=doc_id=%s",
			parsed_doc.get("doc_id", "unknown"),
		)
		pipeline_steps = ["reader"]
		security_enabled = bool(self.security_cfg.get("enabled", True))
		critic_result: dict[str, Any] | None = None
		critic_feedback = ""
		critic_used = False
		rework_iterations = 0
		low_confidence_warning = ""

		if security_enabled:
			masked_doc, placeholder_map = self.security_filter.mask_document(parsed_doc)
			self.logger.info("Security mask applied: %s placeholders", len(placeholder_map))
		else:
			masked_doc = dict(parsed_doc)
			placeholder_map = {}
			self.logger.info("STEP=pipeline.orchestrator | AGENT=SecurityFilter | ACTION=MaskSkipped")

		self.logger.info("STEP=pipeline.orchestrator | AGENT=Reader | ACTION=ReaderStart")
		await self._emit_stream_event(
			stream_callback,
			{
				"event": "stage_start",
				"node": "reader",
				"doc_id": stream_doc_id,
				"content": "Reader 开始抽取公文任务",
			},
		)
		reader_output = await self._run_llm_call(
			self.reader.extract(
				masked_doc,
				stream_callback=self._build_node_stream_callback(
					stream_callback,
					"reader",
					extra_payload={"doc_id": stream_doc_id},
				),
			)
		)
		await self._emit_stream_event(
			stream_callback,
			{
				"event": "stage_done",
				"node": "reader",
				"doc_id": stream_doc_id,
				"content": "Reader 抽取完成",
			},
		)
		self.logger.info(
			"STEP=pipeline.orchestrator | AGENT=Reader | ACTION=ReaderDone | DETAILS=tasks=%s",
			len(reader_output.get("tasks", [])) if isinstance(reader_output.get("tasks"), list) else 0,
		)

		reviewer_enabled = bool(self.orchestrator_cfg.get("enable_reviewer", True))
		rag_context = ""
		if reviewer_enabled and self.rag_retriever.enabled:
			self.logger.info("STEP=pipeline.orchestrator | AGENT=RAGRetriever | ACTION=RetrieveStart")
			rag_context, rag_hits = await asyncio.to_thread(
				self.rag_retriever.retrieve,
				parsed_doc=masked_doc,
				reader_output=reader_output,
			)
			self.logger.info(
				"STEP=pipeline.orchestrator | AGENT=RAGRetriever | ACTION=RetrieveDone | DETAILS=hits=%s",
				rag_hits,
			)
		elif reviewer_enabled:
			self.logger.info("STEP=pipeline.orchestrator | AGENT=RAGRetriever | ACTION=RetrieveSkipped")

		if reviewer_enabled:
			critic_active = self.critic_enabled and self.critic is not None
			max_loops = self.critic_max_rework_loops if critic_active else 1
			reviewer_output = dict(reader_output)

			for attempt in range(1, max_loops + 1):
				self.logger.info(
					"STEP=pipeline.orchestrator | AGENT=Reviewer | ACTION=ReviewerStart | DETAILS=attempt=%s/%s has_feedback=%s",
					attempt,
					max_loops,
					bool(critic_feedback),
				)
				await self._emit_stream_event(
					stream_callback,
					{
						"event": "stage_start",
						"node": "reviewer",
						"doc_id": stream_doc_id,
						"content": f"Reviewer 复核中（第 {attempt}/{max_loops} 轮）",
					},
				)
				reviewer_output = await self._run_llm_call(
					self.reviewer.review(
						reader_output=reviewer_output,
						parsed_doc=masked_doc,
						rag_context=rag_context,
						critic_feedback=critic_feedback,
						stream_callback=self._build_node_stream_callback(
							stream_callback,
							"reviewer",
							extra_payload={"doc_id": stream_doc_id},
						),
					)
				)
				await self._emit_stream_event(
					stream_callback,
					{
						"event": "stage_done",
						"node": "reviewer",
						"doc_id": stream_doc_id,
						"content": f"Reviewer 复核完成（第 {attempt}/{max_loops} 轮）",
					},
				)
				self.logger.info(
					"STEP=pipeline.orchestrator | AGENT=Reviewer | ACTION=ReviewerDone | DETAILS=attempt=%s/%s tasks=%s",
					attempt,
					max_loops,
					len(reviewer_output.get("tasks", [])) if isinstance(reviewer_output.get("tasks"), list) else 0,
				)

				if not critic_active:
					break

				critic_used = True
				self.logger.info(
					"STEP=pipeline.orchestrator | AGENT=Critic | ACTION=CriticStart | DETAILS=attempt=%s/%s threshold=%s",
					attempt,
					max_loops,
					self.critic_score_threshold,
				)
				critic_result = await self._run_llm_call(self.critic.evaluate(parsed_doc=masked_doc, draft_output=reviewer_output))
				self.logger.info(
					"STEP=pipeline.orchestrator | AGENT=Critic | ACTION=CriticDone | DETAILS=attempt=%s/%s score=%s passed=%s",
					attempt,
					max_loops,
					critic_result.get("total_score", 0),
					critic_result.get("passed", False),
				)
				score_value = self._safe_int(critic_result.get("total_score", 0), 0)
				await self._emit_stream_event(
					stream_callback,
					{
						"event": "reviewer_score",
						"node": "reviewer",
						"doc_id": stream_doc_id,
						"content": f"第{attempt}轮复核分数是{score_value}分",
						"meta": {
							"attempt": attempt,
							"total_rounds": max_loops,
							"score": score_value,
						},
					},
				)

				if bool(critic_result.get("passed", False)):
					break

				if attempt < max_loops:
					critic_feedback = str(critic_result.get("feedback", "")).strip()
					rework_iterations = attempt
					self.logger.warning(
						"STEP=pipeline.orchestrator | AGENT=Critic | ACTION=DraftRejected | DETAILS=attempt=%s/%s score=%s retrying=true",
						attempt,
						max_loops,
						critic_result.get("total_score", 0),
					)
					continue

				rework_iterations = max(0, attempt - 1)
				low_confidence_warning = f"Low confidence score: {int(critic_result.get('total_score', 0))}"
				self.logger.warning(
					"STEP=pipeline.orchestrator | AGENT=Critic | ACTION=DraftLoopExhausted | DETAILS=attempt=%s/%s score=%s warning=%s",
					attempt,
					max_loops,
					critic_result.get("total_score", 0),
					low_confidence_warning,
				)

			if critic_active and max_loops == 1:
				rework_iterations = 0

			pipeline_steps.append("reviewer")
			if critic_used:
				pipeline_steps.append("critic")
		else:
			reviewer_output = dict(reader_output)
			self.logger.info("STEP=pipeline.orchestrator | AGENT=Reviewer | ACTION=ReviewerSkipped")

		final_output = self.security_filter.unmask_data(reviewer_output, placeholder_map)
		self.logger.info(
			"STEP=pipeline.orchestrator | AGENT=SecurityFilter | ACTION=UnmaskDone | DETAILS=placeholders=%s",
			len(placeholder_map),
		)

		tasks_with_urgency = self._normalize_tasks_with_urgency(final_output.get("tasks", []))
		final_output["tasks"] = tasks_with_urgency
		final_output["urgency_summary"] = summarize_urgency(tasks_with_urgency)
		final_output["status"] = "pending_approval"
		final_output["approval"] = {
			"required": True,
			"approved_at": "",
			"approved_by": "",
		}
		llm_cfg = self.settings.get("llm", {}) if isinstance(self.settings.get("llm"), Mapping) else {}
		llm_provider = str(llm_cfg.get("provider", "deepseek")).strip() or "deepseek"
		critic_dimensions = {
			"completeness_score": self._safe_int(critic_result.get("completeness_score", 0), 0) if isinstance(critic_result, Mapping) else 0,
			"accuracy_score": self._safe_int(critic_result.get("accuracy_score", 0), 0) if isinstance(critic_result, Mapping) else 0,
			"executability_score": self._safe_int(critic_result.get("executability_score", 0), 0) if isinstance(critic_result, Mapping) else 0,
			"total_score": self._safe_int(critic_result.get("total_score", 0), 0) if isinstance(critic_result, Mapping) else 0,
			"passed": bool(critic_result.get("passed", False)) if isinstance(critic_result, Mapping) else False,
		}
		final_output["pipeline_meta"] = {
			"mask_placeholder_count": len(placeholder_map),
			"pipeline": pipeline_steps,
			"security_enabled": security_enabled,
			"parser": parser_name,
			"router_strategy": router_strategy,
			"llm_provider": llm_provider,
			"critic_enabled": self.critic_enabled,
			"critic_threshold": self.critic_score_threshold,
			"critic_final_score": critic_dimensions["total_score"],
			"rework_iterations": rework_iterations,
			"critic_dimensions": critic_dimensions,
			"critic_feedback": str(critic_result.get("feedback", "")) if isinstance(critic_result, Mapping) else "",
		}
		final_output["critic_evaluation"] = {
			**critic_dimensions,
			"critic_feedback": final_output["pipeline_meta"]["critic_feedback"],
		}
		if low_confidence_warning:
			final_output["warning"] = low_confidence_warning
		self.logger.info(
			"STEP=pipeline.orchestrator | AGENT=Orchestrator | ACTION=DraftDone | DETAILS=pipeline=%s tasks=%s",
			pipeline_steps,
			len(tasks_with_urgency),
		)
		return final_output

	async def execute_dispatch_plan(
		self,
		draft_output: Mapping[str, Any],
		generate_calendar: bool = True,
		save_calendar: bool = False,
		dispatch_owner: str | None = None,
		email_sender: Any | None = None,
		stream_callback: Callable[[Mapping[str, Any]], Any] | None = None,
	) -> dict[str, Any]:
		"""Execute approved plan (Calendar -> Dispatcher -> optional Email)."""
		final_output = dict(draft_output)
		pipeline_meta = final_output.get("pipeline_meta", {}) if isinstance(final_output.get("pipeline_meta"), Mapping) else {}
		pipeline_steps = list(pipeline_meta.get("pipeline", [])) if isinstance(pipeline_meta.get("pipeline"), list) else []
		if not pipeline_steps:
			pipeline_steps = ["reader", "reviewer"]

		tasks_with_urgency = self._normalize_tasks_with_urgency(final_output.get("tasks", []))
		final_output["tasks"] = tasks_with_urgency
		final_output["urgency_summary"] = summarize_urgency(tasks_with_urgency)

		calendar_enabled = bool(self.orchestrator_cfg.get("generate_calendar", True)) and generate_calendar
		if calendar_enabled:
			self.logger.info("STEP=pipeline.orchestrator | AGENT=CalendarBuilder | ACTION=CalendarBuildStart")
			ics_text, events = await asyncio.to_thread(
				build_ics_from_tasks,
				tasks=tasks_with_urgency,
				doc_id=str(final_output.get("doc_id", "unknown_doc")),
				calendar_name=str(self.calendar_cfg.get("calendar_name", "公文任务日程")),
			)
			calendar_info: dict[str, Any] = {
				"event_count": len(events),
				"events": events,
			}
			if save_calendar and events:
				paths_cfg = self.settings.get("paths", {}) if isinstance(self.settings.get("paths"), Mapping) else {}
				final_reports_dir = str(paths_cfg.get("final_reports_dir", "data_workspace/final_reports"))
				out_dir = self.project_root / final_reports_dir
				file_name = f"{final_output.get('doc_id', 'unknown_doc')}.ics"
				ics_path = await asyncio.to_thread(save_ics_file, ics_text, out_dir / file_name)
				calendar_info["ics_file"] = to_relative_path(ics_path)
				self.logger.info("ICS generated: %s", to_relative_path(ics_path))
			final_output["calendar"] = calendar_info
			self.logger.info(
				"STEP=pipeline.orchestrator | AGENT=CalendarBuilder | ACTION=CalendarBuildDone | DETAILS=event_count=%s",
				len(events),
			)
			if "calendar" not in pipeline_steps:
				pipeline_steps.append("calendar")
		else:
			self.logger.info("STEP=pipeline.orchestrator | AGENT=CalendarBuilder | ACTION=CalendarSkipped")

		dispatcher_enabled = bool(self.orchestrator_cfg.get("enable_dispatcher", True))
		if dispatcher_enabled:
			stream_doc_id = str(final_output.get("doc_id", "")).strip() or "unknown_doc"
			configured_owner = ""
			if isinstance(self.settings.get("dispatcher"), Mapping):
				configured_owner = str(self.settings.get("dispatcher", {}).get("target_owner", "")).strip()
			effective_owner = dispatch_owner or configured_owner or None
			await self._emit_stream_event(
				stream_callback,
				{
					"event": "stage_start",
					"node": "dispatcher",
					"doc_id": stream_doc_id,
					"content": "Dispatcher 正在生成下发文案",
				},
			)
			self.logger.info(
				"STEP=pipeline.orchestrator | AGENT=Dispatcher | ACTION=DispatchStart | DETAILS=effective_owner=%s",
				effective_owner or "ALL",
			)
			dispatch_output = await self._run_llm_call(
				self.dispatcher.dispatch(
					final_output,
					target_owner=effective_owner,
					stream_callback=self._build_node_stream_callback(
						stream_callback,
						"dispatcher",
						extra_payload={"doc_id": stream_doc_id},
					),
				)
			)
			final_output["dispatch"] = dispatch_output
			if "dispatcher" not in pipeline_steps:
				pipeline_steps.append("dispatcher")
			await self._emit_stream_event(
				stream_callback,
				{
					"event": "stage_done",
					"node": "dispatcher",
					"doc_id": stream_doc_id,
					"content": "Dispatcher 下发文案生成完成",
				},
			)
			self.logger.info("STEP=pipeline.orchestrator | AGENT=Dispatcher | ACTION=DispatchDone")
		else:
			self.logger.info("STEP=pipeline.orchestrator | AGENT=Dispatcher | ACTION=DispatchSkipped")

		if callable(email_sender):
			self.logger.info("STEP=pipeline.orchestrator | AGENT=EmailGateway | ACTION=EmailStart")
			final_output["email_result"] = email_sender(final_output)
			if "email" not in pipeline_steps:
				pipeline_steps.append("email")
			self.logger.info("STEP=pipeline.orchestrator | AGENT=EmailGateway | ACTION=EmailDone")

		approval = final_output.get("approval", {}) if isinstance(final_output.get("approval"), Mapping) else {}
		approval_payload = dict(approval)
		approval_payload["required"] = True
		if not str(approval_payload.get("approved_at", "")).strip():
			approval_payload["approved_at"] = datetime.now().isoformat(timespec="seconds")
		final_output["approval"] = approval_payload
		final_output["status"] = "dispatched"

		security_enabled = bool(pipeline_meta.get("security_enabled", self.security_cfg.get("enabled", True)))
		mask_placeholder_count = int(pipeline_meta.get("mask_placeholder_count", 0))
		updated_pipeline_meta = dict(pipeline_meta)
		updated_pipeline_meta.update(
			{
				"mask_placeholder_count": mask_placeholder_count,
				"pipeline": pipeline_steps,
				"security_enabled": security_enabled,
			}
		)
		final_output["pipeline_meta"] = updated_pipeline_meta

		if self.rag_retriever.enabled:
			archived = await asyncio.to_thread(self.rag_retriever.archive, final_output)
			self.logger.info(
				"STEP=pipeline.orchestrator | AGENT=RAGRetriever | ACTION=ArchiveDone | DETAILS=archived=%s",
				archived,
			)

		self.logger.info(
			"STEP=pipeline.orchestrator | AGENT=Orchestrator | ACTION=DispatchDone | DETAILS=pipeline=%s tasks=%s",
			pipeline_steps,
			len(tasks_with_urgency),
		)
		return final_output

	async def run(
		self,
		parsed_doc: Mapping[str, Any],
		generate_calendar: bool = True,
		save_calendar: bool = False,
		dispatch_owner: str | None = None,
		stream_callback: Callable[[Mapping[str, Any]], Any] | None = None,
	) -> dict[str, Any]:
		self.logger.info(
			"STEP=pipeline.orchestrator | AGENT=Orchestrator | ACTION=RunStart | DETAILS=doc_id=%s generate_calendar=%s save_calendar=%s dispatch_owner=%s",
			parsed_doc.get("doc_id", "unknown"),
			generate_calendar,
			save_calendar,
			dispatch_owner or "ALL",
		)
		draft = await self.generate_draft_plan(parsed_doc=parsed_doc, stream_callback=stream_callback)
		result = await self.execute_dispatch_plan(
			draft_output=draft,
			generate_calendar=generate_calendar,
			save_calendar=save_calendar,
			dispatch_owner=dispatch_owner,
			stream_callback=stream_callback,
		)
		self.logger.info(
			"STEP=pipeline.orchestrator | AGENT=Orchestrator | ACTION=RunDone | DETAILS=status=%s pipeline=%s",
			result.get("status", "unknown"),
			result.get("pipeline_meta", {}).get("pipeline", []),
		)
		return result

