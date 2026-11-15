"""Runtime configuration (env vars / backend/.env). Never log GEMINI_API_KEY."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
VERSION = "0.1.0"
SOFTWARE = f"ASTRA {VERSION}"
USER_AGENT = f"ASTRA/{VERSION} (NASA Space Apps)"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", extra="ignore")

    gemini_api_key: str = Field(default="", repr=False)
    gemini_model: str = "gemini-flash-latest"
    gemini_fallback_model: str = "gemini-2.5-flash"

    spherex_collections: str = "spherex_dr1,spherex_qr3"
    max_exposures: int = 240
    cutout_concurrency: int = 8
    # "stream": stop reading at the EPSF HDU (fast, no ZODI); "full": download whole cutout (keeps ZODI)
    cutout_mode: Literal["stream", "full"] = "stream"

    cache_dir: Path = BACKEND_DIR / "cache"
    db_path: Path = BACKEND_DIR / "data" / "astra.sqlite3"

    allowed_origins: str = "http://localhost:3000"
    allowed_origin_regex: str = r"https://.*\.vercel\.app"

    simbad_tap_urls: str = (
        "https://simbad.harvard.edu/simbad/sim-tap/sync,"
        "https://simbad.cds.unistra.fr/simbad/sim-tap/sync"
    )
    gaia_tap_url: str = "https://gea.esac.esa.int/tap-server/tap/sync"
    irsa_tap_url: str = "https://irsa.ipac.caltech.edu/TAP/sync"

    @property
    def collections(self) -> list[str]:
        return [c.strip() for c in self.spherex_collections.split(",") if c.strip()]

    @property
    def origins(self) -> list[str]:
        # wildcard entries are handled by allowed_origin_regex
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip() and "*" not in o]

    @property
    def simbad_urls(self) -> list[str]:
        return [u.strip() for u in self.simbad_tap_urls.split(",") if u.strip()]

    @property
    def gemini_enabled(self) -> bool:
        return bool(self.gemini_api_key)


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    if not s.cache_dir.is_absolute():
        s.cache_dir = (BACKEND_DIR / s.cache_dir).resolve()
    if not s.db_path.is_absolute():
        s.db_path = (BACKEND_DIR / s.db_path).resolve()
    s.cache_dir.mkdir(parents=True, exist_ok=True)
    s.db_path.parent.mkdir(parents=True, exist_ok=True)
    return s
