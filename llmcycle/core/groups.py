"""
Group Manager
=============
Provides dynamic runtime management for logical model groups.
"""
from typing import Dict, List, Optional
import threading
import logging

logger = logging.getLogger(__name__)

class GroupManager:
    """Thread-safe manager for routing groups/aliases."""

    def __init__(self, initial_groups: Optional[Dict[str, List[str]]] = None):
        self._lock = threading.Lock()
        self._groups: Dict[str, List[str]] = {}
        if initial_groups:
            for k, v in initial_groups.items():
                self._groups[k] = list(v)

    def set(self, name: str, models: List[str]) -> None:
        """Create or update a group with a list of fallback models."""
        with self._lock:
            self._groups[name] = list(models)
            logger.info(f"Group '{name}' set with {len(models)} models: {models}")

    def remove(self, name: str) -> bool:
        """Delete a group by name. Returns True if removed, False if not found."""
        with self._lock:
            if name in self._groups:
                del self._groups[name]
                logger.info(f"Group '{name}' removed")
                return True
            return False

    def remove_provider(self, provider: str) -> None:
        """Prune any models associated with provider from all groups."""
        p_lower = provider.lower()
        with self._lock:
            for k, models in list(self._groups.items()):
                self._groups[k] = [
                    m for m in models
                    if m.lower() != p_lower and not m.lower().startswith(f"{p_lower}/")
                ]
            logger.info(f"Pruned provider [{p_lower}] from all groups")

    def get(self, name: str) -> Optional[List[str]]:
        """Retrieve the models for a group, or None if the group doesn't exist."""
        with self._lock:
            if name in self._groups:
                return list(self._groups[name])
            return None

    def list_all(self) -> Dict[str, List[str]]:
        """Returns a snapshot of all groups."""
        with self._lock:
            return {k: list(v) for k, v in self._groups.items()}

    def __contains__(self, name: str) -> bool:
        with self._lock:
            return name in self._groups

    async def load(self) -> None:
        """Load groups from storage if configured."""
        if hasattr(self, "storage") and self.storage:
            config = await self.storage.get_config("groups")
            if config and config.value:
                with self._lock:
                    self._groups.clear()
                    for k, v in config.value.items():
                        self._groups[k] = list(v)
                logger.info(f"Loaded {len(self._groups)} groups from storage.")

    async def save(self) -> None:
        """Save current groups to storage if configured."""
        if hasattr(self, "storage") and self.storage:
            with self._lock:
                val = {k: list(v) for k, v in self._groups.items()}
            await self.storage.save_config("groups", val)
            logger.info("Saved groups to storage.")

    async def set_async(self, name: str, models: List[str]) -> None:
        """Set a group and immediately save to storage."""
        self.set(name, models)
        await self.save()

    async def remove_async(self, name: str) -> bool:
        """Remove a group and immediately save to storage."""
        removed = self.remove(name)
        if removed:
            await self.save()
        return removed
