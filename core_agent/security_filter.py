from __future__ import annotations

import copy
import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping


@dataclass
class MaskingResult:
	masked_text: str
	placeholder_to_original: dict[str, str] = field(default_factory=dict)


DEFAULT_PATTERNS: list[dict[str, str]] = [
	{
		"category": "EMAIL",
		"pattern": r"(?<![A-Za-z0-9._%+-])[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}(?![A-Za-z0-9.-])",
	},
	{"category": "PHONE", "pattern": r"(?<!\d)(?:\+?86[-\s]?)?1[3-9]\d{9}(?!\d)"},
	{"category": "LANDLINE", "pattern": r"(?<!\d)0\d{2,3}-?\d{7,8}(?!\d)"},
	{"category": "ID", "pattern": r"(?<!\d)\d{17}[\dXx](?!\d)"},
	{"category": "BANK", "pattern": r"(?<!\d)\d{16,19}(?!\d)"},
	{
		"category": "PERSON",
		"pattern": r"(?P<prefix>(?:联系人|负责人|签发人|经办人|姓名|老师|同学|同志)\s*[：:]?\s*)(?P<value>[\u4e00-\u9fa5·]{2,6})",
	},
]


class SecurityFilter:
	"""Mask sensitive information before sending text to cloud model."""

	def __init__(self, patterns: Iterable[Mapping[str, str]] | None = None) -> None:
		pattern_cfg = list(patterns) if patterns is not None else DEFAULT_PATTERNS
		self.patterns: list[tuple[str, re.Pattern[str]]] = []
		for item in pattern_cfg:
			category = str(item.get("category", "GEN")).upper().strip() or "GEN"
			pattern = str(item.get("pattern", "")).strip()
			if not pattern:
				continue
			self.patterns.append((category, re.compile(pattern)))

	def mask_data(self, text: str) -> MaskingResult:
		"""Mask sensitive entities in plain text."""
		placeholder_to_original: dict[str, str] = {}
		original_to_placeholder: dict[str, str] = {}
		counter: dict[str, int] = {}

		def _allocate_placeholder(category: str, original: str) -> str:
			if original in original_to_placeholder:
				return original_to_placeholder[original]

			index = counter.get(category, 0) + 1
			counter[category] = index
			placeholder = f"[{category}_{index:03d}]"
			original_to_placeholder[original] = placeholder
			placeholder_to_original[placeholder] = original
			return placeholder

		masked = text
		for category, regex in self.patterns:
			if "(?P<value>" in regex.pattern:
				def _replace_with_named_group(match: re.Match[str]) -> str:
					prefix = match.groupdict().get("prefix", "")
					value = match.groupdict().get("value", "")
					if not value:
						return match.group(0)
					placeholder = _allocate_placeholder(category, value)
					return f"{prefix}{placeholder}"

				masked = regex.sub(_replace_with_named_group, masked)
				continue

			def _replace(match: re.Match[str]) -> str:
				original = match.group(0)
				return _allocate_placeholder(category, original)

			masked = regex.sub(_replace, masked)

		return MaskingResult(masked_text=masked, placeholder_to_original=placeholder_to_original)

	def unmask_text(self, text: str, placeholder_to_original: Mapping[str, str]) -> str:
		"""Recover masked text back to original values."""
		result = text
		# Replace longer placeholders first to avoid partial replacements.
		for placeholder in sorted(placeholder_to_original.keys(), key=len, reverse=True):
			result = result.replace(placeholder, str(placeholder_to_original[placeholder]))
		return result

	def mask_document(self, parsed_doc: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, str]]:
		"""Mask parsed document text and each block text with shared mapping."""
		doc = copy.deepcopy(dict(parsed_doc))
		combined_mapping: dict[str, str] = {}

		plain_text = str(doc.get("plain_text", ""))
		plain_result = self.mask_data(plain_text)
		doc["plain_text"] = plain_result.masked_text
		combined_mapping.update(plain_result.placeholder_to_original)

		blocks = doc.get("blocks", [])
		if isinstance(blocks, list):
			masked_blocks: list[dict[str, Any]] = []
			for block in blocks:
				if not isinstance(block, Mapping):
					continue
				new_block = dict(block)
				text = str(new_block.get("text", ""))
				if text:
					masked = self.mask_data(text)
					new_block["text"] = masked.masked_text
					combined_mapping.update(masked.placeholder_to_original)
				masked_blocks.append(new_block)
			doc["blocks"] = masked_blocks

		return doc, combined_mapping

	def unmask_data(self, data: Any, placeholder_to_original: Mapping[str, str]) -> Any:
		"""Recursively unmask placeholders in dict/list/string payloads."""
		if isinstance(data, str):
			return self.unmask_text(data, placeholder_to_original)
		if isinstance(data, list):
			return [self.unmask_data(item, placeholder_to_original) for item in data]
		if isinstance(data, Mapping):
			return {key: self.unmask_data(value, placeholder_to_original) for key, value in data.items()}
		return data

