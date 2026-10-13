#!/usr/bin/env python3
"""Heuristic audit of local asset references in mirrored text bundles."""
from __future__ import annotations
import argparse,re
from pathlib import Path
from urllib.parse import urlsplit,unquote

EXT=r"(?:js|mjs|css|woff2?|ttf|otf|png|jpe?g|webp|svg|gif|ico|mp4|webm|avif|json|map)"
IGNORED_HOSTS={"cdn.utmify.com.br","connect.facebook.net","tracking.utmify.com.br","ingest.xquiz.com.br","api.ipify.org","api6.ipify.org"}
PATTERNS=[
 re.compile(r'''["'`(]((?:/|\./|\.\./)[A-Za-z0-9._~/%%+-]+?\.(?:%s)(?:\?[^"'`\s)]*)?)'''%EXT,re.I),
 re.compile(r'''["'`]((?:assets|chunks|static)/[A-Za-z0-9._~/%%+-]+?\.(?:%s)(?:\?[^"'`\s]*)?)["'`]'''%EXT,re.I),
 re.compile(r'''["'`](/?(?:img|images)/[A-Za-z0-9._~/%+-]+?\.(?:png|jpe?g|webp|svg|gif|avif))["'`]''',re.I),
 re.compile(r'''url\(["']?([^"')]+\.(?:woff2?|ttf|otf|png|jpe?g|webp|svg|gif|avif)(?:\?[^"')]+)?)["']?\)''',re.I),
]
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument("--site",default="site");p.add_argument("--base-url",default="https://planocompleto.com/");p.add_argument("--live",action="store_true",help="HEAD-check missing URLs; may be rate-limited");a=p.parse_args(); root=Path(a.site).resolve(); origin=urlsplit(a.base_url).netloc.lower(); refs=set();
 for f in root.rglob("*"):
  if f.is_file() and (f.suffix.lower() in {".html",".js",".mjs",".css",".json",".map"} or f.name.startswith("css2__q_")):
   try:s=f.read_text("utf-8",errors="replace")
   except OSError:continue
   base=f.parent.relative_to(root)
   for pat in PATTERNS:
    for m in pat.finditer(s):
     original=m.group(1); raw,_,query=original.partition("?")
     if raw.startswith(("data:","blob:","#")):continue
     if raw.startswith("http"):
      u=urlsplit(raw)
      if u.netloc.lower() in IGNORED_HOSTS:continue
      external_base=Path("_external")/u.netloc.lower()
      rel=(external_base/Path(unquote(u.path.lstrip("/")))) if u.netloc.lower()!=origin else Path(unquote(u.path.lstrip("/")))
     else:
      raw=raw.removeprefix("./")
      if raw.startswith("/_external/"): rel=Path(unquote(raw.lstrip("/")))
      elif raw.startswith("/") and len(base.parts)>=2 and base.parts[0]=="_external": rel=Path(base.parts[0])/base.parts[1]/Path(unquote(raw.lstrip("/")))
      else: rel=(Path(unquote(raw.lstrip("/"))) if raw.startswith("/") else base/Path(unquote(raw)))
     if query: rel=Path(str(rel)+"__q_"+re.sub(r"[^A-Za-z0-9._-]","_",query)[:100])
     refs.add((root/rel).resolve())
 # XQuiz stores image URLs by UUID in the embedded funnel JSON.
 try: shell=(root/"index.html").read_text("utf-8",errors="replace")
 except OSError:shell=""
 uuid_pat=re.compile(r'''\\?["'](?:image|logo|favicon)\\?["']\s*:\s*\{[^{}]{0,500}?\\?["']uuid\\?["']\s*:\s*\\?["']([0-9a-fA-F-]{36})''')
 for m in uuid_pat.finditer(shell):refs.add((root/"_external"/"cdn.xquiz.co"/"images"/m.group(1)).resolve())
 missing=sorted(x for x in refs if not x.is_file()); present=len(refs)-len(missing)
 print(f"Asset references (heuristic): {len(refs)}\nPresent on disk: {present}\nMissing: {len(missing)}")
 for x in missing:print("MISSING "+str(x))
 if a.live and missing:
  import urllib.request,urllib.error
  print("\nLive checks are best-effort; inferred/template paths may not be real files.")
  for x in missing:
   try: rel=x.relative_to(root.resolve()).as_posix(); url=a.base_url.rstrip("/")+"/"+rel; req=urllib.request.Request(url,method="HEAD",headers={"User-Agent":"FunnelMirror-Audit/1.0"});
   except ValueError:continue
   try:
    with urllib.request.urlopen(req,timeout=10) as r:print(f"{r.status} {url}")
   except urllib.error.HTTPError as e:print(f"{e.code} {url}")
   except Exception as e:print(f"ERR {e} {url}")
if __name__=="__main__":main()
