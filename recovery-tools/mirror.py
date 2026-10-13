#!/usr/bin/env python3
"""Recursively mirror a live web funnel's public static assets.

Stores origin files under site/ and external asset files under
site/_external/<host>/ so their paths remain unambiguous. Dynamic APIs are
reported, never represented as downloaded static files.
"""
from __future__ import annotations
import argparse, concurrent.futures, html, mimetypes, os, re, sys, time
from collections import deque
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit, unquote
from urllib.request import Request, urlopen

EXT = r"(?:js|mjs|css|woff2?|ttf|otf|png|jpe?g|webp|svg|gif|ico|json|mp4|webm|avif|map)"
REFS = [
    re.compile(r'''(?:["'(`]|^)((?:/|\./|\.\./)[A-Za-z0-9._~/%%+-]+?\.(?:%s)(?:\?[^"'`\s<>]*)?)''' % EXT, re.I),
    re.compile(r'''["'`]((?:assets|chunks|static/chunks|images|img)/[A-Za-z0-9._~/%%+-]+?\.(?:%s)(?:\?[^"'`\s<>]*)?)["'`]''' % EXT, re.I),
    re.compile(r'''["'`](/?(?:img|images)/[A-Za-z0-9._~/%%+-]+?\.(?:png|jpe?g|webp|svg|gif|avif)(?:\?[^"'`\s<>]*)?)["'`]''' , re.I),
    re.compile(r'''(?:src|href|poster)=["']([^"']+)["']''', re.I),
    re.compile(r'''url\(["']?([^"')]+)["']?\)''', re.I),
    re.compile(r'''https?://[^\s"'`<>\\)]+''', re.I),
]
SKIP_SCHEMES = ("data:", "blob:", "javascript:", "mailto:", "tel:", "#")
class Tags(HTMLParser):
    def __init__(self): super().__init__(); self.refs=[]
    def handle_starttag(self, tag, attrs):
        for k,v in attrs:
            if v and k.lower() in {"src","href","poster","srcset"}:
                self.refs.extend(x.strip().split()[0] for x in v.split(",") if x.strip())

def local_path(url, origin):
    p=urlsplit(url); path=unquote(p.path or "/")
    if p.netloc.lower()==origin.lower(): rel=path.lstrip("/") or "index.html"
    else: rel=f"_external/{p.netloc.lower()}/{path.lstrip('/') or 'index.html'}"
    if p.query: rel += "__q_"+re.sub(r"[^A-Za-z0-9._-]","_",p.query)[:100]
    dest=Path("site")/rel
    if ".." in dest.parts: raise ValueError("unsafe path")
    return dest
def read_url(url, timeout):
    req=Request(url, headers={"User-Agent":"FunnelMirror/1.0 (static recovery)"})
    with urlopen(req, timeout=timeout) as r: return r.status, r.headers.get_content_type(), r.read()
def extract(data, ctype, base):
    try: text=data.decode("utf-8", "replace")
    except Exception: return []
    found=[]
    if "html" in ctype or "xml" in ctype:
        parser=Tags()
        try: parser.feed(text); found.extend(parser.refs)
        except Exception: pass
    for pat in REFS:
        found.extend(m.group(1) for m in pat.finditer(text) if m.lastindex)
        if pat is REFS[-1]: found.extend(m.group(0) for m in pat.finditer(text))
    # XQuiz media UUIDs are embedded in the Next.js Flight payload instead of
    # conventional image URLs; turn every image/logo/favicon UUID into a CDN seed.
    image_uuid=re.compile(r'''\\?["'](?:image|logo|favicon)\\?["']\s*:\s*\{[^{}]{0,500}?\\?["']uuid\\?["']\s*:\s*\\?["']([0-9a-fA-F-]{36})''')
    found.extend("https://cdn.xquiz.co/images/"+m.group(1) for m in image_uuid.finditer(text))
    out=[]
    for ref in found:
        ref=html.unescape(ref.strip().rstrip(".,;"))
        if not ref or ref.startswith(SKIP_SCHEMES): continue
        if ref.startswith("/_external/"):
            parts=ref.split("/",3)
            if len(parts)<4: continue
            u="https://"+parts[2]+"/"+parts[3]
        else:u=urljoin(base,ref)
        s=urlsplit(u)
        if s.scheme not in ("http","https") or not s.path: continue
        path=s.path.lower()
        static=(re.search(r"\.("+EXT+r")$",path,re.I) is not None or
                ("xquiz.co" in s.netloc.lower() and path.startswith("/images/")) or
                (s.netloc.lower()=="fonts.bunny.net" and path.startswith("/css2")))
        if not static: continue
        if s.path.endswith("/"): continue
        out.append(u)
    return list(dict.fromkeys(out))

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("url", help="Funnel entry URL")
    ap.add_argument("--out",default=".",help="Output directory (default: current directory)")
    ap.add_argument("--timeout",type=int,default=25)
    ap.add_argument("--max-files",type=int,default=10000)
    ap.add_argument("--host",action="append",default=[],help="Additional host allowed for recursive mirroring")
    ap.add_argument("--seed",action="append",default=[],help="Additional resource URL to add to the discovery queue")
    args=ap.parse_args(); root=Path(args.out).resolve(); root.mkdir(parents=True,exist_ok=True)
    origin=urlsplit(args.url).netloc.lower(); allowed={origin,*[h.lower() for h in args.host]}
    q=deque([args.url,*args.seed]); seen=set(); errors=[]; skipped=set(); api_refs=set(); done=0; mime_map={}; source_to_web={}
    while q and done < args.max_files:
        url=q.popleft(); p=urlsplit(url); key=url
        if key in seen: continue
        seen.add(key)
        if p.netloc.lower() not in allowed:
            # Preserve linked third-party resources only for domains with recognizable static assets.
            if any(x in p.netloc.lower() for x in ("xquiz.co","fonts.bunny.net")):
                allowed.add(p.netloc.lower())
            else: skipped.add(p.netloc.lower()); continue
        if p.path.endswith("/") and done>0: continue
        dest=root/local_path(url,origin)
        source_to_web[url]="/"+dest.relative_to(root/"site").as_posix()
        if dest.exists() and dest.stat().st_size:
            data=dest.read_bytes()
            ctype=("text/css" if "fonts.bunny.net" in p.netloc.lower() and p.path.startswith("/css2") else
                   ("image/webp" if "cdn.xquiz.co" in p.netloc.lower() and p.path.startswith("/images/") else
                    (mimetypes.guess_type(str(dest))[0] or "application/octet-stream")))
        else:
            try:
                status,ctype,data=read_url(url,args.timeout)
                if status<200 or status>=300: errors.append((url,status)); continue
                dest.parent.mkdir(parents=True,exist_ok=True); dest.write_bytes(data)
                mime_map[dest.relative_to(root).as_posix()]=ctype
            except (HTTPError,URLError,TimeoutError,OSError) as e:
                errors.append((url,str(e))); continue
        if ctype!="application/octet-stream":mime_map[dest.relative_to(root/"site").as_posix()]=ctype
        done+=1
        if ctype.startswith("text/") or dest.suffix.lower() in {".html",".js",".mjs",".css",".json",".map"}:
            try: refs=extract(data,ctype,url)
            except Exception: refs=[]
            for ref in refs:
                rp=urlsplit(ref)
                if rp.path.startswith("/api/") or "/api/" in rp.path: api_refs.add(ref); continue
                if rp.path.endswith("/"): continue
                if rp.netloc.lower() in allowed or any(x in rp.netloc.lower() for x in ("xquiz.co","fonts.bunny.net")):
                    if ref not in seen: q.append(ref)
                else: skipped.add(rp.netloc.lower())
        if done%100==0: print(f"{done} files mirrored; {len(q)} queued")
    # Rewrite references to downloaded static resources to the local mirrored paths.
    for f in (root/"site").rglob("*"):
        if not f.is_file() or (f.suffix.lower() not in {".html",".js",".mjs",".css",".json",".map"} and not f.name.startswith("css2__q_")): continue
        try: text=f.read_text("utf-8")
        except (OSError,UnicodeError): continue
        for source,local in sorted(source_to_web.items(),key=lambda x:-len(x[0])):
            text=text.replace(source,local)
        # Keep the CDN setting a valid URL (the app validates it at runtime),
        # but point generated media URLs back into the local mirror.
        if f.suffix.lower() in {".js",".mjs"}:
            text=text.replace('"https://cdn.xquiz.co"','window.location.origin+"/_external/cdn.xquiz.co"')
            text=text.replace('"/_external/cdn.xquiz.co"','window.location.origin+"/_external/cdn.xquiz.co"')
            # Local copy only: permit the recovered funnel to start on localhost.
            text=text.replace('l.includes(a))?((0,i.Z)("----> host permitido"),!0):((0,i.Z)("----> host n\\xe3o permitido"),!1)','!0)')
        f.write_text(text,"utf-8")
    (root/"site"/"_mime_types.json").write_text(__import__("json").dumps(mime_map,indent=2),"utf-8")
    print(f"Mirrored: {done} files; visited: {len(seen)}; remaining queue: {len(q)}")
    print("Hosts not fetched (analytics/payment/other): "+(", ".join(sorted(skipped)) or "none"))
    print("API-like references: "+("\n  ".join(sorted(api_refs)) or "none detected"))
    if errors:
        print(f"Failures: {len(errors)}")
        for u,e in errors[:100]: print(f"  {e}: {u}")
    if q: print("STOPPED at --max-files; rerun with a larger limit to continue.")
if __name__=="__main__": main()
