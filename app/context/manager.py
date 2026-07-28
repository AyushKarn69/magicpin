"""Context manager facade over the versioned context stores."""

from collections.abc import Callable
from typing import Any

from app.context.stores import ContextStore
from app.utils.logging import get_logger

logger = get_logger(__name__)


class ContextManager:
    """Coordinates context storage operations for API and engine layers."""

    def __init__(self, context_store: ContextStore | None = None) -> None:
        self.context_store = context_store or ContextStore()

    def put_context(
        self,
        scope: str,
        context_id: str,
        version: int,
        payload: dict[str, Any],
    ) -> tuple[bool, int | None]:
        """Store a versioned context payload."""
        return self.context_store.put_context(scope, context_id, version, payload)

    def get(self, scope: str, context_id: str) -> Any | None:
        """Look up a context payload by scope and id."""
        return self.context_store.get(scope, context_id)

    def get_context(self, scope: str, context_id: str) -> Any | None:
        """Look up a context payload by scope and id."""
        return self.context_store.get_context(scope, context_id)

    def update_context(
        self,
        scope: str,
        context_id: str,
        updater: Callable[[Any], Any],
    ) -> Any | None:
        """Atomically update one context payload."""
        return self.context_store.update_context(scope, context_id, updater)

    def delete(self, scope: str, context_id: str) -> bool:
        """Delete one context payload."""
        return self.context_store.delete(scope, context_id)

    def delete_context(self, scope: str, context_id: str) -> bool:
        """Delete one context payload."""
        return self.context_store.delete_context(scope, context_id)

    def replace(self, scope: str, context_id: str, version: int, payload: dict[str, Any]) -> None:
        """Atomically replace one context without version checks."""
        self.context_store.replace(scope, context_id, version, payload)

    def replace_context(
        self,
        scope: str,
        context_id: str,
        version: int,
        payload: dict[str, Any],
    ) -> None:
        """Atomically replace one context without version checks."""
        self.context_store.replace_context(scope, context_id, version, payload)

    def atomic_replace(self, scope: str, items: dict[str, tuple[int, dict[str, Any]]]) -> None:
        """Atomically replace all contexts for a scope."""
        self.context_store.atomic_replace(scope, items)

    def atomic_replace_contexts(
        self,
        scope: str,
        items: dict[str, tuple[int, dict[str, Any]]],
    ) -> None:
        """Atomically replace all contexts for a scope."""
        self.context_store.atomic_replace_contexts(scope, items)

    def get_counts(self) -> dict[str, int]:
        """Return context counts by scope."""
        return self.context_store.get_counts()
