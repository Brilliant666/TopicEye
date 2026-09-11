"""Rardar product scope; retained modules remain readable, not executable."""

from app.core.product_profile import is_rardar_product

PAUSED_MODULES = frozenset({"news", "discover", "candidates", "watchlist"})


class RardarModulePaused(ValueError):
    def __init__(self, module: str):
        self.code = f"rardar_{module}_paused"
        super().__init__(self.code)


def require_module_execution(module: str) -> None:
    """Do not alter standalone TopicEye or delete retained Rardar records."""
    if is_rardar_product() and module in PAUSED_MODULES:
        raise RardarModulePaused(module)
