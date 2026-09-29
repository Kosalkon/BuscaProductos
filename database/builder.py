"""Streaming read-only DBF conversion."""

import sqlite3
from pathlib import Path

from dbf.reader import iter_records, open_dbf


def text(value):
    return "" if value is None else str(value).strip()


class DatabaseBuilder:
    def __init__(self, config, logger):
        self.config = config
        self.logger = logger

    def build(self, destination):
        mapping = self.config["product_mapping"]
        source = Path(self.config["sources"]["products"])

        if not source.is_file():
            raise FileNotFoundError(f"Products DBF not found: {source}")

        connection = sqlite3.connect(destination)

        try:
            connection.executescript(
                """
                PRAGMA journal_mode=DELETE;
                PRAGMA synchronous=FULL;

                CREATE TABLE products(
                    id TEXT PRIMARY KEY NOT NULL,
                    internal_code TEXT NOT NULL,
                    name TEXT NOT NULL,
                    price REAL NOT NULL
                ) WITHOUT ROWID;

                CREATE INDEX products_internal_code_idx
                    ON products(internal_code);

                CREATE TABLE equivalents(
                    code TEXT PRIMARY KEY NOT NULL,
                    product_id TEXT NOT NULL
                ) WITHOUT ROWID;

                CREATE INDEX equivalents_product_idx
                    ON equivalents(product_id);

                CREATE TABLE app_metadata(
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                ) WITHOUT ROWID;
                """
            )

            count = 0
            skipped = 0

            for record in iter_records(open_dbf(source)):
                try:
                    product_id = text(record.get(mapping["stable_id"]))

                    if not product_id:
                        skipped += 1
                        continue

                    internal_code = text(
                        record.get(mapping["internal_code"])
                    )

                    name = text(
                        record.get(mapping["name"])
                    )

                    price_value = record.get(mapping["price"])
                    price = float(price_value or 0)

                    connection.execute(
                        """
                        INSERT OR REPLACE INTO products
                        (id, internal_code, name, price)
                        VALUES (?, ?, ?, ?)
                        """,
                        (
                            product_id,
                            internal_code,
                            name,
                            price,
                        ),
                    )

                    count += 1

                except (ValueError, TypeError, UnicodeError) as error:
                    skipped += 1
                    self.logger.warning(
                        "Skipping corrupt record: %s",
                        error,
                    )

            equivalent_count = self.add_equivalents(connection)

            connection.execute(
                "INSERT INTO app_metadata VALUES ('schema_version', '1')"
            )

            connection.execute(
                "INSERT INTO app_metadata VALUES (?, ?)",
                ("equivalent_count", str(equivalent_count)),
            )

            connection.commit()

            return {
                "products": count,
                "equivalents": equivalent_count,
                "skipped": skipped,
            }

        finally:
            connection.close()

    def add_equivalents(self, connection):
        source = Path(
            self.config["sources"].get("equivalents", "")
        )
        fields = self.config["equivalent_mapping"]

        if not source.is_file():
            return 0

        if not fields["product_id"] or not fields["code"]:
            return 0

        count = 0

        for record in iter_records(open_dbf(source)):
            code = text(record.get(fields["code"]))
            product_id = text(record.get(fields["product_id"]))

            if not code or not product_id:
                continue

            connection.execute(
                """
                INSERT OR REPLACE INTO equivalents
                (code, product_id)
                VALUES (?, ?)
                """,
                (code, product_id),
            )

            count += 1

        return count