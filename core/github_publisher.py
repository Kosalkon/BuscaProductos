import json
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request,urlopen
class GitHubPublisher:
    API="https://api.github.com"
    def __init__(self,settings,logger): self.settings,self.logger=settings,logger
    def publish(self,version,assets):
        if not self.settings["enabled"]: return
        repository=self.settings["repository"].strip(); token=self.token()
        if not repository or not token: raise RuntimeError("GitHub enabled but repository or local token file is missing.")
        draft=self.json("POST",f"/repos/{repository}/releases",{"tag_name":f"products-v{version}","name":f"Products v{version}","draft":True,"prerelease":bool(self.settings["prerelease"]),"generate_release_notes":False},token)
        try:
            for asset in assets: self.upload(draft["upload_url"].split("{")[0],asset,token)
            self.json("PATCH",f"/repos/{repository}/releases/{draft['id']}",{"draft":False},token)
        except Exception:
            self.logger.exception("GitHub draft release %s remains invisible.",draft["id"]); raise
    def json(self,method,endpoint,payload,token):
        request=Request(self.API+endpoint,data=json.dumps(payload).encode(),method=method)
        for key,value in {"Authorization":f"Bearer {token}","Accept":"application/vnd.github+json","Content-Type":"application/json","X-GitHub-Api-Version":"2022-11-28"}.items(): request.add_header(key,value)
        try:
            with urlopen(request,timeout=45) as response: return json.loads(response.read().decode())
        except HTTPError as error: raise RuntimeError(f"GitHub API error {error.code}: {error.read().decode('utf-8','replace')}") from error
    def upload(self,url,asset,token):
        request=Request(url+"?name="+quote(asset.name),data=asset.read_bytes(),method="POST")
        for key,value in {"Authorization":f"Bearer {token}","Accept":"application/vnd.github+json","Content-Type":"application/octet-stream"}.items(): request.add_header(key,value)
        with urlopen(request,timeout=180) as response:
            if response.status not in (200,201): raise RuntimeError(f"GitHub upload failed: HTTP {response.status}")
    def token(self):
        path=Path(self.settings.get("token_file","secrets.json"))
        if not path.is_file(): return ""
        try: return str(json.loads(path.read_text(encoding="utf-8")).get("github_token","")).strip()
        except (OSError,ValueError) as error: raise RuntimeError(f"Cannot read GitHub token file: {error}") from error
