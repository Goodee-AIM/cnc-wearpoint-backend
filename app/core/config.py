import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def get_cors_origins() -> list[str]:
    return [
        origin.strip()
        for origin in os.getenv("CORS_ORIGINS", "").split(",")
        if origin.strip()
    ]

def get_local_storage_root() -> Path:
    return Path(
        os.getenv("LOCAL_STORAGE_ROOT", "./storage")
    )