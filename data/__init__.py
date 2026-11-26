"""Persistence seam.

Games are JSON files today.  Adaptive drills / SQLite can be added behind the
same small interface without touching the server or the coach.
"""
from __future__ import annotations

from .store import JsonStore, default_store

__all__ = ["JsonStore", "default_store"]
