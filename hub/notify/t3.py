"""Reading an agent's T3 database (statev2.sqlite, opened read-only) for what a ping says."""

import json
import os
import re
import sqlite3
from datetime import datetime
from urllib.parse import quote

from .text import last_question, plain, short

T3 = os.environ.get('NOTIFY_T3', '/agents/{id}/home/.t3/userdata')  # holds statev2.sqlite
# Chats started through T3's API: subagents, orchestrator workers, companion tasks (companions report those).
IS_WORKER = "json_extract(t.payload_json, '$.creationSource') in ('mcp', 'provider')"


def connect(profile):
    return sqlite3.connect(f'file:{T3.format(id=profile)}/statev2.sqlite?mode=ro', uri=True, timeout=3)


def ts(iso):
    return datetime.fromisoformat(iso.replace('Z', '+00:00')).timestamp() if iso else 0.0


def thread_link(profile, tid):
    """Opens that chat in the T3 iPhone app (scheme t3code, route /threads/<environment>/<thread>, as the app's
    own notifications do in pingdotgg/t3code apps/mobile)."""
    try:
        with open(f'{T3.format(id=profile)}/environment-id') as f:
            env = f.read().strip()
    except OSError:
        return ''
    return f't3code://threads/{quote(env, safe="")}/{quote(tid, safe="")}' if env else ''


def newest_chat_link(profile):
    """A tap-through link to the agent's most recent chat started by the owner ('' if there is none)."""
    try:
        con = connect(profile)
        try:
            row = con.execute(
                'select thread_id from orchestration_v2_projection_threads where deleted_at is null'
                " and json_extract(payload_json, '$.createdBy') = 'user' order by updated_at desc limit 1"
            ).fetchone()
        finally:
            con.close()
    except sqlite3.Error:
        return ''
    return thread_link(profile, row[0]) if row else ''


def last_text(q, rid):
    row = q(
        """select json_extract(payload_json, '$.text') from orchestration_v2_projection_messages
               where run_id = ? and role = 'assistant' order by created_at desc limit 1""",
        (rid,),
    ).fetchone()
    return (row[0] if row else '') or ''


def request_item(q, tid, rqid):
    """The turn item behind a question/approval request: it holds the questions and options."""
    for (payload,) in q(
        """select payload_json from orchestration_v2_projection_turn_items
                           where thread_id = ? and type like '%request%' order by ordinal desc limit 20""",
        (tid,),
    ):
        try:
            item = json.loads(payload)
        except ValueError:
            continue
        if item.get('requestId') == rqid:
            return item
    return {}


def describe_question(item):
    """(headline, details). iOS previews only ~250 characters, so the headline is the asked sentence plus the
    option names; the details are each option's explanation, then the background."""
    qs = item.get('questions') or []
    if not qs:
        return 'The agent is waiting for your answer.', ''
    head = []
    for n, qq in enumerate(qs):
        tag = qq.get('header') if qq.get('header') not in (None, '', 'Question') else ''
        num = f'{n + 1}/{len(qs)} ' if len(qs) > 1 else ''
        head.append(f'{num}{tag + ": " if tag else ""}{last_question(qq.get("question", ""))}')
        labels = [
            short(re.sub(r'\s*\(Recommended\)', ' (recommended)', o.get('label', '')), 40)
            for o in qq.get('options') or []
        ][:5]
        head += [f'{i + 1}️⃣ {label}' for i, label in enumerate(labels)]
        if labels and qq.get('multiSelect'):
            head.append('(pick one or more)')
    lines, context = [], []
    for qq in qs:
        for i, o in enumerate(qq.get('options') or []):
            desc = o.get('description', '')
            if desc and desc != o.get('label'):
                lines.append(f'{chr(9312 + i)} {short(desc, 80)}')  # the label is already in the headline
        if qq.get('multiSelect'):
            lines.append('(pick one or more)')
        q = re.sub(r'\s+', ' ', qq.get('question', '')).strip()
        asked = last_question(q).rstrip('…')
        rest = q.replace(asked, ' ', 1).strip() if asked in q else ''
        if len(rest) > 3:
            context.append(re.sub(r'\s+', ' ', rest))  # the sentences around the actual question
    if context:
        lines.append('ℹ︎ ' + ' '.join(context))  # noqa: RUF001 - the info emoji, on purpose
    return '\n'.join(head), '\n'.join(lines)


def describe_approval(item):
    what = ''
    for k in ('title', 'reason', 'description', 'command', 'input'):
        v = item.get(k)
        if isinstance(v, str) and v.strip():
            what = v
            break
        if isinstance(v, (dict, list)) and v:
            what = json.dumps(v)[:400]
            break
    return '', plain(what) or 'The agent wants permission to continue.'
