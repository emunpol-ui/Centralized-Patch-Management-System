"""
CPMS Backend - Local development launcher.

Convenience entry point so the server can be started with:

    python run.py

Equivalent to running Uvicorn directly:

    uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
"""

from __future__ import annotations

import uvicorn

from backend.core.config import get_settings

if __name__ == "__main__":
    settings = get_settings()
    uvicorn.run(
        "backend.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
        log_config=None,  # defer entirely to backend.core.logging configuration
    )
