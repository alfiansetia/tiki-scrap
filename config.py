import os
from dotenv import load_dotenv

load_dotenv()


def _to_bool(value: str) -> bool:
    return value.lower() in ("true", "1", "yes")


class BaseSettings:
    """Konfigurasi utama aplikasi, dibaca dari file .env"""

    # Debug
    DEBUG: bool = _to_bool(os.getenv("DEBUG", "false"))
    DEBUG_DIR: str = os.path.join(os.path.dirname(__file__), "debug")

    # Browser
    HEADLESS: bool = _to_bool(os.getenv("HEADLESS", "true"))

    # Security
    API_KEY: str = os.getenv("API_KEY", "")

    # Server
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8001"))

    # Tiki URL
    TIKI_TRACK_URL: str = "https://www.tiki.id/id/track"

    # Timeout (detik)
    PAGE_TIMEOUT: int = 60000  # ms
    ELEMENT_TIMEOUT: int = 15000  # ms
    POLLING_TIMEOUT: int = 15  # detik
    RENDER_WAIT: int = 5000  # ms — waktu tunggu JS framework render


settings = BaseSettings()
