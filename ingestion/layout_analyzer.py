from __future__ import annotations

import logging
import re
from copy import deepcopy
from statistics import median
from typing import Any, Mapping

import numpy as np
from PIL import Image

try:
	import cv2
except ImportError:  # pragma: no cover - optional runtime dependency
	cv2 = None


DEFAULT_LAYOUT_CONFIG: dict[str, Any] = {
	"pre_ocr_enabled": True,
	"projection_two_column_enabled": True,
	"projection_middle_min_ratio": 0.35,
	"projection_middle_max_ratio": 0.65,
	"projection_valley_ratio_threshold": 0.36,
	"projection_min_density": 2.0,
	"split_margin_ratio": 0.015,
	"red_stamp_hsv_filter": True,
	"red_h_min_1": 0,
	"red_h_max_1": 10,
	"red_h_min_2": 160,
	"red_h_max_2": 179,
	"red_s_min": 65,
	"red_v_min": 65,
	"red_mask_dilate": 1,
	"table_detect_enabled": True,
	"table_h_kernel_ratio": 0.035,
	"table_v_kernel_ratio": 0.035,
	"table_line_ratio_threshold": 0.010,
	"table_min_boxes": 3,
	"table_min_area_ratio": 0.0007,
	"table_binary_threshold": 0,
	"score_threshold": 0.35,
	"top_right_filter": True,
	"top_region_ratio": 0.18,
	"right_region_ratio": 0.62,
	"header_keywords": ["机密", "秘密", "绝密", "签发", "发文字号", "编号", "红头"],
	"stamp_filter": True,
	"stamp_keywords": ["公章", "印", "章"],
	"stamp_noise_keywords": ["仅供内部留存", "内部留存", "仅供", "作废"],
	"stamp_center_x_min": 0.22,
	"stamp_center_x_max": 0.82,
	"stamp_center_y_min": 0.30,
	"stamp_center_y_max": 0.92,
	"stamp_aspect_min": 0.70,
	"stamp_aspect_max": 1.35,
	"stamp_area_min": 0.002,
	"stamp_area_max": 0.12,
	"stamp_text_max_chars": 14,
	"two_column_min_blocks": 8,
	"two_column_min_each_side": 3,
	"two_column_gap_ratio": 0.22,
	"merge_line_gap_ratio": 1.45,
	"merge_x_tolerance_ratio": 0.10,
}


LOGGER = logging.getLogger("docs_agent.layout_analyzer")


def _merge_config(custom_config: dict[str, Any] | None = None) -> dict[str, Any]:
	config = deepcopy(DEFAULT_LAYOUT_CONFIG)
	if custom_config:
		config.update(custom_config)
	return config


def _normalize_text(text: str) -> str:
	return " ".join(text.replace("\u3000", " ").split())


def _cv2_available() -> bool:
	return cv2 is not None


def _image_to_bgr_array(image: Image.Image) -> np.ndarray:
	rgb = np.array(image.convert("RGB"))
	if _cv2_available():
		return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
	return rgb[:, :, ::-1]


def _bgr_to_pil_image(image_bgr: np.ndarray) -> Image.Image:
	if _cv2_available():
		rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
	else:
		rgb = image_bgr[:, :, ::-1]
	return Image.fromarray(rgb)


def _make_full_page_region(image: Image.Image, page_number: int, analysis: Mapping[str, Any] | None = None) -> list[dict[str, Any]]:
	width, height = image.size
	return [
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
			"analysis": dict(analysis or {}),
		}
	]


def _filter_red_stamp_pixels(image_bgr: np.ndarray, config: dict[str, Any]) -> tuple[np.ndarray, float]:
	if not _cv2_available() or not bool(config.get("red_stamp_hsv_filter", True)):
		return image_bgr, 0.0

	hsv = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2HSV)
	lower_1 = np.array(
		[
			int(config.get("red_h_min_1", 0)),
			int(config.get("red_s_min", 65)),
			int(config.get("red_v_min", 65)),
		],
		dtype=np.uint8,
	)
	upper_1 = np.array(
		[
			int(config.get("red_h_max_1", 10)),
			255,
			255,
		],
		dtype=np.uint8,
	)
	lower_2 = np.array(
		[
			int(config.get("red_h_min_2", 160)),
			int(config.get("red_s_min", 65)),
			int(config.get("red_v_min", 65)),
		],
		dtype=np.uint8,
	)
	upper_2 = np.array(
		[
			int(config.get("red_h_max_2", 179)),
			255,
			255,
		],
		dtype=np.uint8,
	)

	mask_1 = cv2.inRange(hsv, lower_1, upper_1)
	mask_2 = cv2.inRange(hsv, lower_2, upper_2)
	mask = cv2.bitwise_or(mask_1, mask_2)

	dilate_iterations = max(0, int(config.get("red_mask_dilate", 1)))
	if dilate_iterations > 0:
		kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
		mask = cv2.dilate(mask, kernel, iterations=dilate_iterations)

	filtered = image_bgr.copy()
	filtered[mask > 0] = (255, 255, 255)
	removed_ratio = float(np.count_nonzero(mask)) / float(mask.size) if mask.size else 0.0
	return filtered, removed_ratio


def _build_binary_foreground(image_bgr: np.ndarray, config: dict[str, Any]) -> np.ndarray:
	if not _cv2_available():
		gray = np.mean(image_bgr, axis=2).astype(np.uint8)
		return (gray < 200).astype(np.uint8) * 255

	gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
	threshold_value = int(config.get("table_binary_threshold", 0))
	if threshold_value <= 0:
		_, binary_inv = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
	else:
		_, binary_inv = cv2.threshold(gray, threshold_value, 255, cv2.THRESH_BINARY_INV)
	return binary_inv


def _detect_table_structure(image_bgr: np.ndarray, config: dict[str, Any]) -> dict[str, Any]:
	if not bool(config.get("table_detect_enabled", True)) or not _cv2_available():
		return {
			"is_table": False,
			"line_ratio": 0.0,
			"table_box_count": 0,
		}

	binary_inv = _build_binary_foreground(image_bgr, config)
	height, width = binary_inv.shape[:2]
	h_kernel_len = max(20, int(width * float(config.get("table_h_kernel_ratio", 0.035))))
	v_kernel_len = max(20, int(height * float(config.get("table_v_kernel_ratio", 0.035))))

	h_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (h_kernel_len, 1))
	v_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, v_kernel_len))
	horizontal = cv2.morphologyEx(binary_inv, cv2.MORPH_OPEN, h_kernel)
	vertical = cv2.morphologyEx(binary_inv, cv2.MORPH_OPEN, v_kernel)
	line_mask = cv2.bitwise_or(horizontal, vertical)

	line_ratio = float(np.count_nonzero(line_mask)) / float(line_mask.size) if line_mask.size else 0.0
	contours, _ = cv2.findContours(line_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
	min_area = float(width * height) * float(config.get("table_min_area_ratio", 0.0007))
	table_box_count = 0
	for contour in contours:
		x, y, w, h = cv2.boundingRect(contour)
		if float(w * h) >= min_area:
			table_box_count += 1

	is_table = (
		line_ratio >= float(config.get("table_line_ratio_threshold", 0.010))
		or table_box_count >= int(config.get("table_min_boxes", 3))
	)
	return {
		"is_table": is_table,
		"line_ratio": line_ratio,
		"table_box_count": table_box_count,
	}


def _detect_two_column_projection(image_bgr: np.ndarray, config: dict[str, Any]) -> dict[str, Any]:
	if not bool(config.get("projection_two_column_enabled", True)):
		return {
			"is_two_column": False,
			"split_x": int(image_bgr.shape[1] * 0.5),
			"valley_ratio": 1.0,
		}

	binary_inv = _build_binary_foreground(image_bgr, config)
	projection = np.sum(binary_inv > 0, axis=0).astype(np.float32)
	width = int(binary_inv.shape[1])
	mid_start = max(1, int(width * float(config.get("projection_middle_min_ratio", 0.35))))
	mid_end = min(width - 1, int(width * float(config.get("projection_middle_max_ratio", 0.65))))
	if mid_end <= mid_start + 4:
		return {
			"is_two_column": False,
			"split_x": int(width * 0.5),
			"valley_ratio": 1.0,
		}

	middle = projection[mid_start:mid_end]
	if middle.size == 0:
		return {
			"is_two_column": False,
			"split_x": int(width * 0.5),
			"valley_ratio": 1.0,
		}

	valley_offset = int(np.argmin(middle))
	split_x = mid_start + valley_offset
	left_peak = float(np.max(projection[: max(split_x, 1)]))
	right_peak = float(np.max(projection[min(split_x + 1, width - 1) :]))
	base_peak = max(1.0, min(left_peak, right_peak))
	valley_ratio = float(middle[valley_offset]) / base_peak

	left_density = float(np.mean(projection[: max(split_x, 1)]))
	right_density = float(np.mean(projection[min(split_x + 1, width - 1) :]))
	min_density = float(config.get("projection_min_density", 2.0))
	is_two_column = (
		valley_ratio <= float(config.get("projection_valley_ratio_threshold", 0.36))
		and left_density >= min_density
		and right_density >= min_density
	)

	return {
		"is_two_column": is_two_column,
		"split_x": int(split_x),
		"valley_ratio": float(valley_ratio),
		"left_density": left_density,
		"right_density": right_density,
	}


def prepare_ocr_regions(
	image: Image.Image,
	page_number: int,
	config: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
	"""Apply pre-OCR layout analysis and return OCR regions in reading order."""
	cfg = _merge_config(config)
	if not bool(cfg.get("pre_ocr_enabled", True)):
		return _make_full_page_region(image=image, page_number=page_number, analysis={"pre_ocr_enabled": False})

	if not _cv2_available():
		LOGGER.warning(
			"STEP=ingestion.layout | AGENT=LayoutAnalyzer | ACTION=PreOcrFallback | DETAILS=page=%s reason=cv2_not_installed",
			page_number,
		)
		return _make_full_page_region(image=image, page_number=page_number, analysis={"pre_ocr_enabled": True, "cv2_available": False})

	page_width, page_height = image.size
	page_bgr = _image_to_bgr_array(image)
	filtered_bgr, red_removed_ratio = _filter_red_stamp_pixels(page_bgr, cfg)
	table_meta = _detect_table_structure(filtered_bgr, cfg)
	two_col_meta = _detect_two_column_projection(filtered_bgr, cfg)

	analysis = {
		"pre_ocr_enabled": True,
		"cv2_available": True,
		"red_stamp_filtered": bool(red_removed_ratio > 0.0001),
		"red_removed_ratio": float(red_removed_ratio),
		"table_detected": bool(table_meta.get("is_table", False)),
		"table_line_ratio": float(table_meta.get("line_ratio", 0.0)),
		"table_box_count": int(table_meta.get("table_box_count", 0)),
		"two_column_detected": bool(two_col_meta.get("is_two_column", False)),
		"projection_split_x": int(two_col_meta.get("split_x", int(page_width * 0.5))),
		"projection_valley_ratio": float(two_col_meta.get("valley_ratio", 1.0)),
	}

	if not analysis["two_column_detected"]:
		LOGGER.info(
			"STEP=ingestion.layout | AGENT=LayoutAnalyzer | ACTION=PreOcrRegionSingle | DETAILS=page=%s table=%s red_filtered=%s valley_ratio=%.4f",
			page_number,
			analysis["table_detected"],
			analysis["red_stamp_filtered"],
			analysis["projection_valley_ratio"],
		)
		return _make_full_page_region(
			image=_bgr_to_pil_image(filtered_bgr),
			page_number=page_number,
			analysis=analysis,
		)

	split_x = int(analysis["projection_split_x"])
	split_x = max(int(page_width * 0.30), min(int(page_width * 0.70), split_x))
	margin = max(2, int(page_width * float(cfg.get("split_margin_ratio", 0.015))))
	left_end = max(split_x, min(page_width - 2, split_x + (margin // 2)))
	right_start = min(left_end, max(1, split_x - (margin // 2)))

	left_bgr = filtered_bgr[:, :left_end]
	right_bgr = filtered_bgr[:, right_start:]

	left_region = {
		"page": page_number,
		"region_id": f"p{page_number}_left",
		"region_type": "column_left",
		"column": 0,
		"x_offset": 0,
		"y_offset": 0,
		"page_width": float(page_width),
		"page_height": float(page_height),
		"image": _bgr_to_pil_image(left_bgr),
		"analysis": dict(analysis),
	}
	right_region = {
		"page": page_number,
		"region_id": f"p{page_number}_right",
		"region_type": "column_right",
		"column": 1,
		"x_offset": int(right_start),
		"y_offset": 0,
		"page_width": float(page_width),
		"page_height": float(page_height),
		"image": _bgr_to_pil_image(right_bgr),
		"analysis": dict(analysis),
	}

	LOGGER.info(
		"STEP=ingestion.layout | AGENT=LayoutAnalyzer | ACTION=PreOcrRegionSplit | DETAILS=page=%s split_x=%s right_start=%s left_w=%s right_w=%s table=%s red_filtered=%s valley_ratio=%.4f",
		page_number,
		split_x,
		right_start,
		left_bgr.shape[1],
		right_bgr.shape[1],
		analysis["table_detected"],
		analysis["red_stamp_filtered"],
		analysis["projection_valley_ratio"],
	)

	return [left_region, right_region]


def _to_rect(bbox: Any) -> list[float]:
	"""Normalize bbox to [x0, y0, x1, y1]."""
	if isinstance(bbox, list) and len(bbox) == 4 and all(
		isinstance(item, (int, float)) for item in bbox
	):
		x0, y0, x1, y1 = [float(v) for v in bbox]
		return [min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)]

	if isinstance(bbox, list) and len(bbox) >= 4 and all(isinstance(pt, list) for pt in bbox):
		xs = [float(pt[0]) for pt in bbox if len(pt) >= 2]
		ys = [float(pt[1]) for pt in bbox if len(pt) >= 2]
		if xs and ys:
			return [min(xs), min(ys), max(xs), max(ys)]

	return [0.0, 0.0, 0.0, 0.0]


def _looks_garbled(text: str) -> bool:
	if len(text) <= 3:
		return False
	valid_chars = re.findall(r"[\u4e00-\u9fffA-Za-z0-9，。；：、“”‘’（）()《》【】,.!?;:/%\-]", text)
	ratio = len(valid_chars) / max(1, len(text))
	return ratio < 0.45


def _is_header_noise(block: dict[str, Any], config: dict[str, Any]) -> bool:
	if not config.get("top_right_filter", True):
		return False

	x0, _, x1, y1 = block["bbox"]
	page_width = max(float(block.get("page_width", 1.0)), 1.0)
	page_height = max(float(block.get("page_height", 1.0)), 1.0)

	in_top_right = (
		y1 <= page_height * float(config.get("top_region_ratio", 0.18))
		and x0 >= page_width * float(config.get("right_region_ratio", 0.62))
	)
	if not in_top_right:
		return False

	text = block["text"]
	keywords = config.get("header_keywords", [])
	return any(keyword in text for keyword in keywords)


def _is_stamp_noise(block: dict[str, Any], config: dict[str, Any]) -> bool:
	if not config.get("stamp_filter", True):
		return False

	x0, y0, x1, y1 = block["bbox"]
	page_width = max(float(block.get("page_width", 1.0)), 1.0)
	page_height = max(float(block.get("page_height", 1.0)), 1.0)

	width = max(1.0, x1 - x0)
	height = max(1.0, y1 - y0)
	area_ratio = (width * height) / (page_width * page_height)
	aspect = width / height

	center_x_ratio = ((x0 + x1) / 2.0) / page_width
	center_y_ratio = ((y0 + y1) / 2.0) / page_height

	in_center = (
		float(config.get("stamp_center_x_min", 0.22)) <= center_x_ratio <= float(config.get("stamp_center_x_max", 0.82))
		and float(config.get("stamp_center_y_min", 0.30)) <= center_y_ratio <= float(config.get("stamp_center_y_max", 0.92))
	)
	shape_like_stamp = (
		float(config.get("stamp_aspect_min", 0.70)) <= aspect <= float(config.get("stamp_aspect_max", 1.35))
		and float(config.get("stamp_area_min", 0.002)) <= area_ratio <= float(config.get("stamp_area_max", 0.12))
	)

	text = block["text"]
	short_text = len(text) <= int(config.get("stamp_text_max_chars", 14))
	stamp_keywords = config.get("stamp_keywords", [])
	stamp_noise_keywords = config.get("stamp_noise_keywords", [])
	has_stamp_keyword = any(keyword in text for keyword in stamp_keywords)
	has_stamp_noise_keyword = any(keyword in text for keyword in stamp_noise_keywords)

	if in_center and has_stamp_keyword:
		return True
	if in_center and has_stamp_noise_keyword and short_text:
		return True
	if in_center and shape_like_stamp and short_text:
		return True
	return False


def _concat_text(left: str, right: str) -> str:
	if not left:
		return right
	if not right:
		return left

	if re.match(r"[A-Za-z0-9]$", left) and re.match(r"^[A-Za-z0-9]", right):
		return f"{left} {right}"
	return f"{left}{right}"


def _detect_two_column(page_blocks: list[dict[str, Any]], config: dict[str, Any]) -> bool:
	if len(page_blocks) < int(config.get("two_column_min_blocks", 8)):
		return False

	page_width = max(float(page_blocks[0].get("page_width", 1.0)), 1.0)
	centers = sorted((block["bbox"][0] + block["bbox"][2]) / 2.0 for block in page_blocks)
	left_count = sum(center < page_width * 0.50 for center in centers)
	right_count = len(centers) - left_count
	if min(left_count, right_count) < int(config.get("two_column_min_each_side", 3)):
		return False

	q_index_low = int(len(centers) * 0.30)
	q_index_high = int(len(centers) * 0.70)
	q_low = centers[min(q_index_low, len(centers) - 1)]
	q_high = centers[min(q_index_high, len(centers) - 1)]
	span_ratio = (q_high - q_low) / page_width

	return span_ratio >= float(config.get("two_column_gap_ratio", 0.22))


def _order_blocks(page_blocks: list[dict[str, Any]], is_two_column: bool) -> list[dict[str, Any]]:
	if not page_blocks:
		return []

	if not is_two_column:
		ordered = sorted(page_blocks, key=lambda block: (block["bbox"][1], block["bbox"][0]))
		for block in ordered:
			block["column"] = 0
		return ordered

	centers = [(block["bbox"][0] + block["bbox"][2]) / 2.0 for block in page_blocks]
	split_x = median(centers)
	left_col = []
	right_col = []

	for block in page_blocks:
		center_x = (block["bbox"][0] + block["bbox"][2]) / 2.0
		if center_x <= split_x:
			block["column"] = 0
			left_col.append(block)
		else:
			block["column"] = 1
			right_col.append(block)

	left_col.sort(key=lambda block: (block["bbox"][1], block["bbox"][0]))
	right_col.sort(key=lambda block: (block["bbox"][1], block["bbox"][0]))
	return left_col + right_col


def _merge_nearby_lines(ordered_blocks: list[dict[str, Any]], config: dict[str, Any]) -> list[dict[str, Any]]:
	if not ordered_blocks:
		return []

	heights = [max(1.0, block["bbox"][3] - block["bbox"][1]) for block in ordered_blocks]
	line_height = median(heights)
	max_gap = line_height * float(config.get("merge_line_gap_ratio", 1.45))

	page_width = max(float(ordered_blocks[0].get("page_width", 1.0)), 1.0)
	x_tolerance = page_width * float(config.get("merge_x_tolerance_ratio", 0.10))

	merged: list[dict[str, Any]] = []
	current = deepcopy(ordered_blocks[0])

	for block in ordered_blocks[1:]:
		same_column = block.get("column") == current.get("column")
		y_gap = block["bbox"][1] - current["bbox"][3]
		x_shift = abs(block["bbox"][0] - current["bbox"][0])

		if same_column and y_gap <= max_gap and x_shift <= x_tolerance:
			current["text"] = _concat_text(current["text"], block["text"])
			current["bbox"] = [
				min(current["bbox"][0], block["bbox"][0]),
				min(current["bbox"][1], block["bbox"][1]),
				max(current["bbox"][2], block["bbox"][2]),
				max(current["bbox"][3], block["bbox"][3]),
			]
			current["score"] = max(current.get("score", 0.0), block.get("score", 0.0))
		else:
			merged.append(current)
			current = deepcopy(block)

	merged.append(current)
	return merged


def analyze_and_reconstruct_blocks(
	raw_blocks: list[dict[str, Any]],
	config: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
	"""Filter OCR noise and rebuild reading-order text blocks."""
	cfg = _merge_config(config)
	LOGGER.info(
		"STEP=ingestion.layout | AGENT=LayoutAnalyzer | ACTION=AnalyzeStart | DETAILS=raw_blocks=%s score_threshold=%s",
		len(raw_blocks),
		cfg.get("score_threshold", 0.35),
	)
	grouped: dict[int, list[dict[str, Any]]] = {}

	for item in raw_blocks:
		text = _normalize_text(str(item.get("text", "")))
		if not text:
			continue

		normalized = {
			"page": int(item.get("page", 1)),
			"text": text,
			"bbox": _to_rect(item.get("bbox")),
			"score": float(item.get("score", 1.0)),
			"page_width": float(item.get("page_width", 0.0)),
			"page_height": float(item.get("page_height", 0.0)),
		}
		grouped.setdefault(normalized["page"], []).append(normalized)

	result: list[dict[str, Any]] = []

	for page in sorted(grouped.keys()):
		page_blocks = grouped[page]
		filtered: list[dict[str, Any]] = []
		drop_score = 0
		drop_garbled = 0
		drop_header = 0
		drop_stamp = 0

		for block in page_blocks:
			if block["score"] < float(cfg.get("score_threshold", 0.35)):
				drop_score += 1
				continue
			if _looks_garbled(block["text"]) and block["score"] < 0.85:
				drop_garbled += 1
				continue
			if _is_header_noise(block, cfg):
				drop_header += 1
				continue
			if _is_stamp_noise(block, cfg):
				drop_stamp += 1
				continue
			filtered.append(block)

		is_two_column = _detect_two_column(filtered, cfg)
		ordered = _order_blocks(filtered, is_two_column)
		merged = _merge_nearby_lines(ordered, cfg)
		LOGGER.info(
			"STEP=ingestion.layout | AGENT=LayoutAnalyzer | ACTION=PageReconstruct | DETAILS=page=%s input=%s kept=%s merged=%s two_column=%s dropped(score=%s,garbled=%s,header=%s,stamp=%s)",
			page,
			len(page_blocks),
			len(filtered),
			len(merged),
			is_two_column,
			drop_score,
			drop_garbled,
			drop_header,
			drop_stamp,
		)

		for block in merged:
			block.pop("column", None)
			result.append(block)

	LOGGER.info(
		"STEP=ingestion.layout | AGENT=LayoutAnalyzer | ACTION=AnalyzeDone | DETAILS=pages=%s output_blocks=%s",
		len(grouped),
		len(result),
	)

	return result

