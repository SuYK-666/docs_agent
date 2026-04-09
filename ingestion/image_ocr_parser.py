from __future__ import annotations

import asyncio
import importlib
import logging
import os
import sys
from pathlib import Path
from typing import Any, Mapping

import numpy as np
from PIL import Image

from config.logger_setup import to_relative_path
from ingestion.layout_analyzer import analyze_and_reconstruct_blocks, prepare_ocr_regions

try:
	import pypdfium2 as pdfium
except ImportError:  # pragma: no cover - optional dependency runtime check
	pdfium = None

PaddleOCR = None
RapidOCR = None


DEFAULT_OCR_CONFIG: dict[str, Any] = {
	"lang": "ch",
	"use_angle_cls": True,
	"dpi": 240,
	"engine": "auto",
	"allow_fallback": True,
}

SUPPORTED_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp"}
_OCR_ENGINE_CACHE: dict[str, Any] = {}
LOGGER = logging.getLogger("docs_agent.ocr_parser")
_VLM_BUILD_ASSISTANT: Any = None


def _mapping(data: Any) -> Mapping[str, Any]:
	return data if isinstance(data, Mapping) else {}


def _get_vlm_builder() -> Any | None:
	global _VLM_BUILD_ASSISTANT  # pylint: disable=global-statement
	if _VLM_BUILD_ASSISTANT is False:
		return None
	if _VLM_BUILD_ASSISTANT is not None:
		return _VLM_BUILD_ASSISTANT

	tools_dir = Path(__file__).resolve().parent.parent / "tools_&_rag"
	if str(tools_dir) not in sys.path:
		sys.path.insert(0, str(tools_dir))

	try:
		module = importlib.import_module("vlm_ocr_assistant")
		builder = getattr(module, "build_vlm_ocr_assistant", None)
		if builder is None:
			_VLM_BUILD_ASSISTANT = False
			LOGGER.warning(
				"STEP=ingestion.vlm | AGENT=OCRParser | ACTION=BuilderImportFailed | DETAILS=reason=missing_build_function"
			)
			return None
		_VLM_BUILD_ASSISTANT = builder
		return builder
	except Exception as exc:  # pylint: disable=broad-except
		_VLM_BUILD_ASSISTANT = False
		LOGGER.warning(
			"STEP=ingestion.vlm | AGENT=OCRParser | ACTION=BuilderImportFailed | DETAILS=error=%s",
			exc.__class__.__name__,
		)
		return None


def _merge_ocr_config(custom_config: dict[str, Any] | None = None) -> dict[str, Any]:
	config = dict(DEFAULT_OCR_CONFIG)
	if custom_config:
		config.update(custom_config)
	return config


def _get_paddle_ocr_engine(lang: str, use_angle_cls: bool) -> Any:
	cache_key = f"paddle:{lang}:{use_angle_cls}"
	if cache_key in _OCR_ENGINE_CACHE:
		return _OCR_ENGINE_CACHE[cache_key]

	global PaddleOCR  # pylint: disable=global-statement
	if PaddleOCR is None:
		try:
			from paddleocr import PaddleOCR as PaddleOCRClass  # type: ignore
		except ImportError as exc:  # pragma: no cover
			raise RuntimeError(
				"PaddleOCR is not installed. Install paddleocr and paddlepaddle to enable OCR parsing."
			) from exc
		PaddleOCR = PaddleOCRClass

	os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
	engine = PaddleOCR(use_angle_cls=use_angle_cls, lang=lang)
	_OCR_ENGINE_CACHE[cache_key] = engine
	return engine


def _get_rapidocr_engine() -> Any:
	cache_key = "rapidocr"
	if cache_key in _OCR_ENGINE_CACHE:
		return _OCR_ENGINE_CACHE[cache_key]

	global RapidOCR  # pylint: disable=global-statement
	if RapidOCR is None:
		try:
			from rapidocr_onnxruntime import RapidOCR as RapidOCRClass  # type: ignore
		except ImportError as exc:  # pragma: no cover
			raise RuntimeError(
				"RapidOCR is not installed. Install rapidocr-onnxruntime to enable fallback OCR."
			) from exc
		RapidOCR = RapidOCRClass

	engine = RapidOCR()
	_OCR_ENGINE_CACHE[cache_key] = engine
	return engine


def _pdf_to_images(pdf_path: Path, dpi: int) -> list[tuple[int, Image.Image]]:
	if pdfium is None:
		raise RuntimeError("pypdfium2 is not installed. It is required for OCR on PDF files.")
	LOGGER.info(
		"STEP=ingestion.ocr | AGENT=OCRParser | ACTION=RenderPDFToImagesStart | DETAILS=file=%s dpi=%s",
		to_relative_path(pdf_path),
		dpi,
	)

	doc = pdfium.PdfDocument(str(pdf_path))
	pages: list[tuple[int, Image.Image]] = []

	try:
		scale = max(1.0, float(dpi) / 72.0)
		for page_index in range(len(doc)):
			page = doc[page_index]
			bitmap = page.render(scale=scale)
			image = bitmap.to_pil().convert("RGB")
			pages.append((page_index + 1, image))
	finally:
		doc.close()
	LOGGER.info(
		"STEP=ingestion.ocr | AGENT=OCRParser | ACTION=RenderPDFToImagesDone | DETAILS=file=%s pages=%s",
		to_relative_path(pdf_path),
		len(pages),
	)

	return pages


def _load_input_as_images(file_path: Path, dpi: int) -> list[tuple[int, Image.Image]]:
	if file_path.suffix.lower() == ".pdf":
		LOGGER.info("STEP=ingestion.ocr | AGENT=OCRParser | ACTION=LoadPDFInput | DETAILS=file=%s", to_relative_path(file_path))
		return _pdf_to_images(file_path, dpi=dpi)

	if file_path.suffix.lower() in SUPPORTED_IMAGE_SUFFIXES:
		LOGGER.info("STEP=ingestion.ocr | AGENT=OCRParser | ACTION=LoadImageInput | DETAILS=file=%s", to_relative_path(file_path))
		image = Image.open(file_path).convert("RGB")
		return [(1, image)]

	raise ValueError(f"Unsupported OCR file type: {file_path.suffix}")


def _extract_raw_ocr_blocks(
	engine: Any,
	image: Image.Image,
	page_number: int,
	x_offset: float = 0.0,
	y_offset: float = 0.0,
	page_width_override: float | None = None,
	page_height_override: float | None = None,
	region_meta: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
	"""Run OCR on a single page image and return raw text boxes."""

	def _offset_bbox(bbox: Any, offset_x: float, offset_y: float) -> Any:
		if isinstance(bbox, (list, tuple)) and len(bbox) == 4 and all(isinstance(item, (int, float)) for item in bbox):
			x0, y0, x1, y1 = [float(item) for item in bbox]
			return [x0 + offset_x, y0 + offset_y, x1 + offset_x, y1 + offset_y]

		if isinstance(bbox, (list, tuple)):
			shifted: list[list[float]] = []
			for point in bbox:
				if isinstance(point, (list, tuple)) and len(point) >= 2:
					shifted.append([float(point[0]) + offset_x, float(point[1]) + offset_y])
			if shifted:
				return shifted

		return bbox

	image_array = np.array(image)

	result = None
	try:
		result = engine.ocr(image_array, cls=True)
	except TypeError:
		result = engine.ocr(image_array)
	except AttributeError:
		result = engine.predict(image_array)

	if result is None:
		return []

	def _to_list(data: Any) -> list[Any]:
		if data is None:
			return []
		if isinstance(data, list):
			return data
		if hasattr(data, "tolist"):
			return data.tolist()
		return list(data) if isinstance(data, tuple) else [data]

	def _to_score(value: Any) -> float:
		try:
			return float(value)
		except (TypeError, ValueError):
			return 1.0

	width, height = image.size
	page_width = float(page_width_override) if page_width_override is not None else float(width)
	page_height = float(page_height_override) if page_height_override is not None else float(height)
	blocks: list[dict[str, Any]] = []

	# Newer PaddleOCR pipeline format: list[dict] or dict with rec_texts/dt_polys.
	if isinstance(result, dict):
		result = [result]

	if isinstance(result, list) and result and isinstance(result[0], dict):
		for page_result in result:
			texts = _to_list(page_result.get("rec_texts") or page_result.get("texts"))
			scores = _to_list(page_result.get("rec_scores") or page_result.get("scores"))
			polys = _to_list(page_result.get("rec_polys") or page_result.get("dt_polys"))

			for idx, text in enumerate(texts):
				text_value = str(text).strip()
				if not text_value:
					continue

				bbox = polys[idx] if idx < len(polys) else [0.0, 0.0, 0.0, 0.0]
				score = scores[idx] if idx < len(scores) else 1.0
				blocks.append(
					{
						"page": page_number,
						"text": text_value,
						"bbox": _offset_bbox(_to_list(bbox), x_offset, y_offset),
						"score": _to_score(score),
						"page_width": page_width,
						"page_height": page_height,
						"region_type": str((region_meta or {}).get("region_type", "full")),
						"region_id": str((region_meta or {}).get("region_id", "")),
					}
				)

		if blocks:
			return blocks

	if not result:
		return []

	lines = result[0] if isinstance(result, list) and result and isinstance(result[0], list) else result
	if not isinstance(lines, list):
		return []

	for line in lines:
		if not isinstance(line, list) or len(line) < 2:
			continue

		bbox = line[0]
		rec = line[1]
		if not isinstance(rec, (list, tuple)) or not rec:
			continue

		text = str(rec[0]).strip()
		score = _to_score(rec[1]) if len(rec) > 1 else 1.0
		if not text:
			continue

		blocks.append(
			{
				"page": page_number,
				"text": text,
				"bbox": _offset_bbox(bbox, x_offset, y_offset),
				"score": score,
				"page_width": page_width,
				"page_height": page_height,
				"region_type": str((region_meta or {}).get("region_type", "full")),
				"region_id": str((region_meta or {}).get("region_id", "")),
			}
		)

	return blocks


def _extract_raw_ocr_blocks_rapid(
	engine: Any,
	image: Image.Image,
	page_number: int,
	x_offset: float = 0.0,
	y_offset: float = 0.0,
	page_width_override: float | None = None,
	page_height_override: float | None = None,
	region_meta: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
	"""Run OCR through RapidOCR and normalize output format."""

	def _offset_bbox(bbox: Any, offset_x: float, offset_y: float) -> Any:
		if isinstance(bbox, (list, tuple)) and len(bbox) == 4 and all(isinstance(item, (int, float)) for item in bbox):
			x0, y0, x1, y1 = [float(item) for item in bbox]
			return [x0 + offset_x, y0 + offset_y, x1 + offset_x, y1 + offset_y]

		if isinstance(bbox, (list, tuple)):
			shifted: list[list[float]] = []
			for point in bbox:
				if isinstance(point, (list, tuple)) and len(point) >= 2:
					shifted.append([float(point[0]) + offset_x, float(point[1]) + offset_y])
			if shifted:
				return shifted

		return bbox

	image_array = np.array(image)
	result = engine(image_array)

	if isinstance(result, tuple) and len(result) >= 1:
		rapid_lines = result[0]
	else:
		rapid_lines = result

	if not rapid_lines:
		return []

	width, height = image.size
	page_width = float(page_width_override) if page_width_override is not None else float(width)
	page_height = float(page_height_override) if page_height_override is not None else float(height)
	blocks: list[dict[str, Any]] = []

	for line in rapid_lines:
		if not isinstance(line, (list, tuple)) or len(line) < 3:
			continue

		bbox, text, score = line[0], line[1], line[2]
		text_value = str(text).strip()
		if not text_value:
			continue

		blocks.append(
			{
				"page": page_number,
				"text": text_value,
				"bbox": _offset_bbox(bbox, x_offset, y_offset),
				"score": float(score) if score is not None else 1.0,
				"page_width": page_width,
				"page_height": page_height,
				"region_type": str((region_meta or {}).get("region_type", "full")),
				"region_id": str((region_meta or {}).get("region_id", "")),
			}
		)

	return blocks


def _build_ocr_parser_output(
	file_path: Path,
	blocks: list[dict[str, Any]],
	raw_block_count: int,
) -> dict[str, Any]:
	if not blocks:
		raise ValueError(f"No OCR text blocks left after layout analysis: {file_path}")

	normalized_blocks: list[dict[str, Any]] = []
	char_cursor = 0

	for index, item in enumerate(blocks, start=1):
		text = str(item["text"]).strip()
		if not text:
			continue

		start = char_cursor
		end = start + len(text)
		normalized_blocks.append(
			{
				"block_id": f"p{index:04d}",
				"paragraph_index": index,
				"line_index": None,
				"page": int(item.get("page", 1)),
				"text": text,
				"char_start": start,
				"char_end": end,
				"bbox": item.get("bbox", [0.0, 0.0, 0.0, 0.0]),
				"score": float(item.get("score", 1.0)),
			}
		)
		char_cursor = end + 1

	if not normalized_blocks:
		raise ValueError(f"No readable OCR text found in: {file_path}")

	page_set = {int(block["page"]) for block in normalized_blocks}
	plain_text = "\n".join(block["text"] for block in normalized_blocks)

	return {
		"doc_id": file_path.stem,
		"source_file": to_relative_path(file_path),
		"plain_text": plain_text,
		"blocks": normalized_blocks,
		"metadata": {
			"parser": "ocr_parser",
			"supports_page_anchor": True,
			"paragraph_count": len(normalized_blocks),
			"page_count": len(page_set),
			"raw_ocr_block_count": raw_block_count,
			"cleaned_ocr_block_count": len(normalized_blocks),
		},
	}


def _build_vlm_parser_output(
	file_path: Path,
	page_results: list[dict[str, Any]],
	images: list[tuple[int, Image.Image]],
	vlm_meta: Mapping[str, Any],
) -> dict[str, Any]:
	page_size_map: dict[int, tuple[float, float]] = {}
	for page_number, image in images:
		page_size_map[int(page_number)] = (float(image.size[0]), float(image.size[1]))

	def _page_sort_key(item: Any) -> int:
		if isinstance(item, Mapping):
			try:
				return int(item.get("page", 0))
			except (TypeError, ValueError):
				return 0
		return 0

	raw_blocks: list[dict[str, Any]] = []
	for item in sorted(page_results, key=_page_sort_key):
		if not isinstance(item, Mapping):
			continue
		page_number = int(item.get("page", 1))
		text = str(item.get("plain_text", "")).strip()
		if not text:
			continue

		width, height = page_size_map.get(page_number, (0.0, 0.0))
		try:
			confidence = float(item.get("confidence", 1.0))
		except (TypeError, ValueError):
			confidence = 1.0

		raw_blocks.append(
			{
				"page": page_number,
				"text": text,
				"bbox": [0.0, 0.0, width, height],
				"score": confidence,
			}
		)

	if not raw_blocks:
		raise ValueError(f"VLM returned no readable text for file: {file_path}")

	output = _build_ocr_parser_output(file_path=file_path, blocks=raw_blocks, raw_block_count=len(page_results))
	metadata = output.setdefault("metadata", {})
	metadata["parser"] = "vlm_ocr_assist_parser"
	metadata["recognition_mode"] = "vlm_assist"
	metadata["ocr_engine"] = "skipped_by_vlm"
	metadata["raw_ocr_block_count"] = 0
	metadata["cleaned_ocr_block_count"] = len(output.get("blocks", [])) if isinstance(output.get("blocks"), list) else 0
	metadata["raw_vlm_page_count"] = len(page_results)
	metadata["vlm_page_text_count"] = len(raw_blocks)
	metadata["vlm_assist"] = {
		"enabled": True,
		"provider": str(vlm_meta.get("provider", "")),
		"llm_model": str(vlm_meta.get("llm_model", "")),
		"vlm_model": str(vlm_meta.get("vlm_model", "")),
		"reason": str(vlm_meta.get("reason", "")),
		"fallback_to_ocr": False,
		"error": "",
	}
	return output


def parse_ocr_document(
	file_path: str | Path,
	ocr_config: dict[str, Any] | None = None,
	layout_config: dict[str, Any] | None = None,
	settings: Mapping[str, Any] | None = None,
	preferred_provider: str = "",
	api_key_override: str = "",
	enable_vlm_assist: bool | None = None,
) -> dict[str, Any]:
	"""Parse scanned PDF or image with OCR and layout reconstruction."""
	path = Path(file_path)
	if not path.exists():
		raise FileNotFoundError(f"File not found: {path}")

	cfg = _merge_ocr_config(ocr_config)
	images = _load_input_as_images(path, dpi=int(cfg.get("dpi", 240)))
	settings_map = _mapping(settings)
	ingestion_cfg = _mapping(settings_map.get("ingestion"))
	vlm_cfg = _mapping(ingestion_cfg.get("vlm_assist"))

	vlm_status: dict[str, Any] = {
		"enabled": False,
		"provider": "",
		"llm_model": "",
		"vlm_model": "",
		"reason": "vlm_not_attempted",
		"fallback_to_ocr": False,
		"error": "",
	}

	if enable_vlm_assist is None:
		enable_vlm_assist = bool(settings_map) and bool(vlm_cfg.get("enabled", False))

	if enable_vlm_assist and settings_map:
		builder = _get_vlm_builder()
		if builder is None:
			vlm_status["reason"] = "vlm_builder_import_failed"
			vlm_status["fallback_to_ocr"] = True
		else:
			build_result = builder(
				settings_map,
				preferred_provider=preferred_provider,
				api_key_override=api_key_override,
				logger=LOGGER,
			)
			vlm_status.update(
				{
					"enabled": bool(build_result.enabled and build_result.assistant is not None),
					"provider": str(build_result.provider),
					"llm_model": str(build_result.llm_model),
					"vlm_model": str(build_result.vlm_model),
					"reason": str(build_result.reason),
				}
			)

			if build_result.enabled and build_result.assistant is not None:
				try:
					LOGGER.info(
						"STEP=ingestion.vlm | AGENT=OCRParser | ACTION=VLMRecognizeStart | DETAILS=file=%s provider=%s model=%s pages=%s",
						to_relative_path(path),
						build_result.provider,
						build_result.vlm_model,
						len(images),
					)
					page_results = asyncio.run(build_result.assistant.analyze_pages(pages=images, ocr_hints={}))
					output = _build_vlm_parser_output(
						file_path=path,
						page_results=page_results,
						images=images,
						vlm_meta=vlm_status,
					)
					LOGGER.info(
						"STEP=ingestion.vlm | AGENT=OCRParser | ACTION=VLMRecognizeDone | DETAILS=file=%s blocks=%s",
						to_relative_path(path),
						len(output.get("blocks", [])) if isinstance(output.get("blocks"), list) else 0,
					)
					return output
				except Exception as exc:  # pylint: disable=broad-except
					vlm_status["fallback_to_ocr"] = True
					vlm_status["reason"] = f"vlm_runtime_error:{exc.__class__.__name__}"
					vlm_status["error"] = f"{exc.__class__.__name__}: {exc}"
					LOGGER.warning(
						"STEP=ingestion.vlm | AGENT=OCRParser | ACTION=VLMRecognizeFallbackToOCR | DETAILS=file=%s error=%s",
						to_relative_path(path),
						vlm_status["error"],
					)
			else:
				vlm_status["fallback_to_ocr"] = True
				LOGGER.info(
					"STEP=ingestion.vlm | AGENT=OCRParser | ACTION=VLMDisabledUseOCR | DETAILS=file=%s reason=%s provider=%s",
					to_relative_path(path),
					vlm_status["reason"],
					vlm_status["provider"],
				)
	ocr_regions: list[dict[str, Any]] = []
	layout_page_meta: dict[int, dict[str, Any]] = {}
	for page_number, image in images:
		regions = prepare_ocr_regions(image=image, page_number=page_number, config=layout_config)
		if not regions:
			width, height = image.size
			regions = [
				{
					"page": page_number,
					"region_id": f"p{page_number}_full",
					"region_type": "full",
					"column": 0,
					"x_offset": 0,
					"y_offset": 0,
					"page_width": float(width),
					"page_height": float(height),
					"image": image,
					"analysis": {},
				}
			]
		ocr_regions.extend(regions)
		analysis = regions[0].get("analysis", {}) if isinstance(regions[0], Mapping) else {}
		layout_page_meta[int(page_number)] = dict(analysis) if isinstance(analysis, Mapping) else {}

	lang = str(cfg.get("lang", "ch"))
	use_angle_cls = bool(cfg.get("use_angle_cls", True))
	engine_mode = str(cfg.get("engine", "auto")).strip().lower()
	allow_fallback = bool(cfg.get("allow_fallback", True))
	LOGGER.info(
		"STEP=ingestion.ocr | AGENT=OCRParser | ACTION=ParseStart | DETAILS=file=%s engine_mode=%s lang=%s dpi=%s use_angle_cls=%s allow_fallback=%s pages=%s regions=%s",
		to_relative_path(path),
		engine_mode,
		lang,
		cfg.get("dpi", 240),
		use_angle_cls,
		allow_fallback,
		len(images),
		len(ocr_regions),
	)

	def _run_with_paddle() -> list[dict[str, Any]]:
		engine = _get_paddle_ocr_engine(lang=lang, use_angle_cls=use_angle_cls)
		blocks: list[dict[str, Any]] = []
		for region in ocr_regions:
			region_image = region.get("image")
			if not isinstance(region_image, Image.Image):
				continue
			blocks.extend(
				_extract_raw_ocr_blocks(
					engine=engine,
					image=region_image,
					page_number=int(region.get("page", 1)),
					x_offset=float(region.get("x_offset", 0.0)),
					y_offset=float(region.get("y_offset", 0.0)),
					page_width_override=float(region.get("page_width", 0.0)) or None,
					page_height_override=float(region.get("page_height", 0.0)) or None,
					region_meta=region,
				)
			)
		return blocks

	def _run_with_rapid() -> list[dict[str, Any]]:
		engine = _get_rapidocr_engine()
		blocks: list[dict[str, Any]] = []
		for region in ocr_regions:
			region_image = region.get("image")
			if not isinstance(region_image, Image.Image):
				continue
			blocks.extend(
				_extract_raw_ocr_blocks_rapid(
					engine=engine,
					image=region_image,
					page_number=int(region.get("page", 1)),
					x_offset=float(region.get("x_offset", 0.0)),
					y_offset=float(region.get("y_offset", 0.0)),
					page_width_override=float(region.get("page_width", 0.0)) or None,
					page_height_override=float(region.get("page_height", 0.0)) or None,
					region_meta=region,
				)
			)
		return blocks

	raw_blocks: list[dict[str, Any]] = []
	engine_used = ""

	if engine_mode == "paddle":
		try:
			LOGGER.info("STEP=ingestion.ocr | AGENT=OCRParser | ACTION=RunPaddleOCR")
			raw_blocks = _run_with_paddle()
			engine_used = "paddle"
		except Exception as exc:  # pylint: disable=broad-except
			if not allow_fallback:
				raise
			LOGGER.warning(
				"STEP=ingestion.ocr | AGENT=OCRParser | ACTION=FallbackToRapid | DETAILS=reason=%s",
				exc.__class__.__name__,
			)
			raw_blocks = _run_with_rapid()
			engine_used = f"rapid_fallback_from_paddle:{exc.__class__.__name__}"
	elif engine_mode == "rapid":
		LOGGER.info("STEP=ingestion.ocr | AGENT=OCRParser | ACTION=RunRapidOCR")
		raw_blocks = _run_with_rapid()
		engine_used = "rapid"
	else:
		try:
			LOGGER.info("STEP=ingestion.ocr | AGENT=OCRParser | ACTION=RunPaddleOCRAuto")
			raw_blocks = _run_with_paddle()
			engine_used = "paddle"
		except Exception as exc:  # pylint: disable=broad-except
			LOGGER.warning(
				"STEP=ingestion.ocr | AGENT=OCRParser | ACTION=AutoFallbackToRapid | DETAILS=reason=%s",
				exc.__class__.__name__,
			)
			raw_blocks = _run_with_rapid()
			engine_used = f"rapid_fallback_from_paddle:{exc.__class__.__name__}"

	if not raw_blocks:
		raise ValueError(f"OCR returned no text for file: {path}")
	LOGGER.info(
		"STEP=ingestion.ocr | AGENT=OCRParser | ACTION=OCRRawDone | DETAILS=file=%s engine=%s raw_blocks=%s",
		to_relative_path(path),
		engine_used,
		len(raw_blocks),
	)

	cleaned_blocks = analyze_and_reconstruct_blocks(raw_blocks=raw_blocks, config=layout_config)
	LOGGER.info(
		"STEP=ingestion.ocr | AGENT=OCRParser | ACTION=LayoutCleanupDone | DETAILS=file=%s cleaned_blocks=%s",
		to_relative_path(path),
		len(cleaned_blocks),
	)
	output = _build_ocr_parser_output(path, cleaned_blocks, raw_block_count=len(raw_blocks))
	output.setdefault("metadata", {})["ocr_engine"] = engine_used
	output.setdefault("metadata", {})["recognition_mode"] = "ocr"
	if enable_vlm_assist and settings_map:
		output.setdefault("metadata", {})["vlm_assist"] = vlm_status
	two_column_pages = sum(1 for item in layout_page_meta.values() if bool(item.get("two_column_detected", False)))
	table_pages = sum(1 for item in layout_page_meta.values() if bool(item.get("table_detected", False)))
	red_stamp_pages = sum(1 for item in layout_page_meta.values() if bool(item.get("red_stamp_filtered", False)))
	output.setdefault("metadata", {})["layout_analysis"] = {
		"pre_ocr_region_count": len(ocr_regions),
		"two_column_page_count": two_column_pages,
		"table_page_count": table_pages,
		"red_stamp_filtered_page_count": red_stamp_pages,
		"pages": layout_page_meta,
	}
	LOGGER.info(
		"STEP=ingestion.ocr | AGENT=OCRParser | ACTION=ParseDone | DETAILS=doc_id=%s parser=%s ocr_engine=%s blocks=%s",
		output.get("doc_id"),
		output.get("metadata", {}).get("parser"),
		engine_used,
		len(output.get("blocks", [])),
	)
	return output

