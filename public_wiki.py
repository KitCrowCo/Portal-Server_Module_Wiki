# modules/wiki/public_wiki.py
import re, json
from pathlib import Path
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import HTMLResponse, FileResponse

MODULE_META = {"label": "Wiki (Public)", "public": True}

router = APIRouter()
ENV = {}
UI = None
BI = None
WIKI_ROOT = Path("./data/_common")
TAGS_PATH = Path("./data/wiki/tags.json")

def init_module(env: dict):
    global ENV, UI, BI
    ENV.update(env)
    UI = ENV["templates"].env.globals.get("UI")
    BI = ENV["tools"]["built_ins"]

def _load_tags() -> dict:
    try: return json.loads(TAGS_PATH.read_text()) if TAGS_PATH.exists() else {}
    except Exception: return {}

def _is_public(rel_path: str) -> bool: return "public" in _load_tags().get(rel_path, [])

def resolve_path(rel_path: str) -> Path:
    base = WIKI_ROOT.resolve()
    p = (base / rel_path.lstrip("/")).resolve()
    if not str(p).startswith(str(base)): raise HTTPException(status_code=400, detail="Invalid path")
    return p

def _pub_link(m: re.Match) -> str:
    """[[link]] renderer for public pages - only ever links to other whitelisted pages;
    anything not tagged public renders as disabled text, never a working link or a hint that it exists."""
    target, _, alias = m.group(1).partition("|")
    target, alias = target.strip(), alias.strip()
    has_ext = bool(Path(target).suffix)
    file_path = target if has_ext else f"{target}.md"
    display = alias or Path(target).name
    if _is_public(file_path): return f'<a href="/wiki/{file_path}" style="color:var(--accent);border-bottom:var(--border-thick) dotted var(--accent);text-decoration:none">{UI.escape(display)}</a>'
    return f'<span style="color:var(--text_muted);text-decoration:line-through;" title="Not publicly available">{UI.escape(display)}</span>'

def _pub_embed(m: re.Match) -> str:
    target = m.group(1).strip()
    if not _is_public(target): return f'<span style="color:var(--text_muted);">[unavailable: {UI.escape(target)}]</span>'
    ext = Path(target).suffix.lower()
    url = f"/wiki/raw/{target}"
    if ext in (".png",".jpg",".jpeg",".gif",".webp",".svg"): return f'<img src="{url}" alt="{UI.escape(target)}" style="max-width:100%;border-radius:var(--radius);">'
    if ext in (".mp4",".webm",".ogg"): return f'<video src="{url}" controls style="max-width:100%;"></video>'
    return f'<a href="{url}" style="color:var(--accent)">&#x1F4CE; {UI.escape(target)}</a>'

@router.get("/raw/{path:path}")
async def public_raw(path: str):
    if not _is_public(path): raise HTTPException(status_code=404)
    p = resolve_path(path)
    if not p.exists(): raise HTTPException(status_code=404)
    return FileResponse(p)

@router.get("/{path:path}", response_class=HTMLResponse)
async def public_page(path: str, request: Request):
    rel = path if Path(path).suffix else f"{path}.md"
    if not _is_public(rel): raise HTTPException(status_code=404)
    p = resolve_path(rel)
    if not p.exists() or p.suffix.lower() != ".md": raise HTTPException(status_code=404)
    content = p.read_text(encoding="utf-8")
    content = re.sub(r'!\[\[([^\]]+)\]\]', _pub_embed, content)
    content = re.sub(r'\[\[([^\]]+)\]\]', _pub_link, content)
    rendered = BI.md_plus_transpiler(content, mode="extended")
    theme_diff = await ENV["resolve_theme"](request, module_ns="wiki")
    return ENV["templates"].TemplateResponse(name="public_shell.html", request=request, context={"request": request, "title": p.stem, "theme": ENV["theme"], "theme_diff": theme_diff, "content": rendered})