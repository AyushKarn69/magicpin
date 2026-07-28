# Vera AI Decision Engine

Production-grade AI backend for the magicpin Vera AI Challenge submission.

## Architecture Overview

This is an **AI Decision Engine** where the LLM is used ONLY for natural language composition. All business reasoning is deterministic.

### Pipeline

```
Incoming Context
    ↓
Context Store (versioned, thread-safe)
    ↓
Knowledge Graph (fast entity traversal)
    ↓
Feature Extraction (deterministic)
    ↓
Opportunity Generator (all candidates)
    ↓
Business Rule Engine (score adjustments)
    ↓
Priority Scorer (weighted ranking)
    ↓
Decision Planner (Decision Card creation)
    ↓
Prompt Compiler (no raw JSON to LLM)
    ↓
LLM Provider (MockLLMProvider - deterministic)
    ↓
Output Validator
    ↓
HTTP Response
```

## Key Design Principles

1. **Deterministic Business Logic**: LLM never decides which opportunity, which trigger, which CTA
2. **Decision Card Abstraction**: Structured reasoning before LLM sees anything
3. **4-Context Framework**: Category, Merchant, Trigger, Customer properly separated
4. **Single Responsibility**: Each module has ONE job
5. **Production-Ready**: Strong typing, logging, error handling, dependency injection

## Project Structure

```
app/
├── api/                    # FastAPI routes and dependencies
│   ├── routes.py          # Challenge endpoints
│   ├── models.py          # Request/response schemas
│   └── dependencies.py    # DI container
├── context/               # Context storage
│   ├── stores.py          # Thread-safe versioned stores
│   └── knowledge_graph.py # Entity relationship indexing
├── engine/                # Decision pipeline
│   ├── feature_extraction.py      # Extract business features
│   ├── opportunity_generator.py   # Generate candidates
│   ├── business_rules.py          # Deterministic scoring
│   ├── priority_scorer.py         # Weighted ranking
│   └── decision_engine.py         # Main orchestrator
├── planner/               # Decision planning
│   └── decision_planner.py        # Create Decision Cards
├── memory/                # Conversation state
│   ├── conversation_store.py      # State machine
│   └── intent_detector.py         # Deterministic intent detection
├── llm/                   # LLM interface
│   └── provider.py        # MockLLMProvider (no OpenAI yet)
├── validators/            # Output validation
│   └── output_validator.py        # Schema and content checks
├── prompts/               # Prompt compilation
│   └── prompt_compiler.py         # Decision Card → Prompt
├── adapters/              # Category-specific logic
│   └── category_adapter.py        # Dentists, Salons, etc.
├── models/                # Pydantic schemas
│   ├── contexts.py        # 4-context models
│   ├── conversation.py    # State machine models
│   ├── decision.py        # Decision Card model
│   ├── features.py        # Feature extraction models
│   └── opportunities.py   # Opportunity models
└── utils/                 # Configuration and logging
    ├── config.py          # Environment-based settings
    └── logging.py         # Structured logging
```

## API Endpoints

All endpoints match the challenge specification:

- `GET /v1/healthz` - Health check
- `GET /v1/metadata` - Team and bot metadata
- `POST /v1/context` - Receive context pushes
- `POST /v1/tick` - Periodic wake-up, bot initiates messages
- `POST /v1/reply` - Handle merchant/customer replies

## Installation

### Prerequisites

- Python 3.12+
- uv (Python package manager)

### Setup

```bash
# Clone repository
cd magicpin

# Install dependencies using uv
uv pip install -e .

# Create .env file
cp .env.example .env
# Edit .env with your configuration
```

### Environment Variables

```bash
# Server
HOST=0.0.0.0
PORT=8080
VERSION=1.0.0

# Team Info
TEAM_NAME=Team Vera
TEAM_MEMBERS=["Engineer1", "Engineer2"]
CONTACT_EMAIL=team@example.com

# LLM (not used yet - MockLLMProvider only)
OPENAI_API_KEY=sk-placeholder
MODEL_NAME=claude-opus-4-7

# Logging
LOG_LEVEL=INFO
```

## Running the Application

### Local Development

```bash
# Run with uvicorn
python -m uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload

# Or run directly
python app/main.py
```

### Docker

```bash
# Build image
docker build -t vera-ai-engine .

# Run container
docker run -p 8080:8080 --env-file .env vera-ai-engine

# Or use docker-compose
docker-compose up
```

### Verify Server

```bash
# Health check
curl http://localhost:8080/v1/healthz

# Metadata
curl http://localhost:8080/v1/metadata
```

## Testing

```bash
# Run tests
pytest

# Run with coverage
pytest --cov=app --cov-report=html

# Run specific test
pytest tests/test_feature_extraction.py
```

## Dataset Structure

The system uses the challenge dataset:

```
dataset/
├── categories/
│   ├── dentists.json
│   ├── salons.json
│   ├── restaurants.json
│   ├── gyms.json
│   └── pharmacies.json
├── merchants_seed.json        # 10 seed merchants (expands to 50)
├── customers_seed.json        # 15 seed customers (expands to 200)
└── triggers_seed.json         # 25 seed triggers (expands to 100)
```

**Test Subset**: Only 3 merchants used in development tests:
- `m_001_drmeera_dentist_delhi` (Dentist)
- `m_003_studio11_salon_hyderabad` (Salon)
- `m_006_southindiancafe_restaurant_bangalore` (Restaurant)

All other merchants reserved for final evaluation.

## Module Overview

### Context Store
- Thread-safe versioned storage for all 4 context types
- Atomic updates with version control
- O(1) lookup performance

### Knowledge Graph
- Indexed entity relationships
- Fast traversal: Merchant→Category, Customer→Merchant, Trigger→Merchant/Customer
- Bidirectional links maintained

### Feature Extraction
- Deterministic feature computation
- CTR deltas, performance trends, offer status, subscription risk
- No AI/LLM involved

### Opportunity Generator
- Generates ALL applicable opportunities (no ranking)
- 15+ opportunity types: Research Digest, Renewal, Campaign, Offer Promotion, etc.

### Business Rule Engine
- Deterministic score adjustments
- Rules: existing offer boost, performance decline boost, dormancy penalty, suppression
- Urgency-based multipliers

### Priority Scorer
- Weighted ranking: trigger_relevance (30%), merchant_benefit (25%), category_fit (20%), novelty (15%), engagement_potential (10%)
- Deterministic tie-breaking

### Decision Planner
- Converts winning opportunity → Decision Card
- Decision Card = structured reasoning (NO raw JSON to LLM)

### Prompt Compiler
- Decision Card → concise LLM prompt
- Facts, constraints, tone - never raw context data

### Mock LLM Provider
- Deterministic responses based on keywords
- No external API calls
- Returns realistic placeholder messages

### Output Validator
- Schema validation
- Length checks
- Forbidden vocabulary detection
- CTA presence validation

### Category Adapters
- Voice profiles (tone, vocabulary, taboos)
- Offer catalogs
- Seasonal beats
- Vertical-specific logic isolated

### Conversation Memory
- State machine: NEW → QUALIFYING → INTERESTED → ACTION → WAITING → ENDED
- Auto-reply detection (deterministic)
- Suppression key tracking

### Intent Detector
- Deterministic classification (no LLM)
- Intents: COMMITMENT, REJECTION, QUESTION, INFORMATION_PROVIDED, NEUTRAL

## Code Quality

- **Type Safety**: mypy strict mode, full type hints
- **Linting**: ruff for formatting and linting
- **Dependency Injection**: Constructor-based DI throughout
- **SOLID Principles**: Single responsibility, open/closed, etc.
- **No Circular Imports**: Clean module boundaries
- **Structured Logging**: JSON logs with context

## Development

### Type Checking

```bash
mypy app/
```

### Linting

```bash
ruff check app/
ruff format app/
```

### Adding a New Category

1. Create adapter in `app/adapters/category_adapter.py`
2. Implement `get_voice()`, `get_offer_catalog()`, `get_seasonal_beats()`
3. Register in `CategoryAdapterRegistry`

### Adding a New Opportunity Type

1. Add to `OpportunityKind` enum in `app/models/opportunities.py`
2. Implement generator method in `app/engine/opportunity_generator.py`
3. Add decision template in `app/planner/decision_planner.py`

## Deployment

### Production Checklist

- [ ] Set `LOG_LEVEL=INFO` or `WARNING`
- [ ] Configure proper `TEAM_NAME`, `TEAM_MEMBERS`, `CONTACT_EMAIL`
- [ ] Ensure `.env` is not committed (use secrets management)
- [ ] Scale horizontally (stateless design allows multiple instances)
- [ ] Monitor `/v1/healthz` endpoint
- [ ] Set up structured log aggregation

### Challenge Submission

Submit your public URL to the challenge portal. The judge will:
1. Call `/v1/healthz` and `/v1/metadata` to verify bot
2. Push base dataset via `/v1/context`
3. Run test window via `/v1/tick` with triggers
4. Evaluate conversation flows via `/v1/reply`

## Architecture Decisions

### Why MockLLMProvider?
Phase 1 focuses on deterministic pipeline infrastructure. OpenAI integration is phase 2.

### Why Decision Card?
Separates business reasoning (deterministic) from language generation (LLM). Makes system auditable and testable.

### Why No Database?
In-memory stores sufficient for challenge scope. Production would use Redis/PostgreSQL.

### Why Category Adapters?
Vertical-specific logic (voice, offers, seasonality) isolated. Adding new categories doesn't modify core engine.

## License

Proprietary - magicpin Vera AI Challenge Submission

## Contact

- Team: ${TEAM_NAME}
- Email: ${CONTACT_EMAIL}
