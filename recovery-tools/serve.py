#!/usr/bin/env python3
"""Static server with a single-page application fallback."""
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import argparse, json, mimetypes, os, re
from urllib.parse import urlsplit

class SPAHandler(SimpleHTTPRequestHandler):
    server_version="FunnelMirror/1.0"
    def __init__(self,*args,directory=None,**kwargs):
        self.root=directory or "site"
        try:self.mime_map=json.loads(Path(self.root,"_mime_types.json").read_text("utf-8"))
        except Exception:self.mime_map={}
        super().__init__(*args,directory=self.root,**kwargs)
    def do_GET(self):
        path=self.translate_path(self.path)
        if os.path.isfile(path): return super().do_GET()
        # Preserve file-like missing assets as 404; only route-like paths fall back.
        if Path(self.path.split("?",1)[0]).suffix: return self.send_error(404,"Asset not mirrored")
        index=os.path.join(self.root,"index.html")
        if not os.path.isfile(index): return self.send_error(404,"site/index.html is missing; run mirror.py first")
        self.path="/index.html"
        return super().do_GET()
    def translate_path(self,path):
        parsed=urlsplit(path)
        translated=super().translate_path(parsed.path)
        if parsed.query:
            suffix="__q_"+re.sub(r"[^A-Za-z0-9._-]","_",parsed.query)[:100]
            candidate=translated+suffix
            if os.path.isfile(candidate):return candidate
        return translated
    def guess_type(self,path):
        try: rel=Path(path).resolve().relative_to(Path(self.root).resolve()).as_posix()
        except ValueError: rel=""
        return self.mime_map.get(rel) or super().guess_type(path)
    def end_headers(self):
        self.send_header("X-Funnel-Mirror","spa-fallback-v1")
        super().end_headers()
    def log_message(self,fmt,*args): print("%s - %s"%(self.address_string(),fmt%args))

def main():
    p=argparse.ArgumentParser(description=__doc__); p.add_argument("--root",default="site"); p.add_argument("--host",default="127.0.0.1"); p.add_argument("--port",type=int,default=8000); a=p.parse_args()
    if not Path(a.root,"index.html").is_file(): raise SystemExit(f"Missing {a.root}/index.html. Run mirror.py first.")
    s=ThreadingHTTPServer((a.host,a.port),lambda *x:SPAHandler(*x,directory=a.root)); print(f"Serving {Path(a.root).resolve()} at http://{a.host}:{a.port} (SPA fallback enabled)")
    try:s.serve_forever()
    except KeyboardInterrupt: print("\nStopped.")
    finally:s.server_close()
if __name__=="__main__": main()
