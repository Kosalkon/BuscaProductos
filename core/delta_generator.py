"""Compare two SQLite snapshots in key order and write delta operations."""

import json
import sqlite3


TABLES = {
    "products": (
        "id",
        ("id", "internal_code", "name", "price"),
    ),
    "equivalents": (
        "code",
        ("code", "product_id"),
    ),
}


def write_operations(previous_path, current_path, target):
    """Stream ordered rows; memory use stays constant regardless of DBF size."""

    previous = sqlite3.connect(previous_path)
    current = sqlite3.connect(current_path)

    counts = {"upsert": 0, "delete": 0}

    try:
        with target.open("w", encoding="utf-8", newline="\n") as output:
            for table, (key, columns) in TABLES.items():
                _write_table(
                    previous,
                    current,
                    output,
                    table,
                    key,
                    columns,
                    counts,
                )
    finally:
        previous.close()
        current.close()

    return counts


def _write_table(previous, current, output, table, key, columns, counts):
    selection = ", ".join(columns)

    old_cursor = previous.execute(
        f"SELECT {selection} FROM {table} ORDER BY {key}"
    )
    new_cursor = current.execute(
        f"SELECT {selection} FROM {table} ORDER BY {key}"
    )

    old = old_cursor.fetchone()
    new = new_cursor.fetchone()

    while old is not None or new is not None:
        if old is None:
            assert new is not None

            row = {
                column: new[index]
                for index, column in enumerate(columns)
            }

            _write(
                output,
                {
                    "op": "upsert",
                    "table": table,
                    "row": row,
                },
            )

            counts["upsert"] += 1
            new = new_cursor.fetchone()
            continue

        if new is None:
            _write(
                output,
                {
                    "op": "delete",
                    "table": table,
                    "key": old[0],
                },
            )

            counts["delete"] += 1
            old = old_cursor.fetchone()
            continue

        old_key = old[0]
        new_key = new[0]

        if old_key < new_key:
            _write(
                output,
                {
                    "op": "delete",
                    "table": table,
                    "key": old_key,
                },
            )

            counts["delete"] += 1
            old = old_cursor.fetchone()
            continue

        if new_key < old_key:
            row = {
                column: new[index]
                for index, column in enumerate(columns)
            }

            _write(
                output,
                {
                    "op": "upsert",
                    "table": table,
                    "row": row,
                },
            )

            counts["upsert"] += 1
            new = new_cursor.fetchone()
            continue

        if old != new:
            row = {
                column: new[index]
                for index, column in enumerate(columns)
            }

            _write(
                output,
                {
                    "op": "upsert",
                    "table": table,
                    "row": row,
                },
            )

            counts["upsert"] += 1

        old = old_cursor.fetchone()
        new = new_cursor.fetchone()


def _write(output, operation):
    output.write(
        json.dumps(
            operation,
            ensure_ascii=False,
            separators=(",", ":"),
        )
        + "\n"
    )