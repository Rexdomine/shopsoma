# AppSetting Model Fix - Complete

## Problem
Backend server was crashing on startup with:
```
ModuleNotFoundError: No module named 'app.models.mixins'
```

**Location**: `app/models/app_setting.py` line 7

## Root Cause
The `AppSetting` model was trying to import a non-existent `TimestampMixin`:
```python
from app.models.mixins import TimestampMixin

class AppSetting(Base, TimestampMixin):
    ...
```

The codebase doesn't use mixins - all models define timestamps directly.

## Solution
Updated `app/models/app_setting.py` to follow the same pattern as existing models (`User`, `Product`, etc.):

### Changes Made:
1. ✅ Removed `from app.models.mixins import TimestampMixin`
2. ✅ Added required imports: `DateTime` and `func`
3. ✅ Fixed Base import path: `app.core.base` instead of `app.core.database`
4. ✅ Removed mixin from class inheritance: `Base` only
5. ✅ Added timestamp columns directly:
   ```python
   created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
   updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
   ```

## Updated Model
```python
"""Application settings model for admin configuration"""
from sqlalchemy import Column, String, Boolean, Text, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid

from app.core.base import Base


class AppSetting(Base):
    """Application settings table"""
    __tablename__ = "app_settings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    key = Column(String(100), unique=True, nullable=False, index=True)
    value = Column(Text, nullable=True)
    value_type = Column(String(20), nullable=False, default="string")
    description = Column(Text, nullable=True)
    is_public = Column(Boolean, default=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    def __repr__(self):
        return f"<AppSetting(key='{self.key}', value='{self.value}')>"
```

## Verification
✅ Model imports successfully
✅ Backend application starts without errors
✅ Database migration already applied (table exists)

## Status
**FIXED** - Backend server can now start successfully.

## Next Steps
1. Start the backend server: `uvicorn app.main:app --reload`
2. Test ShipBubble integration via admin toggle
3. Activate ShipBubble API key in dashboard if needed
