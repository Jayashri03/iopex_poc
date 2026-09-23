"""Run once to create the database and tables from db/schema.sql."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from db.connection import get_raw_connection  # noqa: E402

SCHEMA_PATH = pathlib.Path(__file__).resolve().parent.parent / "db" / "schema.sql"


def main():
    sql = SCHEMA_PATH.read_text(encoding="utf-8")
    statements = [s.strip() for s in sql.split(";") if s.strip()]

    conn = get_raw_connection()
    cursor = conn.cursor()
    for statement in statements:
        cursor.execute(statement)
    conn.commit()
    cursor.close()
    conn.close()
    print(f"Applied {len(statements)} statements from {SCHEMA_PATH}")


if __name__ == "__main__":
    main()
