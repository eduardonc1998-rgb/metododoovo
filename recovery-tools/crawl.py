#!/usr/bin/env python3
"""Convenience launcher for the bundled Playwright crawler (crawl.mjs)."""
import os, shutil, subprocess, sys
from pathlib import Path

here=Path(__file__).resolve().parent
node=os.environ.get('NODE','node')
if shutil.which(node) is None:
    raise SystemExit('Node.js was not found. Install Node.js 20+ and the Playwright package, then retry.')
env=os.environ.copy()
if 'NODE_PATH' not in env:
    env['NODE_PATH']=str(Path(r'C:\Users\Usuario\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\node_modules'))
script=here/'crawl.mjs'
raise SystemExit(subprocess.call([node,str(script),*sys.argv[1:]],cwd=here,env=env))
