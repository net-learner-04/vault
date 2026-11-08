from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv
import os

load_dotenv()

DATABASE_URL = str(os.getenv("DATABASE_URL"))

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def run_migrations():
    """Add columns introduced after the first release.

    Alembic is listed as a dependency but no migration files ship with this
    snapshot, so we keep an idempotent, SQLite-safe migration that only adds
    missing columns to existing tables.
    """
    additions = {
        "users": {
            "dek_wrapped": "VARCHAR",
            "dek_nonce": "VARCHAR",
            "dek_tag": "VARCHAR",
            "kek_salt": "VARCHAR",
            "dek_wrapped_recovery": "VARCHAR",
            "dek_nonce_recovery": "VARCHAR",
            "dek_tag_recovery": "VARCHAR",
        },
        "files": {
            "enc_iv": "VARCHAR",
        },
        "shared_links": {
            "dek_wrapped": "VARCHAR",
            "dek_nonce": "VARCHAR",
            "dek_tag": "VARCHAR",
        },
    }
    with engine.connect() as conn:
        for table, columns in additions.items():
            try:
                existing = {row[1] for row in conn.exec_driver_sql(f"PRAGMA table_info({table})")}
            except Exception:
                continue
            for column, ddl in columns.items():
                if column not in existing:
                    conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")
        conn.commit()
