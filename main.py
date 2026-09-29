from __future__ import annotations

import argparse
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox

from dbf.reader import open_dbf
from core.change_detector import SourceChangeDetector
from core.publisher import Publisher
from utils.config import load_config
from utils.logger import configure_logging


PRODUCT_FIELDS = {"ARTNROAR1", "ARTDESC", "ARTIMP"}
ARTBAR_FIELDS = {"ARBNROAR1", "ARBCODBAR"}


def select_product_dbf():
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)

    path = filedialog.askopenfilename(
        title="Select products DBF",
        filetypes=[("DBF files", "*.dbf"), ("All files", "*.*")],
    )

    root.destroy()
    return Path(path) if path else None


def get_fields(path):
    try:
        db = open_dbf(path)
        return set(db.field_names)
    except Exception:
        return set()


def validate_dbf(path, required_fields):
    fields = get_fields(path)
    return required_fields.issubset(fields)


def show_error(message):
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    messagebox.showerror("Invalid DBF", message, parent=root)
    root.destroy()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Builds safe, versioned product database packages."
    )
    parser.add_argument("--config", default="config/config.json")
    parser.add_argument("--watch", action="store_true")
    parser.add_argument("--interval", type=int, default=60)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    config = load_config(Path(args.config))

    products_dbf = select_product_dbf()
    if products_dbf is None:
        return 0

    if not validate_dbf(products_dbf, PRODUCT_FIELDS):
        show_error(
            "The selected file is not a valid Articulos.dbf.\n\n"
            "Required fields:\n"
            "ARTNROAR1\n"
            "ARTDESC\n"
            "ARTIMP"
        )
        return 1

    config["sources"]["products"] = str(products_dbf)

    artbar_dbf = products_dbf.parent / "Artbar.dbf"

    if not artbar_dbf.exists():
        show_error(
            "Artbar.dbf was not found in the same folder as Articulos.dbf."
        )
        return 1

    if not validate_dbf(artbar_dbf, ARTBAR_FIELDS):
        show_error(
            "The Artbar.dbf file is invalid.\n\n"
            "Required fields:\n"
            "ARBNROAR1\n"
            "ARBCODBAR"
        )
        return 1

    config["sources"]["equivalents"] = str(artbar_dbf)

    logger = configure_logging(config["paths"]["log_file"])

    publisher = Publisher(config, logger)

    sources = [
        path for path in config["sources"].values()
        if path
    ]

    detector = SourceChangeDetector(
        sources,
        config["paths"]["state_dir"],
    )

    publisher.repair_legacy_empty_deltas()

    def publish_if_needed(force=False):
        if force or detector.changed():
            published = publisher.publish_update()

            if published is None:
                logger.info("No update was published.")
            else:
                detector.remember()
        else:
            logger.info("No source changes detected; nothing to publish.")

    publish_if_needed(args.force)

    if args.watch:
        logger.info(
            "Watching source metadata every %s seconds. Press Ctrl+C to stop.",
            args.interval,
        )
        try:
            while True:
                detector.wait_for_change(args.interval)
                publish_if_needed()
        except KeyboardInterrupt:
            logger.info("Stopped by user.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())