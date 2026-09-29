import sqlite3

db = sqlite3.connect("output/inspect/products.sqlite")

for table in ("products", "equivalents", "app_metadata"):
    print(f"\n--- {table} ---")

    rows = db.execute(f"PRAGMA table_info({table})")

    for row in rows:
        print(row)

db.close()