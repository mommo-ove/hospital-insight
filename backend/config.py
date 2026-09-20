from dataclasses import dataclass
from datetime import date
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Settings:
    database_path: Path
    llm_mode: str = "demo"
    llm_base_url: str = ""
    llm_model: str = ""
    llm_api_key: str = ""
    llm_timeout: float = 30
    seed_excel: Path | None = None
    today: date | None = None

    @classmethod
    def from_env(cls):
        load_dotenv(ROOT / ".env", override=False)
        db = Path(os.getenv("DATABASE_PATH", "data/hospital.db"))
        seed = os.getenv("SEED_EXCEL", "院管数据.xlsx")
        seed_path = None if seed.lower() == "none" else Path(seed)
        mode = os.getenv("LLM_MODE", "demo").lower()
        if mode not in {"demo", "cloud"}:
            raise ValueError("LLM_MODE 必须为 demo 或 cloud")
        return cls(
            database_path=db if db.is_absolute() else ROOT / db,
            llm_mode=mode,
            llm_base_url=os.getenv("LLM_BASE_URL", "").rstrip("/"),
            llm_model=os.getenv("LLM_MODEL", ""),
            llm_api_key=os.getenv("LLM_API_KEY", ""),
            llm_timeout=float(os.getenv("LLM_TIMEOUT_SECONDS", "30")),
            seed_excel=(seed_path if seed_path is None or seed_path.is_absolute() else ROOT / seed_path),
        )

