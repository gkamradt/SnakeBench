#!/usr/bin/env python3
"""
Apply database migrations to Supabase PostgreSQL.
"""

import sys
import os
from database_postgres import get_connection

def apply_migration(migration_file: str):
    """Apply a migration SQL file to the database."""

    # Read migration file
    migration_path = os.path.join(os.path.dirname(__file__), 'migrations', migration_file)

    if not os.path.exists(migration_path):
        print(f"Error: Migration file not found: {migration_path}")
        return False

    with open(migration_path, 'r') as f:
        migration_sql = f.read()

    print(f"Applying migration: {migration_file}")
    print("=" * 60)

    try:
        conn = get_connection()
        cursor = conn.cursor()

        # Execute the migration
        cursor.execute(migration_sql)
        conn.commit()

        print(f"✓ Migration {migration_file} applied successfully!")

        cursor.close()
        conn.close()

        return True

    except Exception as e:
        print(f"✗ Error applying migration: {e}")
        return False


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python apply_migration.py <migration_file>")
        print("Example: python apply_migration.py 002_live_game_tracking.sql")
        sys.exit(1)

    migration_file = sys.argv[1]
    success = apply_migration(migration_file)

    sys.exit(0 if success else 1)
