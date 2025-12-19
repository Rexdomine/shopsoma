"""Temporary script to add manage_preferences table if it doesn't exist."""
from sqlalchemy import text
from sqlalchemy import create_engine
from app.core.config import settings

statement = text(
    """
    CREATE TABLE IF NOT EXISTS manage_preferences (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        user_id UUID NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
        interest VARCHAR(50),
        preferred_language VARCHAR(100),
        preferred_currency VARCHAR(10),
        favorite_designers JSONB NOT NULL DEFAULT '[]'::jsonb,
        favorite_categories JSONB NOT NULL DEFAULT '[]'::jsonb,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    """
)

def main():
    engine = create_engine(settings.DATABASE_URL)
    with engine.begin() as conn:
        conn.execute(statement)
        print("manage_preferences table ensured.")

if __name__ == "__main__":
    main()
