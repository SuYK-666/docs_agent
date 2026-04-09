from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from config.logger_setup import to_relative_path
from docx import Document
from pypdf import PdfReader

try:
	import fitz
except ImportError:  # pragma: no cover
	fitz = None


LOGGER = logging.getLogger("docs_agent.text_parser")


def _normalize_text(text: str) -> str:
	return " ".join(text.split())


def _yield_non_empty_lines(text: str) -> list[str]:
	normalized = text.replace("\x00", "")
	lines = re.split(r"\r?\n+", normalized)
	return [_normalize_text(line) for line in lines if _normalize_text(line)]


def _extract_pdf_lines_with_pypdf(path: Path, min_line_chars: int) -> tuple[list[dict[str, Any]], list[int]]:
	reader = PdfReader(str(path), strict=False)
	raw_blocks: list[dict[str, Any]] = []
	page_char_count: list[int] = []

	for page_number, page in enumerate(reader.pages, start=1):
		page_text = page.extract_text() or ""
		page_char_count.append(len(page_text.strip()))
		lines = _yield_non_empty_lines(page_text)

		for line_index, line in enumerate(lines, start=1):
			if len(line) < min_line_chars:
				continue
			raw_blocks.append(
				{
					"paragraph_index": None,
					"line_index": line_index,
					"page": page_number,
					"text": line,
				}
			)

	return raw_blocks, page_char_count


def _extract_pdf_lines_with_pymupdf(path: Path, min_line_chars: int) -> tuple[list[dict[str, Any]], list[int]]:
	if fitz is None:
		return [], []

	doc = fitz.open(str(path))
	raw_blocks: list[dict[str, Any]] = []
	page_char_count: list[int] = []

	try:
		for page_number, page in enumerate(doc, start=1):
			page_text = page.get_text("text") or ""
			page_char_count.append(len(page_text.strip()))
			lines = _yield_non_empty_lines(page_text)

			for line_index, line in enumerate(lines, start=1):
				if len(line) < min_line_chars:
					continue
				raw_blocks.append(
					{
						"paragraph_index": None,
						"line_index": line_index,
						"page": page_number,
						"text": line,
					}
				)
	finally:
		doc.close()

	return raw_blocks, page_char_count


def inspect_pdf_text_density(file_path: str | Path) -> dict[str, Any]:
	"""Inspect extractable text density with pypdf and optional PyMuPDF fallback."""
	path = Path(file_path)
	if not path.exists():
		raise FileNotFoundError(f"File not found: {path}")
	LOGGER.info("STEP=ingestion.inspect_pdf | AGENT=TextParser | ACTION=InspectStart | DETAILS=file=%s", to_relative_path(path))

	pypdf_blocks, pypdf_counts = _extract_pdf_lines_with_pypdf(path, min_line_chars=1)
	pymupdf_blocks, pymupdf_counts = _extract_pdf_lines_with_pymupdf(path, min_line_chars=1)

	pypdf_total = sum(pypdf_counts)
	pymupdf_total = sum(pymupdf_counts)
	use_engine = "pypdf" if pypdf_total >= pymupdf_total else "pymupdf"

	selected_counts = pypdf_counts if use_engine == "pypdf" else pymupdf_counts
	selected_total = sum(selected_counts)
	selected_non_empty = sum(1 for count in selected_counts if count > 0)
	page_count = max(len(pypdf_counts), len(pymupdf_counts), 0)

	stats = {
		"page_count": page_count,
		"page_char_count": selected_counts,
		"non_empty_pages": selected_non_empty,
		"non_empty_page_ratio": selected_non_empty / max(1, page_count),
		"total_chars": selected_total,
		"engine": use_engine,
		"engine_stats": {
			"pypdf": {
				"total_chars": pypdf_total,
				"non_empty_pages": sum(1 for count in pypdf_counts if count > 0),
				"page_count": len(pypdf_counts),
			},
			"pymupdf": {
				"total_chars": pymupdf_total,
				"non_empty_pages": sum(1 for count in pymupdf_counts if count > 0),
				"page_count": len(pymupdf_counts),
			},
		},
		"pypdf_block_count": len(pypdf_blocks),
		"pymupdf_block_count": len(pymupdf_blocks),
	}
	LOGGER.info(
		"STEP=ingestion.inspect_pdf | AGENT=TextParser | ACTION=InspectDone | DETAILS=engine=%s page_count=%s non_empty_ratio=%.3f total_chars=%s",
		stats.get("engine"),
		stats.get("page_count"),
		float(stats.get("non_empty_page_ratio", 0.0)),
		stats.get("total_chars"),
	)
	return stats


def _finalize_blocks(
	path: Path,
	raw_blocks: list[dict[str, Any]],
	parser_name: str,
	supports_page_anchor: bool,
	metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
	LOGGER.debug(
		"STEP=ingestion.finalize | AGENT=TextParser | ACTION=FinalizeStart | DETAILS=file=%s parser=%s raw_blocks=%s",
		to_relative_path(path),
		parser_name,
		len(raw_blocks),
	)
	blocks: list[dict[str, Any]] = []
	char_cursor = 0

	for item in raw_blocks:
		text = str(item["text"])
		block_id = f"p{len(blocks) + 1:04d}"
		start = char_cursor
		end = start + len(text)
		block = {
			"block_id": block_id,
			"paragraph_index": item.get("paragraph_index"),
			"line_index": item.get("line_index"),
			"page": item.get("page"),
			"text": text,
			"char_start": start,
			"char_end": end,
		}
		if "bbox" in item:
			block["bbox"] = item["bbox"]
		if "score" in item:
			block["score"] = item["score"]
		blocks.append(block)
		char_cursor = end + 1

	if not blocks:
		raise ValueError(f"No readable text found in: {path}")

	plain_text = "\n".join(block["text"] for block in blocks)

	base_metadata: dict[str, Any] = {
		"parser": parser_name,
		"paragraph_count": len(blocks),
		"supports_page_anchor": supports_page_anchor,
	}
	if metadata:
		base_metadata.update(metadata)

	output = {
		"doc_id": path.stem,
		"source_file": to_relative_path(path),
		"plain_text": plain_text,
		"blocks": blocks,
		"metadata": base_metadata,
	}
	LOGGER.info(
		"STEP=ingestion.finalize | AGENT=TextParser | ACTION=FinalizeDone | DETAILS=file=%s parser=%s blocks=%s chars=%s",
		to_relative_path(path),
		parser_name,
		len(blocks),
		len(plain_text),
	)
	return output


def parse_word_document(file_path: str | Path) -> dict[str, Any]:
	"""Parse .docx file and return text blocks with citation anchors."""

	path = Path(file_path)
	if not path.exists():
		raise FileNotFoundError(f"File not found: {path}")
	if path.suffix.lower() != ".docx":
		raise ValueError("Word parser only supports .docx files.")
	LOGGER.info("STEP=ingestion.word | AGENT=TextParser | ACTION=ParseWordStart | DETAILS=file=%s", to_relative_path(path))

	document = Document(str(path))
	raw_blocks: list[dict[str, Any]] = []

	for paragraph_index, paragraph in enumerate(document.paragraphs, start=1):
		text = _normalize_text(paragraph.text)
		if not text:
			continue
		raw_blocks.append(
			{
				"paragraph_index": paragraph_index,
				"line_index": None,
				"page": None,
				"text": text,
			}
		)

	LOGGER.info(
		"STEP=ingestion.word | AGENT=TextParser | ACTION=ExtractParagraphsDone | DETAILS=non_empty_paragraphs=%s",
		len(raw_blocks),
	)
	return _finalize_blocks(
		path=path,
		raw_blocks=raw_blocks,
		parser_name="docx_text_parser",
		supports_page_anchor=False,
	)


def parse_text_document(file_path: str | Path) -> dict[str, Any]:
	"""Parse plain text file and return line blocks."""
	path = Path(file_path)
	if not path.exists():
		raise FileNotFoundError(f"File not found: {path}")
	if path.suffix.lower() != ".txt":
		raise ValueError("Text parser only supports .txt files.")
	LOGGER.info("STEP=ingestion.text | AGENT=TextParser | ACTION=ParseTextStart | DETAILS=file=%s", to_relative_path(path))

	encodings = ["utf-8", "utf-8-sig", "gb18030", "gbk"]
	content = ""
	used_encoding = "utf-8"
	for encoding in encodings:
		try:
			content = path.read_text(encoding=encoding)
			used_encoding = encoding
			break
		except UnicodeDecodeError:
			continue
	if not content:
		content = path.read_text(encoding="utf-8", errors="replace")
		used_encoding = "utf-8(replace)"

	raw_blocks: list[dict[str, Any]] = []
	for line_index, line in enumerate(_yield_non_empty_lines(content), start=1):
		raw_blocks.append(
			{
				"paragraph_index": line_index,
				"line_index": line_index,
				"page": None,
				"text": line,
			}
		)

	LOGGER.info(
		"STEP=ingestion.text | AGENT=TextParser | ACTION=ParseTextDone | DETAILS=file=%s lines=%s chars=%s encoding=%s",
		to_relative_path(path),
		len(raw_blocks),
		len(content),
		used_encoding,
	)

	return _finalize_blocks(
		path=path,
		raw_blocks=raw_blocks,
		parser_name="txt_text_parser",
		supports_page_anchor=False,
		metadata={"encoding": used_encoding},
	)


def parse_pdf_text_document(file_path: str | Path, min_line_chars: int = 2) -> dict[str, Any]:
	"""Parse text-based PDF and return line blocks with page anchors."""
	path = Path(file_path)
	if not path.exists():
		raise FileNotFoundError(f"File not found: {path}")
	if path.suffix.lower() != ".pdf":
		raise ValueError("PDF text parser only supports .pdf files.")
	LOGGER.info(
		"STEP=ingestion.pdf_text | AGENT=TextParser | ACTION=ParsePDFTextStart | DETAILS=file=%s min_line_chars=%s",
		to_relative_path(path),
		min_line_chars,
	)

	pypdf_blocks, pypdf_counts = _extract_pdf_lines_with_pypdf(path, min_line_chars=min_line_chars)
	pymupdf_blocks, pymupdf_counts = _extract_pdf_lines_with_pymupdf(path, min_line_chars=min_line_chars)

	pypdf_total = sum(pypdf_counts)
	pymupdf_total = sum(pymupdf_counts)
	if pypdf_total >= pymupdf_total and pypdf_blocks:
		raw_blocks = pypdf_blocks
		page_char_count = pypdf_counts
		parser_name = "pdf_text_parser:pypdf"
	elif pymupdf_blocks:
		raw_blocks = pymupdf_blocks
		page_char_count = pymupdf_counts
		parser_name = "pdf_text_parser:pymupdf"
	else:
		raw_blocks = pypdf_blocks
		page_char_count = pypdf_counts
		parser_name = "pdf_text_parser:pypdf"

	LOGGER.info(
		"STEP=ingestion.pdf_text | AGENT=TextParser | ACTION=EngineSelected | DETAILS=parser=%s pypdf_chars=%s pymupdf_chars=%s block_count=%s",
		parser_name,
		pypdf_total,
		pymupdf_total,
		len(raw_blocks),
	)

	page_count = max(len(pypdf_counts), len(pymupdf_counts))

	return _finalize_blocks(
		path=path,
		raw_blocks=raw_blocks,
		parser_name=parser_name,
		supports_page_anchor=True,
		metadata={
			"page_count": page_count,
			"page_char_count": page_char_count,
			"engine_stats": {
				"pypdf_total_chars": pypdf_total,
				"pymupdf_total_chars": pymupdf_total,
			},
		},
	)

