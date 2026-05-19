"""
Backward-compat re-export module.

New code should import from app.core.config directly.
This file will be removed after all consumers are migrated.
"""

from app.core.config import *  # noqa: F401,F403
from app.core.config import Settings, settings  # noqa: F401
