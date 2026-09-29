"""Тесты не читают рабочие ключи и не меняют состояние установленного сервиса."""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
os.environ["RADAR_LOAD_ENV"] = "0"
os.environ["RADAR_NO_WATCHDOG"] = "1"
os.environ["RADAR_DEMO"] = "0"
for name in ("YANDEX_API_KEY", "YANDEX_FOLDER_ID", "OPENALEX_API_KEY", "RADAR_LLM_API_KEY",
             "RADAR_MODEL", "RADAR_LLM_URL", "RADAR_LLM_REASONING_EFFORT", "RADAR_CACHE_ONLY"):
    os.environ.pop(name, None)
_test_state = tempfile.TemporaryDirectory(prefix="radar-tests-")
os.environ["RADAR_RUNS_DIR"] = _test_state.name
