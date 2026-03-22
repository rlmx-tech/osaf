from decimal import Decimal

from sqlalchemy import Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class SharkSpecies(Base):
    __tablename__ = "shark_species"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    common_name: Mapped[str] = mapped_column(String(100), nullable=False)
    scientific_name: Mapped[str] = mapped_column(
        String(100), unique=True, nullable=False
    )
    family: Mapped[str | None] = mapped_column(String(100))
    danger_rating: Mapped[str | None] = mapped_column(String(20))
    max_size_meters: Mapped[Decimal | None] = mapped_column(Numeric(4, 1))
    notes: Mapped[str | None] = mapped_column(Text)
