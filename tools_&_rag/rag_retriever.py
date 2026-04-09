from __future__ import annotations

import datetime as dt
import hashlib
import json
import logging
import re
import threading
from pathlib import Path
from typing import Any, Mapping

from config.logger_setup import to_relative_path

try:
	import chromadb
	from chromadb.api.models.Collection import Collection
	from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
except Exception as exc:  # pragma: no cover - import guard for lightweight fallback
	chromadb = None  # type: ignore[assignment]
	Collection = Any  # type: ignore[misc,assignment]
	SentenceTransformerEmbeddingFunction = None  # type: ignore[assignment]
	_CHROMA_IMPORT_ERROR = exc
else:
	_CHROMA_IMPORT_ERROR = None

_RERANKER_IMPORT_ERROR = None
_EMBEDDING_FN_CACHE: dict[str, Any] = {}
_EMBEDDING_FN_CACHE_LOCK = threading.Lock()
_RERANKER_MODEL_CACHE: dict[str, Any] = {}
_RERANKER_MODEL_CACHE_LOCK = threading.Lock()
_VECTOR_STORE_DISABLED_REASON = ""
_VECTOR_STORE_DISABLED_LOCK = threading.Lock()


LOGGER = logging.getLogger("docs_agent.rag_retriever")


def _set_vector_store_disabled(reason: str) -> None:
	reason_text = _safe_text(reason, fallback="unknown_error")[:240]
	global _VECTOR_STORE_DISABLED_REASON  # noqa: PLW0603
	with _VECTOR_STORE_DISABLED_LOCK:
		if not _VECTOR_STORE_DISABLED_REASON:
			_VECTOR_STORE_DISABLED_REASON = reason_text


def _get_vector_store_disabled_reason() -> str:
	with _VECTOR_STORE_DISABLED_LOCK:
		return _VECTOR_STORE_DISABLED_REASON


def _safe_text(value: Any, fallback: str = "") -> str:
	text = str(value).strip() if value is not None else ""
	return text or fallback


def _is_effective_doc_type(value: Any) -> bool:
	doc_type = _safe_text(value)
	if not doc_type:
		return False
	return doc_type not in {"未提及", "未知", "无", "-"}


def _normalize_doc_type(value: Any) -> str:
	doc_type = _safe_text(value)
	if _is_effective_doc_type(doc_type):
		return doc_type
	return "通用公文"


def _tokenize(text: str) -> set[str]:
	raw_tokens = re.findall(r"[A-Za-z0-9_]{2,}|[\u4e00-\u9fff]{2,}", str(text))
	tokens: set[str] = set()
	for token in raw_tokens:
		if re.fullmatch(r"[\u4e00-\u9fff]{2,}", token):
			tokens.add(token)
			for idx in range(len(token) - 1):
				tokens.add(token[idx : idx + 2])
		else:
			tokens.add(token.lower())
	return {item for item in tokens if len(item) >= 2}


def _collect_task_names(tasks: Any) -> list[str]:
	if not isinstance(tasks, list):
		return []
	items: list[str] = []
	for task in tasks:
		if not isinstance(task, Mapping):
			continue
		name = _safe_text(task.get("task_name"))
		if name and name not in items:
			items.append(name)
	return items


def _collect_owners(tasks: Any) -> list[str]:
	if not isinstance(tasks, list):
		return []
	items: list[str] = []
	for task in tasks:
		if not isinstance(task, Mapping):
			continue
		owner = _safe_text(task.get("owner"))
		if owner and owner not in items:
			items.append(owner)
	return items


def _collect_risks(value: Any) -> list[str]:
	if not isinstance(value, list):
		return []
	risks: list[str] = []
	for item in value:
		text = _safe_text(item)
		if text and text not in risks:
			risks.append(text)
	return risks


def _build_query_text(parsed_doc: Mapping[str, Any], reader_output: Mapping[str, Any], query_text_chars: int) -> str:
	doc_id = _safe_text(reader_output.get("doc_id") or parsed_doc.get("doc_id"))
	title = _safe_text(reader_output.get("title"))
	doc_type = _safe_text(reader_output.get("doc_type"))
	summary = _safe_text(reader_output.get("summary"))
	plain_text = _safe_text(parsed_doc.get("plain_text"))[: max(120, query_text_chars)]
	tasks = "；".join(_collect_task_names(reader_output.get("tasks"))[:8])
	return "\n".join(part for part in [doc_id, title, doc_type, summary, tasks, plain_text] if part)


def _build_feature_text(output: Mapping[str, Any]) -> str:
	title = _safe_text(output.get("title"), fallback=_safe_text(output.get("doc_id"), fallback="未命名公文"))
	doc_type = _safe_text(output.get("doc_type"), fallback="未提及")
	summary = _safe_text(output.get("summary"), fallback="未提及")
	task_names = _collect_task_names(output.get("tasks"))
	owners = _collect_owners(output.get("tasks"))
	risks = _collect_risks(output.get("risks_or_unclear_points"))

	task_text = "；".join(task_names[:12]) if task_names else "未提及"
	owner_text = "；".join(owners[:8]) if owners else "未提及"
	risk_text = "；".join(risks[:6]) if risks else "未提及"

	feature_text = (
		f"标题：{title}\n"
		f"类型：{doc_type}\n"
		f"摘要：{summary}\n"
		f"任务列表：{task_text}\n"
		f"责任主体：{owner_text}\n"
		f"风险提示：{risk_text}"
	)
	return feature_text[:4000]


def _build_record_id(doc_id: str) -> str:
	clean = doc_id.strip() or "unknown_doc"
	digest = hashlib.sha1(clean.encode("utf-8")).hexdigest()  # noqa: S324 - non-security id hash
	return f"doc_{digest[:24]}"


def _clamp_similarity(value: float) -> float:
	return max(0.0, min(1.0, value))


def _distance_to_similarity(distance: Any) -> float:
	try:
		distance_value = float(distance)
	except (TypeError, ValueError):
		return 0.0
	# Chroma cosine distance: distance ~= 1 - cosine_similarity
	return _clamp_similarity(1.0 - distance_value)


def _build_context(matches: list[dict[str, Any]]) -> str:
	if not matches:
		return ""

	lines: list[str] = ["以下为检索到的历史相似公文摘要："]
	for idx, item in enumerate(matches, start=1):
		title = _safe_text(item.get("title"), fallback=_safe_text(item.get("doc_id"), fallback=f"历史记录{idx}"))
		doc_type = _safe_text(item.get("doc_type"), fallback="未提及")
		summary = _safe_text(item.get("summary"), fallback="未提及")
		tasks = item.get("task_names", [])
		task_preview = "；".join(str(name).strip() for name in tasks[:3] if str(name).strip()) if isinstance(tasks, list) else ""

		similarity = item.get("similarity")
		similarity_text = f"{float(similarity):.3f}" if isinstance(similarity, (float, int)) else "-"
		risk_preview = _safe_text(item.get("risk_preview"), fallback="未提及")

		lines.append(f"[历史{idx}] 相似度：{similarity_text} | 标题：{title} | 类型：{doc_type}")
		lines.append(f"摘要：{summary}")
		if task_preview:
			lines.append(f"关键任务：{task_preview}")
		if risk_preview and risk_preview != "未提及":
			lines.append(f"风险提示：{risk_preview}")

	text = "\n".join(lines)
	return text[:2400]


class RAGRetriever:
	"""Local semantic retriever based on ChromaDB and local embedding model."""

	def __init__(
		self,
		db_dir: str | Path,
		top_k: int = 3,
		enabled: bool = True,
		rag_settings: Mapping[str, Any] | None = None,
	) -> None:
		self.db_dir = Path(db_dir)
		self.top_k = max(1, int(top_k))
		self.enabled = bool(enabled)
		rag_cfg = rag_settings if isinstance(rag_settings, Mapping) else {}

		self.collection_name = _safe_text(rag_cfg.get("collection_name"), fallback="docs_agent_archive")
		self.embedding_model = _safe_text(rag_cfg.get("embedding_model"), fallback="BAAI/bge-small-zh")
		self.reranker_model_name = _safe_text(rag_cfg.get("reranker_model"), fallback="BAAI/bge-reranker-base")
		self.rerank_enabled = bool(rag_cfg.get("rerank_enabled", True))
		self.prewarm_reranker_enabled = bool(rag_cfg.get("prewarm_reranker", True))
		self.rerank_candidates = max(self.top_k, int(rag_cfg.get("rerank_candidates", 15)))
		self.rerank_score_threshold = float(rag_cfg.get("rerank_score_threshold", 0.5))
		self.fallback_enabled = bool(rag_cfg.get("fallback_enabled", True))
		self.similarity_threshold = _clamp_similarity(float(rag_cfg.get("similarity_threshold", 0.75)))
		self.query_text_chars = max(120, int(rag_cfg.get("query_text_chars", 1000)))
		self.metadata_json_max_chars = max(0, int(rag_cfg.get("metadata_json_max_chars", 0)))

		dynamic_cfg = rag_cfg.get("dynamic_threshold", {}) if isinstance(rag_cfg.get("dynamic_threshold"), Mapping) else {}
		self.dynamic_enabled = bool(dynamic_cfg.get("enabled", True))
		self.dynamic_short_query_chars = max(50, int(dynamic_cfg.get("short_query_chars", 320)))
		self.dynamic_long_query_chars = max(self.dynamic_short_query_chars + 1, int(dynamic_cfg.get("long_query_chars", 1200)))
		self.dynamic_short_query_bonus = max(0.0, float(dynamic_cfg.get("short_query_bonus", 0.05)))
		self.dynamic_long_query_penalty = max(0.0, float(dynamic_cfg.get("long_query_penalty", 0.03)))
		self.dynamic_min = _clamp_similarity(float(dynamic_cfg.get("min", 0.70)))
		self.dynamic_max = _clamp_similarity(float(dynamic_cfg.get("max", 0.90)))
		if self.dynamic_min > self.dynamic_max:
			self.dynamic_min, self.dynamic_max = self.dynamic_max, self.dynamic_min

		self.persist_dir = self.db_dir / "chroma"
		self.fallback_archive_file = self.db_dir / "archive_db.jsonl"
		self.collection: Collection | None = None
		self.reranker_model: Any | None = None
		self._reranker_lock = threading.Lock()
		self._reranker_init_attempted = False
		self.ready = False
		self.vector_available = False

		self._init_vector_store()

	def _init_vector_store(self) -> None:
		if not self.enabled:
			LOGGER.info("RAG向量检索未启用。")
			return

		disabled_reason = _get_vector_store_disabled_reason()
		if disabled_reason:
			self.ready = False
			self.vector_available = False
			self.enabled = bool(self.fallback_enabled)
			LOGGER.warning(
				"RAG向量检索已在当前进程禁用，直接使用本地回退检索。reason=%s",
				disabled_reason,
			)
			return

		if chromadb is None or SentenceTransformerEmbeddingFunction is None:
			if self.fallback_enabled:
				LOGGER.warning(
					"RAG向量检索不可用: 缺少 chromadb/sentence-transformers 依赖。已切换本地回退检索模式。error=%s",
					_CHROMA_IMPORT_ERROR,
				)
				self.ready = False
				self.vector_available = False
				self.enabled = True
			else:
				LOGGER.warning(
					"RAG向量检索不可用且回退模式关闭。error=%s",
					_CHROMA_IMPORT_ERROR,
				)
				self.enabled = False
			return

		try:
			self.persist_dir.mkdir(parents=True, exist_ok=True)
			embedding_fn = _EMBEDDING_FN_CACHE.get(self.embedding_model)
			if embedding_fn is None:
				with _EMBEDDING_FN_CACHE_LOCK:
					embedding_fn = _EMBEDDING_FN_CACHE.get(self.embedding_model)
					if embedding_fn is None:
						embedding_fn = SentenceTransformerEmbeddingFunction(model_name=self.embedding_model)
						_EMBEDDING_FN_CACHE[self.embedding_model] = embedding_fn
						LOGGER.info("RAG Embedding模型已缓存: model=%s", self.embedding_model)
					else:
						LOGGER.info("RAG Embedding模型复用缓存: model=%s", self.embedding_model)
			else:
				LOGGER.info("RAG Embedding模型复用缓存: model=%s", self.embedding_model)
			client = chromadb.PersistentClient(path=str(self.persist_dir))
			self.collection = client.get_or_create_collection(
				name=self.collection_name,
				embedding_function=embedding_fn,
				metadata={"hnsw:space": "cosine"},
			)
			self.ready = True
			self.vector_available = True
			if self.rerank_enabled:
				LOGGER.info("RAG重排模型将按需加载: model=%s", self.reranker_model_name)
			LOGGER.info(
				"RAG向量引擎就绪: collection=%s model=%s db=%s",
				self.collection_name,
				self.embedding_model,
				to_relative_path(self.persist_dir),
			)
		except Exception as exc:  # pylint: disable=broad-except
			err_text = _safe_text(exc, fallback=exc.__class__.__name__)
			_set_vector_store_disabled(err_text)
			self.collection = None
			self.ready = False
			self.vector_available = False
			if self.fallback_enabled:
				LOGGER.warning(
					"RAG向量引擎初始化失败，已切换本地回退检索模式并禁用本进程向量检索。error=%s",
					err_text,
				)
				self.enabled = True
			else:
				self.enabled = False

	def _ensure_reranker_loaded(self) -> None:
		global _RERANKER_IMPORT_ERROR  # noqa: PLW0603

		if not self.rerank_enabled:
			return
		if self.reranker_model is not None:
			return

		cached_model = _RERANKER_MODEL_CACHE.get(self.reranker_model_name)
		if cached_model is not None:
			self.reranker_model = cached_model
			self._reranker_init_attempted = True
			LOGGER.info("RAG重排模型复用缓存: model=%s", self.reranker_model_name)
			return
		if self._reranker_init_attempted:
			return

		with self._reranker_lock:
			if self.reranker_model is not None or self._reranker_init_attempted:
				return
			self._reranker_init_attempted = True

			try:
				from sentence_transformers import CrossEncoder as _CrossEncoder
			except Exception as exc:  # pylint: disable=broad-except
				_RERANKER_IMPORT_ERROR = exc
				LOGGER.warning("RAG重排模型不可用: sentence-transformers 导入失败，已回退向量排序。error=%s", exc)
				return

			try:
				with _RERANKER_MODEL_CACHE_LOCK:
					cached_again = _RERANKER_MODEL_CACHE.get(self.reranker_model_name)
					if cached_again is not None:
						self.reranker_model = cached_again
						LOGGER.info("RAG重排模型复用缓存: model=%s", self.reranker_model_name)
					else:
						self.reranker_model = _CrossEncoder(self.reranker_model_name)
						_RERANKER_MODEL_CACHE[self.reranker_model_name] = self.reranker_model
						LOGGER.info("RAG重排模型就绪: model=%s", self.reranker_model_name)
			except Exception as exc:  # pylint: disable=broad-except
				self.reranker_model = None
				LOGGER.warning("RAG重排模型初始化失败，回退向量排序: %s", exc)

	def prewarm_reranker(self) -> bool:
		"""Warm up reranker in advance to hide first-hit latency during retrieve()."""
		if not self.enabled or not self.ready or not self.rerank_enabled:
			return False
		if not self.prewarm_reranker_enabled:
			return False
		self._ensure_reranker_loaded()
		return self.reranker_model is not None

	def _resolve_similarity_threshold(self, query_text: str) -> float:
		threshold = self.similarity_threshold
		if self.dynamic_enabled:
			query_len = len(query_text)
			if query_len <= self.dynamic_short_query_chars:
				threshold += self.dynamic_short_query_bonus
			elif query_len >= self.dynamic_long_query_chars:
				threshold -= self.dynamic_long_query_penalty
			threshold = max(self.dynamic_min, min(self.dynamic_max, threshold))
		return _clamp_similarity(threshold)

	def _build_output_json_text(self, output: Mapping[str, Any]) -> str:
		payload = json.dumps(output, ensure_ascii=False, separators=(",", ":"))
		if self.metadata_json_max_chars > 0 and len(payload) > self.metadata_json_max_chars:
			return payload[: self.metadata_json_max_chars]
		return payload

	def _load_fallback_records(self) -> list[dict[str, Any]]:
		if not self.fallback_archive_file.exists():
			return []
		records: list[dict[str, Any]] = []
		for line in self.fallback_archive_file.read_text(encoding="utf-8").splitlines():
			text = line.strip()
			if not text:
				continue
			try:
				payload = json.loads(text)
			except json.JSONDecodeError:
				continue
			if isinstance(payload, dict):
				records.append(payload)
		return records

	def _retrieve_fallback(self, query_text: str, query_doc_type: str, threshold: float) -> tuple[str, int]:
		records = self._load_fallback_records()
		if not records:
			LOGGER.info("RAG回退检索完成: 命中=0 db=%s", to_relative_path(self.fallback_archive_file))
			return "", 0

		query_tokens = _tokenize(query_text)
		if not query_tokens:
			LOGGER.info("RAG回退检索完成: 查询Token为空，命中=0")
			return "", 0

		scored: list[tuple[float, dict[str, Any]]] = []
		for record in records:
			record_tokens = set()
			keywords = record.get("keywords")
			if isinstance(keywords, list):
				record_tokens = {str(item).strip().lower() for item in keywords if str(item).strip()}
			if not record_tokens:
				record_text = "\n".join(
					[
						_safe_text(record.get("title")),
						_safe_text(record.get("summary")),
						"；".join(str(item).strip() for item in record.get("task_names", []) if str(item).strip())
						if isinstance(record.get("task_names"), list)
						else "",
					]
				)
				record_tokens = _tokenize(record_text)

			overlap = len(query_tokens & record_tokens)
			if overlap <= 0:
				continue

			base = overlap / max(len(query_tokens), 1)
			record_doc_type = _safe_text(record.get("doc_type"))
			if query_doc_type and record_doc_type and query_doc_type == record_doc_type:
				base += 0.08
			similarity = _clamp_similarity(base)
			if similarity < threshold:
				continue

			match = {
				"doc_id": _safe_text(record.get("doc_id")),
				"title": _safe_text(record.get("title")),
				"doc_type": record_doc_type,
				"summary": _safe_text(record.get("summary")),
				"task_names": record.get("task_names", []) if isinstance(record.get("task_names"), list) else [],
				"risk_preview": _safe_text(record.get("risk_preview"), fallback="未提及"),
				"similarity": similarity,
			}
			scored.append((similarity, match))

		scored.sort(key=lambda item: item[0], reverse=True)
		top_matches = [item[1] for item in scored[: self.top_k]]
		LOGGER.info(
			"RAG回退检索完成: 命中=%s threshold=%.3f db=%s",
			len(top_matches),
			threshold,
			to_relative_path(self.fallback_archive_file),
		)
		return _build_context(top_matches), len(top_matches)

	def _archive_fallback(self, output: Mapping[str, Any]) -> bool:
		doc_id = _safe_text(output.get("doc_id"))
		if not doc_id:
			return False

		records = self._load_fallback_records()
		existing_ids = {_safe_text(item.get("doc_id")) for item in records}
		if doc_id in existing_ids:
			return False

		tasks = output.get("tasks", [])
		task_names = _collect_task_names(tasks)
		owners = _collect_owners(tasks)
		risks = _collect_risks(output.get("risks_or_unclear_points"))

		record = {
			"doc_id": doc_id,
			"title": _safe_text(output.get("title"), fallback=doc_id),
			"doc_type": _normalize_doc_type(output.get("doc_type")),
			"summary": _safe_text(output.get("summary"), fallback="未提及"),
			"task_names": task_names,
			"owners": owners,
			"risk_preview": "；".join(risks[:6]) if risks else "未提及",
			"keywords": sorted(
				_tokenize(
					"\n".join(
						[
							_safe_text(output.get("title")),
							_safe_text(output.get("summary")),
							"；".join(task_names[:10]),
							"；".join(owners[:10]),
							"；".join(risks[:6]),
						]
					)
				)
			)[:200],
			"archived_at": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
		}

		self.db_dir.mkdir(parents=True, exist_ok=True)
		with self.fallback_archive_file.open("a", encoding="utf-8") as file:
			file.write(json.dumps(record, ensure_ascii=False) + "\n")
		return True

	def retrieve(self, parsed_doc: Mapping[str, Any], reader_output: Mapping[str, Any]) -> tuple[str, int]:
		if not self.enabled:
			return "", 0

		query_text = _build_query_text(
			parsed_doc=parsed_doc,
			reader_output=reader_output,
			query_text_chars=self.query_text_chars,
		)
		if not query_text:
			LOGGER.info("RAG检索完成: 查询文本为空，跳过。")
			return "", 0

		effective_threshold = self._resolve_similarity_threshold(query_text)
		current_doc_type = _safe_text(reader_output.get("doc_type"))
		query_doc_type = current_doc_type if _is_effective_doc_type(current_doc_type) else ""

		if not self.ready or self.collection is None:
			if self.fallback_enabled:
				return self._retrieve_fallback(query_text=query_text, query_doc_type=query_doc_type, threshold=effective_threshold)
			return "", 0

		try:
			query_kwargs: dict[str, Any] = {
				"query_texts": [query_text],
				"n_results": max(self.rerank_candidates, self.top_k),
				"include": ["metadatas", "distances", "documents"],
			}
			if query_doc_type:
				query_kwargs["where"] = {"doc_type": query_doc_type}
			query_result = self.collection.query(**query_kwargs)
		except Exception as exc:  # pylint: disable=broad-except
			LOGGER.exception("RAG检索失败: %s", exc)
			return "", 0

		meta_groups = query_result.get("metadatas") or [[]]
		distance_groups = query_result.get("distances") or [[]]
		doc_groups = query_result.get("documents") or [[]]

		metadatas = meta_groups[0] if isinstance(meta_groups, list) and meta_groups else []
		distances = distance_groups[0] if isinstance(distance_groups, list) and distance_groups else []
		documents = doc_groups[0] if isinstance(doc_groups, list) and doc_groups else []

		candidate_matches: list[dict[str, Any]] = []
		for idx, metadata in enumerate(metadatas):
			if not isinstance(metadata, Mapping):
				continue
			vector_similarity = _distance_to_similarity(distances[idx] if idx < len(distances) else None)
			record_doc_type = _safe_text(metadata.get("doc_type"))
			adaptive_threshold = effective_threshold
			if query_doc_type and record_doc_type and query_doc_type != record_doc_type:
				adaptive_threshold = _clamp_similarity(effective_threshold + 0.03)
			coarse_threshold = _clamp_similarity(adaptive_threshold - 0.25)
			if vector_similarity < coarse_threshold:
				continue

			feature_text = _safe_text(documents[idx]) if idx < len(documents) else ""
			if not feature_text:
				feature_text = "\n".join(
					[
						_safe_text(metadata.get("title")),
						_safe_text(metadata.get("summary")),
						_safe_text(metadata.get("task_preview")),
					]
				)

			task_preview = _safe_text(metadata.get("task_preview"), fallback="")
			match = {
				"doc_id": _safe_text(metadata.get("doc_id")),
				"title": _safe_text(metadata.get("title")),
				"doc_type": record_doc_type,
				"summary": _safe_text(metadata.get("summary")),
				"task_names": [item for item in task_preview.split("；") if item],
				"risk_preview": _safe_text(metadata.get("risk_preview"), fallback="未提及"),
				"vector_similarity": vector_similarity,
				"similarity": vector_similarity,
				"feature_text": feature_text,
			}
			candidate_matches.append(match)

		ranked_matches: list[dict[str, Any]] = []
		query_feature_text = _build_feature_text(reader_output)
		if not query_feature_text:
			query_feature_text = query_text
		should_vector_fallback = True

		if self.rerank_enabled and candidate_matches and self.reranker_model is None:
			self._ensure_reranker_loaded()

		if self.rerank_enabled and self.reranker_model is not None and candidate_matches:
			should_vector_fallback = False
			pairs = [(query_feature_text, _safe_text(item.get("feature_text"))) for item in candidate_matches]
			try:
				rerank_scores_raw = self.reranker_model.predict(pairs)
				if hasattr(rerank_scores_raw, "tolist"):
					rerank_scores = rerank_scores_raw.tolist()
				elif isinstance(rerank_scores_raw, (list, tuple)):
					rerank_scores = list(rerank_scores_raw)
				else:
					rerank_scores = [rerank_scores_raw]

				reranked_with_scores: list[dict[str, Any]] = []
				for item, score in zip(candidate_matches, rerank_scores):
					scored_item = dict(item)
					try:
						rerank_score = float(score)
					except (TypeError, ValueError):
						continue
					scored_item["rerank_score"] = rerank_score
					scored_item["similarity"] = rerank_score
					reranked_with_scores.append(scored_item)

				reranked_with_scores.sort(key=lambda item: float(item.get("rerank_score", -1e9)), reverse=True)
				ranked_matches = [
					item for item in reranked_with_scores if float(item.get("rerank_score", -1e9)) >= self.rerank_score_threshold
				]
				LOGGER.info(
					"RAG精排完成: 粗筛=%s 保留=%s 阈值=%.3f",
					len(candidate_matches),
					len(ranked_matches),
					self.rerank_score_threshold,
				)
			except Exception as exc:  # pylint: disable=broad-except
				should_vector_fallback = True
				LOGGER.warning("RAG精排失败，回退向量排序: %s", exc)

		if not ranked_matches and should_vector_fallback:
			ranked_matches = [
				item for item in candidate_matches if float(item.get("vector_similarity", 0.0)) >= effective_threshold
			]
			ranked_matches.sort(key=lambda item: float(item.get("vector_similarity", 0.0)), reverse=True)

		top_matches = ranked_matches[: self.top_k]

		LOGGER.info(
			"RAG检索完成: 命中=%s threshold=%.3f db=%s",
			len(top_matches),
			effective_threshold,
			to_relative_path(self.persist_dir),
		)
		return _build_context(top_matches), len(top_matches)

	def archive(self, output: Mapping[str, Any]) -> bool:
		if not self.enabled:
			return False

		doc_id = _safe_text(output.get("doc_id"))
		if not doc_id:
			return False

		vector_saved = False
		fallback_saved = False
		if self.fallback_enabled:
			fallback_saved = self._archive_fallback(output)
			if fallback_saved:
				LOGGER.info("RAG回退归档完成: doc_id=%s -> %s", doc_id, to_relative_path(self.fallback_archive_file))

		if not self.ready or self.collection is None:
			return fallback_saved

		record_id = _build_record_id(doc_id)
		try:
			existing = self.collection.get(ids=[record_id], include=["metadatas"])
			if existing.get("ids"):
				LOGGER.info("RAG归档跳过: doc_id=%s 已存在（向量库）。", doc_id)
				return fallback_saved
		except Exception as exc:  # pylint: disable=broad-except
			LOGGER.warning("RAG归档预检查失败，继续写入: doc_id=%s error=%s", doc_id, exc)

		tasks = output.get("tasks", [])
		task_names = _collect_task_names(tasks)
		risks = _collect_risks(output.get("risks_or_unclear_points"))
		feature_text = _build_feature_text(output)
		output_json = self._build_output_json_text(output)

		metadata = {
			"doc_id": doc_id,
			"title": _safe_text(output.get("title"), fallback=doc_id),
			"doc_type": _normalize_doc_type(output.get("doc_type")),
			"summary": _safe_text(output.get("summary"), fallback="未提及"),
			"task_preview": "；".join(task_names[:8]) if task_names else "未提及",
			"risk_preview": "；".join(risks[:6]) if risks else "未提及",
			"output_json": output_json,
			"archived_at": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
		}

		try:
			self.collection.add(
				ids=[record_id],
				documents=[feature_text],
				metadatas=[metadata],
			)
			vector_saved = True
		except Exception as exc:  # pylint: disable=broad-except
			LOGGER.exception("RAG归档失败: doc_id=%s error=%s", doc_id, exc)
			return fallback_saved

		LOGGER.info("RAG归档完成: doc_id=%s -> %s/%s", doc_id, to_relative_path(self.persist_dir), self.collection_name)
		return vector_saved or fallback_saved
