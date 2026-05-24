"""Adapter packages for :mod:`rath.memory`.

Each adapter module is import-time guarded behind its own optional extra and
registers itself with :mod:`rath.memory.registry`. Importing this barrel does
**not** trigger adapter imports; the public :mod:`rath.memory.__init__`
performs a ``try/except ImportError`` import of known adapters.
"""

from __future__ import annotations
