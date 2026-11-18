-- Application-only counters. One durable row per UTC day for all public duels.
CREATE SCHEMA IF NOT EXISTS snakebench_private;
CREATE TABLE IF NOT EXISTS snakebench_private.jev_daily_budget (
    day date PRIMARY KEY,
    reserved_tokens bigint NOT NULL CHECK (reserved_tokens >= 0)
);
