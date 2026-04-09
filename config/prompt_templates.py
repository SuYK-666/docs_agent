from __future__ import annotations

import json
from typing import Any, Iterable, Mapping


READER_JSON_SCHEMA_HINT: dict[str, Any] = {
	"doc_id": "string",
	"doc_type": "事务性通知 | 管理办法/规章制度 | 其他",
	"title": "string",
	"document_no": "string, use '无' or '未提及' when unavailable",
	"publish_date": "string, allowed: YYYY-MM-DD / YYYY-MM / YYYY / '无' / '未提及'",
	"issuing_department": "string, use '无' or '未提及' when unavailable",
	"summary": "<= 250 Chinese characters, must contain 3 sections",
	"tasks": [
		{
			"task_id": "string",
			"task_name": "string",
			"owner": "string, cannot be empty",
			"deadline": "string, keep legacy-compatible deadline text",
			"deadline_start": "YYYY-MM-DD | '无'",
			"deadline_end": "YYYY-MM-DD | '无'",
			"deadline_display": "display text such as '2026-07-17至2026-08-20' | '长期有效' | '按需执行' | '无' | '未提及'",
			"deliverables": ["string"],
			"action_suggestion": "string, MUST be checklist style: '1....；2....；3....'",
			"source_anchor": {
				"block_id": "p0001",
				"quote": "short quote from original text",
			},
		}
	],
	"risks_or_unclear_points": ["string, natural language only, no internal IDs like p0008"],
	"follow_up_questions": ["string"],
}


def build_reader_system_prompt(summary_target_chars: int = 250) -> str:
	"""Build the system prompt used by Reader Agent."""
	schema_text = json.dumps(READER_JSON_SCHEMA_HINT, ensure_ascii=False, indent=2)
	return (
		"You are Reader Agent for Chinese government-style official documents. "
		"Extract actionable information with strict factual grounding.\n\n"
		"Hard rules:\n"
		"1) Output must be valid JSON only. No markdown, no prose outside JSON.\n"
		"2) Never fabricate data. If a field is not provided, use '无' or '未提及'. "
		"Do not output null anywhere.\n"
		"3) Date extraction must be literal. If source says only '2026年3月', keep month-level date only. "
		"Do not invent day values like 2026-03-01.\n"
		"4) Infer owner responsibly: if no explicit person/department is named, infer implicit executor from context "
		"(e.g., 各学院, 参赛团队, 全体教职工), and do not leave owner empty.\n"
		"5) Determine document type first. For 事务性通知, extract concrete deadlines whenever available. "
		"For 管理办法/规章制度, use '长期有效' or '按需执行' for process-oriented tasks.\n"
		"6) Internal source labels like p0001 are allowed only in source_anchor.block_id. "
		"In summary/tasks/risks/questions, do not expose internal IDs; use natural language only.\n"
		"7) summary must be <= "
		f"{summary_target_chars} Chinese characters and include exactly three prefixed sections:\n"
		"【核心主旨】：...\n【关键动作】：...\n【涉及范围】：...\n"
		"8) Keep output compact for reliability: tasks <= 8, risks <= 4, follow_up_questions <= 4.\n"
		"9) Every task must include source_anchor.block_id and short source quote.\n"
		"10) Deliverables must be checklist-ready with pattern '[交付载体/格式] + [核心内容]'. "
		"Avoid vague nouns only. Example: '参赛作品（含文档与10分钟内演示视频）', "
		"'上推国赛作品数据（通过国赛平台填报）'.\n"
		"11) Keep deliverables concrete and verifiable (forms, reports, attachments, submissions, etc.).\n"
		"12) Time extraction for activity/competition/meeting tasks must preserve ranges with three fields: "
		"deadline_start, deadline_end, deadline_display. "
		"Example: 7月17日至8月20日 -> 'deadline_start':'2026-07-17', "
		"'deadline_end':'2026-08-20', 'deadline_display':'2026-07-17至2026-08-20'.\n"
		"13) action_suggestion MUST be SOP checklist style, not one-sentence prose.\n"
		"Correct example: '1. 拍摄5-10张全景/特写照片；2. 筛选确保单张大于2MB且无水印；"
		"3. 统一命名为[学院-序号-场景]格式。'\n"
		"Wrong example: '按要求拍摄并筛选照片，注意命名规范。'\n\n"
		"Required JSON schema (type hints):\n"
		f"{schema_text}\n"
	)


def build_reader_user_prompt(
	doc_id: str,
	plain_text: str,
	source_blocks: Iterable[Mapping[str, Any]],
	max_blocks: int = 180,
	max_text_chars: int = 45_000,
) -> str:
	"""Build the user prompt with source blocks for citation anchors."""
	clipped_text = plain_text[:max_text_chars]
	block_lines: list[str] = []

	for index, block in enumerate(source_blocks):
		if index >= max_blocks:
			block_lines.append("... (truncated source blocks)")
			break
		block_id = str(block.get("block_id", ""))
		paragraph_index = block.get("paragraph_index")
		text = str(block.get("text", "")).strip().replace("\n", " ")
		if not text:
			continue
		block_lines.append(
			f"{block_id} | paragraph_index={paragraph_index} | text={text}"
		)

	source_block_text = "\n".join(block_lines)
	return (
		f"Document ID: {doc_id}\n\n"
		"Please classify document type before filling tasks.\n"
		"Document full text (possibly clipped for token safety):\n"
		f"{clipped_text}\n\n"
		"Source blocks for citation anchors:\n"
		f"{source_block_text}\n\n"
		"Reminder: internal block labels can appear only at source_anchor.block_id."
		" Natural-language fields must not include labels like p0008.\n"
		"Return only valid JSON matching the schema in system prompt."
	)

