from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any, Mapping

import yaml

from config.logger_setup import get_log_session, get_logger, log_step, setup_logger, to_relative_path
from core_agent.agent_reader import ReaderAgent
from core_agent.orchestrator import Orchestrator
from ingestion.router import route_document


PROJECT_ROOT = Path(__file__).resolve().parent
TOOLS_RAG_DIR = PROJECT_ROOT / "tools_&_rag"
if str(TOOLS_RAG_DIR) not in sys.path:
	sys.path.insert(0, str(TOOLS_RAG_DIR))

from deepseek_client import DeepSeekClient, DeepSeekConfig  # noqa: E402  pylint: disable=wrong-import-position


DEFAULT_UI_PORT = 1708


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


def load_settings(settings_path: Path) -> dict[str, Any]:
	logger = get_logger("main")
	log_step(logger, "settings", "Main", "LoadSettingsStart", f"settings_path={to_relative_path(settings_path)}")
	if not settings_path.exists():
		raise FileNotFoundError(f"settings file not found: {settings_path}")
	with settings_path.open("r", encoding="utf-8") as file:
		loaded = yaml.safe_load(file) or {}
	if not isinstance(loaded, dict):
		raise ValueError("settings.yaml must contain a YAML object at top level.")
	log_step(logger, "settings", "Main", "LoadSettingsDone", f"top_keys={list(loaded.keys())}")
	return loaded


def resolve_input_doc(file_arg: str | None, settings: Mapping[str, Any]) -> Path:
	logger = get_logger("main")
	if file_arg:
		candidate = Path(file_arg)
		if not candidate.is_absolute():
			candidate = PROJECT_ROOT / candidate
		log_step(logger, "input", "Main", "UseExplicitFile", f"file={to_relative_path(candidate)}")
		return candidate

	raw_docs_dir = PROJECT_ROOT / str(settings.get("paths", {}).get("raw_docs_dir", "data_workspace/raw_docs"))
	patterns = [
		"*.txt",
		"*.docx",
		"*.pdf",
		"*.png",
		"*.jpg",
		"*.jpeg",
		"*.bmp",
		"*.tif",
		"*.tiff",
		"*.webp",
	]

	docs: list[Path] = []
	for pattern in patterns:
		docs.extend(raw_docs_dir.glob(pattern))

	docs = sorted(docs, key=lambda item: item.stat().st_mtime, reverse=True)
	if not docs:
		raise FileNotFoundError(
			"No supported input file found in "
			f"{raw_docs_dir}. Place .docx/.pdf/image file there or pass --file."
		)
	log_step(logger, "input", "Main", "SelectLatestFile", f"selected={to_relative_path(docs[0])} | candidates={len(docs)}")
	return docs[0]


def build_client(settings: Mapping[str, Any]) -> DeepSeekClient:
	logger = get_logger("main")
	deepseek_settings = _mapping(settings.get("deepseek"))
	llm_settings = _mapping(settings.get("llm"))
	provider_settings = _mapping(llm_settings.get("providers"))

	raw_provider = _first_non_empty(llm_settings.get("provider"), deepseek_settings.get("provider"), fallback="deepseek")
	provider = _normalize_provider(raw_provider)
	provider_defaults = LLM_PROVIDER_PRESETS.get(provider, LLM_PROVIDER_PRESETS["deepseek"])
	provider_cfg = _mapping(provider_settings.get(provider))

	base_url = _first_non_empty(
		provider_cfg.get("base_url"),
		llm_settings.get("base_url"),
		deepseek_settings.get("base_url"),
		provider_defaults.get("base_url"),
		fallback="https://api.deepseek.com",
	)
	model = _first_non_empty(
		provider_cfg.get("model"),
		llm_settings.get("model"),
		deepseek_settings.get("model"),
		provider_defaults.get("model"),
		fallback="deepseek-chat",
	)
	api_key = _first_non_empty(
		provider_cfg.get("api_key"),
		llm_settings.get("api_key"),
		deepseek_settings.get("api_key"),
	)
	api_key_env = _first_non_empty(
		provider_cfg.get("api_key_env"),
		llm_settings.get("api_key_env"),
		deepseek_settings.get("api_key_env"),
		provider_defaults.get("api_key_env"),
		fallback="DEEPSEEK_API_KEY",
	)

	if not api_key:
		# Compatibility: users sometimes put the literal API key in api_key_env.
		if api_key_env.startswith("sk-"):
			api_key = api_key_env
		else:
			api_key = os.getenv(api_key_env, "").strip()

	if not api_key:
		raise RuntimeError(
			f"Missing API key for provider '{provider}'. "
			f"Set llm.providers.{provider}.api_key or environment variable: {api_key_env}"
		)

	timeout_seconds = int(
		provider_cfg.get(
			"timeout_seconds",
			llm_settings.get("timeout_seconds", deepseek_settings.get("timeout_seconds", 60)),
		)
	)
	max_retries = int(
		provider_cfg.get(
			"max_retries",
			llm_settings.get("max_retries", deepseek_settings.get("max_retries", 4)),
		)
	)
	backoff_base_seconds = int(
		provider_cfg.get(
			"backoff_base_seconds",
			llm_settings.get("backoff_base_seconds", deepseek_settings.get("backoff_base_seconds", 2)),
		)
	)
	temperature = float(provider_cfg.get("temperature", llm_settings.get("temperature", deepseek_settings.get("temperature", 0))))
	top_p = float(provider_cfg.get("top_p", llm_settings.get("top_p", deepseek_settings.get("top_p", 1))))
	max_output_tokens = int(
		provider_cfg.get(
			"max_output_tokens",
			llm_settings.get("max_output_tokens", deepseek_settings.get("max_output_tokens", 1500)),
		)
	)
	request_json_mode = bool(
		provider_cfg.get(
			"request_json_mode",
			llm_settings.get(
				"request_json_mode",
				deepseek_settings.get("request_json_mode", bool(provider_defaults.get("request_json_mode", True))),
			),
		)
	)
	chat_completions_path = _first_non_empty(
		provider_cfg.get("chat_completions_path"),
		llm_settings.get("chat_completions_path"),
		provider_defaults.get("chat_completions_path"),
		fallback="/chat/completions",
	)
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
	extra_headers = provider_cfg.get("extra_headers", llm_settings.get("extra_headers", {}))
	extra_headers_mapping = dict(extra_headers) if isinstance(extra_headers, Mapping) else {}

	log_step(
		logger,
		"llm",
		"Main",
		"BuildClient",
		f"provider={provider} | model={model} | base_url={base_url} | timeout={timeout_seconds}",
	)

	client_config = DeepSeekConfig(
		api_key=api_key,
		base_url=base_url,
		model=model,
		timeout_seconds=timeout_seconds,
		max_retries=max_retries,
		backoff_base_seconds=backoff_base_seconds,
		temperature=temperature,
		top_p=top_p,
		max_output_tokens=max_output_tokens,
		request_json_mode=request_json_mode,
		provider=provider,
		chat_completions_path=chat_completions_path,
		auth_header_name=auth_header_name,
		auth_header_prefix=auth_header_prefix,
		extra_headers=extra_headers_mapping,
	)
	return DeepSeekClient(client_config)


def save_cache(output: Mapping[str, Any], settings: Mapping[str, Any], file_tag: str = "reader") -> Path:
	logger = get_logger("main")
	cache_dir = PROJECT_ROOT / str(
		settings.get("paths", {}).get("processed_cache_dir", "data_workspace/processed_cache")
	)
	cache_dir.mkdir(parents=True, exist_ok=True)
	doc_id = str(output.get("doc_id", "unknown_doc"))
	output_path = cache_dir / f"{doc_id}.{file_tag}.json"
	with output_path.open("w", encoding="utf-8") as file:
		json.dump(output, file, ensure_ascii=False, indent=2)
	log_step(logger, "output", "Main", "SaveJsonCache", f"path={to_relative_path(output_path)}")
	return output_path


def run_crawler_stage(
	settings: Mapping[str, Any],
	enable_crawler: bool,
	crawler_site: str,
	crawler_url: str,
	crawler_count: int,
	crawler_force: bool,
) -> dict[str, Any] | None:
	logger = get_logger("main")
	spider_cfg = settings.get("spiders", {}) if isinstance(settings.get("spiders"), Mapping) else {}
	auto_run = bool(spider_cfg.get("auto_run", False))
	config_enabled = bool(spider_cfg.get("enabled", False))

	if not enable_crawler and not auto_run:
		log_step(logger, "crawler", "Main", "CrawlerSkipped", "reason=disabled")
		return None
	if not config_enabled and not enable_crawler:
		log_step(logger, "crawler", "Main", "CrawlerSkipped", "reason=config_disabled")
		return None

	raw_docs_dir = PROJECT_ROOT / str(settings.get("paths", {}).get("raw_docs_dir", "data_workspace/raw_docs"))
	log_step(
		logger,
		"crawler",
		"Main",
		"CrawlerStart",
		f"site={crawler_site or 'default'} url_override={crawler_url or 'none'} count={max(1, crawler_count)} force={crawler_force}",
	)

	from ingestion.web_crawler import run_crawler  # pylint: disable=import-outside-toplevel

	result = run_crawler(
		settings=settings,
		raw_docs_dir=raw_docs_dir,
		limit=max(1, crawler_count),
		site_name=crawler_site.strip() or None,
		list_url_override=crawler_url.strip() or None,
		force=crawler_force,
	)

	failed_cache_files_raw = result.get("failed_cache_files", []) if isinstance(result, Mapping) else []
	failed_cache_files = [
		str(item).strip()
		for item in failed_cache_files_raw
		if str(item).strip()
	] if isinstance(failed_cache_files_raw, list) else []

	failed_reports: list[dict[str, str]] = []
	if failed_cache_files:
		output_delivery_dir = PROJECT_ROOT / "output_&_delivery"
		if str(output_delivery_dir) not in sys.path:
			sys.path.insert(0, str(output_delivery_dir))

		import report_renderer  # type: ignore  # pylint: disable=import-error,import-outside-toplevel

		paths_cfg = settings.get("paths", {}) if isinstance(settings.get("paths"), Mapping) else {}
		report_dir = PROJECT_ROOT / str(paths_cfg.get("final_reports_dir", "data_workspace/final_reports")) / "reports"
		template_dir = output_delivery_dir / "templates"

		for index, rel_path in enumerate(failed_cache_files, start=1):
			cache_path = PROJECT_ROOT / rel_path
			if not cache_path.exists():
				continue
			rendered = report_renderer.render_selected_reports_from_json(
				json_path=cache_path,
				output_dir=report_dir,
				template_dir=template_dir,
				include_formats=["md", "html", "docx"],
				section_index=index,
			)
			failed_reports.append(
				{
					"cache": to_relative_path(cache_path),
					"md": to_relative_path(rendered["md"]),
					"html": to_relative_path(rendered["html"]),
					"docx": to_relative_path(rendered["docx"]),
				}
			)

		if failed_reports:
			log_step(
				logger,
				"crawler",
				"Main",
				"CrawlerFailureReportsRendered",
				f"count={len(failed_reports)} report_dir={to_relative_path(report_dir)}",
			)
			if isinstance(result, dict):
				result["failed_reports"] = failed_reports

	log_step(
		logger,
		"crawler",
		"Main",
		"CrawlerDone",
		(
			f"listed={result.get('listed', 0)} new_notices={result.get('new_notices', 0)} "
			f"failed={result.get('failed', 0)} "
			f"attachments={len(result.get('attachment_files', [])) if isinstance(result.get('attachment_files'), list) else 0}"
		),
	)
	return result


def _collect_email_owners(result: Mapping[str, Any], dispatch_owner: str) -> list[str]:
	explicit_owner = dispatch_owner.strip()
	if explicit_owner:
		return [explicit_owner]

	owners: list[str] = []
	tasks = result.get("tasks", [])
	if isinstance(tasks, list):
		for task in tasks:
			if not isinstance(task, Mapping):
				continue
			owner = str(task.get("owner", "")).strip()
			if not owner:
				continue
			if owner not in owners:
				owners.append(owner)

	return owners or ["默认"]


def run_email_stage(
	settings: Mapping[str, Any],
	result: Mapping[str, Any],
	cache_path: Path,
	source_file: Path,
	dispatch_owner: str,
) -> list[dict[str, Any]]:
	logger = get_logger("main")
	output_delivery_dir = PROJECT_ROOT / "output_&_delivery"
	if str(output_delivery_dir) not in sys.path:
		sys.path.insert(0, str(output_delivery_dir))

	import report_renderer  # type: ignore  # pylint: disable=import-error,import-outside-toplevel
	import email_gateway  # type: ignore  # pylint: disable=import-error,import-outside-toplevel

	paths_cfg = settings.get("paths", {}) if isinstance(settings.get("paths"), Mapping) else {}
	final_reports_dir = PROJECT_ROOT / str(paths_cfg.get("final_reports_dir", "data_workspace/final_reports"))
	reports_dir = final_reports_dir / "reports"

	_, html_path, _ = report_renderer.render_report_from_json(
		json_path=cache_path,
		output_dir=reports_dir,
		template_dir=output_delivery_dir / "templates",
	)

	calendar = result.get("calendar", {}) if isinstance(result.get("calendar"), Mapping) else {}
	ics_file = str(calendar.get("ics_file", "")).strip()
	owners = _collect_email_owners(result=result, dispatch_owner=dispatch_owner)
	title = str(result.get("title") or result.get("doc_id") or "公文任务提醒").strip()
	subject = f"[公文速阅] {title}"

	responses: list[dict[str, Any]] = []
	for owner in owners:
		try:
			resp = email_gateway.send_report(
				owner=owner,
				report_html_path=html_path,
				source_file_path=source_file,
				ics_file_path=ics_file,
				subject=subject,
				settings=settings,
			)
			responses.append(resp)
		except Exception as exc:  # pylint: disable=broad-except
			logger.exception(
				"STEP=email | AGENT=Main | ACTION=SendFailed | DETAILS=owner=%s reason=%s",
				owner,
				exc,
			)
			responses.append(
				{
					"status": "failed",
					"owner": owner,
					"error": str(exc),
				}
			)

	success = sum(1 for item in responses if str(item.get("status", "")).lower() == "sent")
	fail = len(responses) - success
	log_step(
		logger,
		"email",
		"Main",
		"EmailStageDone",
		f"total={len(responses)} success={success} failed={fail} html={to_relative_path(html_path)}",
	)
	return responses


def run_reader_pipeline(
	file_arg: str | None,
	config_arg: str,
	save_output: bool,
	preview_parse: bool,
	preview_chars: int,
	pipeline_mode: str,
	save_calendar: bool,
	dispatch_owner: str,
	enable_crawler: bool,
	crawler_site: str,
	crawler_url: str,
	crawler_count: int,
	crawler_force: bool,
	send_email: bool,
) -> None:
	settings_path = PROJECT_ROOT / config_arg
	settings = load_settings(settings_path)

	app_settings = settings.get("app", {})
	logging_settings = settings.get("logging", {})
	log_dir = str(logging_settings.get("dir", "log"))
	log_config_file = str(logging_settings.get("config_file", "log/logging.yaml"))
	setup_logger(
		log_level=str(app_settings.get("log_level", "INFO")),
		log_file=str(logging_settings.get("file", "")) or None,
		log_dir=log_dir,
		config_file=log_config_file,
		force_reconfigure=True,
	)
	main_logger = get_logger("main")
	email_cfg = settings.get("email", {}) if isinstance(settings.get("email"), Mapping) else {}
	email_enabled_by_config = bool(email_cfg.get("enabled", False))
	should_send_email = send_email or email_enabled_by_config
	session = get_log_session()
	if session is not None:
		log_step(
			main_logger,
			"startup",
			"Main",
			"LoggerReady",
			f"run_id={session.run_id} | log_file={to_relative_path(session.log_file)}",
		)

	log_step(
		main_logger,
		"startup",
		"Main",
		"PipelineArgs",
		(
			f"pipeline_mode={pipeline_mode} | preview_parse={preview_parse} | save_output={save_output} "
			f"| save_calendar={save_calendar} | dispatch_owner={dispatch_owner or 'none'} "
			f"| crawler_enable={enable_crawler} | crawler_site={crawler_site or 'default'} "
			f"| crawler_count={max(1, crawler_count)} | crawler_force={crawler_force} "
			f"| send_email_cli={send_email} | send_email_config={email_enabled_by_config}"
		),
	)

	crawler_result = run_crawler_stage(
		settings=settings,
		enable_crawler=enable_crawler,
		crawler_site=crawler_site,
		crawler_url=crawler_url,
		crawler_count=crawler_count,
		crawler_force=crawler_force,
	)

	if crawler_result is not None:
		crawler_failed = _safe_int(crawler_result.get("failed", 0), 0)
		crawler_new = _safe_int(crawler_result.get("new_notices", 0), 0)
		if crawler_failed > 0 and crawler_new <= 0 and not file_arg:
			log_step(
				main_logger,
				"pipeline",
				"Main",
				"CrawlerFailureShortCircuit",
				f"failed={crawler_failed} new_notices={crawler_new} action=skip_reader_rag",
			)
			print(json.dumps(crawler_result, ensure_ascii=False, indent=2))
			return

	input_doc = resolve_input_doc(file_arg, settings)
	log_step(main_logger, "ingestion", "Main", "RouteDocumentStart", f"file={to_relative_path(input_doc)}")
	parsed_doc = route_document(input_doc, settings=settings)
	router_meta = parsed_doc.get("metadata", {}).get("router", {}) if isinstance(parsed_doc.get("metadata"), Mapping) else {}
	log_step(
		main_logger,
		"ingestion",
		"Main",
		"RouteDocumentDone",
		f"doc_id={parsed_doc.get('doc_id')} | parser={parsed_doc.get('metadata', {}).get('parser')} | strategy={router_meta.get('strategy')} | blocks={len(parsed_doc.get('blocks', []))}",
	)

	if preview_parse:
		log_step(main_logger, "preview", "Main", "PreviewParseOnly", f"preview_chars={preview_chars}")
		preview_meta = {
			"doc_id": parsed_doc.get("doc_id"),
			"source_file": parsed_doc.get("source_file"),
			"parser": parsed_doc.get("metadata", {}).get("parser"),
			"ocr_engine": parsed_doc.get("metadata", {}).get("ocr_engine"),
			"router": parsed_doc.get("metadata", {}).get("router", {}),
			"block_count": len(parsed_doc.get("blocks", [])),
		}
		print(json.dumps(preview_meta, ensure_ascii=False, indent=2))
		print("\n=== Parsed Plain Text Preview ===\n")
		print(str(parsed_doc.get("plain_text", ""))[: max(0, int(preview_chars))])
		return

	client = build_client(settings)

	if pipeline_mode == "reader":
		log_step(main_logger, "pipeline", "ReaderAgent", "ReaderModeStart", "")
		reader_settings = settings.get("reader", {})
		reader = ReaderAgent(
			client=client,
			summary_target_chars=int(reader_settings.get("summary_target_words", 250)),
			json_retry_times=int(reader_settings.get("json_retry_times", 3)),
			max_output_tokens=int(reader_settings.get("max_output_tokens", 2600)),
		)
		result = asyncio.run(reader.extract(parsed_doc))
		cache_tag = "reader"
	else:
		log_step(main_logger, "pipeline", "Orchestrator", "OrchestratorModeStart", "")
		orchestrator = Orchestrator(client=client, settings=settings, project_root=PROJECT_ROOT)
		result = asyncio.run(
			orchestrator.run(
				parsed_doc=parsed_doc,
				generate_calendar=True,
				save_calendar=save_calendar,
				dispatch_owner=dispatch_owner.strip() or None,
			)
		)
		cache_tag = "agent"

	log_step(
		main_logger,
		"pipeline",
		"Main",
		"PipelineDone",
		f"doc_id={result.get('doc_id')} | tasks={len(result.get('tasks', [])) if isinstance(result.get('tasks'), list) else 0} | cache_tag={cache_tag}",
	)

	print(json.dumps(result, ensure_ascii=False, indent=2))

	output_path: Path | None = None
	if save_output:
		output_path = save_cache(result, settings, file_tag=cache_tag)
		print(f"\nSaved JSON cache: {to_relative_path(output_path)}")

	if should_send_email:
		if pipeline_mode != "orchestrator":
			log_step(main_logger, "email", "Main", "EmailStageSkipped", "reason=reader_mode")
		else:
			if output_path is None:
				output_path = save_cache(result, settings, file_tag=cache_tag)
				log_step(main_logger, "email", "Main", "AutoSaveCacheForEmail", f"path={to_relative_path(output_path)}")
			responses = run_email_stage(
				settings=settings,
				result=result,
				cache_path=output_path,
				source_file=input_doc,
				dispatch_owner=dispatch_owner,
			)
			print("\nEmail Results:")
			print(json.dumps(responses, ensure_ascii=False, indent=2))

	log_step(main_logger, "shutdown", "Main", "RunCompleted", f"doc_id={result.get('doc_id')}")


def run_ui_console(host: str, port: int) -> None:
	"""Start the lightweight frontend console for manual HITL/UI testing."""
	output_delivery_dir = PROJECT_ROOT / "output_&_delivery"
	if str(output_delivery_dir) not in sys.path:
		sys.path.insert(0, str(output_delivery_dir))

	import html_console_server  # type: ignore  # pylint: disable=import-error,import-outside-toplevel

	print(f"[docs_agent] Frontend console bootstrap: host={host}, fixed_port={port}")
	html_console_server.run_server(host=host, port=port)


def parse_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser(
		description="docs_agent runner: default starts frontend UI, optional pipeline execution"
	)
	parser.add_argument(
		"--start-ui",
		action="store_true",
		help="Start lightweight frontend console (same as default with no args).",
	)
	parser.add_argument(
		"--run-pipeline",
		action="store_true",
		help="Force running parser/agent pipeline mode even when no other args are provided.",
	)
	parser.add_argument(
		"--ui-host",
		default="127.0.0.1",
		help="Frontend console bind host.",
	)
	parser.add_argument(
		"--ui-port",
		type=int,
		default=DEFAULT_UI_PORT,
		help="Frontend console bind port.",
	)
	parser.add_argument(
		"--file",
		help="Target file path (.docx/.pdf/image). If omitted, picks latest in raw_docs_dir.",
	)
	parser.add_argument(
		"--config",
		default="config/settings.yaml",
		help="YAML config path relative to project root.",
	)
	parser.add_argument(
		"--save-cache",
		action="store_true",
		help="Save pipeline JSON to data_workspace/processed_cache.",
	)
	parser.add_argument(
		"--pipeline-mode",
		choices=["orchestrator", "reader"],
		default="orchestrator",
		help="Run full multi-agent orchestrator or legacy reader-only mode.",
	)
	parser.add_argument(
		"--save-calendar",
		action="store_true",
		help="When using orchestrator mode, save generated .ics file to final_reports_dir.",
	)
	parser.add_argument(
		"--dispatch-owner",
		default="",
		help="Only generate dispatch content for this owner (supports common normalization).",
	)
	parser.add_argument(
		"--preview-parse",
		action="store_true",
		help="Only run parser and print cleaned plain text preview before LLM.",
	)
	parser.add_argument(
		"--preview-chars",
		type=int,
		default=2500,
		help="Character count to show when --preview-parse is enabled.",
	)
	parser.add_argument(
		"--enable-crawler",
		action="store_true",
		help="Run stage-0 web crawler feeder before parsing local files.",
	)
	parser.add_argument(
		"--crawl-site",
		default="",
		help="Crawler site key under settings.spiders.sites.",
	)
	parser.add_argument(
		"--crawl-url",
		default="",
		help="Override crawler list_url while reusing configured selectors.",
	)
	parser.add_argument(
		"--crawl-count",
		type=int,
		default=5,
		help="Number of latest notices to fetch from list page.",
	)
	parser.add_argument(
		"--crawl-force",
		action="store_true",
		help="Ignore URL history and force crawl all selected notices.",
	)
	parser.add_argument(
		"--send-email",
		action="store_true",
		help="Send rendered HTML report with .ics and source-file attachments after pipeline completion.",
	)
	return parser.parse_args()


if __name__ == "__main__":
	args = parse_args()
	start_ui_by_default = len(sys.argv) == 1 and not args.run_pipeline
	if args.start_ui or start_ui_by_default:
		run_ui_console(host=args.ui_host, port=args.ui_port)
	else:
		run_reader_pipeline(
			file_arg=args.file,
			config_arg=args.config,
			save_output=args.save_cache,
			preview_parse=args.preview_parse,
			preview_chars=args.preview_chars,
			pipeline_mode=args.pipeline_mode,
			save_calendar=args.save_calendar,
			dispatch_owner=args.dispatch_owner,
			enable_crawler=args.enable_crawler,
			crawler_site=args.crawl_site,
			crawler_url=args.crawl_url,
			crawler_count=args.crawl_count,
			crawler_force=args.crawl_force,
			send_email=args.send_email,
		)

