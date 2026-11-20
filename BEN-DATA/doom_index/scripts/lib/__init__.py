"""Shared helpers for the Doom Index collection scripts.

Importing this package puts the project root on ``sys.path`` so that
``from config import settings`` works no matter where a script is launched.
"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
