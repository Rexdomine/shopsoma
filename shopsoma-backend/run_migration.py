#!/usr/bin/env python3
"""
Quick script to apply the settings table migration
Run from shopsoma-backend directory: python3 run_migration.py
"""
import subprocess
import sys
import os

def run_command(cmd, description):
    """Run a shell command and print output"""
    print(f"\n{'='*60}")
    print(f"{description}")
    print(f"{'='*60}")
    print(f"Command: {cmd}\n")

    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)

    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)

    if result.returncode != 0:
        print(f"\n❌ Error: Command failed with exit code {result.returncode}")
        return False

    print("✓ Success")
    return True

def main():
    print("\n" + "="*60)
    print("Settings Table Migration Script")
    print("="*60)

    # Check if we're in the right directory
    if not os.path.exists('alembic.ini'):
        print("\n❌ Error: alembic.ini not found!")
        print("Please run this script from the shopsoma-backend directory")
        sys.exit(1)

    # Activate venv and run alembic
    commands = [
        ("source venv/bin/activate && alembic current", "1. Checking current migration state"),
        ("source venv/bin/activate && alembic upgrade head", "2. Applying pending migrations"),
    ]

    for cmd, desc in commands:
        if not run_command(cmd, desc):
            sys.exit(1)

    # Verify table creation (optional, requires psql)
    print(f"\n{'='*60}")
    print("3. Verifying settings table (optional)")
    print(f"{'='*60}")
    print("\nAttempting to verify table creation...")

    verify_cmd = 'psql -U shopsoma -d shopsoma_db -c "SELECT COUNT(*) as count FROM settings;"'
    result = subprocess.run(verify_cmd, shell=True, capture_output=True, text=True)

    if result.returncode == 0:
        print("✓ Settings table exists and is accessible")
        print(result.stdout)
    else:
        print("⚠ Could not verify table (psql may not be available)")
        print("This is OK - the migration should still have succeeded")

    print("\n" + "="*60)
    print("✓ Migration Process Complete!")
    print("="*60)
    print("\nNext steps:")
    print("1. Restart your backend server:")
    print("   cd /Users/rex/Documents/Shopsoma/shopsoma-backend")
    print("   source venv/bin/activate")
    print("   uvicorn app.main:app --reload")
    print("\n2. Test the API endpoint:")
    print("   curl http://localhost:8000/api/v1/settings/public/exchange-rate")
    print("\n3. Test in frontend:")
    print("   Navigate to http://localhost:5173/admin/settings")
    print("")

if __name__ == "__main__":
    main()
