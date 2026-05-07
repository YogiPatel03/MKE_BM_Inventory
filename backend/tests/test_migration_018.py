"""
Tests for migration 018 telegram_chat_id cleanup SQL.

Runs the migration's upgrade SQL statements against a minimal in-memory SQLite
table to verify:
  - NULL values stay NULL
  - Negative IDs (group/supergroup chat IDs) are nulled
  - Unique positive IDs survive
  - Duplicate positive IDs: lowest-id row kept, others nulled
  - After cleanup, all remaining non-null values are unique (constraint-safe)

Uses a dedicated engine/session so it does not touch the main test schema.
"""
import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# SQL replicated from migration 018 upgrade() — must stay in sync.
_STEP_NULL_NEGATIVES = (
    "UPDATE users SET telegram_chat_id = NULL WHERE telegram_chat_id LIKE '-%'"
)

_STEP_NULL_DUPS = """
    UPDATE users SET telegram_chat_id = NULL
    WHERE telegram_chat_id IS NOT NULL
    AND id NOT IN (
        SELECT MIN(id) FROM users
        WHERE telegram_chat_id IS NOT NULL
        GROUP BY telegram_chat_id
    )
    AND telegram_chat_id IN (
        SELECT telegram_chat_id FROM users
        WHERE telegram_chat_id IS NOT NULL
        GROUP BY telegram_chat_id HAVING COUNT(*) > 1
    )
"""


@pytest_asyncio.fixture
async def mig_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.execute(text(
            "CREATE TABLE users (id INTEGER PRIMARY KEY, telegram_chat_id TEXT)"
        ))
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    await engine.dispose()


async def _seed(db: AsyncSession, rows: list[tuple[int, str | None]]) -> None:
    for row_id, chat_id in rows:
        await db.execute(
            text("INSERT INTO users (id, telegram_chat_id) VALUES (:id, :c)"),
            {"id": row_id, "c": chat_id},
        )
    await db.commit()


async def _run_cleanup(db: AsyncSession) -> None:
    await db.execute(text(_STEP_NULL_NEGATIVES))
    await db.execute(text(_STEP_NULL_DUPS))
    await db.commit()


async def _chat_id(db: AsyncSession, row_id: int) -> str | None:
    result = await db.execute(
        text("SELECT telegram_chat_id FROM users WHERE id = :id"), {"id": row_id}
    )
    return result.scalar_one()


# ─── Tests ────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_null_stays_null(mig_db):
    """Rows already NULL are untouched."""
    await _seed(mig_db, [(1, None), (2, None)])
    await _run_cleanup(mig_db)
    assert await _chat_id(mig_db, 1) is None
    assert await _chat_id(mig_db, 2) is None


@pytest.mark.asyncio
async def test_unique_negative_is_nulled(mig_db):
    """A single user with a negative (group) chat ID is nulled."""
    await _seed(mig_db, [(1, "-100123456")])
    await _run_cleanup(mig_db)
    assert await _chat_id(mig_db, 1) is None


@pytest.mark.asyncio
async def test_duplicate_negatives_are_nulled(mig_db):
    """Two users who both linked from the same group are both nulled."""
    await _seed(mig_db, [(1, "-100999"), (2, "-100999")])
    await _run_cleanup(mig_db)
    assert await _chat_id(mig_db, 1) is None
    assert await _chat_id(mig_db, 2) is None


@pytest.mark.asyncio
async def test_unique_positive_survives(mig_db):
    """A correctly linked user with a unique positive ID keeps their value."""
    await _seed(mig_db, [(1, "12345678")])
    await _run_cleanup(mig_db)
    assert await _chat_id(mig_db, 1) == "12345678"


@pytest.mark.asyncio
async def test_duplicate_positives_keeps_min_id(mig_db):
    """For duplicate positive IDs the earliest-registered user keeps the value; others nulled."""
    await _seed(mig_db, [(1, "99999"), (2, "99999"), (3, "99999")])
    await _run_cleanup(mig_db)
    assert await _chat_id(mig_db, 1) == "99999"  # lowest id survives
    assert await _chat_id(mig_db, 2) is None
    assert await _chat_id(mig_db, 3) is None


@pytest.mark.asyncio
async def test_unique_constraint_applicable_after_cleanup(mig_db):
    """After cleanup, no duplicate non-null values remain — constraint can be added."""
    await _seed(mig_db, [
        (1, None),
        (2, "-100group"),    # unique negative → nulled
        (3, "111"),           # unique positive → kept
        (4, "222"),           # duplicate positive, lower id → kept
        (5, "222"),           # duplicate positive, higher id → nulled
        (6, "-100group2"),    # another unique negative → nulled
    ])
    await _run_cleanup(mig_db)

    result = await mig_db.execute(text(
        "SELECT COUNT(*) FROM ("
        "  SELECT telegram_chat_id FROM users"
        "  WHERE telegram_chat_id IS NOT NULL"
        "  GROUP BY telegram_chat_id HAVING COUNT(*) > 1"
        ")"
    ))
    assert result.scalar() == 0, "duplicate non-null values remain after cleanup"
