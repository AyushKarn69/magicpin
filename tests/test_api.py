"""Basic API tests."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.context.stores import ContextStore
from app.main import app
from app.models.contexts import CategoryContext, CustomerContext, MerchantContext, TriggerContext
from app.models.decision import DecisionCard
from app.validators.output_validator import OutputValidator

client = TestClient(app)


def test_root():
    """Test root endpoint."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "Vera AI Decision Engine"
    assert "version" in data


def test_healthz():
    """Test health check endpoint."""
    response = client.get("/v1/healthz")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "uptime_seconds" in data
    assert "contexts_loaded" in data


def test_metadata():
    """Test metadata endpoint."""
    response = client.get("/v1/metadata")
    assert response.status_code == 200
    data = response.json()
    assert "team_name" in data
    assert "team_members" in data
    assert "model" in data
    assert "approach" in data


def test_environment_file_contains_groq_configuration():
    """The Groq settings must be present in the workspace config."""
    env_path = Path(__file__).resolve().parents[1] / ".env"
    env_text = env_path.read_text(encoding="utf-8")

    assert "magicpin=" in env_text


def test_context_push_category():
    """Test context push with category."""
    payload = {
        "scope": "category",
        "context_id": "dentists",
        "version": 1,
        "payload": {
            "slug": "dentists",
            "voice": {
                "tone": "peer_clinical",
                "vocab_allowed": ["fluoride", "caries"],
                "taboos": ["cure", "guaranteed"],
            },
            "peer_stats": {
                "avg_rating": 4.4,
                "avg_reviews": 62,
                "avg_ctr": 0.030,
                "scope": "delhi_solo_practices",
            },
            "offer_catalog": [],
            "digest": [],
            "patient_content_library": [],
            "seasonal_beats": [],
            "trend_signals": [],
        },
        "delivered_at": "2026-04-26T10:00:00Z",
    }
    
    response = client.post("/v1/context", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["accepted"] is True
    assert "ack_id" in data


def test_context_push_duplicate_version_is_idempotent():
    """Re-posting the same version should be treated as a no-op instead of a conflict."""
    payload = {
        "scope": "merchant",
        "context_id": "dup_merchant",
        "version": 3,
        "payload": {
            "merchant_id": "dup_merchant",
            "category_slug": "salons",
            "identity": {
                "name": "Bright Salon",
                "city": "Delhi",
                "locality": "Janpath",
                "place_id": "place-dup",
                "verified": True,
                "languages": ["english"],
            },
            "subscription": {"status": "active", "plan": "pro"},
            "performance": {"window_days": 7, "views": 120, "calls": 9, "directions": 3, "ctr": 0.02},
        },
        "delivered_at": "2026-04-26T10:00:00Z",
    }

    first = client.post("/v1/context", json=payload)
    second = client.post("/v1/context", json=payload)

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["accepted"] is True


def test_context_push_version_conflict():
    """Test context push with stale version."""
    # Push version 2 first
    payload_v2 = {
        "scope": "category",
        "context_id": "test_category",
        "version": 2,
        "payload": {
            "slug": "dentists",
            "voice": {"tone": "test", "vocab_allowed": [], "taboos": []},
            "peer_stats": {
                "avg_rating": 4.0,
                "avg_reviews": 50,
                "avg_ctr": 0.03,
                "scope": "test",
            },
            "offer_catalog": [],
            "digest": [],
            "patient_content_library": [],
            "seasonal_beats": [],
            "trend_signals": [],
        },
        "delivered_at": "2026-04-26T10:00:00Z",
    }
    client.post("/v1/context", json=payload_v2)
    
    # Try to push version 1 (stale)
    payload_v1 = payload_v2.copy()
    payload_v1["version"] = 1
    
    response = client.post("/v1/context", json=payload_v1)
    assert response.status_code == 409
    data = response.json()
    assert data["accepted"] is False
    assert data["reason"] == "stale_version"
    assert data["current_version"] == 2


def test_context_push_invalid_scope_returns_400():
    """Invalid scopes should fail validation with a 400 response."""
    payload = {
        "scope": "unknown_scope",
        "context_id": "bad",
        "version": 1,
        "payload": {},
        "delivered_at": "2026-04-26T10:00:00Z",
    }

    response = client.post("/v1/context", json=payload)
    assert response.status_code == 400
    data = response.json()
    assert data["accepted"] is False
    assert data["reason"] == "invalid_scope"


def test_context_push_malformed_json_returns_400():
    """Malformed JSON should be handled gracefully with a 400 response."""
    response = client.post(
        "/v1/context",
        content='{"scope": "merchant", "context_id": "bad", ',
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 400


def test_tick_empty():
    """Test tick with no triggers."""
    payload = {
        "now": "2026-04-26T10:00:00Z",
        "available_triggers": [],
    }
    
    response = client.post("/v1/tick", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "actions" in data
    assert isinstance(data["actions"], list)


def test_context_store_supports_core_operations_and_versioning():
    """Context store should support get/put/update/delete/replace/atomic replace semantics."""
    store = ContextStore()

    accepted, current_version = store.put_context(
        scope="merchant",
        context_id="m1",
        version=1,
        payload={
            "merchant_id": "m1",
            "category_slug": "dentists",
            "identity": {
                "name": "Smile Care",
                "city": "Delhi",
                "locality": "Connaught Place",
                "place_id": "place-1",
                "verified": True,
                "languages": ["english"],
            },
            "subscription": {"status": "active", "plan": "pro"},
            "performance": {"window_days": 7, "views": 100, "calls": 10, "directions": 2, "ctr": 0.02},
        },
    )
    assert accepted is True
    assert current_version is None

    merchant = store.get_context("merchant", "m1")
    assert merchant is not None
    assert merchant.identity.name == "Smile Care"

    updated = store.update_context(
        "merchant",
        "m1",
        lambda payload: payload.model_copy(update={"identity": payload.identity.model_copy(update={"city": "Mumbai"})}),
    )
    assert updated is not None
    assert updated.identity.city == "Mumbai"

    store.replace_context(
        "merchant",
        "m1",
        version=2,
        payload={
            "merchant_id": "m1",
            "category_slug": "dentists",
            "identity": {
                "name": "Smile Care",
                "city": "Bengaluru",
                "locality": "Koramangala",
                "place_id": "place-2",
                "verified": True,
                "languages": ["english"],
            },
            "subscription": {"status": "active", "plan": "pro"},
            "performance": {"window_days": 7, "views": 110, "calls": 11, "directions": 3, "ctr": 0.025},
        },
    )
    replaced = store.get_context("merchant", "m1")
    assert replaced is not None
    assert replaced.identity.city == "Bengaluru"

    store.atomic_replace_contexts(
        "merchant",
        {
            "m2": (
                1,
                {
                    "merchant_id": "m2",
                    "category_slug": "salons",
                    "identity": {
                        "name": "Luxe Salon",
                        "city": "Delhi",
                        "locality": "Saraswati Colony",
                        "place_id": "place-3",
                        "verified": True,
                        "languages": ["english"],
                    },
                    "subscription": {"status": "active", "plan": "basic"},
                    "performance": {"window_days": 7, "views": 50, "calls": 8, "directions": 1, "ctr": 0.01},
                },
            )
        },
    )
    assert store.get_context("merchant", "m2") is not None
    assert store.get_context("merchant", "m1") is None

    assert store.delete_context("merchant", "m2") is True
    assert store.get_context("merchant", "m2") is None


def test_validator_rejects_hallucinated_offer_and_price():
    """The validator should reject unsupported offers, prices, and dates."""
    validator = OutputValidator()
    card = DecisionCard(
        decision="send_follow_up",
        priority=3,
        facts=["The merchant has an active offer for a free consultation."],
        reason="A reminder is helpful.",
        cta="open_ended",
        tone="warm_retail",
        audience="customer",
        send_as="vera",
        constraints={"max_body_length": 220, "taboos": []},
        suppression_key="sup-1",
        merchant_id="m1",
        trigger_id="t1",
    )
    category = CategoryContext(
        slug="salons",
        voice={"tone": "warm_retail", "vocab_allowed": ["appointment", "booking"], "taboos": []},
        peer_stats={"avg_rating": 4.2, "avg_reviews": 30, "avg_ctr": 0.04, "scope": "test"},
    )

    parsed, result = validator.validate_raw_response(
        '{"message": "Book today for only Rs. 999 and get a 50% discount on a free trial on 12 June.", "cta": "open_ended", "rationale": "Needs a CTA."}',
        card=card,
        category=category,
    )

    assert parsed is not None
    assert result.valid is False
    assert any("Hallucinated price" in error for error in result.errors)
    assert any("Hallucinated date" in error for error in result.errors)
