"""
Common schemas used across the application
"""
from typing import Generic, TypeVar, List
from pydantic import BaseModel

# Type variable for generic pagination
T = TypeVar('T')


class PaginatedResponse(BaseModel, Generic[T]):
    """Paginated response schema"""
    items: List[T]
    total: int
    page: int
    page_size: int
    total_pages: int

    class Config:
        from_attributes = True
