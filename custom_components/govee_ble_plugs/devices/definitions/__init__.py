"""Importing this package registers every device definition as a side effect."""
from __future__ import annotations

from . import lights, plugs  # noqa: F401  (registration happens at import)
