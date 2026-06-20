# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nimesh Cheedella

"""Payment — Stripe checkout records."""


from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import Column, DateTime, Integer, Numeric, String
from sqlalchemy import ForeignKey
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.sql import func
from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:  # pragma: no cover
    from .user import User


class Payment(SQLModel, table=True):
    __tablename__ = "payments"

    id: UUID = Field(
        sa_column=Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    )
    user_id: UUID = Field(
        sa_column=Column(
            PGUUID(as_uuid=True),
            ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )
    )
    stripe_session_id: str = Field(
        sa_column=Column(String(255), nullable=False, unique=True, index=True)
    )
    sku: str = Field(sa_column=Column(String(64), nullable=False))
    shots_purchased: int = Field(sa_column=Column(Integer, nullable=False))
    dollar_amount: Decimal = Field(sa_column=Column(Numeric(12, 4), nullable=False))
    currency: str = Field(default="usd", sa_column=Column(String(8), nullable=False, server_default="usd"))
    status: str = Field(sa_column=Column(String(32), nullable=False))  # 'completed' | 'pending' | 'failed' | 'refunded'
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now()),
    )

    user: "User" = Relationship(back_populates="payments")


__all__ = ["Payment"]
