"""bootstrap_rent.py — create the 5 Rent tables (Lane A, Task 2).

Reads rent_schema.sql and executes each CREATE TABLE as its own cur.execute()
call — the connector does not run multi-statement strings by default. Depends on
bootstrap.py having already created HACKDB.PUBLIC (snow.get_conn connects into it).
"""
from dotenv import load_dotenv; load_dotenv()
from snow import get_conn

RENT_TABLES = ("BUNDLE_REGISTRY", "FIXTURE_SUPPORT_MAP", "EVAL_RESULTS", "RETRIEVAL_LOG", "RENT_LEDGER")


def load_statements(path: str = "rent_schema.sql") -> list[str]:
    with open(path) as f:
        sql = f.read()
    # Each CREATE TABLE is terminated by ';'; no statement body contains an internal ';'.
    return [s.strip() for s in sql.split(";") if s.strip()]


def main():
    conn = get_conn(); cur = conn.cursor()
    statements = load_statements()
    for stmt in statements:
        cur.execute(stmt)
    conn.commit()
    cur.execute("""SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES
                   WHERE TABLE_SCHEMA='PUBLIC' AND TABLE_NAME IN
                   ('BUNDLE_REGISTRY','FIXTURE_SUPPORT_MAP','EVAL_RESULTS','RETRIEVAL_LOG','RENT_LEDGER')""")
    n = cur.fetchone()[0]
    print(f"rent schema: executed {len(statements)} statements, {n} rent tables present")
    assert n == 5, f"expected 5 rent tables, found {n}"


if __name__ == "__main__":
    main()
