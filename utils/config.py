import json
from pathlib import Path


DEFAULTS = {
    "paths": {
        "output_dir": "output",
        "state_dir": "state",
        "log_file": "logs/updater.log",
    },
    "product_mapping": {
        "stable_id": "ARTNROAR1",
        "internal_code": "ARTNROAR1",
        "name": "ARTDESC",
        "price": "ARTIMP",
    },
    "equivalent_mapping": {
        "product_id": "ARBNROAR1",
        "code": "ARBCODBAR",
    },
    "updates": {
        "full_snapshot_interval": 20,
    },
    "github": {
        "enabled": False,
        "repository": "",
        "token_file": "secrets.json",
        "prerelease": False,
    },
}


def load_config(path: Path) -> dict:
    config = json.loads(path.read_text(encoding="utf-8"))
    base = path.parent.parent.resolve()

    for section, values in DEFAULTS.items():
        config.setdefault(section, {})

        for key, value in values.items():
            config[section].setdefault(key, value)

    for section in ("sources", "paths"):
        for key, value in list(config[section].items()):
            config[section][key] = str((base / value).resolve())

    return config