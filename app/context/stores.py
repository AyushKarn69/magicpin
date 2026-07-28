"""Context storage implementation with versioning and thread safety."""

import copy
import threading
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, Generic, TypeVar

from app.models.contexts import (
    CategoryContext,
    CustomerContext,
    MerchantContext,
    TriggerContext,
)
from app.utils.logging import get_logger

T = TypeVar("T")
logger = get_logger(__name__)


class VersionedContext(Generic[T]):
    """Wrapper for a context with version tracking."""

    def __init__(self, context_id: str, version: int, payload: T) -> None:
        self.context_id = context_id
        self.version = version
        self.payload = payload
        self.stored_at = datetime.now(UTC)


class BaseStore(Generic[T]):
    """Thread-safe base store with versioning."""

    def __init__(self) -> None:
        self._store: dict[str, VersionedContext[T]] = {}
        self._lock = threading.RLock()

    def put(self, context_id: str, version: int, payload: T) -> tuple[bool, int | None]:
        """
        Store a context with version control.
        
        Returns:
            (success, current_version if rejected)
        """
        with self._lock:
            existing = self._store.get(context_id)

            if existing and existing.version > version:
                logger.debug(
                    "context_version_rejected",
                    context_id=context_id,
                    existing_version=existing.version,
                    requested_version=version,
                )
                return False, existing.version

            if existing and existing.version == version:
                logger.info(
                    "context_version_idempotent",
                    context_id=context_id,
                    version=version,
                )
                return True, None

            self._store[context_id] = VersionedContext(
                context_id, version, copy.deepcopy(payload)
            )
            logger.info(
                "context_stored",
                context_id=context_id,
                version=version,
                stored_at=self._store[context_id].stored_at.isoformat(),
            )
            return True, None

    def get(self, context_id: str) -> T | None:
        """Get the latest version of a context."""
        with self._lock:
            versioned = self._store.get(context_id)
            return copy.deepcopy(versioned.payload) if versioned else None

    def update(
        self,
        context_id: str,
        updater: Callable[[T], T],
    ) -> T | None:
        """Atomically update an existing context payload."""
        with self._lock:
            versioned = self._store.get(context_id)
            if not versioned:
                return None

            updated_payload = updater(copy.deepcopy(versioned.payload))
            versioned.payload = copy.deepcopy(updated_payload)
            versioned.stored_at = datetime.now(UTC)
            logger.info(
                "context_updated",
                context_id=context_id,
                version=versioned.version,
                stored_at=versioned.stored_at.isoformat(),
            )
            return copy.deepcopy(versioned.payload)

    def replace(self, context_id: str, version: int, payload: T) -> None:
        """Atomically replace one context without stale-version rejection."""
        with self._lock:
            self._store[context_id] = VersionedContext(
                context_id, version, copy.deepcopy(payload)
            )
            logger.info(
                "context_replaced",
                context_id=context_id,
                version=version,
            )

    def delete(self, context_id: str) -> bool:
        """Delete a context by id."""
        with self._lock:
            deleted = self._store.pop(context_id, None) is not None
            if deleted:
                logger.info("context_deleted", context_id=context_id)
            return deleted

    def atomic_replace(self, items: dict[str, tuple[int, T]]) -> None:
        """Atomically replace the full contents of this store."""
        with self._lock:
            self._store = {
                context_id: VersionedContext(
                    context_id,
                    version,
                    copy.deepcopy(payload),
                )
                for context_id, (version, payload) in items.items()
            }
            logger.info("store_atomic_replaced", count=len(self._store))

    def get_version(self, context_id: str) -> int | None:
        """Get the current version number."""
        with self._lock:
            versioned = self._store.get(context_id)
            return versioned.version if versioned else None

    def list_ids(self) -> list[str]:
        """List all context IDs."""
        with self._lock:
            return list(self._store.keys())

    def count(self) -> int:
        """Count stored contexts."""
        with self._lock:
            return len(self._store)


class CategoryStore(BaseStore[CategoryContext]):
    """Store for CategoryContext objects."""

    pass


class MerchantStore(BaseStore[MerchantContext]):
    """Store for MerchantContext objects."""

    pass


class CustomerStore(BaseStore[CustomerContext]):
    """Store for CustomerContext objects."""

    pass


class TriggerStore(BaseStore[TriggerContext]):
    """Store for TriggerContext objects."""

    def get_active_triggers(self) -> list[TriggerContext]:
        """Get all non-expired triggers."""
        with self._lock:
            now = datetime.utcnow()
            active = []
            
            for versioned in self._store.values():
                trigger = versioned.payload
                try:
                    expires_at = datetime.fromisoformat(
                        trigger.expires_at.replace("Z", "+00:00")
                    )
                    if expires_at > now:
                        active.append(trigger)
                except (ValueError, AttributeError):
                    # Invalid expiry format - include it
                    active.append(trigger)
            
            return active


class ContextStore:
    """Main context store managing all context types."""

    def __init__(self) -> None:
        self.categories = CategoryStore()
        self.merchants = MerchantStore()
        self.customers = CustomerStore()
        self.triggers = TriggerStore()
        logger.info("context_store_initialized")

    def put_context(
        self,
        scope: str,
        context_id: str,
        version: int,
        payload: dict[str, Any],
    ) -> tuple[bool, int | None]:
        """
        Store a context based on scope.
        
        Returns:
            (success, current_version if rejected)
        """
        if scope == "category":
            ctx = CategoryContext(**payload)
            return self.categories.put(context_id, version, ctx)
        elif scope == "merchant":
            ctx = MerchantContext(**payload)
            return self.merchants.put(context_id, version, ctx)
        elif scope == "customer":
            ctx = CustomerContext(**payload)
            return self.customers.put(context_id, version, ctx)
        elif scope == "trigger":
            ctx = TriggerContext(**payload)
            return self.triggers.put(context_id, version, ctx)
        else:
            raise ValueError(f"Unknown scope: {scope}")

    def get(self, scope: str, context_id: str) -> Any | None:
        """Get a context payload by scope and id."""
        return self.get_context(scope, context_id)

    def put(self, scope: str, context_id: str, version: int, payload: dict[str, Any]) -> tuple[bool, int | None]:
        """Store a versioned context payload."""
        return self.put_context(scope, context_id, version, payload)

    def update(self, scope: str, context_id: str, updater: Callable[[Any], Any]) -> Any | None:
        """Atomically update a context payload by scope and id."""
        return self.update_context(scope, context_id, updater)

    def delete(self, scope: str, context_id: str) -> bool:
        """Delete a context by scope and id."""
        return self.delete_context(scope, context_id)

    def replace(self, scope: str, context_id: str, version: int, payload: dict[str, Any]) -> None:
        """Replace a context payload by scope and id."""
        self.replace_context(scope, context_id, version, payload)

    def atomic_replace(self, scope: str, items: dict[str, tuple[int, dict[str, Any]]]) -> None:
        """Replace all contexts for one scope."""
        self.atomic_replace_contexts(scope, items)

    def get_context(self, scope: str, context_id: str) -> Any | None:
        """Get a context payload by scope and id."""
        store = self._store_for_scope(scope)
        return store.get(context_id)

    def update_context(
        self,
        scope: str,
        context_id: str,
        updater: Callable[[Any], Any],
    ) -> Any | None:
        """Atomically update a context by scope and id."""
        store = self._store_for_scope(scope)
        return store.update(context_id, updater)

    def delete_context(self, scope: str, context_id: str) -> bool:
        """Delete a context by scope and id."""
        store = self._store_for_scope(scope)
        return store.delete(context_id)

    def replace_context(
        self,
        scope: str,
        context_id: str,
        version: int,
        payload: dict[str, Any],
    ) -> None:
        """Atomically replace one context without version checks."""
        ctx = self._model_for_scope(scope, payload)
        store = self._store_for_scope(scope)
        store.replace(context_id, version, ctx)

    def atomic_replace_contexts(
        self,
        scope: str,
        items: dict[str, tuple[int, dict[str, Any]]],
    ) -> None:
        """Atomically replace all contexts for one scope."""
        store = self._store_for_scope(scope)
        typed_items = {
            context_id: (version, self._model_for_scope(scope, payload))
            for context_id, (version, payload) in items.items()
        }
        store.atomic_replace(typed_items)

    def get_counts(self) -> dict[str, int]:
        """Get counts of all context types."""
        return {
            "category": self.categories.count(),
            "merchant": self.merchants.count(),
            "customer": self.customers.count(),
            "trigger": self.triggers.count(),
        }

    def _store_for_scope(self, scope: str) -> BaseStore[Any]:
        if scope == "category":
            return self.categories
        if scope == "merchant":
            return self.merchants
        if scope == "customer":
            return self.customers
        if scope == "trigger":
            return self.triggers
        raise ValueError(f"Unknown scope: {scope}")

    def _model_for_scope(self, scope: str, payload: dict[str, Any]) -> Any:
        if scope == "category":
            return CategoryContext(**payload)
        if scope == "merchant":
            return MerchantContext(**payload)
        if scope == "customer":
            return CustomerContext(**payload)
        if scope == "trigger":
            return TriggerContext(**payload)
        raise ValueError(f"Unknown scope: {scope}")
