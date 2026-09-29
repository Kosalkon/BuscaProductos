import json
from pathlib import Path
class VersionManager:
    def __init__(self,state_dir): self.path=Path(state_dir)/"version.json"
    def next_version(self): return 1 if not self.path.exists() else int(json.loads(self.path.read_text(encoding="utf-8"))["version"])+1
    def save(self,metadata):
        self.path.parent.mkdir(parents=True,exist_ok=True); temp=self.path.with_suffix(".tmp")
        temp.write_text(json.dumps(metadata,ensure_ascii=False,indent=2),encoding="utf-8"); temp.replace(self.path)
