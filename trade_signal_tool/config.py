import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


DEFAULT_SPOT_ENV_PATH = Path(__file__).resolve().parents[2] / "spot-trade-bot" / ".env"


@dataclass(frozen=True)
class Settings:
    telegram_bot_token: Optional[str] = None
    telegram_chat_id: Optional[str] = None

    @classmethod
    def from_env(cls, spot_env_path: Optional[Path] = None) -> "Settings":
        load_dotenv(spot_env_path or DEFAULT_SPOT_ENV_PATH)
        return cls(
            telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN"),
            telegram_chat_id=os.getenv("TELEGRAM_CHAT_ID"),
        )


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))
