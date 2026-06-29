"""Declarative SQLAlchemy base shared by all ORBI models."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class for all persisted ORBI entities."""
