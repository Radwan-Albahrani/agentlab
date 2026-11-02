"""The gate's pages: the /_agentlab/ menu (your agent's tools; admins also switch agents and open the hub) and the
"not available" page. Self-contained, no external assets: it must load even when nothing else does. Tool links are
relative because everyone's agent lives on the same domain (which one you reach depends on who you are); sign-ins,
onboarding and app pairing live on the person's hub."""

from html import escape
from urllib.parse import quote

from .config import NONE

TOOLS = (
    ('/', 'Chats', 'T3: your agent chats'),
    ('/_agentlab/accounts/browser', 'Browser', "The agent's screen, while it has a browser open"),
    ('/_agentlab/terminal/', 'Terminal', 'A shell in the workspace'),
    ('/_agentlab/files/', 'Files', 'Browse and transfer workspace files'),
)

STYLE = """
:root{--bg:#f5f5f7;--card:#fff;--fg:#1d1d1f;--muted:#6e6e73;--line:#d2d2d7;--accent:#0071e3;--accent-soft:#e8f1fc;
--warn-soft:#fff4e5;--warn:#a05a00}
@media (prefers-color-scheme:dark){:root{--bg:#000;--card:#1c1c1e;--fg:#f5f5f7;--muted:#98989d;--line:#38383a;
--accent:#2997ff;--accent-soft:#0a2540;--warn-soft:#3a2a10;--warn:#ffb340;color-scheme:dark}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.45 -apple-system,BlinkMacSystemFont,"SF Pro Text",
"Segoe UI",Roboto,Helvetica,Arial,sans-serif;-webkit-font-smoothing:antialiased}
main{max-width:760px;margin:0 auto;padding:56px max(16px,env(safe-area-inset-right)) 64px max(16px,env(safe-area-inset-left))}
h1{font-size:32px;font-weight:700;letter-spacing:-.02em;margin:0 0 4px;text-wrap:balance}
h2{font-size:13px;font-weight:600;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);margin:36px 0 10px}
.who{color:var(--muted);margin:0}
.card{background:var(--card);border:1px solid var(--line);border-radius:18px;padding:18px 20px;margin-bottom:12px}
.card h3{margin:0 0 12px;font-size:17px;font-weight:600}
.banner{background:var(--warn-soft);color:var(--warn);border-radius:14px;padding:12px 16px;margin-top:20px;
display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap}
.banner a{color:inherit;font-weight:600}
.apps{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px}
a.app{display:block;padding:12px 14px;border-radius:12px;background:var(--accent-soft);color:var(--fg);
text-decoration:none;transition:transform .2s cubic-bezier(.32,.72,0,1)}
a.app:hover{transform:translateY(-2px)}
a.app b{display:block;color:var(--accent);font-weight:600}
a.app span{font-size:13px;color:var(--muted)}
.row{display:flex;justify-content:space-between;gap:12px;align-items:center;padding:10px 0;border-top:1px solid var(--line)}
.row:first-child{border-top:0}
.row a{color:var(--accent);text-decoration:none;font-weight:500}
.sub{color:var(--muted);font-size:14px;margin-left:6px}
.empty{color:var(--muted)}
@media (prefers-reduced-motion:reduce){a.app{transition:none}}
"""


def _doc(title, body):
    return (
        f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" '
        f'content="width=device-width,initial-scale=1,viewport-fit=cover"><title>{escape(title)}</title>'
        f'<style>{STYLE}</style></head><body><main>{body}</main></body></html>'
    )


def _rows(ids, current):
    return ''.join(
        f'<div class="row"><span>{escape(i)}</span>'
        + ('<span class="sub">Current</span>' if i == current else f'<a href="/_agentlab/view/{quote(i)}">Open</a>')
        + '</div>'
        for i in ids
    )


def menu(cfg, email, admin, current, pending=False):
    """The picker and switcher. `current` is the agent this domain reaches for this person right now (NONE when they
    have several and haven't picked, or none at all); `pending` means it is theirs and onboarding isn't finished."""
    hub, own = cfg.hub_url(), cfg.owned(email)
    out = ' &middot; <a href="/_agentlab/oidc/logout">Sign out</a>' if cfg.https else ''
    body = f'<h1>{escape(cfg.name)} agents</h1><p class="who">Signed in as {escape(email)}{out}</p>'
    if current != NONE and current not in own:
        owner = cfg.agents[current]['owner']
        body += (
            f'<div class="banner"><span>Viewing <b>{escape(current)}</b> ({escape(owner)})</span>'
            '<a href="/_agentlab/view/me">Stop viewing</a></div>'
        )
    if pending:
        body += (
            '<div class="banner"><span>Finish setting up this agent: sign in to Claude or Codex.</span>'
            f'<a href="{escape(hub)}/agents/{quote(current)}/onboarding">Continue</a></div>'
        )
    if current != NONE:
        tools = [*TOOLS[:1], (f'{hub}/agents/{quote(current)}', 'Accounts', 'Sign-ins, connectors, apps'), *TOOLS[1:]]
        links = ''.join(
            f'<a class="app" href="{escape(href)}"><b>{label}</b><span>{escape(hint)}</span></a>'
            for href, label, hint in tools
        )
        body += f'<h2>Agent</h2><div class="card"><h3>{escape(current)}</h3><div class="apps">{links}</div></div>'
    if own:
        body += f'<h2>Your agents</h2><div class="card">{_rows(own, current)}</div>'
    elif not admin:
        body += '<h2>Your agents</h2><div class="card empty">You don&rsquo;t have an agent yet. Ask an admin to add you.</div>'
    if own or admin:
        body += (
            f'<h2>Hub</h2><div class="card"><div class="row"><span>Sign-ins, apps, companions'
            f'{", the cluster" if admin else ""}</span><a href="{escape(hub)}/">Open</a></div></div>'
        )
    if admin:
        owners = sorted({a['owner'] for i, a in cfg.agents.items() if i not in own})
        groups = ''.join(
            f'<div class="card"><h3>{escape(o)}</h3>'
            f'{_rows([i for i in sorted(cfg.agents) if cfg.agents[i]["owner"] == o], current)}</div>'
            for o in owners
        )
        body += f'<h2>Everyone else</h2>{groups or "<div class=card><span class=empty>Nobody else yet.</span></div>"}'
    return _doc(f'{cfg.name} agents', body)


def denied():
    return _doc(
        'Not available',
        '<h1>Not available</h1><p class="who">You\'re not signed in, or this isn\'t yours. '
        'If you think it should be, ask an admin.</p>',
    )


def signin_failed():
    return _doc(
        'Sign-in did not finish',
        '<h1>Sign-in did not finish</h1><p class="who">It took too long or was interrupted. '
        '<a href="/">Try again</a>.</p>',
    )
