"""D20 Agent RPG — Health and system endpoints."""

from fastapi import APIRouter
from app.models.schemas import HealthResponse
from app.services.database import db_healthcheck

router = APIRouter(tags=["system"])


@router.get("/health", response_model=HealthResponse)
def health():
    return HealthResponse(db_connected=db_healthcheck())


@router.get("/")
def root():
    return {
        "service": "AgentDungeon",
        "version": "0.1.0",
        "docs": "/docs",
        "health": "/health",
    }
