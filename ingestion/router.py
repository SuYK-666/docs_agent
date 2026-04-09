from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Mapping

from config.logger_setup import to_relative_path
from ingestion.image_ocr_parser import SUPPORTED_IMAGE_SUFFIXES, parse_ocr_document
from ingestion.text_parser import (
	inspect_pdf_text_density,
	parse_pdf_text_document,
	parse_text_document,
	parse_word_document,
)


LOGGER = logging.getLogger("docs_agent.router")


def _mapping(data: Any) -> Mapping[str, Any]:
	return data if isinstance(data, Mapping) else {}


def route_document(file_path: str | Path, settings: Mapping[str, Any] | None = None) -> dict[str, Any]:
	"""Route file to proper parser based on extension and PDF text density."""
	path = Path(file_path)
	if not path.exists():
		raise FileNotFoundError(f"File not found: {path}")
	LOGGER.info("STEP=ingestion.route | AGENT=Router | ACTION=RouteStart | DETAILS=file=%s", to_relative_path(path))

	suffix = path.suffix.lower()
	settings = settings or {}
	ingestion_cfg = _mapping(settings.get("ingestion"))
	router_cfg = _mapping(ingestion_cfg.get("router"))
	ocr_cfg = _mapping(ingestion_cfg.get("ocr"))
	layout_cfg = _mapping(ingestion_cfg.get("layout"))

	def _attach_router_meta(parsed: dict[str, Any], strategy: str) -> dict[str, Any]:
		meta = parsed.setdefault("metadata", {})
		router_meta: dict[str, Any] = {
			"input_ext": suffix,
			"strategy": strategy,
		}
		recognition_mode = str(_mapping(meta).get("recognition_mode", "")).strip()
		if recognition_mode:
			router_meta["recognition_mode"] = recognition_mode
		meta["router"] = router_meta
		return parsed

	if suffix == ".docx":
		LOGGER.info("STEP=ingestion.route | AGENT=Router | ACTION=SelectWordParser | DETAILS=suffix=%s", suffix)
		parsed = parse_word_document(path)
		return _attach_router_meta(parsed, "word_text")

	if suffix == ".txt":
		LOGGER.info("STEP=ingestion.route | AGENT=Router | ACTION=SelectTextParser | DETAILS=suffix=%s", suffix)
		parsed = parse_text_document(path)
		return _attach_router_meta(parsed, "text_plain")

	if suffix in SUPPORTED_IMAGE_SUFFIXES:
		LOGGER.info("STEP=ingestion.route | AGENT=Router | ACTION=SelectImageOCR | DETAILS=suffix=%s", suffix)
		parsed = parse_ocr_document(
			path,
			ocr_config=dict(ocr_cfg),
			layout_config=dict(layout_cfg),
			settings=settings,
		)
		return _attach_router_meta(parsed, "image_ocr")

	if suffix != ".pdf":
		raise ValueError(f"Unsupported file type: {suffix}")

	pdf_mode = str(router_cfg.get("pdf_mode", "auto")).lower().strip()
	LOGGER.info("STEP=ingestion.route | AGENT=Router | ACTION=PDFMode | DETAILS=pdf_mode=%s", pdf_mode)
	if pdf_mode not in {"auto", "text", "ocr"}:
		raise ValueError("ingestion.router.pdf_mode must be one of: auto, text, ocr")

	def _parse_via_ocr() -> dict[str, Any]:
		return parse_ocr_document(
			path,
			ocr_config=dict(ocr_cfg),
			layout_config=dict(layout_cfg),
			settings=settings,
		)

	pdf_text_stats: dict[str, Any] | None = None
	strategy = ""

	if pdf_mode == "text":
		LOGGER.info("STEP=ingestion.route | AGENT=Router | ACTION=ForceTextParser",)
		parsed = parse_pdf_text_document(path)
		strategy = "pdf_text_forced"
	elif pdf_mode == "ocr":
		LOGGER.info("STEP=ingestion.route | AGENT=Router | ACTION=ForceOCRParser",)
		parsed = _parse_via_ocr()
		strategy = "pdf_ocr_forced"
	else:
		pdf_text_stats = inspect_pdf_text_density(path)
		min_ratio = float(router_cfg.get("pdf_text_page_ratio_threshold", 0.6))
		min_total_chars = int(router_cfg.get("pdf_text_total_chars_threshold", 180))
		has_text_layer = (
			pdf_text_stats["non_empty_page_ratio"] >= min_ratio
			and pdf_text_stats["total_chars"] >= min_total_chars
		)
		LOGGER.info(
			"STEP=ingestion.route | AGENT=Router | ACTION=EvaluatePDFDensity | DETAILS=ratio=%.3f threshold=%.3f total_chars=%s threshold_chars=%s has_text_layer=%s engine=%s",
			float(pdf_text_stats.get("non_empty_page_ratio", 0.0)),
			min_ratio,
			pdf_text_stats.get("total_chars"),
			min_total_chars,
			has_text_layer,
			pdf_text_stats.get("engine"),
		)

		if has_text_layer:
			try:
				LOGGER.info("STEP=ingestion.route | AGENT=Router | ACTION=AutoSelectTextParser",)
				parsed = parse_pdf_text_document(path)
				strategy = "pdf_text_auto"
			except ValueError:
				LOGGER.warning("STEP=ingestion.route | AGENT=Router | ACTION=TextParserFailedFallbackToOCR")
				parsed = _parse_via_ocr()
				strategy = "pdf_ocr_auto_fallback"
		else:
			LOGGER.info("STEP=ingestion.route | AGENT=Router | ACTION=AutoSelectOCRParser",)
			parsed = _parse_via_ocr()
			strategy = "pdf_ocr_auto"

	parsed = _attach_router_meta(parsed, strategy)
	if pdf_text_stats is not None:
		parsed["metadata"]["router"]["pdf_text_density"] = pdf_text_stats

	LOGGER.info(
		"STEP=ingestion.route | AGENT=Router | ACTION=RouteDone | DETAILS=strategy=%s parser=%s blocks=%s",
		strategy,
		parsed.get("metadata", {}).get("parser"),
		len(parsed.get("blocks", [])) if isinstance(parsed.get("blocks"), list) else 0,
	)

	return parsed

