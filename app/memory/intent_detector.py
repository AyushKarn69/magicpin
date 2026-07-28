"""Deterministic intent detection from merchant messages."""

from app.utils.logging import get_logger

logger = get_logger(__name__)


class IntentDetector:
    """Deterministic intent classifier (no LLM)."""

    @staticmethod
    def detect_intent(message: str) -> str:
        """
        Classify merchant message intent deterministically.
        
        Intents:
        - COMMITMENT: yes, sure, go ahead, let's do it
        - REJECTION: not interested, no thanks, stop
        - QUESTION: what, how, when, which
        - INFORMATION_PROVIDED: contains phone/address patterns
        - NEUTRAL: default
        """
        message_lower = message.lower().strip()

        # COMMITMENT patterns
        commitment_patterns = [
            "yes", "sure", "go ahead", "let's do it", "start", "ok",
            "okay", "please", "haan", "thik hai", "chalega", "kar do",
            "send", "share", "show me", "draft", "create"
        ]
        for pattern in commitment_patterns:
            if pattern in message_lower:
                logger.debug("intent_detected", intent="COMMITMENT", message=message[:50])
                return "COMMITMENT"

        # REJECTION patterns
        rejection_patterns = [
            "not interested", "no thanks", "stop", "unsubscribe",
            "don't send", "nahi chahiye", "no", "nope", "later",
            "not now", "busy"
        ]
        for pattern in rejection_patterns:
            if pattern in message_lower:
                logger.debug("intent_detected", intent="REJECTION", message=message[:50])
                return "REJECTION"

        # QUESTION patterns
        question_words = ["what", "how", "when", "which", "where", "who", "why", "kya", "kaise", "kab"]
        if any(message_lower.startswith(word) for word in question_words) or "?" in message:
            logger.debug("intent_detected", intent="QUESTION", message=message[:50])
            return "QUESTION"

        # INFORMATION_PROVIDED patterns (phone numbers, addresses)
        import re
        phone_pattern = r'\b\d{10}\b|\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b'
        if re.search(phone_pattern, message):
            logger.debug("intent_detected", intent="INFORMATION_PROVIDED", message=message[:50])
            return "INFORMATION_PROVIDED"

        # Default
        logger.debug("intent_detected", intent="NEUTRAL", message=message[:50])
        return "NEUTRAL"
