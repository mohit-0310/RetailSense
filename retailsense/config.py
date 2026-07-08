from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env", override=True)
RAW_DATA_DIR = PROJECT_ROOT / "m5-forecasting-accuracy"
DEFAULT_PREPARED_DIR = PROJECT_ROOT / os.getenv("RETAILSENSE_PREPARED_DIR", "prepared")


def _env_flag(name: str, default: str = "0") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    raw_data_dir: Path = RAW_DATA_DIR
    prepared_dir: Path = DEFAULT_PREPARED_DIR
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
    openai_api_key: str | None = os.getenv("OPENAI_API_KEY")
    use_openai_agents: bool = _env_flag("RETAILSENSE_USE_OPENAI_AGENTS", "0")
    agent_timeout_seconds: float = float(os.getenv("RETAILSENSE_AGENT_TIMEOUT_SECONDS", "12"))

    @property
    def agent_mode(self) -> str:
        if self.openai_api_key and self.use_openai_agents:
            return "openai-agents-sdk"
        return "local-fallback"


settings = Settings()
