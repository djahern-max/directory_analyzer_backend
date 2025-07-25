from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.config import settings
from app.core.logging import setup_logging
from app.core.exceptions import setup_exception_handlers
from app.api import auth, payments  # Import modules that exist
from app.api.directories import router as directories_router  # Import router directly
from app.api.middleware import setup_middleware
from app.api import document_chat


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    # Startup
    setup_logging()
    yield
    # Shutdown
    pass


def create_application() -> FastAPI:
    """Create and configure FastAPI application"""

    app = FastAPI(
        title=settings.app_name,
        description="Analyze construction document directories to identify main contracts",
        version="1.0.0",
        debug=settings.debug,
        lifespan=lifespan,
        openapi_version="3.1.0",
    )

    # Setup middleware
    setup_middleware(app)

    # Setup exception handlers
    setup_exception_handlers(app)

    # Include routers - FIXED: Use correct imports
    app.include_router(directories_router, prefix="/directories", tags=["directories"])
    app.include_router(auth.router, prefix="/auth", tags=["authentication"])
    app.include_router(payments.router, prefix="/payments", tags=["payments"])
    app.include_router(document_chat.router)

    return app


# Create the app instance
app = create_application()


@app.get("/")
async def root():
    """Root endpoint with API information"""
    return {
        "message": f"{settings.app_name} API",
        "version": "1.0.0",
        "status": "running",
        "endpoints": {
            "health": "/health",
            "directories": "/directories",
            "auth": "/auth",
            "docs": "/docs",
            "redoc": "/redoc",
        },
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app", host=settings.host, port=settings.port, reload=settings.debug
    )
