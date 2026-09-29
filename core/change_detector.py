"""Low-cost metadata polling suitable for old or network file systems."""
import json
import time
from pathlib import Path
class SourceChangeDetector:
    def __init__(self,sources,state_dir=None):
        self.sources=[Path(p) for p in sources]
        self.path=Path(state_dir)/"sources.json" if state_dir else None
        self._last=self._load()
    def _load(self):
        if not self.path or not self.path.exists(): return None
        try: return tuple(tuple(row) for row in json.loads(self.path.read_text(encoding="utf-8")))
        except (OSError,ValueError): return None
    def signature(self):
        return tuple((str(p),p.stat().st_size,p.stat().st_mtime_ns) if p.exists() else (str(p),None,None) for p in self.sources)
    def changed(self): return self._last is None or self.signature()!=self._last
    def remember(self):
        self._last=self.signature()
        if self.path:
            self.path.parent.mkdir(parents=True,exist_ok=True)
            temporary=self.path.with_suffix(".tmp")
            temporary.write_text(json.dumps(self._last),encoding="utf-8")
            temporary.replace(self.path)
    def wait_for_change(self,seconds): time.sleep(max(1,seconds))
