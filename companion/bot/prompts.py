"""Every message the companion writes for the agent or the triage model."""

from datetime import datetime

from . import when
from .config import AGENT_FILES, NAME, RECENT, RECENT_DM, org, work_tools


def outbox(folder):
    return f'{AGENT_FILES}/outbox/{folder}'


def task(
    ask,
    owner,
    where,
    lines,
    files,
    folder,
    channel,
    channels,
    open_polls,
    guest=None,
    fresh=False,
    approved=False,
    history=(),
):
    """A task given in Slack by the owner, or by a `guest` they gave access (channel: '' for a DM).
    fresh: asked in a new message, not in a thread, so `lines` are only what came just before it.
    approved: the owner approved this one ask (the requests channel), so follow-ups stay within it.
    history: what the companion did with this person lately (its own records), for a message that refers back."""
    who = guest or owner
    if fresh:
        span = f'{RECENT_DM // 86400} days' if not channel else f'{RECENT // 60} minutes'
        p = ask + (
            f'\n\n---\n{who} wrote this in a new message in {where}. For context, the messages there in the {span}'
            ' before it (the last one is the request; earlier ones are past conversations, so leave them alone unless'
            ' the request points to them):\n'
        )
    else:
        p = ask + f'\n\n---\n{who} asked in {where}. The whole thread (use your Slack tools only if you need more):\n'
    p += '\n'.join(lines[-60:]) or '(no other messages)'
    if history:
        p += (
            f'\n\nYour recent work with {who}, newest last. A short message like "done" or "I fixed them" probably'
            ' refers to one of these: check its T3 chat before asking what they mean.\n' + '\n'.join(history)
        )
    if files:
        p += '\n\nAttachments, downloaded for you:\n' + '\n'.join(f'- {f}' for f in files)
    p += '\n\nGather what you need first (issue tracker, GitHub, error monitoring, the code).'
    box = outbox(folder)
    if guest:
        return p + colleague_rules(box, guest, owner, channels, approved)
    then = 'Messages to this channel go at once; anywhere else' if channel else 'Everything'
    return (
        p + '\n\n## Your final message\nIt is posted word for word as your reply in this thread, for everyone in it:'
        ' the answer, readable on its own, not how you got there (no tool or character counts, no "I sent an edit").'
        ' If there is nothing new to say, end with exactly one line `NO_REPLY: <short reason>` and nothing is posted.'
        + sending(
            box,
            owner,
            [
                '"thread": this thread, at once (files or extra messages to go with your reply)',
                *elsewhere(owner, channels, f'{then} waits for {owner} to approve a preview'),
            ],
            polls_and_edits(owner, open_polls),
        )
        + work_accounts(owner)
    )


def colleague_rules(box, guest, owner, channels, approved=False):
    """A colleague's task: two audiences, each told on purpose (cases.py): the colleague hears only what the agent
    sends them; its final message is the owner's."""
    rules = (
        f'\n\n## Who hears what\n{guest} is a colleague {owner} lets use {NAME}: you work for {guest} here, with'
        f" {owner}'s tools and logins. You talk to two people and choose what each one hears:"
        f'\n- **{guest}** hears only the messages you send them ("to": "{guest}"). Answer each message from {guest}'
        ' this way, written to them, readable on its own: the answer, not how you got there.'
        f'\n- **{owner}** gets your final message, and only {owner} does: a line or two on what you did and sent,'
        f' and anything they should know or decide. {owner} also sees a copy of everything {guest} says and'
        ' everything you send them.'
        f'\nMessages from {guest} start with "{guest}:". A message without that prefix is {owner} talking to you'
        f' privately: answer in your final message, and send {guest} something only when {owner} tells you to.'
        + sending(
            box,
            owner,
            [f'"{guest}": their thread, at once', *elsewhere(owner, channels, f"Anyone else waits for {owner}'s OK")],
            approvals(owner, guest, f'tell {guest} you are checking with {owner}'),
        )
        + credentials(guest)
    )
    return rules + (within_approval(guest, owner) if approved else '')


def within_approval(guest, owner):
    """An approved ask: follow-ups that leave it, or want sensitive information, go back to the owner first."""
    return (
        f'\n{owner} approved this request as {guest} asked it above, and only that. Small refinements are fine. A'
        ' follow-up that makes it a different or clearly bigger job, or asks for sensitive or confidential'
        ' information the request does not need, needs an "approval" first, with "details" saying how it differs.'
    )


def follow_up_reminder(owner):
    return (
        f'\n\n(Reminder: if this goes beyond what {owner} approved or asks for sensitive information, send an'
        f' "approval" to {owner} first.)'
    )


def colleague_turn(guest, owner):
    """Tacked onto a colleague's follow-up: who hears what."""
    return f'\n\n({guest} hears only what you send them with "to": "{guest}"; your final message goes to {owner}.)'


def side_answer(question, record):
    """For the quick model: a side question about a chat, answered from its record only."""
    return (
        "Someone asked about an AI agent's ongoing work. Answer from the record below only, in at most two short"
        ' sentences (under 40 words): where it is and what it is doing now, or the direct answer to the question.'
        ' No greeting, no preamble, no filler, no headings, no lists, no guessing beyond the record. If the record'
        f' does not say, say so in one sentence. {when.RULE}\n\n'
        f'Question: {question}\n\nRecord:\n{record}'
    )


def owner_private(owner, guest, box, said, pending=''):
    """The owner's message in a case thread, for the agent."""
    hold = f' Your approval request ({pending}) still waits for their Approve or Reject: do not make that change.'
    return (
        f'{owner} (private, not {guest}): {said}\n\n---\nAnswer {owner} in your final message; {guest} sees none of'
        f' this. Send {guest} something only if {owner} tells you to ({box}/send.json, "to": "{guest}").'
        + (hold if pending else '')
    )


def sending(box, owner, recipients, more=''):
    """The outbox (outbox.py): one file, typed items, an explicit "to", and receipts to check."""
    return (
        f'\n\n## Sending\nYou never post, send, email or upload anything yourself: {NAME} does, from {box}/send.json'
        ' (one item, or a list). Every item has a "type", and a message says who it is "to"; nothing has a default.'
        '\n- {"type": "message", "to": "<who>", "text": "<standard markdown>", "files": ["<names>"]}. "to" is one of:'
        + ''.join(f'\n  - {r}' for r in recipients)
        + f'\nFiles you send go in {box}/ first; name them in "files". Write messages the way people talk there:'
        f' short, clear, friendly. {when.RULE} That goes for your final message too. It is {when.say(form="date")}'
        ' now.'
        + more
        + f'\nWhat became of each item (sent, waiting for {owner}, approved, rejected, refused and why) is in'
        f' {box}/receipts.json, by "id". Check it before you say something went out, and fix what was refused.'
    )


def elsewhere(owner, channels, rule):
    known = ', '.join(f'#{c["name"]}' for c in channels) or f'none: {NAME} has to be invited first'
    return [
        f'"#<channel>": a new message there (channels {NAME} is in: {known})',
        f'"<a person\'s name>", or a list of up to 10: a DM from {NAME}, in {owner}\'s voice as relayed by {NAME}'
        f' ("{owner} asked me to let you know…")',
        f'{rule}.',
    ]


def polls_and_edits(owner, open_polls, sent=''):
    now = datetime.now().astimezone().isoformat(timespec='minutes')
    return (
        '\n- A poll: a message to a channel with "poll": {"question": "...", "options": ["<2 to 10 short labels>"],'
        ' "closes": "<ISO 8601 with offset>", "multiple": <true if people may pick several>}. "text" introduces it,'
        f' without the closing time, which {NAME} shows itself; {NAME} runs it (buttons, count, closing, the winner).'
        f' The time now is {now} (ISO, for "closes"); with no closing time given, pick a sensible one.'
        + editing(owner, sent)
        + poll_changes(owner, open_polls)
    )


def editing(owner, sent=''):
    """How to change a message the agent sent (posts._apply_edit)."""
    return (
        (f'\nMessages you sent so far (id: where: start):\n{sent}' if sent else '')
        + f'\n- {{"type": "edit", "id": "<the message\'s id>", "text": "<the complete new text>"}}: changes a message'
        f' you sent to a channel or person, wherever it went (when {owner} asks). Never send a correction as a new'
        ' message.'
    )


def poll_changes(owner, open_polls):
    """How to change an open poll; nothing when none is open."""
    if not open_polls:
        return ''
    return (
        f'{open_polls}'
        '\n- {"type": "poll_change", "poll": "<poll id>", ...only the fields that change: "multiple": true | false,'
        ' "closes": "<ISO 8601>", "text": "<a new intro>"}. To vote for someone (only when asked), add'
        ' "vote": {"for": "<their name>", "options": ["<option label>"]} (or "remove": true).'
        f" {NAME} applies it at once; switching to single choice keeps each voter's latest pick; a vote shows as added"
        f' by {owner}.'
    )


def approvals(owner, who, then):
    return (
        f"\n- Needs {owner}'s OK first: permissions or access, money, deleting anything, changing settings or data in a"
        ' live service or account, sharing anything confidential (contracts, HR, salaries, customer data,'
        f' credentials), and anything going outside {org()}. Code on a branch or pull request needs no OK. Prepare it'
        ' without changing anything, then send {"type": "approval", "action": "<one line: exactly what will'
        ' change>", "details": "<where, who, current vs new>", "files": ["<files that would go out>"]}'
        f' and {then}. The decision arrives as your next message: after "APPROVED" make the change and check it'
        ' worked; after "REJECTED" change nothing. A newer approval replaces the one waiting;'
        ' {"type": "withdraw", "why": "..."} takes it back when you drop the plan.'
    )


def ask(text, owner, channel, channels, folder, review, open_polls):
    """An ask the owner typed on the hub."""
    picked = (
        f'It goes to channel {channel} ("to": "{channel}").'
        if channel
        else 'No channel was picked: take it from the words, and ask if it is unclear.'
    )
    rule = (
        f'{owner} approves a preview first'
        if review
        else f'{owner} said not to ask: it goes out at once, so get it right'
    )
    return (
        f'{owner} asked from the dashboard:\n\n{text}\n\n---\n'
        f"This is for Slack: {NAME} ({owner}'s Slack assistant) posts as itself; your job is to prepare it. {picked}"
        ' If it needs facts (issue tracker, GitHub, the code, email), gather them first.'
        + sending(outbox(folder), owner, elsewhere(owner, channels, rule), polls_and_edits(owner, open_polls))
    )


def errand(who, how, owner, asked, lines, files, folder):
    """An errand: someone asked the owner for something; the agent handles it as them."""
    return (
        f'{who} {how} in Slack, asking:\n\n{asked}\n\n---\nThe conversation around it:\n'
        + ('\n'.join(lines[-40:]) or '(nothing else)')
        + (('\n\nAttachments, downloaded for you:\n' + '\n'.join(f'- {f}' for f in files)) if files else '')
        + f'\n\nYou are handling this for {owner} while they are busy, as them, with their connected tools and'
        ' browser logins.'
        f' First decide: is {who} asking {owner} for something you can do yourself (get access or documents, look'
        f' something up, change something in a service {owner} manages, check the code)? If not, or it needs'
        f' {owner} personally (a decision, an opinion, a promise), reply with exactly one line'
        ' `NO_ACTION: <short reason>` and stop.'
        f'\n\nYour final message goes to {owner}, in this thread. Language: everything for {owner} is in English,'
        f" whatever language {who} wrote in; only messages to {who} are in {who}'s language."
        + TOOL_CHOICE
        + sending(
            outbox(folder),
            owner,
            [
                f'"{who}": your answer to them, with any documents (invoices, receipts) as "files". {owner} taps Send'
                ' first, unless it follows an approval they just gave',
                f'"thread": {owner}, in this thread (files for them to look at)',
            ],
            approvals(owner, who, 'end your turn with one line saying you are waiting for approval')
            + f' An approval may carry "reply": "<what to tell {who} once it is done>"; it goes to them when your'
            ' approved turn completes.',
        )
        + credentials(who)
        + work_accounts(owner)
    )


TOOL_CHOICE = (
    '\n\nTools: check which connected (MCP) tools this chat has before opening the browser, and use a matching one'
    ' for lookups and approved changes alike. Use the browser only when no tool covers it or the tool is down,'
    ' never to get around a tool that refused. After a change, read the state back to confirm it; if the result'
    ' is unclear, check before retrying so nothing happens twice.'
)


def work_accounts(owner):
    """The owner's work tools (work-mail, work-secret), for the owner's own tasks and errands."""
    tools = work_tools()
    return f"\n\nIf this needs something from {owner}'s work accounts:\n{tools}" if tools else ''


def credentials(person):
    """The one way a password leaves: a new account's first-login password, as a credential item."""
    return (
        '\n\nNever put a password or code in a message or file, with one exception: a temporary first-login password'
        f' a service showed you for an account you just created for {person} goes ONLY in a'
        ' {"type": "credential", "service": "<name>", "url": "<sign-in address>", "username": "...", "password": "...",'
        f' "note": "<e.g. must be changed at first login>"}}. {NAME} asks first, then DMs it to {person} privately.'
        ' Never vault passwords or 2FA codes.'
    )


def triage(owner, who, convo, texts):
    """Team-mode triage of a colleague's message to the owner."""
    return (
        f'You triage Slack messages for {owner} (works at {org()}) and their assistant. The assistant can use'
        f" {owner}'s connected work tools, their browser logins and the codebase"
        + (', plus their work accounts' if work_tools() else '')
        + '.\n\nEarlier in this conversation:\n'
        + (convo or '(nothing)')
        + f'\n\nNew message(s) from {who}:\n'
        + '\n'.join(texts)
        + f'\n\nClassify what {who} wants from {owner}:'
        '\n- "errand": an unmistakable, small, concrete request the assistant can finish alone: send or find'
        ' documents or invoices, give or change access to a work tool, look one thing up. Only when it is clearly'
        ' asked for; when in doubt it is not an errand.'
        '\n- "task": real work: building, fixing or investigating something in the product or code, or anything'
        ' bigger or open-ended.'
        f'\n- "nothing": greetings, thanks, small talk, FYIs, opinions, decisions, scheduling, or anything only'
        f' {owner} can answer.'
        '\nReply with JSON only: {"kind": "errand" | "task" | "nothing", "what": "<one short line in English: what'
        ' is asked>"}'
    )


def revise_draft(folder, key, owner, feedback, next_revision, video=False):
    if video:
        return (
            f'Revise the product update draft in {folder}/{key}/ (update.md, the attachments (screenshots or video) '
            f'listed in ready.json under "images"). Feedback from {owner}:\n\n{feedback}\n\n'
            'Keep everything else as it is. The attachments (screenshots or video) are attached as files, so never '
            'reference them inside update.md (no ![...](...) lines or links to them). Rewrite update.md (standard '
            'markdown) and any attachments you change (you may replace or re-render the video), then rewrite '
            f'ready.json LAST with "revision": {next_revision}. Do not post anything to Slack; the new draft is '
            'previewed for approval automatically.'
        )
    return (
        f'Revise the product update draft in {folder}/{key}/ (update.md, the screenshots listed in '
        f'ready.json). Feedback from {owner}:\n\n{feedback}\n\n'
        'Keep everything else as it is. The screenshots are attached as files, so never reference them inside '
        'update.md (no ![...](...) lines). Rewrite update.md (standard markdown) and any screenshots you '
        f'change, then rewrite ready.json LAST with "revision": {next_revision}. Do not post anything '
        'to Slack; the new draft is previewed for approval automatically.'
    )
