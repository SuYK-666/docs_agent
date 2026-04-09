from __future__ import annotations

import datetime as dt
import logging
import logging.config
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class LogSession:
	run_id: str
	started_at: str
	log_file: Path


_ACTIVE_SESSION: LogSession | None = None
PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _load_logging_config(config_file: Path) -> dict[str, Any]:
	if not config_file.exists():
		return {}
	try:
		loaded = yaml.safe_load(config_file.read_text(encoding="utf-8")) or {}
		return loaded if isinstance(loaded, dict) else {}
	except Exception:  # pylint: disable=broad-except
		return {}


def _build_default_dict_config(
	console_level: str,
	file_level: str,
	log_file: Path,
	log_format: str,
	date_format: str,
) -> dict[str, Any]:
	return {
		"version": 1,
		"disable_existing_loggers": False,
		"formatters": {
			"standard": {
				"format": log_format,
				"datefmt": date_format,
			}
		},
		"handlers": {
			"console": {
				"class": "logging.StreamHandler",
				"level": console_level,
				"formatter": "standard",
				"stream": "ext://sys.stderr",
			},
			"file": {
				"class": "logging.FileHandler",
				"level": file_level,
				"formatter": "standard",
				"filename": str(log_file),
				"encoding": "utf-8",
			},
		},
		"loggers": {
			"docs_agent": {
				"level": "DEBUG",
				"handlers": ["console", "file"],
				"propagate": False,
			}
		},
	}


def _resolve_log_file(log_dir: Path, log_file: str | None, run_id: str) -> Path:
	if log_file:
		path = Path(log_file)
		if path.suffix.lower() == ".log" and path.name.startswith("log_"):
			return path
	return log_dir / f"log_{run_id}.log"


def to_relative_path(path_value: str | Path | None, base_dir: Path | None = None) -> str:
	"""Convert path to a workspace-relative string for logs and payload metadata."""
	if path_value is None:
		return ""

	text = str(path_value).strip()
	if not text:
		return ""

	path = Path(text)
	base = base_dir or PROJECT_ROOT

	if not path.is_absolute():
		return path.as_posix()

	try:
		return path.relative_to(base).as_posix()
	except ValueError:
		try:
			return Path(os.path.relpath(str(path), str(base))).as_posix()
		except ValueError:
			return path.name or path.as_posix()


def setup_logger(
	log_level: str = "INFO",
	log_file: str | None = None,
	log_dir: str = "log",
	config_file: str = "log/logging.yaml",
	force_reconfigure: bool = False,
) -> logging.Logger:
	"""Configure and return the shared project logger with per-run log file."""
	global _ACTIVE_SESSION

	logger = logging.getLogger("docs_agent")
	if logger.handlers and not force_reconfigure:
		return logger

	if force_reconfigure:
		for handler in logger.handlers[:]:
			logger.removeHandler(handler)
			handler.close()

	now = dt.datetime.now()
	run_id = now.strftime("%Y%m%d_%H%M%S")
	log_dir_path = Path(log_dir)
	log_dir_path.mkdir(parents=True, exist_ok=True)
	resolved_log_file = _resolve_log_file(log_dir_path, log_file, run_id)
	resolved_log_file.parent.mkdir(parents=True, exist_ok=True)

	config_path = Path(config_file)
	config_data = _load_logging_config(config_path)
	logging_cfg = config_data.get("logging", {}) if isinstance(config_data.get("logging"), dict) else {}

	console_level = str(logging_cfg.get("console_level", log_level)).upper()
	file_level = str(logging_cfg.get("file_level", "DEBUG")).upper()
	log_format = str(
		logging_cfg.get(
			"format",
			"%(asctime)s | %(levelname)s | %(name)s | %(message)s",
		)
	)
	date_format = str(logging_cfg.get("datefmt", "%Y-%m-%d %H:%M:%S"))

	dict_config = _build_default_dict_config(
		console_level=console_level,
		file_level=file_level,
		log_file=resolved_log_file,
		log_format=log_format,
		date_format=date_format,
	)
	logging.config.dictConfig(dict_config)

	logger = logging.getLogger("docs_agent")
	log_file_for_message = to_relative_path(resolved_log_file)
	logger.info(
		"RUN_START | run_id=%s | started_at=%s | log_file=%s",
		run_id,
		now.strftime("%Y-%m-%d %H:%M:%S"),
		log_file_for_message,
	)

	_ACTIVE_SESSION = LogSession(
		run_id=run_id,
		started_at=now.strftime("%Y-%m-%d %H:%M:%S"),
		log_file=Path(log_file_for_message),
	)

	return logger


def get_log_session() -> LogSession | None:
	"""Return active logging session metadata if initialized."""
	return _ACTIVE_SESSION


def log_step(
	logger: logging.Logger,
	step: str,
	agent: str,
	action: str,
	details: str = "",
) -> None:
	"""Unified step log format for detailed decision tracing."""
	message = f"STEP={step} | AGENT={agent} | ACTION={action}"
	if details.strip():
		message = f"{message} | DETAILS={details.strip()}"
	logger.info(message)

def get_logger(name: str) -> logging.Logger:
	"""Return child logger under docs_agent namespace."""
	return logging.getLogger(f"docs_agent.{name}")

