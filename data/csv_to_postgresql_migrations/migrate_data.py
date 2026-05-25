"""
migrate_data.py
Reads the four CSV files and inserts normalised data into PostgreSQL.
Run create_schema.py first to ensure all tables exist.
"""

import csv
from datetime import datetime
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

# ── Config ────────────────────────────────────────────────────────────────────
DATABASE_URL = "postgresql+psycopg2://postgres:admin@localhost:5432/ml_ops_project"
DATA_DIR = Path("ml-latest-small")


# ── Helpers ───────────────────────────────────────────────────────────────────
def read_csv(filename: str) -> list[dict]:
    with open(DATA_DIR / filename, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def unix_to_ts(value: str) -> datetime | None:
    try:
        return datetime.utcfromtimestamp(int(value))
    except (ValueError, TypeError):
        return None


# ── Migration steps ───────────────────────────────────────────────────────────
def migrate_movies(session: Session, rows: list[dict]) -> dict[int, list[str]]:
    """Insert movies; return {movie_id: [genre, …]} for later use."""
    genre_map: dict[int, list[str]] = {}
    for row in rows:
        movie_id = int(row["movieId"])
        genre_names = [
            g.strip()
            for g in row["genres"].split("|")
            if g.strip() and g.strip() != "(no genres listed)"
        ]
        genre_map[movie_id] = genre_names

        session.execute(
            text(
                "INSERT INTO movie.movies (id, title) VALUES (:id, :title) ON CONFLICT DO NOTHING"
            ),
            {"id": movie_id, "title": row["title"].strip()},
        )
    session.flush()
    print(f"  ✔  movies: {len(rows)} rows")
    return genre_map


def migrate_genres(session: Session, genre_map: dict[int, list[str]]) -> dict[str, int]:
    """Collect unique genre names, upsert into enum.genres, return name→id."""
    all_genres = sorted({g for genres in genre_map.values() for g in genres})
    genre_id: dict[str, int] = {}
    for idx, name in enumerate(all_genres, start=1):
        session.execute(
            text(
                """
                INSERT INTO enum.genres (id, name)
                VALUES (:id, :name)
                ON CONFLICT (name) DO NOTHING
            """
            ),
            {"id": idx, "name": name},
        )
        genre_id[name] = idx
    session.flush()
    # Re-fetch ids in case rows already existed with different ids
    result = session.execute(text("SELECT id, name FROM enum.genres"))
    genre_id = {row.name: row.id for row in result}
    print(f"  ✔  genres: {len(all_genres)} unique genres")
    return genre_id


def migrate_movie_genres(
    session: Session, genre_map: dict[int, list[str]], genre_id: dict[str, int]
):
    count = 0
    for movie_id, genres in genre_map.items():
        for genre_name in genres:
            gid = genre_id.get(genre_name)
            if gid is None:
                continue
            session.execute(
                text(
                    """
                    INSERT INTO movie.movie_genres (id_movie, id_genre)
                    VALUES (:id_movie, :id_genre)
                    ON CONFLICT (id_movie, id_genre) DO NOTHING
                """
                ),
                {"id_movie": movie_id, "id_genre": gid},
            )
            count += 1
    session.flush()
    print(f"  ✔  movie_genres: {count} rows")


def migrate_links(session: Session, rows: list[dict]):
    for idx, row in enumerate(rows, start=1):
        session.execute(
            text(
                """
                INSERT INTO movie.links (id, id_movie, "imdbId", "tmdbId")
                VALUES (:id, :id_movie, :imdbId, :tmdbId)
                ON CONFLICT DO NOTHING
            """
            ),
            {
                "id": idx,
                "id_movie": int(row["movieId"]),
                "imdbId": str(row["imdbId"]),
                "tmdbId": str(row["tmdbId"]),
            },
        )
    session.flush()
    print(f"  ✔  links: {len(rows)} rows")


def collect_users(ratings_rows: list[dict], tags_rows: list[dict]) -> set[int]:
    """Gather every userId that appears in ratings or tags."""
    return {int(r["userId"]) for r in ratings_rows} | {
        int(r["userId"]) for r in tags_rows
    }


def migrate_users(session: Session, user_ids: set[int]):
    for uid in sorted(user_ids):
        session.execute(
            text("INSERT INTO users.users (id) VALUES (:id) ON CONFLICT DO NOTHING"),
            {"id": uid},
        )
    session.flush()
    print(f"  ✔  users: {len(user_ids)} rows")


def migrate_ratings(session: Session, rows: list[dict]):
    for idx, row in enumerate(rows, start=1):
        session.execute(
            text(
                """
                INSERT INTO rating.ratings (id, id_movie, id_user, rating, timestamp)
                VALUES (:id, :id_movie, :id_user, :rating, :timestamp)
                ON CONFLICT DO NOTHING
            """
            ),
            {
                "id": idx,
                "id_movie": int(row["movieId"]),
                "id_user": int(row["userId"]),
                "rating": float(row["rating"]),
                "timestamp": unix_to_ts(row["timestamp"]),
            },
        )
    session.flush()
    print(f"  ✔  ratings: {len(rows)} rows")


def migrate_tags(session: Session, rows: list[dict]):
    for idx, row in enumerate(rows, start=1):
        session.execute(
            text(
                """
                INSERT INTO movie.tags (id, id_movie, id_user, tag, timestamp)
                VALUES (:id, :id_movie, :id_user, :tag, :timestamp)
                ON CONFLICT DO NOTHING
            """
            ),
            {
                "id": idx,
                "id_movie": int(row["movieId"]),
                "id_user": int(row["userId"]),
                "tag": row["tag"].strip(),
                "timestamp": unix_to_ts(row["timestamp"]),
            },
        )
    session.flush()
    print(f"  ✔  tags: {len(rows)} rows")


# ── Entry point ───────────────────────────────────────────────────────────────
def main():
    print("📂  Reading CSV files …")
    movies_rows = read_csv("movies.csv")
    links_rows = read_csv("links.csv")
    ratings_rows = read_csv("ratings.csv")
    tags_rows = read_csv("tags.csv")

    engine = create_engine(DATABASE_URL, echo=False)

    print("\n🚀  Starting migration …")
    with Session(engine) as session:
        # 1. Movies (needed before FKs in every other table)
        genre_map = migrate_movies(session, movies_rows)

        # 2. Genres (enum lookup table)
        genre_id = migrate_genres(session, genre_map)

        # 3. Movie ↔ genre join table
        migrate_movie_genres(session, genre_map, genre_id)

        # 4. Links
        migrate_links(session, links_rows)

        # 5. Users (collect all unique user ids from ratings + tags first)
        user_ids = collect_users(ratings_rows, tags_rows)
        migrate_users(session, user_ids)

        # 6. Ratings
        migrate_ratings(session, ratings_rows)

        # 7. Tags
        migrate_tags(session, tags_rows)

        session.commit()

    print("\n✅  Migration complete.")


if __name__ == "__main__":
    main()
