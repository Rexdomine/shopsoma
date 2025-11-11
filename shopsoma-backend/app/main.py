"""
Shopsoma Backend API
Main application entry point
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

# Import routers
from app.api.v1 import auth, products

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events"""
    # Startup
    print("🚀 Shopsoma API starting...")
    # TODO: Initialize database connection pool
    # TODO: Initialize Redis connection
    yield
    # Shutdown
    print("👋 Shopsoma API shutting down...")
    # TODO: Close database connections
    # TODO: Close Redis connections

app = FastAPI(
    title="Shopsoma API",
    description="Multi-vendor marketplace for African fashion",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    lifespan=lifespan
)

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],  # Update in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "Welcome to Shopsoma API",
        "version": "1.0.0",
        "status": "operational"
    }

@app.get("/healthz")
async def health_check():
    """Health check endpoint for Render"""
    return {"status": "healthy"}

# Include routers
app.include_router(auth.router, prefix="/api/v1")
app.include_router(products.router, prefix="/api/v1")

# TODO: Add more routers as they're implemented
# app.include_router(vendors.router, prefix="/api/v1")
# app.include_router(orders.router, prefix="/api/v1")
# app.include_router(admin.router, prefix="/api/v1")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
