"""
Base class for SQLAlchemy models
Separated to avoid circular imports and async engine initialization issues with Alembic
"""
from sqlalchemy.orm import declarative_base

# Create declarative base
Base = declarative_base()
