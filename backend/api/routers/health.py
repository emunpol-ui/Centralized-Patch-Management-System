"""Health check router (CPM-001, unmodified)."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict

from fastapi import APIRouter

from backend.api.dependencies import SettingsDependency

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/health", tags=["Health"])


@router.get("", summary="Health check")
async def health_check(settings: SettingsDependency) -> Dict[str, Any]:
    logger.debug("Health check requested.")
    return {
        "success": True,
        "message": "CPMS backend is running.",
        "data": {
            "app_name": settings.APP_NAME,
            "version": settings.APP_VERSION,
            "environment": settings.APP_ENV,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    }
