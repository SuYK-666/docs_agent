from __future__ import annotations

import asyncio
import base64
import io
import json
import logging
import os
import re
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from PIL import Image

from deepseek_client import DeepSeekClient, DeepSeekConfig


LLM_PROVIDER_PRESETS: dict[str, dict[str, Any]] = {
	"deepseek": {
		"display_name": "DeepSeek",
		"base_url": "https://api.deepseek.com",
		"model": "deepseek-chat",
		"api_key_env": "DEEPSEEK_API_KEY",
		"chat_completions_path": "/chat/completions",
		"request_json_mode": True,
	},
	"tongyi": {
		"display_name": "阿里通义系列",
		"base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
		"model": "qwen-max",
		"api_key_env": "DASHSCOPE_API_KEY",
		"chat_completions_path": "/chat/completions",
		"request_json_mode": True,
	},
	"wenxin": {
		"display_name": "百度文心系列",
		"base_url": "https://qianfan.baidubce.com/v2",
		"model": "ernie-4.0-turbo-8k",
		"api_key_env": "QIANFAN_API_KEY",
		"chat_completions_path": "/chat/completions",
		"request_json_mode": False,
	},
	"gaoding": {
		"display_name": "稿定设计",
		"base_url": "https://open.gaoding.com/v1",
		"model": "gd-gpt-4o-mini",
		"api_key_env": "GAODING_API_KEY",
		"chat_completions_path": "/chat/completions",
		"request_json_mode": False,
	},
	"modelwhale": {
		"display_name": "和鲸ModelWhale",
		"base_url": "https://api.modelwhale.cn/v1",
		"model": "modelwhale-chat",
		"api_key_env": "MODELWHALE_API_KEY",
		"chat_completions_path": "/chat/completions",
		"request_json_mode": False,
	},
	"jimeng": {
		"display_name": "即梦",
		"base_url": "https://api.jimeng.ai/v1",
		"model": "jimeng-large",
		"api_key_env": "JIMENG_API_KEY",
		"chat_completions_path": "/chat/completions",
		"request_json_mode": False,
	},
	"doubao": {
		"display_name": "豆包AI",
		"base_url": "https://ark.cn-beijing.volces.com/api/v3",
		"model": "doubao-pro-32k",
		"api_key_env": "ARK_API_KEY",
		"chat_completions_path": "/chat/completions",
		"request_json_mode": True,
	},
	"spark": {
		"display_name": "科大讯飞星火",
		"base_url": "https://spark-api-open.xf-yun.com/v1",
		"model": "generalv3.5",
		"api_key_env": "SPARK_API_KEY",
		"chat_completions_path": "/chat/completions",
		"request_json_mode": False,
	},
	"kimi": {
		"display_name": "Kimi",
		"base_url": "https://api.moonshot.cn/v1",
		"model": "moonshot-v1-8k",
		"api_key_env": "MOONSHOT_API_KEY",
		"chat_completions_path": "/chat/completions",
		"request_json_mode": True,
	},
	"hunyuan": {
		"display_name": "腾讯混元系列",
		"base_url": "https://api.hunyuan.cloud.tencent.com/v1",
		"model": "hunyuan-turbo",
		"api_key_env": "HUNYUAN_API_KEY",
		"chat_completions_path": "/chat/completions",
		"request_json_mode": False,
	},
	"zhipu": {
		"display_name": "智谱AI",
		"base_url": "https://open.bigmodel.cn/api/paas/v4",
		"model": "glm-4-flash",
		"api_key_env": "ZHIPU_API_KEY",
		"chat_completions_path": "/chat/completions",
		"request_json_mode": True,
	},
}


LLM_PROVIDER_ALIASES = {
	"deepseek": "deepseek",
	"阿里通义系列": "tongyi",
	"tongyi": "tongyi",
	"qwen": "tongyi",
	"百度文心系列": "wenxin",
	"wenxin": "wenxin",
	"ernie": "wenxin",
	"稿定设计": "gaoding",
	"gaoding": "gaoding",
	"和鲸modelwhale": "modelwhale",
	"modelwhale": "modelwhale",
	"即梦": "jimeng",
	"jimeng": "jimeng",
	"豆包ai": "doubao",
	"豆包": "doubao",
	"doubao": "doubao",
	"科大讯飞星火": "spark",
	"星火": "spark",
	"spark": "spark",
	"kimi": "kimi",
	"腾讯混元系列": "hunyuan",
	"混元": "hunyuan",
	"hunyuan": "hunyuan",
	"智谱ai": "zhipu",
	"智谱": "zhipu",
	"zhipu": "zhipu",
}


# Framework-level VLM model hints for existing 11 providers.
# If current llm.model is already vision-capable we will use it first.
VLM_PROVIDER_FALLBACK_MODELS: dict[str, list[str]] = {
	"deepseek": ["deepseek-vl2"],
	"tongyi": ["qwen-vl-max"],
	"wenxin": ["ernie-4.5-vl-32k"],
	"gaoding": [],
	"modelwhale": [],
	"jimeng": ["jimeng-vl-large"],
	"doubao": ["doubao-vision-pro-32k"],
	"spark": ["spark-vision"],
	"kimi": ["moonshot-v1-vision-preview"],
	"hunyuan": ["hunyuan-vision"],
	"zhipu": ["glm-4v-plus"],
}


# API-level multimodal capability by provider.
# `False` means current official endpoint is text-only for chat payloads.
# Can be overridden in settings: ingestion.vlm_assist.providers.<provider>.supports_multimodal_api
PROVIDER_MULTIMODAL_API_CAPABILITY: dict[str, bool] = {
	"deepseek": False,
}


VISION_MODEL_HINTS = (
	"vl",
	"vision",
	"4v",
	"gpt-4o",
	"multimodal",
	"omni",
)


@dataclass
class LLMRuntimeProfile:
	provider: str
	model: str
	api_key: str
	api_key_env: str
	base_url: str
	timeout_seconds: int
	max_retries: int
	backoff_base_seconds: int
	top_p: float
	auth_header_name: str
	auth_header_prefix: str
	extra_headers: dict[str, str]
	chat_completions_path: str


@dataclass
class VLMBuildResult:
	enabled: bool
	reason: str
	provider: str
	llm_model: str
	vlm_model: str
	assistant: "VLMOCRAssistant | None"


def _mapping(value: Any) -> Mapping[str, Any]:
	return value if isinstance(value, Mapping) else {}


def _first_non_empty(*values: Any, fallback: str = "") -> str:
	for value in values:
		text = str(value).strip() if value is not None else ""
		if text:
			return text
	return fallback


def _safe_int(value: Any, default: int = 0) -> int:
	try:
		return int(float(value))
	except (TypeError, ValueError):
		return default


def _normalize_provider(raw_provider: Any) -> str:
	key = str(raw_provider).strip()
	if not key:
		return "deepseek"
	return LLM_PROVIDER_ALIASES.get(key.lower(), LLM_PROVIDER_ALIASES.get(key, key.lower()))


def _looks_like_vision_model(model: str) -> bool:
	text = str(model or "").strip().lower()
	if not text:
		return False
	for hint in VISION_MODEL_HINTS:
		if hint in text:
			return True
	return False


def _resolve_runtime_profile(
	settings: Mapping[str, Any],
	*,
	preferred_provider: str = "",
	api_key_override: str = "",
) -> LLMRuntimeProfile:
	deepseek_settings = _mapping(settings.get("deepseek"))
	llm_settings = _mapping(settings.get("llm"))
	provider_settings = _mapping(llm_settings.get("providers"))

	raw_provider = _first_non_empty(preferred_provider, llm_settings.get("provider"), deepseek_settings.get("provider"), fallback="deepseek")
	provider = _normalize_provider(raw_provider)
	provider_defaults = LLM_PROVIDER_PRESETS.get(provider, LLM_PROVIDER_PRESETS["deepseek"])
	provider_cfg = _mapping(provider_settings.get(provider))

	base_url = _first_non_empty(
		provider_cfg.get("base_url"),
		llm_settings.get("base_url"),
		provider_defaults.get("base_url"),
		deepseek_settings.get("base_url"),
		fallback="https://api.deepseek.com",
	)
	model = _first_non_empty(
		provider_cfg.get("model"),
		llm_settings.get("model"),
		provider_defaults.get("model"),
		deepseek_settings.get("model"),
		fallback="deepseek-chat",
	)
	api_key = _first_non_empty(
		api_key_override,
		provider_cfg.get("api_key"),
		llm_settings.get("api_key"),
		deepseek_settings.get("api_key"),
	)
	api_key_env = _first_non_empty(
		provider_cfg.get("api_key_env"),
		llm_settings.get("api_key_env"),
		provider_defaults.get("api_key_env"),
		deepseek_settings.get("api_key_env"),
		fallback="DEEPSEEK_API_KEY",
	)

	if not api_key:
		if api_key_env.startswith("sk-"):
			api_key = api_key_env
		else:
			api_key = os.getenv(api_key_env, "").strip()

	if not api_key:
		raise RuntimeError(
			f"Missing API key for provider '{provider}'. "
			f"Set llm.providers.{provider}.api_key or env: {api_key_env}"
		)

	timeout_seconds = _safe_int(
		provider_cfg.get(
			"timeout_seconds",
			llm_settings.get("timeout_seconds", deepseek_settings.get("timeout_seconds", 60)),
		),
		default=60,
	)
	max_retries = _safe_int(
		provider_cfg.get(
			"max_retries",
			llm_settings.get("max_retries", deepseek_settings.get("max_retries", 4)),
		),
		default=4,
	)
	backoff_base_seconds = _safe_int(
		provider_cfg.get(
			"backoff_base_seconds",
			llm_settings.get("backoff_base_seconds", deepseek_settings.get("backoff_base_seconds", 2)),
		),
		default=2,
	)
	top_p = float(provider_cfg.get("top_p", llm_settings.get("top_p", deepseek_settings.get("top_p", 1))))

	auth_header_name = _first_non_empty(
		provider_cfg.get("auth_header_name"),
		llm_settings.get("auth_header_name"),
		provider_defaults.get("auth_header_name"),
		fallback="Authorization",
	)
	auth_header_prefix = _first_non_empty(
		provider_cfg.get("auth_header_prefix"),
		llm_settings.get("auth_header_prefix"),
		provider_defaults.get("auth_header_prefix"),
		fallback="Bearer ",
	)
	extra_headers_raw = provider_cfg.get("extra_headers", llm_settings.get("extra_headers", {}))
	extra_headers = dict(extra_headers_raw) if isinstance(extra_headers_raw, Mapping) else {}

	chat_completions_path = _first_non_empty(
		provider_cfg.get("chat_completions_path"),
		llm_settings.get("chat_completions_path"),
		provider_defaults.get("chat_completions_path"),
		fallback="/chat/completions",
	)

	return LLMRuntimeProfile(
		provider=provider,
		model=model,
		api_key=api_key,
		api_key_env=api_key_env,
		base_url=base_url,
		timeout_seconds=max(15, timeout_seconds),
		max_retries=max(1, max_retries),
		backoff_base_seconds=max(1, backoff_base_seconds),
		top_p=top_p,
		auth_header_name=auth_header_name,
		auth_header_prefix=auth_header_prefix,
		extra_headers=extra_headers,
		chat_completions_path=chat_completions_path,
	)


def list_provider_vlm_support() -> dict[str, bool]:
	return {provider: bool(models) for provider, models in VLM_PROVIDER_FALLBACK_MODELS.items()}


class VLMOCRAssistant:
	def __init__(
		self,
		client: DeepSeekClient,
		*,
		provider: str,
		vlm_model: str,
		max_output_tokens: int = 2400,
		temperature: float = 0.0,
		max_parallel_pages: int = 2,
		logger: logging.Logger | None = None,
	) -> None:
		self.client = client
		self.provider = provider
		self.vlm_model = vlm_model
		self.max_output_tokens = max(600, int(max_output_tokens))
		self.temperature = float(temperature)
		self.max_parallel_pages = max(1, int(max_parallel_pages))
		self.logger = logger or logging.getLogger("docs_agent.vlm_assist")

	@staticmethod
	def _image_to_data_url(image: Image.Image, image_format: str = "PNG") -> str:
		buffer = io.BytesIO()
		image.save(buffer, format=image_format)
		encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
		return f"data:image/{image_format.lower()};base64,{encoded}"

	@staticmethod
	def _compact_ocr_hint(ocr_text_hint: str, max_chars: int = 1400) -> str:
		text = re.sub(r"\s+", " ", str(ocr_text_hint or "")).strip()
		if len(text) <= max_chars:
			return text
		return text[:max_chars].rstrip() + "..."

	@staticmethod
	def _parse_json_relaxed(raw_content: str) -> dict[str, Any]:
		text = str(raw_content or "").strip()
		if not text:
			raise ValueError("VLM empty response")

		try:
			parsed = json.loads(text)
			if isinstance(parsed, dict):
				return parsed
		except json.JSONDecodeError:
			pass

		cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE | re.DOTALL).strip()
		left = cleaned.find("{")
		right = cleaned.rfind("}")
		if left != -1 and right != -1 and right > left:
			candidate = cleaned[left : right + 1]
			parsed = json.loads(candidate)
			if isinstance(parsed, dict):
				return parsed

		raise ValueError("VLM output is not valid JSON object")

	def _build_page_prompt(self, page_number: int, ocr_text_hint: str = "") -> str:
		hint = self._compact_ocr_hint(ocr_text_hint)
		return (
			"你是公文视觉解析助手（VLM），请仅输出 JSON，不要输出任何额外文字。\n"
			"请针对当前页完成以下任务：\n"
			"1) 识别页面核心正文，纠正 OCR 常见错字/断行问题；\n"
			"2) 提示是否存在跨页表格延续迹象；\n"
			"3) 标注红章/印章对文本遮挡的影响；\n"
			"4) 给出结构化抽取建议（标题区、正文区、附件区）。\n\n"
			"输出 JSON 字段必须包含：\n"
			"page, plain_text, table_cross_page, stamp_occlusion, structure_hints, confidence, notes。\n"
			f"当前页码：{page_number}。\n"
			f"OCR 先验文本（可为空）：{hint or '无'}"
		)

	async def analyze_page(
		self,
		*,
		page_image: Image.Image,
		page_number: int,
		ocr_text_hint: str = "",
	) -> dict[str, Any]:
		prompt = self._build_page_prompt(page_number=page_number, ocr_text_hint=ocr_text_hint)
		data_url = self._image_to_data_url(page_image)

		messages: list[dict[str, Any]] = [
			{
				"role": "system",
				"content": "You are a precise document vision parser. Return JSON only.",
			},
			{
				"role": "user",
				"content": [
					{"type": "text", "text": prompt},
					{"type": "image_url", "image_url": {"url": data_url}},
				],
			},
		]

		self.logger.info(
			"STEP=ingestion.vlm | AGENT=VLMAssist | ACTION=AnalyzePageStart | DETAILS=provider=%s model=%s page=%s",
			self.provider,
			self.vlm_model,
			page_number,
		)
		response = await self.client.chat_completion(
			messages=messages,
			response_format={"type": "json_object"},
			temperature=self.temperature,
			max_tokens=self.max_output_tokens,
			stream=False,
		)
		content = self.client.get_message_content(response)
		parsed = self._parse_json_relaxed(content)
		parsed.setdefault("page", page_number)
		parsed.setdefault("plain_text", "")
		parsed.setdefault("table_cross_page", False)
		parsed.setdefault("stamp_occlusion", "none")
		parsed.setdefault("structure_hints", [])
		parsed.setdefault("confidence", 0.0)
		parsed.setdefault("notes", "")
		self.logger.info(
			"STEP=ingestion.vlm | AGENT=VLMAssist | ACTION=AnalyzePageDone | DETAILS=page=%s confidence=%s",
			page_number,
			parsed.get("confidence"),
		)
		return parsed

	async def analyze_pages(
		self,
		*,
		pages: Sequence[tuple[int, Image.Image]],
		ocr_hints: Mapping[int, str] | None = None,
		max_parallel_pages: int | None = None,
	) -> list[dict[str, Any]]:
		if not pages:
			return []

		hints = dict(ocr_hints or {})
		parallel = max(1, int(max_parallel_pages or self.max_parallel_pages))
		semaphore = asyncio.Semaphore(parallel)
		results: list[dict[str, Any]] = []

		async def _run_one(item: tuple[int, Image.Image]) -> None:
			page_number, image = item
			async with semaphore:
				result = await self.analyze_page(
					page_image=image,
					page_number=page_number,
					ocr_text_hint=hints.get(page_number, ""),
				)
				results.append(result)

		await asyncio.gather(*[_run_one(item) for item in pages])
		results.sort(key=lambda row: int(row.get("page", 0)))
		return results


def build_vlm_ocr_assistant(
	settings: Mapping[str, Any],
	*,
	preferred_provider: str = "",
	api_key_override: str = "",
	logger: logging.Logger | None = None,
) -> VLMBuildResult:
	runtime = _resolve_runtime_profile(
		settings,
		preferred_provider=preferred_provider,
		api_key_override=api_key_override,
	)
	log = logger or logging.getLogger("docs_agent.vlm_assist")

	ingestion_cfg = _mapping(settings.get("ingestion"))
	vlm_cfg = _mapping(ingestion_cfg.get("vlm_assist"))
	if not bool(vlm_cfg.get("enabled", True)):
		return VLMBuildResult(
			enabled=False,
			reason="vlm_disabled_by_config",
			provider=runtime.provider,
			llm_model=runtime.model,
			vlm_model="",
			assistant=None,
		)

	provider_cfg = _mapping(_mapping(vlm_cfg.get("providers")).get(runtime.provider))
	if provider_cfg.get("enabled") is False:
		return VLMBuildResult(
			enabled=False,
			reason=f"vlm_disabled_for_provider:{runtime.provider}",
			provider=runtime.provider,
			llm_model=runtime.model,
			vlm_model="",
			assistant=None,
		)

	supports_multimodal_api = bool(
		provider_cfg.get(
			"supports_multimodal_api",
			PROVIDER_MULTIMODAL_API_CAPABILITY.get(runtime.provider, True),
		)
	)
	if not supports_multimodal_api:
		return VLMBuildResult(
			enabled=False,
			reason=f"provider_multimodal_not_supported:{runtime.provider}",
			provider=runtime.provider,
			llm_model=runtime.model,
			vlm_model="",
			assistant=None,
		)

	configured_model = _first_non_empty(provider_cfg.get("model"), vlm_cfg.get("default_model"))
	if configured_model:
		selected_vlm_model = configured_model
		reason = "configured_vlm_model"
	elif _looks_like_vision_model(runtime.model):
		selected_vlm_model = runtime.model
		reason = "llm_model_is_vision_capable"
	else:
		candidate_models_raw = provider_cfg.get("candidate_models", VLM_PROVIDER_FALLBACK_MODELS.get(runtime.provider, []))
		candidate_models = [str(item).strip() for item in candidate_models_raw] if isinstance(candidate_models_raw, list) else []
		candidate_models = [item for item in candidate_models if item]
		if not candidate_models:
			return VLMBuildResult(
				enabled=False,
				reason=f"no_known_vlm_model_for_provider:{runtime.provider}",
				provider=runtime.provider,
				llm_model=runtime.model,
				vlm_model="",
				assistant=None,
			)
		selected_vlm_model = candidate_models[0]
		reason = "provider_vlm_fallback_model"

	max_output_tokens = _safe_int(vlm_cfg.get("max_output_tokens"), default=2400)
	temperature = float(vlm_cfg.get("temperature", 0))
	max_parallel_pages = _safe_int(vlm_cfg.get("max_parallel_pages"), default=2)

	client = DeepSeekClient(
		DeepSeekConfig(
			api_key=runtime.api_key,
			base_url=runtime.base_url,
			model=selected_vlm_model,
			timeout_seconds=runtime.timeout_seconds,
			max_retries=runtime.max_retries,
			backoff_base_seconds=runtime.backoff_base_seconds,
			temperature=temperature,
			top_p=runtime.top_p,
			max_output_tokens=max_output_tokens,
			request_json_mode=False,
			provider=runtime.provider,
			chat_completions_path=runtime.chat_completions_path,
			auth_header_name=runtime.auth_header_name,
			auth_header_prefix=runtime.auth_header_prefix,
			extra_headers=runtime.extra_headers,
		)
	)

	assistant = VLMOCRAssistant(
		client=client,
		provider=runtime.provider,
		vlm_model=selected_vlm_model,
		max_output_tokens=max_output_tokens,
		temperature=temperature,
		max_parallel_pages=max_parallel_pages,
		logger=log,
	)
	log.info(
		"STEP=ingestion.vlm | AGENT=VLMAssist | ACTION=BuildAssistantDone | DETAILS=provider=%s llm_model=%s vlm_model=%s reason=%s",
		runtime.provider,
		runtime.model,
		selected_vlm_model,
		reason,
	)
	return VLMBuildResult(
		enabled=True,
		reason=reason,
		provider=runtime.provider,
		llm_model=runtime.model,
		vlm_model=selected_vlm_model,
		assistant=assistant,
	)
