"""Model choices and cache location shared by the app and Windows downloader."""
import os
from pathlib import Path

MODELS = ("tiny", "base", "small", "medium", "large-v3", "large-v3-turbo")
ROOT = Path(__file__).resolve().parent.parent


def model_cache(data_root=None):
    return Path(os.environ.get("STT_MODEL_CACHE") or
                Path(data_root or os.environ.get("STT_DATA_DIR") or ROOT / "data") / "models").resolve()
