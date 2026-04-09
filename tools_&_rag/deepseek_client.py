from __future__ import annotations

import asyncio
import inspect
import json
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping
from urllib.parse import urlparse

import httpx

from config.logger_setup import get_logger


class RetryableDeepSeekError(RuntimeError):
	"""Retryable API or network error."""


StreamChunkCallback = Callable[[str], Any]


@dataclass
class DeepSeekConfig:
	api_key: str
	base_url: str = "https://api.deepseek.com"
	model: str = "deepseek-chat"
	timeout_seconds: int = 60
	max_retries: int = 4
	backoff_base_seconds: int = 2
	temperature: float = 0.0
	top_p: float = 1.0
	max_output_tokens: int = 1500
	request_json_mode: bool = True
	provider: str = "deepseek"
	chat_completions_path: str = "/chat/completions"
	auth_header_name: str = "Authorization"
	auth_header_prefix: str = "Bearer "
	extra_headers: dict[str, str] = field(default_factory=dict)


class DeepSeekClient:
	def __init__(self, config: DeepSeekConfig) -> None:
		if not config.api_key.strip():
			raise ValueError("LLM API key is empty.")

		self.config = config
		self.endpoint = self._resolve_endpoint(config.base_url, config.chat_completions_path)
		self.logger = get_logger("deepseek_client")

	@staticmethod
	def _resolve_endpoint(base_url: str, path: str) -> str:
		path_text = str(path).strip()
		parsed = urlparse(path_text)
		if parsed.scheme and parsed.netloc:
			return path_text

		base = str(base_url).strip().rstrip("/")
		if not path_text:
			return f"{base}/chat/completions"

		normalized = path_text if path_text.startswith("/") else f"/{path_text}"
		return f"{base}{normalized}"

	def _build_headers(self) -> dict[str, str]:
		headers = {"Content-Type": "application/json"}
		header_name = str(self.config.auth_header_name).strip()
		if header_name:
			prefix = str(self.config.auth_header_prefix or "")
			headers[header_name] = f"{prefix}{self.config.api_key}"

		for key, value in self.config.extra_headers.items():
			key_text = str(key).strip()
			if not key_text:
				continue
			headers[key_text] = str(value)
		return headers

	async def chat_completion(
		self,
		messages: list[dict[str, str]],
		response_format: Mapping[str, Any] | None = None,
		temperature: float | None = None,
		max_tokens: int | None = None,
		stream: bool = False,
		stream_callback: StreamChunkCallback | None = None,
	) -> dict[str, Any]:
		effective_temperature = self.config.temperature if temperature is None else temperature
		effective_tokens = self.config.max_output_tokens if max_tokens is None else max_tokens
		effective_stream = bool(stream)

		self.logger.info(
			"STEP=llm.request | AGENT=DeepSeekClient | ACTION=BuildPayload | DETAILS=provider=%s model=%s messages=%s temperature=%s max_tokens=%s stream=%s",
			self.config.provider,
			self.config.model,
			len(messages),
			effective_temperature,
			effective_tokens,
			effective_stream,
		)

		payload: dict[str, Any] = {
			"model": self.config.model,
			"messages": messages,
			"temperature": effective_temperature,
			"top_p": self.config.top_p,
			"max_tokens": effective_tokens,
			"stream": effective_stream,
		}

		if response_format is not None:
			payload["response_format"] = dict(response_format)
		elif self.config.request_json_mode:
			payload["response_format"] = {"type": "json_object"}

		headers = self._build_headers()
		max_retries = max(1, int(self.config.max_retries))

		limits = httpx.Limits(max_connections=64, max_keepalive_connections=20)
		timeout = httpx.Timeout(self.config.timeout_seconds)
		async with httpx.AsyncClient(timeout=timeout, limits=limits) as client:
			for attempt in range(1, max_retries + 1):
				try:
					self.logger.info(
						"STEP=llm.request | AGENT=DeepSeekClient | ACTION=HTTPPostStart | DETAILS=provider=%s attempt=%s/%s endpoint=%s",
						self.config.provider,
						attempt,
						max_retries,
						self.endpoint,
					)
					if effective_stream:
						data = await self._stream_chat_completion(
							client=client,
							headers=headers,
							payload=payload,
							stream_callback=stream_callback,
						)
					else:
						response = await client.post(
							self.endpoint,
							headers=headers,
							json=payload,
						)
						data = self._handle_http_response(response)
						self.logger.info(
							"STEP=llm.request | AGENT=DeepSeekClient | ACTION=HTTPPostDone | DETAILS=provider=%s attempt=%s status=%s",
							self.config.provider,
							attempt,
							response.status_code,
						)
					self._log_usage(data)
					if effective_stream:
						self.logger.info(
							"STEP=llm.request | AGENT=DeepSeekClient | ACTION=HTTPStreamDone | DETAILS=provider=%s attempt=%s",
							self.config.provider,
							attempt,
						)
					return data
				except (RetryableDeepSeekError, httpx.TimeoutException, httpx.TransportError) as exc:
					if attempt >= max_retries:
						raise RuntimeError(f"{self.config.provider} request failed after {attempt} attempts: {exc}") from exc
					wait_seconds = self.config.backoff_base_seconds * (2 ** (attempt - 1))
					self.logger.warning(
						"%s request failed (attempt %s/%s). Retry in %ss. reason=%s",
						self.config.provider,
						attempt,
						max_retries,
						wait_seconds,
						exc,
					)
					await asyncio.sleep(wait_seconds)

		raise RuntimeError(f"{self.config.provider} request loop ended unexpectedly.")

	@staticmethod
	def _normalize_stream_piece(content: Any) -> str:
		if isinstance(content, str):
			return content

		if isinstance(content, list):
			parts: list[str] = []
			for item in content:
				if isinstance(item, str):
					parts.append(item)
					continue
				if not isinstance(item, Mapping):
					continue
				text = item.get("text")
				if isinstance(text, str):
					parts.append(text)
					continue
				inner = item.get("content")
				if isinstance(inner, str):
					parts.append(inner)
			return "".join(parts)

		return ""

	def _extract_stream_delta(self, chunk: Mapping[str, Any]) -> str:
		choices = chunk.get("choices")
		if not isinstance(choices, list) or not choices:
			return ""

		first = choices[0] if isinstance(choices[0], Mapping) else {}
		delta = first.get("delta") if isinstance(first, Mapping) else {}
		if isinstance(delta, Mapping):
			piece = self._normalize_stream_piece(delta.get("content"))
			if piece:
				return piece

		message = first.get("message") if isinstance(first, Mapping) else {}
		if isinstance(message, Mapping):
			piece = self._normalize_stream_piece(message.get("content"))
			if piece:
				return piece

		return ""

	async def _emit_stream_chunk(self, callback: StreamChunkCallback | None, text: str) -> None:
		if callback is None or not text:
			return
		try:
			result = callback(text)
			if inspect.isawaitable(result):
				await result
		except Exception as exc:  # pylint: disable=broad-except
			self.logger.warning(
				"STEP=llm.request | AGENT=DeepSeekClient | ACTION=StreamCallbackError | DETAILS=provider=%s error=%s",
				self.config.provider,
				exc,
			)

	async def _stream_chat_completion(
		self,
		*,
		client: httpx.AsyncClient,
		headers: Mapping[str, str],
		payload: Mapping[str, Any],
		stream_callback: StreamChunkCallback | None,
	) -> dict[str, Any]:
		self.logger.info(
			"STEP=llm.request | AGENT=DeepSeekClient | ACTION=HTTPStreamStart | DETAILS=provider=%s endpoint=%s",
			self.config.provider,
			self.endpoint,
		)

		full_parts: list[str] = []
		meta: dict[str, Any] = {}
		usage: dict[str, Any] | None = None
		finish_reason = "stop"

		async with client.stream(
			"POST",
			self.endpoint,
			headers=dict(headers),
			json=dict(payload),
		) as response:
			status = response.status_code
			if status == 429 or status >= 500:
				body = await response.aread()
				text = body.decode("utf-8", errors="ignore")
				raise RetryableDeepSeekError(f"HTTP {status}: {text[:400]}")
			if status >= 400:
				body = await response.aread()
				text = body.decode("utf-8", errors="ignore")
				raise RuntimeError(f"{self.config.provider} request rejected with HTTP {status}: {text[:400]}")

			async for raw_line in response.aiter_lines():
				line = str(raw_line).strip()
				if not line or line.startswith(":"):
					continue
				if not line.startswith("data:"):
					continue

				data_line = line[5:].strip()
				if not data_line:
					continue
				if data_line == "[DONE]":
					break

				try:
					chunk = json.loads(data_line)
				except json.JSONDecodeError:
					continue
				if not isinstance(chunk, Mapping):
					continue

				if not meta:
					meta = {
						"id": chunk.get("id", ""),
						"object": chunk.get("object", "chat.completion.chunk"),
						"created": chunk.get("created", int(time.time())),
						"model": chunk.get("model", self.config.model),
					}

				chunk_usage = chunk.get("usage")
				if isinstance(chunk_usage, Mapping):
					usage = dict(chunk_usage)

				choices = chunk.get("choices")
				if isinstance(choices, list) and choices and isinstance(choices[0], Mapping):
					maybe_finish = choices[0].get("finish_reason")
					if isinstance(maybe_finish, str) and maybe_finish.strip():
						finish_reason = maybe_finish.strip()

				piece = self._extract_stream_delta(chunk)
				if piece:
					full_parts.append(piece)
					await self._emit_stream_chunk(stream_callback, piece)

		full_content = "".join(full_parts)
		if not full_content.strip():
			raise RetryableDeepSeekError(f"{self.config.provider} returned empty streamed content.")

		response_json: dict[str, Any] = {
			"id": meta.get("id", ""),
			"object": "chat.completion",
			"created": int(meta.get("created", int(time.time()))),
			"model": str(meta.get("model", self.config.model)),
			"choices": [
				{
					"index": 0,
					"message": {"role": "assistant", "content": full_content},
					"finish_reason": finish_reason,
				}
			],
		}
		if usage:
			response_json["usage"] = usage
		return response_json

	def get_message_content(self, response_json: Mapping[str, Any]) -> str:
		choices = response_json.get("choices")
		if not isinstance(choices, list) or not choices:
			raise RuntimeError(f"Invalid {self.config.provider} response: missing choices.")

		first_choice = choices[0] if isinstance(choices[0], Mapping) else {}
		message = first_choice.get("message", {}) if isinstance(first_choice, Mapping) else {}
		content = message.get("content") if isinstance(message, Mapping) else None

		if isinstance(content, str) and content.strip():
			return content.strip()

		if isinstance(content, list):
			parts: list[str] = []
			for item in content:
				if isinstance(item, str):
					parts.append(item)
					continue
				if not isinstance(item, Mapping):
					continue
				text = item.get("text")
				if isinstance(text, str) and text.strip():
					parts.append(text)
					continue
				inner = item.get("content")
				if isinstance(inner, str) and inner.strip():
					parts.append(inner)
			merged = "".join(parts).strip()
			if merged:
				return merged

		raise RuntimeError(f"Invalid {self.config.provider} response: empty content.")

	def _handle_http_response(self, response: httpx.Response) -> dict[str, Any]:
		status = response.status_code
		if status == 429 or status >= 500:
			raise RetryableDeepSeekError(f"HTTP {status}: {response.text[:400]}")
		if status >= 400:
			raise RuntimeError(f"{self.config.provider} request rejected with HTTP {status}: {response.text[:400]}")

		try:
			loaded = response.json()
		except ValueError as exc:
			raise RetryableDeepSeekError(f"{self.config.provider} returned non-JSON body.") from exc

		if not isinstance(loaded, dict):
			raise RetryableDeepSeekError(f"{self.config.provider} returned unexpected response structure.")
		return loaded

	def _log_usage(self, response_json: Mapping[str, Any]) -> None:
		usage = response_json.get("usage")
		if not isinstance(usage, Mapping):
			return
		self.logger.info(
			"token usage provider=%s prompt=%s completion=%s total=%s",
			self.config.provider,
			usage.get("prompt_tokens"),
			usage.get("completion_tokens"),
			usage.get("total_tokens"),
		)

