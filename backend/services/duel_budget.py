"""Reserve Jev input-token allowances before the frontend can spend them."""
import os
from contextlib import closing
from decimal import Decimal

from database_postgres import get_connection

# Four worst-case requests. Unused credit stays in the active frontend process.
BLOCK_TOKENS = 4 * 65536
USD_PER_MILLION = Decimal("0.042")


def reserve_budget():
    usd = Decimal(os.getenv("PLAY_AI_DAILY_USD", "1"))
    if not usd.is_finite() or usd < 0:
        raise ValueError("Invalid daily limit")
    cap = int(usd * 1_000_000 / USD_PER_MILLION)
    if cap < 65536:
        return None
    grant = min(cap, BLOCK_TOKENS)
    with closing(get_connection()) as conn:
        conn.set_session(readonly=False, autocommit=False)
        with conn, conn.cursor() as cur:
            # PostgreSQL serializes competing inserts/updates for the same UTC day.
            # A lost HTTP response or restart can waste a grant but cannot reuse it.
            cur.execute("""
                INSERT INTO snakebench_private.jev_daily_budget AS b (day, reserved_tokens)
                VALUES ((CURRENT_TIMESTAMP AT TIME ZONE 'UTC')::date, %s)
                ON CONFLICT (day) DO UPDATE
                SET reserved_tokens = b.reserved_tokens + EXCLUDED.reserved_tokens
                WHERE b.reserved_tokens + EXCLUDED.reserved_tokens <= %s
                RETURNING day
            """, (grant, cap))
            row = cur.fetchone()
            return {"day": row["day"].isoformat(), "tokens": grant} if row else None
