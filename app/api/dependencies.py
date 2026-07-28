"""FastAPI dependency injection."""

from functools import lru_cache

from app.adapters.category_adapter import CategoryAdapterRegistry
from app.context.knowledge_graph import KnowledgeGraph
from app.context.manager import ContextManager
from app.context.stores import ContextStore
from app.engine.decision_engine import DecisionEngine
from app.llm.provider import FallbackTemplateProvider, LLMProvider, OpenAIProvider
from app.memory.conversation_store import ConversationStore
from app.memory.intent_detector import IntentDetector
from app.utils.config import get_settings


class AppState:
    """Application state container."""

    def __init__(self) -> None:
        # Core stores
        self.context_store = ContextStore()
        self.context_manager = ContextManager(self.context_store)
        self.knowledge_graph = KnowledgeGraph()
        self.conversation_store = ConversationStore()
        
        # Adapters and providers
        settings = get_settings()
        self.adapter_registry = CategoryAdapterRegistry()
        self.llm_provider: LLMProvider = OpenAIProvider(
            api_key=settings.openai_api_key,
            model_name=settings.model_name,
            fallback_provider=FallbackTemplateProvider(),
        )
        
        # Intent detector
        self.intent_detector = IntentDetector()
        
        # Decision engine
        self.decision_engine = DecisionEngine(
            context_store=self.context_store,
            knowledge_graph=self.knowledge_graph,
            conversation_store=self.conversation_store,
            adapter_registry=self.adapter_registry,
            llm_provider=self.llm_provider,
            context_manager=self.context_manager,
        )


# Global app state
_app_state: AppState | None = None


@lru_cache()
def get_app_state() -> AppState:
    """Get or create the singleton app state."""
    global _app_state
    if _app_state is None:
        _app_state = AppState()
    return _app_state


def get_context_store() -> ContextStore:
    """Dependency: context store."""
    return get_app_state().context_store


def get_context_manager() -> ContextManager:
    """Dependency: context manager."""
    return get_app_state().context_manager


def get_knowledge_graph() -> KnowledgeGraph:
    """Dependency: knowledge graph."""
    return get_app_state().knowledge_graph


def get_conversation_store() -> ConversationStore:
    """Dependency: conversation store."""
    return get_app_state().conversation_store


def get_decision_engine() -> DecisionEngine:
    """Dependency: decision engine."""
    return get_app_state().decision_engine


def get_intent_detector() -> IntentDetector:
    """Dependency: intent detector."""
    return get_app_state().intent_detector
