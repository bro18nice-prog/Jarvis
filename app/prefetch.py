"""Descarca modelul Whisper o data, la instalare, ca prima pornire sa fie rapida."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "app"))
os.environ.setdefault("HF_HOME", os.path.join(ROOT, "models", "hf"))

from ears import Ears  # noqa: E402

e = Ears(os.path.join(ROOT, "models"), lang="ro")
print("Whisper pregatit:", e.device_info)