from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager

from app.config import settings
from app.core.logging import setup_logging
from app.core.exceptions import setup_exception_handlers
from app.api import health, directories
from app.api.middleware import setup_middleware


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
       lifespan=lifespan
   )
   
   # Setup middleware
   setup_middleware(app)
   
   # Setup exception handlers
   setup_exception_handlers(app)
   
   # Include routers
   app.include_router(health.router, tags=["health"])
   app.include_router(
       directories.router, 
       prefix="/directories", 
       tags=["directories"]
   )
   
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
           "docs": "/docs",
           "redoc": "/redoc"
       }
   }


if __name__ == "__main__":
   import uvicorn
   uvicorn.run(
       "app.main:app",
       host=settings.host,
       port=settings.port,
       reload=settings.debug
   )
