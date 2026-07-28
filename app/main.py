"""Main FastAPI application."""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import router
from app.utils.config import get_settings
from app.utils.logging import get_logger, request_logging_middleware, setup_logging

# Setup logging first
setup_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager."""
    settings = get_settings()
    logger.info(
        "application_starting",
        version=settings.version,
        team=settings.team_name,
    )
    yield
    logger.info("application_shutting_down")


# Create FastAPI app
app = FastAPI(
    title="Vera AI Decision Engine",
    description="Production-grade AI Decision Engine for magicpin Vera AI Challenge",
    version=get_settings().version,
    lifespan=lifespan,
)

# Add structured request logging middleware
app.middleware("http")(request_logging_middleware)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routes
app.include_router(router)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Return a 400 for malformed or invalid request payloads instead of FastAPI's default 422."""
    return JSONResponse(
        status_code=400,
        content={
            "accepted": False,
            "reason": "invalid_request",
            "details": "Request body is malformed or invalid",
        },
    )


@app.get("/")
async def root() -> dict[str, str]:
    """Root endpoint."""
    return {
        "service": "Vera AI Decision Engine",
        "version": get_settings().version,
        "status": "operational",
    }


if __name__ == "__main__":
    import uvicorn
    
    settings = get_settings()
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=False,
        log_level=settings.log_level.lower(),
    )
