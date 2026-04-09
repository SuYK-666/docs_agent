from __future__ import annotations

import hashlib
import httpx
import json
import logging
import random
import re
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Mapping
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
import trafilatura
from playwright.sync_api import Browser, BrowserContext, Error as PlaywrightError, TimeoutError as PlaywrightTimeoutError, sync_playwright

from config.logger_setup import log_step, to_relative_path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
LOGGER = logging.getLogger("docs_agent.web_crawler")

DEFAULT_HEADERS = {
	"User-Agent": (
		"Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
		"AppleWebKit/537.36 (KHTML, like Gecko) "
		"Chrome/124.0.0.0 Safari/537.36"
	),
	"Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
	"Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}

ATTACHMENT_SUFFIXES = {
	".pdf",
	".doc",
	".docx",
	".xls",
	".xlsx",
	".ppt",
	".pptx",
	".zip",
	".rar",
	".7z",
	".txt",
}

DEFAULT_USER_AGENTS = (
	"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
	"(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
	"Mozilla/5.0 (Macintosh; Intel Mac OS X 13_6) AppleWebKit/537.36 "
	"(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
	"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
	"(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
	"Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
)

NOTICE_TITLE_HINTS = (
	"通知",
	"公示",
	"竞赛",
	"管理办法",
	"实施方案",
	"申报",
	"评审",
	"名单",
	"公告",
	"活动",
	"报名",
	"项目",
)


class RetryableCrawlError(RuntimeError):
	"""Transient crawl error that should be retried with backoff."""


class LoginRequiredError(RuntimeError):
	"""The target page requires authentication and current cookie state is not valid."""

	def __init__(self, url: str, reason: str) -> None:
		super().__init__(reason)
		self.url = _safe_text(url)
		self.reason = _safe_text(reason, fallback="需要登录")


@dataclass(frozen=True)
class SpiderRuntimeConfig:
	timeout_seconds: int
	verify_ssl: bool
	force_encoding: str
	max_retries: int
	backoff_base_seconds: int
	sleep_min_seconds: float
	sleep_max_seconds: float
	headless: bool
	browser_channel: str
	wait_network_idle: bool
	wait_selector_timeout_seconds: int
	storage_state_file: Path
	allow_manual_login: bool
	manual_login_timeout_seconds: int
	user_agents: tuple[str, ...]
	login_url_keywords: tuple[str, ...]
	login_title_keywords: tuple[str, ...]


def _safe_int(value: Any, default: int) -> int:
	try:
		return int(float(value))
	except (TypeError, ValueError):
		return default


def _safe_float(value: Any, default: float) -> float:
	try:
		return float(value)
	except (TypeError, ValueError):
		return default


def _safe_text(value: Any, fallback: str = "") -> str:
	text = str(value).strip() if value is not None else ""
	return text or fallback


def _safe_filename(text: str, fallback: str = "document", max_len: int = 90) -> str:
	cleaned = re.sub(r"[\\/:*?\"<>|]+", "_", text).strip()
	cleaned = re.sub(r"\s+", " ", cleaned)
	if not cleaned:
		cleaned = fallback
	if len(cleaned) > max_len:
		cleaned = cleaned[:max_len].rstrip()
	return cleaned


def _ensure_unique_path(path: Path) -> Path:
	if not path.exists():
		return path

	stem = path.stem
	suffix = path.suffix
	parent = path.parent
	for index in range(2, 10000):
		candidate = parent / f"{stem}_{index}{suffix}"
		if not candidate.exists():
			return candidate
	return path


def _load_history(history_file: Path) -> set[str]:
	if not history_file.exists():
		return set()

	try:
		payload = json.loads(history_file.read_text(encoding="utf-8"))
	except Exception:  # pylint: disable=broad-except
		return set()

	if not isinstance(payload, list):
		return set()

	return {str(item).strip() for item in payload if str(item).strip()}


def _save_history(history_file: Path, urls: set[str]) -> None:
	history_file.parent.mkdir(parents=True, exist_ok=True)
	ordered = sorted(urls)
	history_file.write_text(json.dumps(ordered, ensure_ascii=False, indent=2), encoding="utf-8")


@dataclass(frozen=True)
class SpiderRule:
	list_url: str
	list_selector: str
	title_selector: str
	content_selector: str
	attachment_selector: str

	@classmethod
	def from_mapping(cls, data: Mapping[str, Any]) -> "SpiderRule":
		return cls(
			list_url=_safe_text(data.get("list_url")),
			list_selector=_safe_text(data.get("list_selector"), fallback="a[href]"),
			title_selector=_safe_text(data.get("title_selector"), fallback="h1"),
			content_selector=_safe_text(data.get("content_selector"), fallback="body"),
			attachment_selector=_safe_text(
				data.get("attachment_selector"),
				fallback="a[href$='.pdf'], a[href$='.doc'], a[href$='.docx']",
			),
		)


def _build_runtime_config(spider_cfg: Mapping[str, Any]) -> SpiderRuntimeConfig:
	retry_cfg = spider_cfg.get("retry", {}) if isinstance(spider_cfg.get("retry"), Mapping) else {}
	humanize_cfg = spider_cfg.get("humanize", {}) if isinstance(spider_cfg.get("humanize"), Mapping) else {}
	playwright_cfg = spider_cfg.get("playwright", {}) if isinstance(spider_cfg.get("playwright"), Mapping) else {}
	auth_cfg = spider_cfg.get("auth", {}) if isinstance(spider_cfg.get("auth"), Mapping) else {}

	configured_agents_raw = humanize_cfg.get("user_agents", []) if isinstance(humanize_cfg.get("user_agents"), list) else []
	configured_agents = [str(item).strip() for item in configured_agents_raw if str(item).strip()]
	user_agents = tuple(configured_agents or list(DEFAULT_USER_AGENTS))

	storage_state_rel = _safe_text(auth_cfg.get("storage_state_file"), fallback="data_workspace/cookies/spider_state.json")
	storage_state_file = PROJECT_ROOT / storage_state_rel

	login_url_keywords = auth_cfg.get("login_url_keywords", ["login", "cas", "oauth", "sso"]) if isinstance(auth_cfg.get("login_url_keywords"), list) else ["login", "cas", "oauth", "sso"]
	login_title_keywords = auth_cfg.get("login_title_keywords", ["登录", "统一身份认证", "身份认证", "扫码"]) if isinstance(auth_cfg.get("login_title_keywords"), list) else ["登录", "统一身份认证", "身份认证", "扫码"]

	return SpiderRuntimeConfig(
		timeout_seconds=max(5, _safe_int(spider_cfg.get("timeout_seconds", 25), 25)),
		verify_ssl=bool(spider_cfg.get("verify_ssl", False)),
		force_encoding=_safe_text(spider_cfg.get("force_encoding")),
		max_retries=max(1, _safe_int(retry_cfg.get("max_retries", 3), 3)),
		backoff_base_seconds=max(1, _safe_int(retry_cfg.get("backoff_base_seconds", 2), 2)),
		sleep_min_seconds=max(0.0, _safe_float(humanize_cfg.get("sleep_min_seconds", 1.5), 1.5)),
		sleep_max_seconds=max(0.0, _safe_float(humanize_cfg.get("sleep_max_seconds", 3.5), 3.5)),
		headless=bool(playwright_cfg.get("headless", True)),
		browser_channel=_safe_text(playwright_cfg.get("browser_channel")),
		wait_network_idle=bool(playwright_cfg.get("wait_network_idle", True)),
		wait_selector_timeout_seconds=max(2, _safe_int(playwright_cfg.get("wait_selector_timeout_seconds", 15), 15)),
		storage_state_file=storage_state_file,
		allow_manual_login=bool(auth_cfg.get("allow_manual_login", False)),
		manual_login_timeout_seconds=max(15, _safe_int(auth_cfg.get("manual_login_timeout_seconds", 120), 120)),
		user_agents=user_agents,
		login_url_keywords=tuple(str(item).lower().strip() for item in login_url_keywords if str(item).strip()),
		login_title_keywords=tuple(str(item).lower().strip() for item in login_title_keywords if str(item).strip()),
	)


def _build_headers(spider_cfg: Mapping[str, Any]) -> dict[str, str]:
	headers = dict(DEFAULT_HEADERS)
	custom_headers = spider_cfg.get("headers", {}) if isinstance(spider_cfg.get("headers"), Mapping) else {}
	for key, value in custom_headers.items():
		headers[str(key)] = str(value)
	return headers


def _pick_user_agent(runtime_cfg: SpiderRuntimeConfig) -> str:
	if runtime_cfg.user_agents:
		return random.choice(runtime_cfg.user_agents)
	return DEFAULT_HEADERS["User-Agent"]


def _sleep_between_requests(runtime_cfg: SpiderRuntimeConfig) -> None:
	minimum = max(0.0, runtime_cfg.sleep_min_seconds)
	maximum = max(minimum, runtime_cfg.sleep_max_seconds)
	if maximum <= 0:
		return
	wait_seconds = random.uniform(minimum, maximum)
	time.sleep(wait_seconds)


def _is_login_page(url: str, title: str, runtime_cfg: SpiderRuntimeConfig) -> bool:
	url_lower = _safe_text(url).lower()
	title_lower = _safe_text(title).lower()
	if any(keyword and keyword in url_lower for keyword in runtime_cfg.login_url_keywords):
		return True
	if any(keyword and keyword in title_lower for keyword in runtime_cfg.login_title_keywords):
		return True
	return False


def _is_retryable_exception(exc: Exception) -> bool:
	if isinstance(exc, (httpx.TimeoutException, httpx.TransportError)):
		return True
	if isinstance(exc, (RetryableCrawlError, PlaywrightTimeoutError)):
		return True
	if isinstance(exc, PlaywrightError):
		message = str(exc).lower()
		retry_tokens = [
			"timeout",
			"timed out",
			"net::err",
			"connection",
			"429",
			"502",
			"503",
			"504",
		]
		return any(token in message for token in retry_tokens)
	return False


def _retry_with_backoff(
	*,
	runtime_cfg: SpiderRuntimeConfig,
	url: str,
	step: str,
	action: Callable[[], Any],
) -> Any:
	last_error: Exception | None = None
	for attempt in range(1, runtime_cfg.max_retries + 1):
		try:
			return action()
		except LoginRequiredError:
			raise
		except Exception as exc:  # pylint: disable=broad-except
			last_error = exc
			if attempt >= runtime_cfg.max_retries or not _is_retryable_exception(exc):
				raise

			wait_seconds = runtime_cfg.backoff_base_seconds * (2 ** (attempt - 1))
			log_step(
				LOGGER,
				"crawler.retry",
				"WebCrawler",
				"RetryWait",
				f"step={step} url={url} attempt={attempt}/{runtime_cfg.max_retries} wait={wait_seconds}s reason={exc}",
			)
			time.sleep(wait_seconds)

	if last_error is not None:
		raise last_error
	raise RuntimeError(f"retry failed without explicit error: {step}")


def _launch_browser(playwright: Any, runtime_cfg: SpiderRuntimeConfig, force_headed: bool = False) -> Browser:
	launch_kwargs: dict[str, Any] = {"headless": False if force_headed else runtime_cfg.headless}
	if runtime_cfg.browser_channel:
		launch_kwargs["channel"] = runtime_cfg.browser_channel
	return playwright.chromium.launch(**launch_kwargs)


def _build_browser_context(
	browser: Browser,
	runtime_cfg: SpiderRuntimeConfig,
	headers: Mapping[str, str],
	user_agent: str,
) -> BrowserContext:
	context_kwargs: dict[str, Any] = {
		"ignore_https_errors": not runtime_cfg.verify_ssl,
		"user_agent": user_agent,
	}
	if runtime_cfg.storage_state_file.exists():
		context_kwargs["storage_state"] = str(runtime_cfg.storage_state_file)

	context = browser.new_context(**context_kwargs)
	extra_headers = {
		str(key): str(value)
		for key, value in headers.items()
		if str(key).strip() and str(key).lower() != "user-agent"
	}
	if extra_headers:
		context.set_extra_http_headers(extra_headers)
	return context


def _open_rendered_page(
	context: BrowserContext,
	url: str,
	runtime_cfg: SpiderRuntimeConfig,
) -> dict[str, Any]:
	page = context.new_page()
	timeout_ms = runtime_cfg.timeout_seconds * 1000
	try:
		# Wait for global network idle instead of waiting any specific CSS selector.
		response = page.goto(url, wait_until="networkidle", timeout=timeout_ms)

		status = response.status if response is not None else 200
		final_url = _safe_text(page.url, fallback=url)
		title = _safe_text(page.title())

		if status in {429, 502, 503, 504}:
			raise RetryableCrawlError(f"HTTP {status}")
		if status in {401, 403} or _is_login_page(final_url, title, runtime_cfg):
			raise LoginRequiredError(url=final_url, reason=f"需要登录或权限校验（status={status}）")

		html = page.content()
		return {
			"html": html,
			"title": title,
			"status": status,
			"final_url": final_url,
		}
	finally:
		page.close()


def _extract_title_from_html(html: str, selector: str) -> str:
	soup = BeautifulSoup(html, "lxml")
	node = soup.select_one(selector) if selector else None
	if node is not None:
		return _safe_text(node.get_text(" ", strip=True))
	if soup.title is not None:
		return _safe_text(soup.title.get_text(" ", strip=True))
	return ""


def _extract_attachments_from_html(html: str, detail_url: str, selector: str) -> list[dict[str, str]]:
	if not selector:
		return []
	soup = BeautifulSoup(html, "lxml")
	results: list[dict[str, str]] = []
	seen: set[str] = set()
	for anchor in soup.select(selector):
		href = _safe_text(anchor.get("href"))
		if not href:
			continue
		file_url = urljoin(detail_url, href)
		if file_url in seen:
			continue
		seen.add(file_url)
		name = _safe_text(anchor.get_text(" ", strip=True), fallback=Path(urlparse(file_url).path).name or "附件")
		results.append({"name": name, "url": file_url})
	return results


def _extract_clean_content(html: str, fallback_selector: str) -> str:
	extracted = trafilatura.extract(
		html,
		include_comments=False,
		include_tables=True,
		no_fallback=False,
		output_format="txt",
	)
	cleaned = _safe_text(extracted)
	if cleaned:
		return cleaned

	# Fallback only when algorithmic extraction fails completely.
	soup = BeautifulSoup(html, "lxml")
	node = soup.select_one(fallback_selector) if fallback_selector else soup.body
	if node is None:
		return "未提取到正文内容"
	return _safe_text(node.get_text("\n", strip=True), fallback="未提取到正文内容")


def _is_navigation_href(href: str) -> bool:
	value = _safe_text(href).lower()
	if not value:
		return True
	if value in {"#", "/"}:
		return True
	if value.startswith("#"):
		return True
	if value.startswith("javascript:"):
		return True
	if value.startswith("mailto:"):
		return True
	if value.startswith("tel:"):
		return True
	return False


def _looks_like_notice_title(text: str) -> bool:
	normalized = re.sub(r"\s+", "", _safe_text(text))
	if not normalized:
		return False
	if any(token in normalized for token in NOTICE_TITLE_HINTS):
		return True
	return len(normalized) >= 10


def _is_home_or_list_link(url: str, list_url: str) -> bool:
	target = urlparse(url)
	base = urlparse(list_url)
	target_path = _safe_text(target.path).rstrip("/").lower()
	base_path = _safe_text(base.path).rstrip("/").lower()
	if target_path in {"", "/"}:
		return True
	if base_path and target_path == base_path and not _safe_text(target.query):
		return True
	filename = Path(target_path).name.lower()
	if filename.startswith("index") and not _safe_text(target.query):
		return True
	return False


def _extract_notice_links_heuristic(soup: BeautifulSoup, list_url: str) -> list[dict[str, str]]:
	base = urlparse(list_url)
	strict: list[dict[str, str]] = []
	relaxed: list[dict[str, str]] = []
	seen: set[str] = set()

	for anchor in soup.select("a[href]"):
		href = _safe_text(anchor.get("href"))
		if _is_navigation_href(href):
			continue

		url = urljoin(list_url, href)
		parsed = urlparse(url)
		if parsed.scheme not in {"http", "https"}:
			continue
		if base.netloc and parsed.netloc and parsed.netloc.lower() != base.netloc.lower():
			continue
		if _is_home_or_list_link(url=url, list_url=list_url):
			continue
		if url in seen:
			continue

		title = _safe_text(anchor.get_text(" ", strip=True))
		if not title:
			title = _safe_text(anchor.get("title"))
		if not title:
			continue

		item = {"title": title, "url": url}
		if _looks_like_notice_title(title):
			strict.append(item)
			seen.add(url)
			continue

		normalized = re.sub(r"\s+", "", title)
		suffix = Path(parsed.path).suffix.lower()
		if len(normalized) >= 6 and suffix in {".html", ".htm", ".shtml", ".pdf", ".doc", ".docx"}:
			relaxed.append(item)
			seen.add(url)

	return strict if strict else relaxed


def fetch_notice_list(
	browser: Browser,
	rule: SpiderRule,
	limit: int,
	runtime_cfg: SpiderRuntimeConfig,
	headers: Mapping[str, str],
) -> list[dict[str, str]]:
	"""Fetch detail links from list page after dynamic rendering is fully completed."""
	context = _build_browser_context(browser, runtime_cfg, headers=headers, user_agent=_pick_user_agent(runtime_cfg))
	try:
		rendered = _retry_with_backoff(
			runtime_cfg=runtime_cfg,
			url=rule.list_url,
			step="ListFetch",
			action=lambda: _open_rendered_page(
				context=context,
				url=rule.list_url,
				runtime_cfg=runtime_cfg,
			),
		)

		html = _safe_text(rendered.get("html"), fallback="")
		soup = BeautifulSoup(html, "lxml")
		candidates = _extract_notice_links_heuristic(soup=soup, list_url=rule.list_url)
		if not candidates:
			raise RetryableCrawlError("list page contains no candidate notice links")

		results: list[dict[str, str]] = []
		seen: set[str] = set()
		for item in candidates:
			url = _safe_text(item.get("url"))
			title = _safe_text(item.get("title"))
			if not url:
				continue
			if url in seen:
				continue
			seen.add(url)
			if not title:
				parsed = urlparse(url)
				title = Path(parsed.path).name or "未命名通知"

			results.append({"title": title, "url": url})
			if len(results) >= max(1, limit):
				break

		return results
	finally:
		context.close()


def parse_detail_page(
	browser: Browser,
	detail_url: str,
	rule: SpiderRule,
	runtime_cfg: SpiderRuntimeConfig,
	headers: Mapping[str, str],
) -> dict[str, Any]:
	"""Parse detail page by browser-rendered DOM + algorithmic content extraction."""
	context = _build_browser_context(browser, runtime_cfg, headers=headers, user_agent=_pick_user_agent(runtime_cfg))
	try:
		rendered = _retry_with_backoff(
			runtime_cfg=runtime_cfg,
			url=detail_url,
			step="DetailFetch",
			action=lambda: _open_rendered_page(
				context=context,
				url=detail_url,
				runtime_cfg=runtime_cfg,
			),
		)

		html = _safe_text(rendered.get("html"), fallback="")
		title = _extract_title_from_html(html=html, selector=rule.title_selector)
		if not title:
			title = "未命名通知"

		content_text = _extract_clean_content(html=html, fallback_selector=rule.content_selector)
		attachments = _extract_attachments_from_html(html=html, detail_url=detail_url, selector=rule.attachment_selector)

		return {
			"url": detail_url,
			"final_url": _safe_text(rendered.get("final_url"), fallback=detail_url),
			"title": title,
			"content": content_text,
			"attachments": attachments,
		}
	finally:
		context.close()


def _build_notice_text(title: str, detail_url: str, content: str) -> str:
	now_text = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
	parts = [
		f"标题：{title}",
		f"来源链接：{detail_url}",
		f"抓取时间：{now_text}",
		"",
		"正文：",
		content,
		"",
	]
	return "\n".join(parts)


def _save_notice_text(raw_docs_dir: Path, title: str, detail_url: str, content: str) -> Path:
	raw_docs_dir.mkdir(parents=True, exist_ok=True)
	file_name = f"{_safe_filename(title, fallback='网页通知')}.txt"
	path = _ensure_unique_path(raw_docs_dir / file_name)
	path.write_text(_build_notice_text(title=title, detail_url=detail_url, content=content), encoding="utf-8")
	return path


def _is_direct_file_url(url: str) -> bool:
	parsed = urlparse(url)
	suffix = Path(parsed.path).suffix.lower()
	if not suffix:
		return False
	if suffix in {".html", ".htm", ".shtml"}:
		return False
	return suffix in ATTACHMENT_SUFFIXES


def _build_download_filename(url: str, title_hint: str) -> str:
	parsed = urlparse(url)
	name_from_url = Path(parsed.path).name
	if name_from_url:
		return _safe_filename(name_from_url, fallback="downloaded_file")

	base = _safe_filename(title_hint, fallback="downloaded_file")
	if Path(base).suffix:
		return base
	return f"{base}.bin"


def _download_direct_source_file(
	*,
	url: str,
	title_hint: str,
	raw_docs_dir: Path,
	runtime_cfg: SpiderRuntimeConfig,
	headers: Mapping[str, str],
) -> Path:
	raw_docs_dir.mkdir(parents=True, exist_ok=True)

	request_headers = {
		str(key): str(value)
		for key, value in headers.items()
		if str(key).strip()
	}
	request_headers["User-Agent"] = _pick_user_agent(runtime_cfg)

	def _download_once() -> tuple[bytes, str]:
		with httpx.Client(
			timeout=runtime_cfg.timeout_seconds,
			verify=runtime_cfg.verify_ssl,
			follow_redirects=True,
			headers=request_headers,
		) as client:
			response = client.get(url)

		status = int(response.status_code)
		if status in {429, 502, 503, 504}:
			raise RetryableCrawlError(f"direct_file HTTP {status}")
		if status in {401, 403}:
			raise LoginRequiredError(url=str(response.url), reason=f"需要登录或权限校验（status={status}）")
		if status >= 400:
			raise RuntimeError(f"direct_file rejected HTTP {status}")

		content = response.content
		if not content:
			raise RetryableCrawlError("direct_file empty body")

		return content, str(response.url)

	binary, final_url = _retry_with_backoff(
		runtime_cfg=runtime_cfg,
		url=url,
		step="DirectFileDownload",
		action=_download_once,
	)

	file_name = _build_download_filename(final_url or url, title_hint=title_hint)
	output_path = _ensure_unique_path(raw_docs_dir / file_name)
	output_path.write_bytes(binary)
	return output_path


def download_attachments(
	browser: Browser,
	attachments: list[dict[str, str]],
	raw_docs_dir: Path,
	title_prefix: str,
	runtime_cfg: SpiderRuntimeConfig,
	headers: Mapping[str, str],
) -> list[Path]:
	"""Download attachments with browser session state, retries and backoff."""
	raw_docs_dir.mkdir(parents=True, exist_ok=True)
	saved_files: list[Path] = []
	prefix = _safe_filename(title_prefix, fallback="网页通知", max_len=45)
	context = _build_browser_context(browser, runtime_cfg, headers=headers, user_agent=_pick_user_agent(runtime_cfg))
	try:
		for index, item in enumerate(attachments, start=1):
			file_url = _safe_text(item.get("url"))
			if not file_url:
				continue

			parsed = urlparse(file_url)
			url_name = Path(parsed.path).name
			ext = Path(url_name).suffix.lower()
			if ext and ext not in ATTACHMENT_SUFFIXES:
				continue

			raw_name = _safe_text(item.get("name"), fallback=url_name or f"附件{index}{ext or '.bin'}")
			base_name = _safe_filename(raw_name, fallback=f"附件{index}")
			if not Path(base_name).suffix and ext:
				base_name = f"{base_name}{ext}"
			elif not Path(base_name).suffix:
				base_name = f"{base_name}.bin"

			final_name = f"[{prefix}]-{base_name}"
			output_path = _ensure_unique_path(raw_docs_dir / final_name)

			def _download_once() -> bytes:
				response = context.request.get(
					file_url,
					timeout=runtime_cfg.timeout_seconds * 1000,
					fail_on_status_code=False,
				)
				status = int(response.status)
				if status in {429, 502, 503, 504}:
					raise RetryableCrawlError(f"attachment HTTP {status}")
				if status >= 400:
					raise RuntimeError(f"attachment download rejected HTTP {status}")
				return response.body()

			binary = _retry_with_backoff(
				runtime_cfg=runtime_cfg,
				url=file_url,
				step="AttachmentDownload",
				action=_download_once,
			)

			output_path.write_bytes(binary)
			saved_files.append(output_path)
			_sleep_between_requests(runtime_cfg)
	finally:
		context.close()

	return saved_files


def _build_failed_item(url: str, reason: str, step: str) -> dict[str, Any]:
	return {
		"status": "failed",
		"url": _safe_text(url),
		"reason": _safe_text(reason, fallback="未知异常"),
		"step": _safe_text(step, fallback="crawl"),
		"occurred_at": datetime.now().isoformat(timespec="seconds"),
	}


def _build_failed_report_payload(item: Mapping[str, Any], index: int) -> dict[str, Any]:
	url = _safe_text(item.get("url"), fallback="unknown")
	reason = _safe_text(item.get("reason"), fallback="URL不可达")
	digest = hashlib.md5(url.encode("utf-8")).hexdigest()[:10]
	doc_id = f"crawl_failed_{datetime.now().strftime('%Y%m%d%H%M%S')}_{index}_{digest}"
	warning_text = "警告：该网址来源抓取失败，请人工核实原链接。"

	return {
		"status": "failed",
		"doc_id": doc_id,
		"title": "网页抓取失败告警",
		"document_no": "抓取异常",
		"publish_date": datetime.now().strftime("%Y-%m-%d"),
		"issuing_department": "在线爬虫模块",
		"doc_type": "抓取失败告警",
		"summary": f"{warning_text} 原链接：{url}；失败原因：{reason}",
		"tasks": [],
		"risks_or_unclear_points": [
			warning_text,
			f"原链接：{url}",
			f"失败原因：{reason}",
		],
		"follow_up_questions": [
			"请人工打开原链接确认该通知是否已下线或需要登录。",
			"如需继续自动抓取，请更新 Cookie 状态后重试。",
		],
		"warning": warning_text,
		"crawl_error": {
			"url": url,
			"reason": reason,
			"step": _safe_text(item.get("step"), fallback="crawl"),
		},
	}


def _save_failed_report_cache(settings: Mapping[str, Any], payload: Mapping[str, Any]) -> Path:
	paths_cfg = settings.get("paths", {}) if isinstance(settings.get("paths"), Mapping) else {}
	cache_dir = PROJECT_ROOT / str(paths_cfg.get("processed_cache_dir", "data_workspace/processed_cache"))
	cache_dir.mkdir(parents=True, exist_ok=True)
	file_stem = _safe_filename(_safe_text(payload.get("doc_id"), fallback="crawl_failed"), fallback="crawl_failed")
	cache_path = _ensure_unique_path(cache_dir / f"{file_stem}.agent.json")
	cache_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
	return cache_path


def _run_manual_login_flow(playwright: Any, runtime_cfg: SpiderRuntimeConfig, headers: Mapping[str, str], login_url: str) -> bool:
	if not runtime_cfg.allow_manual_login:
		return False

	runtime_cfg.storage_state_file.parent.mkdir(parents=True, exist_ok=True)
	log_step(
		LOGGER,
		"crawler.auth",
		"WebCrawler",
		"ManualLoginStart",
		f"login_url={login_url} timeout={runtime_cfg.manual_login_timeout_seconds}s storage={to_relative_path(runtime_cfg.storage_state_file)}",
	)

	try:
		browser = _launch_browser(playwright, runtime_cfg, force_headed=True)
		context = _build_browser_context(
			browser,
			runtime_cfg,
			headers=headers,
			user_agent=_pick_user_agent(runtime_cfg),
		)
		try:
			page = context.new_page()
			page.goto(login_url, wait_until="domcontentloaded", timeout=runtime_cfg.timeout_seconds * 1000)
			page.wait_for_timeout(runtime_cfg.manual_login_timeout_seconds * 1000)
			context.storage_state(path=str(runtime_cfg.storage_state_file))
		finally:
			context.close()
			browser.close()
	except Exception as exc:  # pylint: disable=broad-except
		LOGGER.warning(
			"STEP=crawler.auth | AGENT=WebCrawler | ACTION=ManualLoginFailed | DETAILS=url=%s reason=%s",
			login_url,
			exc,
		)
		return False

	success = runtime_cfg.storage_state_file.exists()
	log_step(
		LOGGER,
		"crawler.auth",
		"WebCrawler",
		"ManualLoginDone",
		f"success={success} storage={to_relative_path(runtime_cfg.storage_state_file)}",
	)
	return success


def run_crawler(
	settings: Mapping[str, Any],
	raw_docs_dir: Path,
	limit: int = 5,
	site_name: str | None = None,
	list_url_override: str | None = None,
	force: bool = False,
	keyword: str | None = None,
	progress_callback: Callable[[Mapping[str, Any]], None] | None = None,
) -> dict[str, Any]:
	"""Run crawler as feeder: dynamic rendering, clean extraction and standardized failure outputs."""
	spider_cfg = settings.get("spiders", {}) if isinstance(settings.get("spiders"), Mapping) else {}
	sites_cfg = spider_cfg.get("sites", {}) if isinstance(spider_cfg.get("sites"), Mapping) else {}

	selected_site = (site_name or "").strip() or _safe_text(spider_cfg.get("default_site"))
	if not selected_site and not list_url_override:
		raise ValueError("Crawler requires spiders.default_site or --crawl-site/--crawl-url.")

	site_rule_map = sites_cfg.get(selected_site, {}) if selected_site else {}
	if site_rule_map and not isinstance(site_rule_map, Mapping):
		site_rule_map = {}

	rule = SpiderRule.from_mapping(site_rule_map if isinstance(site_rule_map, Mapping) else {})
	if list_url_override:
		rule = SpiderRule(
			list_url=_safe_text(list_url_override),
			list_selector=rule.list_selector,
			title_selector=rule.title_selector,
			content_selector=rule.content_selector,
			attachment_selector=rule.attachment_selector,
		)

	if not rule.list_url:
		raise ValueError("Crawler list_url is empty. Configure spiders.sites.<name>.list_url or pass --crawl-url.")

	runtime_cfg = _build_runtime_config(spider_cfg)
	history_file_rel = _safe_text(spider_cfg.get("history_file"), fallback="data_workspace/history_urls.json")
	history_file = PROJECT_ROOT / history_file_rel
	headers = _build_headers(spider_cfg)

	known_urls = _load_history(history_file)
	keyword_text = _safe_text(keyword).lower()
	listed = 0
	new_notices = 0
	skipped = 0
	filtered_out = 0
	direct_file_routed = 0
	text_files: list[Path] = []
	attachment_files: list[Path] = []
	failed_items: list[dict[str, Any]] = []
	failed_cache_files: list[Path] = []
	total_candidates = 0

	def _report_progress(
		*,
		current: int,
		total: int,
		message: str,
		percent: int | float | None = None,
		stage: str = "progress",
		discovered_file: str = "",
		parser_hint: str = "",
	) -> None:
		if progress_callback is None:
			return
		payload: dict[str, Any] = {
			"current": max(0, int(current)),
			"total": max(0, int(total)),
			"message": _safe_text(message, fallback="网页抓取处理中"),
			"stage": _safe_text(stage, fallback="progress"),
		}
		if discovered_file:
			payload["discovered_file"] = _safe_text(discovered_file)
		if parser_hint:
			payload["parser_hint"] = _safe_text(parser_hint)
		if percent is not None:
			try:
				payload["percent"] = float(percent)
			except (TypeError, ValueError):
				pass
		try:
			progress_callback(payload)
		except Exception as exc:  # pylint: disable=broad-except
			LOGGER.warning(
				"STEP=crawler | AGENT=WebCrawler | ACTION=ProgressCallbackError | DETAILS=error=%s",
				exc,
			)

	log_step(
		LOGGER,
		"crawler",
		"WebCrawler",
		"Start",
		(
			f"site={selected_site or 'adhoc'} list_url={rule.list_url} limit={max(1, limit)} "
			f"keyword={keyword_text or 'none'} headless={runtime_cfg.headless} "
			f"raw_docs_dir={to_relative_path(raw_docs_dir)} history_file={to_relative_path(history_file)}"
		),
	)

	with sync_playwright() as playwright:
		browser = _launch_browser(playwright, runtime_cfg)
		try:
			try:
				_report_progress(current=0, total=max(1, limit), message="正在请求公告列表", percent=5, stage="list_start")
				notices = fetch_notice_list(
					browser=browser,
					rule=rule,
					limit=max(1, limit),
					runtime_cfg=runtime_cfg,
					headers=headers,
				)
			except LoginRequiredError as exc:
				manual_ok = _run_manual_login_flow(playwright, runtime_cfg, headers, exc.url or rule.list_url)
				if manual_ok:
					notices = fetch_notice_list(
						browser=browser,
						rule=rule,
						limit=max(1, limit),
						runtime_cfg=runtime_cfg,
						headers=headers,
					)
				else:
					failed_items.append(_build_failed_item(url=rule.list_url, reason=exc.reason, step="list_fetch"))
					notices = []

			listed = len(notices)
			total_candidates = max(1, listed)
			candidate_titles = [
				f"{idx}. {_safe_text(item.get('title'), fallback='未命名公告')}"
				for idx, item in enumerate(notices, start=1)
			]
			candidate_text = "；".join(candidate_titles) if candidate_titles else "无"
			_report_progress(
				current=0,
				total=total_candidates,
				message=f"列表抓取完成，发现 {listed} 条候选公告：{candidate_text}",
				percent=10,
				stage="list_done",
			)

			for index, notice in enumerate(notices, start=1):
				notice_title_hint = _safe_text(notice.get("title"), fallback="网页通知")
				detail_url = _safe_text(notice.get("url"))
				if not detail_url:
					_report_progress(
						current=index,
						total=total_candidates,
						message=f"第 {index}/{total_candidates} 条链接无效，已跳过：{notice_title_hint}",
						stage="notice_skip",
					)
					continue
				if not force and detail_url in known_urls:
					skipped += 1
					_report_progress(
						current=index,
						total=total_candidates,
						message=f"第 {index}/{total_candidates} 条为历史公告，已跳过：{notice_title_hint}",
						stage="notice_skip",
					)
					continue
				_report_progress(
					current=max(0, index - 1),
					total=total_candidates,
					message=f"正在抓取第 {index}/{total_candidates} 条：{notice_title_hint}",
					stage="notice_start",
				)

				_sleep_between_requests(runtime_cfg)

				if _is_direct_file_url(detail_url):
					try:
						downloaded_source = _download_direct_source_file(
							url=detail_url,
							title_hint=notice_title_hint,
							raw_docs_dir=raw_docs_dir,
							runtime_cfg=runtime_cfg,
							headers=headers,
						)
					except LoginRequiredError as exc:
						manual_ok = _run_manual_login_flow(playwright, runtime_cfg, headers, exc.url or detail_url)
						if not manual_ok:
							failed_items.append(_build_failed_item(url=detail_url, reason=exc.reason, step="direct_file_download"))
							_report_progress(
								current=index,
								total=total_candidates,
								message=f"第 {index}/{total_candidates} 条下载失败：{exc.reason}",
								stage="notice_error",
							)
							continue
						downloaded_source = _download_direct_source_file(
							url=detail_url,
							title_hint=notice_title_hint,
							raw_docs_dir=raw_docs_dir,
							runtime_cfg=runtime_cfg,
							headers=headers,
						)
					except Exception as exc:  # pylint: disable=broad-except
						failed_items.append(_build_failed_item(url=detail_url, reason=str(exc), step="direct_file_download"))
						_report_progress(
							current=index,
							total=total_candidates,
							message=f"第 {index}/{total_candidates} 条下载失败：{exc}",
							stage="notice_error",
						)
						continue

					if keyword_text:
						file_name = downloaded_source.name.lower()
						if keyword_text not in notice_title_hint.lower() and keyword_text not in file_name:
							filtered_out += 1
							downloaded_source.unlink(missing_ok=True)
							_report_progress(
								current=index,
								total=total_candidates,
								message=f"第 {index}/{total_candidates} 条不匹配关键词，已过滤：{notice_title_hint}",
								stage="notice_filtered",
							)
							continue

					text_files.append(downloaded_source)
					direct_file_routed += 1
					known_urls.add(detail_url)
					new_notices += 1
					log_step(
						LOGGER,
						"crawler",
						"WebCrawler",
						"NoticeDone",
						f"url={detail_url} route=direct_file source={to_relative_path(downloaded_source)} attachments=0",
					)
					_report_progress(
						current=index,
						total=total_candidates,
						message=f"完成第 {index}/{total_candidates} 条：{notice_title_hint}（直链文件 {downloaded_source.name}）",
						stage="notice_done",
						discovered_file=downloaded_source.name,
						parser_hint="ocr" if downloaded_source.suffix.lower() in {".pdf", ".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp"} else "text",
					)
					continue

				try:
					detail = parse_detail_page(
						browser=browser,
						detail_url=detail_url,
						rule=rule,
						runtime_cfg=runtime_cfg,
						headers=headers,
					)
				except LoginRequiredError as exc:
					manual_ok = _run_manual_login_flow(playwright, runtime_cfg, headers, exc.url or detail_url)
					if not manual_ok:
						failed_items.append(_build_failed_item(url=detail_url, reason=exc.reason, step="detail_fetch"))
						_report_progress(
							current=index,
							total=total_candidates,
							message=f"第 {index}/{total_candidates} 条详情抓取失败：{notice_title_hint}，{exc.reason}",
							stage="notice_error",
						)
						continue
					detail = parse_detail_page(
						browser=browser,
						detail_url=detail_url,
						rule=rule,
						runtime_cfg=runtime_cfg,
						headers=headers,
					)
				except Exception as exc:  # pylint: disable=broad-except
					failed_items.append(_build_failed_item(url=detail_url, reason=str(exc), step="detail_fetch"))
					_report_progress(
						current=index,
						total=total_candidates,
						message=f"第 {index}/{total_candidates} 条详情抓取失败：{notice_title_hint}，{exc}",
						stage="notice_error",
					)
					continue

				title = _safe_text(detail.get("title"), fallback=_safe_text(notice.get("title"), fallback="网页通知"))
				content = _safe_text(detail.get("content"), fallback="未提取到正文内容")
				if keyword_text:
					in_title = keyword_text in title.lower()
					in_content = keyword_text in content.lower()
					if not in_title and not in_content:
						filtered_out += 1
						_report_progress(
							current=index,
							total=total_candidates,
							message=f"第 {index}/{total_candidates} 条不匹配关键词，已过滤：{title}",
							stage="notice_filtered",
						)
						continue

				text_path = _save_notice_text(
					raw_docs_dir=raw_docs_dir,
					title=title,
					detail_url=detail_url,
					content=content,
				)
				text_files.append(text_path)

				attachments = detail.get("attachments", [])
				attachment_items = attachments if isinstance(attachments, list) else []
				try:
					downloaded = download_attachments(
						browser=browser,
						attachments=[item for item in attachment_items if isinstance(item, Mapping)],
						raw_docs_dir=raw_docs_dir,
						title_prefix=title,
						runtime_cfg=runtime_cfg,
						headers=headers,
					)
				except Exception as exc:  # pylint: disable=broad-except
					downloaded = []
					failed_items.append(_build_failed_item(url=detail_url, reason=f"附件下载失败: {exc}", step="attachment_download"))

				attachment_files.extend(downloaded)
				known_urls.add(detail_url)
				new_notices += 1
				log_step(
					LOGGER,
					"crawler",
					"WebCrawler",
					"NoticeDone",
					f"url={detail_url} txt={to_relative_path(text_path)} attachments={len(downloaded)}",
				)
				_report_progress(
					current=index,
					total=total_candidates,
					message=f"完成第 {index}/{total_candidates} 条：{title}（正文+附件 {len(downloaded)}）",
					stage="notice_done",
					discovered_file=text_path.name,
					parser_hint="text",
				)
		finally:
			browser.close()

	_report_progress(
		current=total_candidates,
		total=total_candidates,
		message=f"抓取阶段完成：新增 {new_notices} 条，失败 {len(failed_items)} 条",
		percent=100,
		stage="done",
	)

	for index, item in enumerate(failed_items, start=1):
		payload = _build_failed_report_payload(item=item, index=index)
		cache_path = _save_failed_report_cache(settings=settings, payload=payload)
		failed_cache_files.append(cache_path)
		item["cache_file"] = to_relative_path(cache_path)
		log_step(
			LOGGER,
			"crawler",
			"WebCrawler",
			"FailureCached",
			f"url={item.get('url', '')} reason={item.get('reason', '')} cache={to_relative_path(cache_path)}",
		)

	_save_history(history_file, known_urls)
	failure_count = len(failed_items)
	status = "success"
	if new_notices == 0 and failure_count > 0:
		status = "failed"
	elif failure_count > 0:
		status = "partial_failed"

	summary = {
		"status": status,
		"site": selected_site or "adhoc",
		"list_url": rule.list_url,
		"keyword": keyword_text,
		"listed": listed,
		"new_notices": new_notices,
		"skipped": skipped,
		"filtered_out": filtered_out,
		"direct_file_routed": direct_file_routed,
		"failed": failure_count,
		"failed_items": failed_items,
		"failed_cache_files": [to_relative_path(path) for path in failed_cache_files],
		"text_files": [to_relative_path(path) for path in text_files],
		"attachment_files": [to_relative_path(path) for path in attachment_files],
		"history_file": to_relative_path(history_file),
		"storage_state_file": to_relative_path(runtime_cfg.storage_state_file),
		"raw_docs_dir": to_relative_path(raw_docs_dir),
	}

	log_step(
		LOGGER,
		"crawler",
		"WebCrawler",
		"Done",
		(
			f"status={summary['status']} listed={summary['listed']} new_notices={summary['new_notices']} "
			f"skipped={summary['skipped']} filtered_out={summary['filtered_out']} direct_file_routed={summary['direct_file_routed']} "
			f"failed={summary['failed']} txt_files={len(text_files)} "
			f"attachment_files={len(attachment_files)}"
		),
	)

	return summary
