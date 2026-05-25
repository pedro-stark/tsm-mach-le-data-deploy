"""
create_schema.py
Creates all schemas and tables in PostgreSQL using SQLAlchemy.
Run this before the migration script.
"""

from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    String,
    Double,
    ForeignKey,
    TIMESTAMP,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import declarative_base, relationship

# ── Connection ────────────────────────────────────────────────────────────────
DATABASE_URL = "postgresql+psycopg2://postgres:admin@localhost:5432/ml_ops_project"
engine = create_engine(DATABASE_URL, echo=True)

Base = declarative_base()


# ── Schema: enum ──────────────────────────────────────────────────────────────
class Genre(Base):
    __tablename__ = "genres"
    __table_args__ = {"schema": "enum"}

    id = Column(Integer, primary_key=True, autoincrement=False)
    name = Column(String(64), nullable=False, unique=True)


# ── Schema: users ─────────────────────────────────────────────────────────────
class User(Base):
    __tablename__ = "users"
    __table_args__ = {"schema": "users"}

    id = Column(Integer, primary_key=True, autoincrement=False)


# ── Schema: movie ─────────────────────────────────────────────────────────────
class Movie(Base):
    __tablename__ = "movies"
    __table_args__ = {"schema": "movie"}

    id = Column(Integer, primary_key=True, autoincrement=False)
    title = Column(String(512), nullable=False)


class Link(Base):
    __tablename__ = "links"
    __table_args__ = {"schema": "movie"}

    id = Column(Integer, primary_key=True, autoincrement=False)
    id_movie = Column(Integer, ForeignKey("movie.movies.id"), nullable=False)
    imdbId = Column(String(64), nullable=False, unique=True)
    tmdbId = Column(String(64), nullable=False, unique=True)


class Tag(Base):
    __tablename__ = "tags"
    __table_args__ = {"schema": "movie"}

    id = Column(Integer, primary_key=True, autoincrement=True)
    id_movie = Column(Integer, ForeignKey("movie.movies.id"), nullable=False)
    id_user = Column(Integer, ForeignKey("users.users.id"), nullable=False)
    tag = Column(String(512), nullable=False)
    timestamp = Column(TIMESTAMP, nullable=True)


class MovieGenre(Base):
    __tablename__ = "movie_genres"
    __table_args__ = (
        UniqueConstraint("id_movie", "id_genre", name="uq_movie_genre"),
        {"schema": "movie"},
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    id_movie = Column(Integer, ForeignKey("movie.movies.id"), nullable=False)
    id_genre = Column(Integer, ForeignKey("enum.genres.id"), nullable=False)


# ── Schema: rating ────────────────────────────────────────────────────────────
class Rating(Base):
    __tablename__ = "ratings"
    __table_args__ = {"schema": "rating"}

    id = Column(Integer, primary_key=True, autoincrement=True)
    id_movie = Column(Integer, ForeignKey("movie.movies.id"), nullable=False)
    id_user = Column(Integer, ForeignKey("users.users.id"), nullable=False)
    rating = Column(Double, nullable=False)
    timestamp = Column(TIMESTAMP, nullable=True)


# ── Main ──────────────────────────────────────────────────────────────────────
def create_all():
    schemas = ["enum", "users", "movie", "rating"]
    with engine.connect() as conn:
        for schema in schemas:
            conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {schema}"))
        conn.commit()

    Base.metadata.create_all(engine)
    print("✅  All schemas and tables created successfully.")


if __name__ == "__main__":
    create_all()
