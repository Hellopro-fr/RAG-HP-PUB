"""normalization_db schema (spec §4 / [J] §4, plus plan deltas P1-P2 and C9 tables)."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    CHAR,
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects import mysql
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _bin(length: int):
    """Accent- and case-sensitive VARCHAR on MySQL ('décibels' != 'decibels', 'Litres' != 'litres')."""
    return String(length).with_variant(
        mysql.VARCHAR(length, charset="utf8mb4", collation="utf8mb4_bin"), "mysql"
    )


# SQLite only auto-increments an INTEGER PRIMARY KEY.
_BIGINT_PK = BigInteger().with_variant(Integer, "sqlite")
# No table-level collation: a utf8mb4_bin table would give its CHAR(36) FK columns a collation
# different from the parent's ids and MySQL rejects the FK (error 3780). Case/accent sensitivity
# is carried per column by _bin() where it matters (tokens, pint definitions, rule keys).
_MYSQL = {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"}
_SOURCE = Enum("seed", "manual", "auto_proposal", name="unit_source")


class Base(DeclarativeBase):
    pass


class UnitDimensionRow(Base):
    __tablename__ = "unit_dimensions"
    __table_args__ = (UniqueConstraint("name", name="uniq_dim_name"), _MYSQL)

    id: Mapped[str] = mapped_column(CHAR(36), primary_key=True)
    name: Mapped[str] = mapped_column(_bin(64))
    canonical_unit: Mapped[str] = mapped_column(String(128))
    bypass_pint: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime)
    updated_at: Mapped[datetime] = mapped_column(DateTime)


class UnitRow(Base):
    __tablename__ = "units"
    __table_args__ = (
        UniqueConstraint("token", name="uniq_unit_token"),
        Index("idx_unit_status", "status"),
        Index("idx_unit_dimension", "dimension_id"),
        Index("idx_unit_kind", "kind"),
        _MYSQL,
    )

    id: Mapped[str] = mapped_column(CHAR(36), primary_key=True)
    token: Mapped[str] = mapped_column(_bin(128))
    case_sensitive: Mapped[bool] = mapped_column(Boolean, default=False)
    aliases: Mapped[list | None] = mapped_column(JSON, nullable=True)
    kind: Mapped[str] = mapped_column(Enum("NORMAL", "PASSTHROUGH", name="unit_kind"), default="NORMAL")
    label_condition: Mapped[str | None] = mapped_column(String(128), nullable=True)
    pint_definition: Mapped[str | None] = mapped_column(_bin(255), nullable=True)
    depends_on: Mapped[list | None] = mapped_column(JSON, nullable=True)
    rewrite_expression: Mapped[str | None] = mapped_column(String(255), nullable=True)
    dimension_id: Mapped[str | None] = mapped_column(
        CHAR(36), ForeignKey("unit_dimensions.id", ondelete="RESTRICT"), nullable=True
    )
    canonical_override: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(
        Enum("ACTIVE", "PENDING", "REJECTED", "DISABLED", name="unit_status"), default="ACTIVE"
    )
    source: Mapped[str] = mapped_column(_SOURCE, default="manual")
    regression_sample: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # plan delta P2
    sort_order: Mapped[int] = mapped_column(BigInteger, default=0)  # plan delta P1
    created_by: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime)
    updated_at: Mapped[datetime] = mapped_column(DateTime)


class RegistryMetaRow(Base):
    __tablename__ = "registry_meta"
    __table_args__ = (CheckConstraint("id = 1", name="chk_meta_singleton"), _MYSQL)

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True, autoincrement=False)
    registry_version: Mapped[int] = mapped_column(BigInteger, default=1)
    last_bumped_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_bumped_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class UnitEventRow(Base):
    """Transactional outbox (spec §4.1)."""

    __tablename__ = "unit_events"
    __table_args__ = (UniqueConstraint("registry_version", name="uniq_event_version"), _MYSQL)

    id: Mapped[int] = mapped_column(_BIGINT_PK, primary_key=True, autoincrement=True)
    registry_version: Mapped[int] = mapped_column(BigInteger)
    payload: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class UnitTypeRow(Base):
    __tablename__ = "unit_types"
    __table_args__ = (UniqueConstraint("code", name="uniq_unit_type_code"), _MYSQL)

    id: Mapped[str] = mapped_column(CHAR(36), primary_key=True)
    code: Mapped[str] = mapped_column(String(64))
    label: Mapped[str] = mapped_column(String(128))
    description: Mapped[str | None] = mapped_column(String(512), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime)
    updated_at: Mapped[datetime] = mapped_column(DateTime)


class DimensionUnitTypeRow(Base):
    __tablename__ = "dimension_unit_types"
    __table_args__ = (_MYSQL,)

    dimension_id: Mapped[str] = mapped_column(
        CHAR(36), ForeignKey("unit_dimensions.id", ondelete="RESTRICT"), primary_key=True
    )
    unit_type_id: Mapped[str] = mapped_column(
        CHAR(36), ForeignKey("unit_types.id", ondelete="RESTRICT"), primary_key=True
    )
    created_by: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime)


# --- Created in P1, used from P2/P3 (spec §4.2): schema only, never read in P1. ---


class LabelRuleRow(Base):
    __tablename__ = "label_rules"
    __table_args__ = (
        UniqueConstraint("key_substring", name="uniq_label_key"),
        UniqueConstraint("priority", name="uniq_label_priority"),
        Index("idx_label_active_priority", "is_active", "priority"),
        _MYSQL,
    )

    id: Mapped[str] = mapped_column(CHAR(36), primary_key=True)
    key_substring: Mapped[str] = mapped_column(_bin(255))
    dimension_id: Mapped[str] = mapped_column(CHAR(36), ForeignKey("unit_dimensions.id", ondelete="RESTRICT"))
    priority: Mapped[int] = mapped_column(Integer)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    source: Mapped[str] = mapped_column(_SOURCE, default="manual")
    created_by: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime)
    updated_at: Mapped[datetime] = mapped_column(DateTime)


class DisambiguationRuleRow(Base):
    __tablename__ = "disambiguation_rules"
    __table_args__ = (
        UniqueConstraint("trigger_unit", name="uniq_disambig_trigger"),
        _MYSQL,
    )

    id: Mapped[str] = mapped_column(CHAR(36), primary_key=True)
    trigger_unit: Mapped[str] = mapped_column(_bin(128))
    keyword_list: Mapped[list] = mapped_column(JSON)
    match_dimension_id: Mapped[str] = mapped_column(CHAR(36), ForeignKey("unit_dimensions.id", ondelete="RESTRICT"))
    match_pint_expr: Mapped[str | None] = mapped_column(String(255), nullable=True)
    default_dimension_id: Mapped[str | None] = mapped_column(
        CHAR(36), ForeignKey("unit_dimensions.id", ondelete="RESTRICT"), nullable=True
    )
    default_pint_expr: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime)
    updated_at: Mapped[datetime] = mapped_column(DateTime)


class UnitProposalRow(Base):
    __tablename__ = "unit_proposals"
    __table_args__ = (
        UniqueConstraint("dedup_key", name="uniq_proposal_dedup"),
        Index("idx_proposal_state_occ", "state", "occurrence_count"),
        _MYSQL,
    )

    id: Mapped[int] = mapped_column(_BIGINT_PK, primary_key=True, autoincrement=True)
    dedup_key: Mapped[str] = mapped_column(CHAR(64))
    raw_unit: Mapped[str] = mapped_column(String(128))
    normalized_unit: Mapped[str] = mapped_column(String(128))
    dimension_hint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    data_type: Mapped[str] = mapped_column(String(32))
    occurrence_count: Mapped[int] = mapped_column(BigInteger, default=1)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime)
    sample_labels: Mapped[list] = mapped_column(JSON)
    sample_value: Mapped[str | None] = mapped_column(String(64), nullable=True)
    state: Mapped[str] = mapped_column(
        Enum("PENDING", "VALIDATING", "ACTIVE", "REJECTED", "REJECTED_VALIDATION", "SUPERSEDED",
             name="proposal_state"),
        default="PENDING",
    )
    proposed_definition: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_by: Mapped[str] = mapped_column(String(64), default="auto-collector")
    reviewed_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    updated_at: Mapped[datetime] = mapped_column(DateTime)
