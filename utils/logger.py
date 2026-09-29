import logging
from pathlib import Path
def configure_logging(log_file):
    path=Path(log_file); path.parent.mkdir(parents=True,exist_ok=True)
    logger=logging.getLogger("dbf_updater")
    if logger.handlers: return logger
    logger.setLevel(logging.INFO); formatter=logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    for handler in (logging.FileHandler(path,encoding="utf-8"),logging.StreamHandler()):
        handler.setFormatter(formatter); logger.addHandler(handler)
    return logger
