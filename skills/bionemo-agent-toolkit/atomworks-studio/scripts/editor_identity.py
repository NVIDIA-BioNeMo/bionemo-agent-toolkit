"""Identify the editor session store without exposing its filesystem path."""
import hashlib
from pathlib import Path


def store_identity(path):
    return hashlib.sha256(str(Path(path).resolve()).encode()).hexdigest()
