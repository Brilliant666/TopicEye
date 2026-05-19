"""
Backward-compat re-export module.

New code should import from app.core.database directly.
This file will be removed after all consumers are migrated.
"""

from app.core.database import *  # noqa: F401,F403
from app.core.database import (  # noqa: F401
    engine,
    Base,
    async_session,
    get_db,
)
