# Vera AI Decision Engine - Architecture Document

## Executive Summary

This is a **production-grade AI Decision Engine** for the magicpin Vera AI Challenge. The core architectural principle is: **the LLM never makes business decisions**. All reasoning about which opportunity to pursue, which trigger matters, which CTA to use, and which facts are important is done by deterministic code. The LLM is used ONLY for natural language composition.

## System Architecture

### High-Level Pipeline

```
┌─────────────────────────────────────────────────────────────────┐
│                     Incoming Context                            │
│            (Category, Merchant, Trigger, Customer)              │
└──────────────────────────┬──────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Context Store                                │
│          (Thread-safe, Versioned, O(1) lookup)                  │
└──────────────────────────┬──────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│                  Knowledge Graph                                │
│       (Indexed relationships for fast traversal)                │
└──────────────────────────┬──────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│                Feature Extraction                               │
│         (Deterministic business feature computation)            │
└──────────────────────────┬──────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│              Opportunity Generator                              │
│            (Generate ALL candidate opportunities)               │
└──────────────────────────┬──────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│              Business Rule Engine                               │
│          (Deterministic score adjustments)                      │
└──────────────────────────┬──────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│                Priority Scorer                                  │
│            (Weighted ranking algorithm)                         │
└──────────────────────────┬──────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│               Decision Planner                                  │
│         (Create Decision Card - NO raw JSON)                    │
└──────────────────────────┬──────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│                 Decision Card                                   │
│  {decision, priority, facts, reason, cta, tone, constraints}    │
└──────────────────────────┬──────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│               Prompt Compiler                                   │
│     (Decision Card → Concise Prompt, no context JSON)           │
└──────────────────────────┬──────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│            LLM Provider (Mock Only)                             │
│         (Deterministic natural language composition)            │
└──────────────────────────┬──────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│              Output Validator                                   │
│      (Schema, length, vocabulary, CTA validation)               │
└──────────────────────────┬──────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│                  HTTP Response                                  │
│            (Challenge-compliant JSON)                           │
└─────────────────────────────────────────────────────────────────┘
```

## Module Responsibilities

### 1. Context Store (`app/context/stores.py`)

**Responsibility**: Thread-safe versioned storage for all 4 context types.

**Key Features**:
- Generic `BaseStore<T>` with version control
- Atomic updates with version conflict detection
- O(1) average-case lookup
- Thread-safe with `RLock`
- Specialized stores: `CategoryStore`, `MerchantStore`, `CustomerStore`, `TriggerStore`

**Data Flow**:
- IN: `POST /v1/context` pushes
- OUT: Contexts retrieved by ID

### 2. Knowledge Graph (`app/context/knowledge_graph.py`)

**Responsibility**: Index entity relationships for fast traversal.

**Key Relationships**:
- Merchant → Category (via `category_slug`)
- Customer → Merchant (via `merchant_id`)
- Trigger → Merchant + Customer (via `merchant_id`, `customer_id`)
- Bidirectional: Merchant → [Customers], Merchant → [Triggers]

**Data Flow**:
- IN: Contexts from Context Store
- OUT: Fast lookups (O(1) average)

### 3. Feature Extractor (`app/engine/feature_extraction.py`)

**Responsibility**: Extract structured business features from raw contexts.

**Features Extracted**:
- Performance: CTR delta vs peer, declining calls/views, performance spike
- Offers: active count, expired count, recency
- Subscription: risk, days until renewal, expired status
- Engagement: days since last contact, stale posts
- Customer: lapse rate, retention rate, high-risk cohort
- Review: negative/positive themes
- Language: preference, Hindi support

**Data Flow**:
- IN: MerchantContext, CategoryContext, TriggerContext, CustomerContext
- OUT: ExtractedFeatures object

### 4. Opportunity Generator (`app/engine/opportunity_generator.py`)

**Responsibility**: Generate ALL applicable candidate opportunities (no ranking).

**Opportunity Types** (15+):
- Research Digest
- Renewal
- Campaign
- Offer Promotion / Creation
- Profile Optimization
- Festival Campaign
- Patient Recall
- Education
- Customer Followup
- Review Response
- Compliance Alert
- Curious Ask
- Winback
- Milestone Celebration
- Active Planning

**Data Flow**:
- IN: ExtractedFeatures
- OUT: List of Opportunity objects with raw scores

### 5. Business Rule Engine (`app/engine/business_rules.py`)

**Responsibility**: Apply deterministic rules to adjust opportunity scores.

**Rules**:
- Existing offer → 1.5x boost to promotion
- No offer → 2.0x boost to creation
- Performance decline → 1.3x boost to campaigns
- Dormant merchant (14+ days) → 0.7x penalty
- Suppression check → score = 0 if duplicate
- Trigger urgency (≥4) → boost by `urgency * 0.2`

**Data Flow**:
- IN: List of opportunities, ExtractedFeatures
- OUT: Opportunities with adjusted_score

### 6. Priority Scorer (`app/engine/priority_scorer.py`)

**Responsibility**: Rank opportunities using weighted criteria.

**Weights**:
- Trigger relevance: 30%
- Merchant benefit: 25%
- Category fit: 20%
- Novelty: 15%
- Engagement potential: 10%

**Scoring Logic**:
- Each component scored 0-10
- Weighted sum multiplied by adjusted_score
- Deterministic tie-breaking by urgency

**Data Flow**:
- IN: Opportunities with adjusted scores, ExtractedFeatures
- OUT: Ranked opportunities by weighted_score

### 7. Decision Planner (`app/planner/decision_planner.py`)

**Responsibility**: Convert top opportunity into a Decision Card.

**Decision Card Schema**:
```python
{
    "decision": str,              # Core action to communicate
    "priority": int (1-5),        # Mapped from weighted score
    "facts": list[str],           # 3-5 verifiable data points
    "reason": str,                # Why this decision
    "cta": str,                   # binary_yes_stop | open_ended | none
    "tone": str,                  # From category voice
    "audience": str,              # merchant | customer
    "send_as": str,               # vera | merchant_on_behalf
    "constraints": dict,          # Max length, taboos, language
    "suppression_key": str,       # For dedup
    "merchant_id": str,
    "customer_id": str | None,
    "trigger_id": str
}
```

**Data Flow**:
- IN: Top Opportunity, MerchantContext, CategoryContext
- OUT: Decision Card (NO RAW JSON)

### 8. Prompt Compiler (`app/prompts/prompt_compiler.py`)

**Responsibility**: Convert Decision Card to concise LLM prompt.

**Prompt Structure**:
1. Role and tone instruction
2. Task and reason
3. Key facts (bullet points)
4. CTA instruction
5. Constraints (length, language, taboos)
6. Audience specification

**Critical**: Prompt NEVER contains raw context JSON. Only Decision Card fields.

**Data Flow**:
- IN: Decision Card
- OUT: String prompt

### 9. Mock LLM Provider (`app/llm/provider.py`)

**Responsibility**: Deterministic natural language composition for testing.

**Implementation**:
- Keyword-based responses
- No external API calls
- Deterministic output for same prompt
- Realistic placeholder messages

**Future**: Replace with OpenAI integration (same interface).

**Data Flow**:
- IN: Prompt string
- OUT: Composed message body

### 10. Output Validator (`app/validators/output_validator.py`)

**Responsibility**: Validate composed messages before sending.

**Checks**:
- Not empty
- Within max length (2000 chars)
- No forbidden vocabulary (taboos)
- CTA presence (question mark for open_ended, choices for binary)
- Tone appropriateness (basic heuristics)

**Data Flow**:
- IN: Message body, Decision Card, CategoryContext
- OUT: ValidationResult (valid: bool, errors: list[str])

### 11. Category Adapters (`app/adapters/category_adapter.py`)

**Responsibility**: Isolate vertical-specific logic.

**Adapters**:
- DentistAdapter: peer_clinical tone, clinical vocabulary, no medical claims
- SalonAdapter: warm_retail tone, styling vocabulary
- RestaurantAdapter: friendly_casual tone, food vocabulary
- GymAdapter: motivational tone, fitness vocabulary
- PharmacyAdapter: professional_helpful tone, no medical advice

**Interface**:
- `get_voice()` → VoiceProfile
- `get_offer_catalog()` → list[OfferTemplate]
- `get_seasonal_beats()` → list[SeasonalBeat]
- `lookup_digest_item(id)` → DigestItem | None

**Data Flow**:
- IN: Category slug
- OUT: Category-specific rules and templates

### 12. Conversation Store (`app/memory/conversation_store.py`)

**Responsibility**: Track conversation state and history.

**State Machine**:
```
NEW → QUALIFYING → INTERESTED → ACTION → WAITING → ENDED
```

**Features**:
- Turn history with timestamps
- Auto-reply detection (deterministic)
- Suppression key tracking
- Auto-reply count
- State transitions

**Data Flow**:
- IN: Turns from `/v1/reply`
- OUT: State, history, suppression status

### 13. Intent Detector (`app/memory/intent_detector.py`)

**Responsibility**: Classify merchant message intent (no LLM).

**Intents**:
- COMMITMENT: "yes", "sure", "go ahead"
- REJECTION: "not interested", "no thanks", "stop"
- QUESTION: starts with question word or contains "?"
- INFORMATION_PROVIDED: contains phone/address patterns
- NEUTRAL: default

**Data Flow**:
- IN: Message string
- OUT: Intent classification

### 14. Decision Engine (`app/engine/decision_engine.py`)

**Responsibility**: Main orchestrator - runs the full pipeline.

**Process**:
1. Load trigger and associated contexts
2. Extract features
3. Generate opportunities
4. Apply business rules
5. Score and rank
6. Check threshold (min 5.0)
7. Plan decision card
8. Compile prompt
9. Generate message (LLM)
10. Validate output
11. Create conversation
12. Record suppression
13. Return ComposedAction

**Data Flow**:
- IN: Trigger ID
- OUT: ComposedAction | None

## API Layer

### Endpoints

#### `GET /v1/healthz`
- Returns: status, uptime, context counts
- No business logic

#### `GET /v1/metadata`
- Returns: team info, model, approach
- From configuration

#### `POST /v1/context`
- Accepts: scope, context_id, version, payload
- Stores in Context Store
- Updates Knowledge Graph
- Returns: accepted, ack_id, stored_at

#### `POST /v1/tick`
- Accepts: now, available_triggers
- Processes each trigger via Decision Engine
- Returns: list of actions

#### `POST /v1/reply`
- Accepts: conversation_id, from_role, message, etc.
- Detects auto-reply and intent
- Updates conversation state
- Returns: action (send/wait/end), body, rationale

### Dependencies

Dependency injection via `app/api/dependencies.py`:
- `AppState` singleton container
- Lazy initialization of all components
- FastAPI `Depends()` for route injection

## Data Models

All models use Pydantic v2 with strict validation:

### Context Models (`app/models/contexts.py`)
- CategoryContext
- MerchantContext
- CustomerContext
- TriggerContext
- Supporting models: VoiceProfile, PeerStats, DigestItem, etc.

### Conversation Models (`app/models/conversation.py`)
- ConversationSession
- ConversationState (enum)
- ConversationTurn

### Decision Models (`app/models/decision.py`)
- DecisionCard

### Feature Models (`app/models/features.py`)
- ExtractedFeatures

### Opportunity Models (`app/models/opportunities.py`)
- Opportunity
- OpportunityKind (enum)

## Configuration & Logging

### Configuration (`app/utils/config.py`)
- Pydantic Settings
- Environment variable loading
- Type-safe settings access
- Cached singleton

### Logging (`app/utils/logging.py`)
- Structlog for structured JSON logging
- Log levels from config
- Context variables
- ISO timestamps

## Testing Strategy

### Test Subset
Only 3 merchants used in development:
- `m_001_drmeera_dentist_delhi`
- `m_003_studio11_salon_hyderabad`
- `m_006_southindiancafe_restaurant_bangalore`

All other merchants reserved for evaluation.

### Test Coverage
- Unit tests for each module
- Integration tests for pipeline
- API tests for endpoints
- Conversation flow tests

## Deployment

### Docker
- Multi-stage build
- Python 3.12 slim base
- uv for fast dependency installation
- Port 8080 exposed

### Scalability
- Stateless design (can scale horizontally)
- In-memory stores (fast but not persistent)
- Thread-safe operations
- No external dependencies (except LLM in future)

### Monitoring
- Structured logs for aggregation
- Health check endpoint
- Uptime tracking
- Context load metrics

## Security

- No PII logged
- Environment-based secrets
- CORS middleware
- Input validation on all endpoints
- Schema validation on contexts

## Future Enhancements

### Phase 2: OpenAI Integration
- Replace MockLLMProvider with OpenAIProvider
- Same interface, different implementation
- Add retry logic, rate limiting
- Add cost tracking

### Phase 3: Persistence
- Replace in-memory stores with Redis/PostgreSQL
- Add conversation history persistence
- Add analytics database

### Phase 4: Advanced Features
- Multi-turn conversation optimization
- A/B testing framework for prompts
- Reinforcement learning from judge feedback
- Real-time analytics dashboard

## Conclusion

This architecture achieves the core goal: **deterministic business reasoning with LLM-only language composition**. Every business decision is traceable, testable, and auditable. The LLM is a utility for natural language, not a decision-maker.

The system is production-ready, modular, and extensible. Adding new categories, opportunities, or business rules requires minimal changes to core modules.
