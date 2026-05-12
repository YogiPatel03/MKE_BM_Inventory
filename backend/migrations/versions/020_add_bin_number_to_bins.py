"""Add bin_number to bins

Revision ID: 020
Revises: 019
Create Date: 2026-05-11
"""
from alembic import op
import sqlalchemy as sa

revision = "020"
down_revision = "019"
branch_labels = None
depends_on = None


def _case_insensitive_duplicates(table: str, column: str) -> list[dict]:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        query = sa.text(f"""
            SELECT lower({column}) AS normalized_value, COUNT(*) AS count, array_agg(id ORDER BY id) AS ids
            FROM {table}
            WHERE {column} IS NOT NULL
            GROUP BY lower({column})
            HAVING COUNT(*) > 1
        """)
    else:
        query = sa.text(f"""
            SELECT lower({column}) AS normalized_value, COUNT(*) AS count, group_concat(id) AS ids
            FROM {table}
            WHERE {column} IS NOT NULL
            GROUP BY lower({column})
            HAVING COUNT(*) > 1
        """)
    return list(bind.execute(query).mappings().all())


def _raise_if_case_insensitive_duplicates(table: str, column: str, label: str) -> None:
    duplicates = _case_insensitive_duplicates(table, column)
    if not duplicates:
        return
    details = "; ".join(
        f"{row['normalized_value']} count={row['count']} ids={row['ids']}"
        for row in duplicates
    )
    raise RuntimeError(
        f"Cannot create case-insensitive unique index for {label}: "
        f"existing duplicates must be cleaned before applying this migration. {details}"
    )


def _create_case_insensitive_unique_index(index_name: str, table: str, column: str) -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.create_index(
            index_name,
            table,
            [sa.text(f"lower({column})")],
            unique=True,
            postgresql_where=sa.text(f"{column} IS NOT NULL"),
        )
    elif bind.dialect.name == "sqlite":
        op.execute(sa.text(
            f"CREATE UNIQUE INDEX {index_name} ON {table} (lower({column})) "
            f"WHERE {column} IS NOT NULL"
        ))
    else:
        op.create_index(index_name, table, [sa.text(f"lower({column})")], unique=True)


def _drop_index_if_exists(index_name: str, table_name: str) -> None:
    bind = op.get_bind()
    if bind.dialect.name in {"postgresql", "sqlite"}:
        op.execute(sa.text(f"DROP INDEX IF EXISTS {index_name}"))
    else:
        op.drop_index(index_name, table_name=table_name)


def _drop_items_sku_exact_unique_if_exists() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute(sa.text("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM pg_constraint c
                JOIN pg_class t ON t.oid = c.conrelid
                WHERE c.conname = 'items_sku_key'
                  AND t.relname = 'items'
            ) THEN
                ALTER TABLE items DROP CONSTRAINT items_sku_key;
            END IF;
        END $$;
    """))


def _create_items_sku_exact_unique_if_missing() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute(sa.text("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_constraint c
                JOIN pg_class t ON t.oid = c.conrelid
                WHERE c.conname = 'items_sku_key'
                  AND t.relname = 'items'
            ) THEN
                ALTER TABLE items ADD CONSTRAINT items_sku_key UNIQUE (sku);
            END IF;
        END $$;
    """))


def upgrade() -> None:
    op.add_column("bins", sa.Column("bin_number", sa.String(length=100), nullable=True))
    _raise_if_case_insensitive_duplicates("items", "sku", "items.sku")
    _raise_if_case_insensitive_duplicates("bins", "bin_number", "bins.bin_number")
    _drop_items_sku_exact_unique_if_exists()
    _drop_index_if_exists("ix_bins_bin_number", "bins")
    _create_case_insensitive_unique_index("ux_items_sku_lower", "items", "sku")
    _create_case_insensitive_unique_index("ux_bins_bin_number_lower", "bins", "bin_number")


def downgrade() -> None:
    _drop_index_if_exists("ux_bins_bin_number_lower", "bins")
    _drop_index_if_exists("ux_items_sku_lower", "items")
    _create_items_sku_exact_unique_if_missing()
    op.drop_column("bins", "bin_number")
