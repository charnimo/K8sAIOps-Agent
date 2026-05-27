from sqlalchemy import create_engine, text

from app.database.database import ensure_sqlite_schema


def test_sqlite_schema_backfills_incident_visibility_columns(tmp_path):
    db_path = tmp_path / "app.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})

    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE incident_records (id INTEGER PRIMARY KEY, incident_id VARCHAR)"))

    ensure_sqlite_schema(engine)

    with engine.connect() as connection:
        rows = connection.execute(text("PRAGMA table_info(incident_records)")).mappings().all()

    columns = {row["name"] for row in rows}
    assert "viewed_by" in columns
    assert "dismissed_by" in columns
