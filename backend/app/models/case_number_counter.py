from sqlalchemy import Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class CaseNumberCounter(Base):
    """Durable high-water marks for yearly public case identifiers."""

    __tablename__ = "case_number_counters"

    year: Mapped[int] = mapped_column(Integer, primary_key=True)
    last_value: Mapped[int] = mapped_column(Integer, nullable=False)
