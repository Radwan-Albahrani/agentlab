"""Every message the companion writes for the agent or the triage model."""

from datetime import datetime

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
        return p + colleague_rules(box, guest, owner, channels, approved) + credentials(box, owner, guest)
    then = (
        f'Other channels and people: {owner} approves a preview first.'
        if channel
        else f'{owner} approves a preview first.'
    )
    return (
        p + '\n\nYour final message is posted word for word as your reply in this thread, for everyone in it: the'
        ' answer, readable on its own, not how you got there (no tool or character counts, no "I sent an edit"). If'
        ' there is nothing new because you already posted or edited it, end with exactly one line'
        ' `NO_REPLY: <short reason>` and nothing is posted.'
        + sending(box, owner, channels, then, open_polls, here=True)
        + work_accounts(owner)
        + credentials(box, owner)
    )


def colleague_rules(box, guest, owner, channels, approved=False):
    """A colleague's task: two audiences. The colleague gets only what the agent sends them; the final message and
    everything else goes to the owner, who follows the case (cases.py)."""
    known = ', '.join(f'#{c["name"]}' for c in channels) or '(none yet)'
    rules = (
        f'\n\n## Who hears what\n{guest} is a colleague {owner} lets use {NAME}: you work for {guest} here, with'
        f" {owner}'s tools and logins. You are talking to two people, and you choose what each one hears:"
        f'\n- **{guest}** hears only what you send them: write {box}/send.json:'
        f' {{"text": "<the message, written to {guest}, readable on its own: the answer, not how you got there>",'
        ' "files": ["<names of files you put in the same folder>"]}. It reaches their thread at once. Answer each message'
        f' from {guest} this way; for several messages, write a list. You never post to Slack yourself.'
        f'\n- **{owner}** gets your final message, and only {owner} does: a line or two on what you did and sent,'
        f' and anything they should know or decide. {owner} also sees a copy of everything {guest} says and'
        ' everything you send them.'
        f'\nMessages from {guest} start with "{guest}:". A message without that prefix is {owner} talking to you'
        f' privately: answer in your final message, and send {guest} something only when {owner} tells you to.'
        f'\nAnyone else: add "to": "#<channel>" or "<a person\'s name>" to the message in send.json; {owner}'
        f' approves a preview first. Channels {NAME} is in: {known}.'
        f"\n\n## Needs {owner}'s OK first\nPermissions or access, money, deleting anything, changing settings or"
        ' data in a live service, sharing anything confidential (contracts, HR, salaries, customer data,'
        f' credentials), and anything going outside {org()}. Code on a branch or pull request needs no OK.'
        f' Prepare it without changing anything, write {box}/approval.json: {{"action": "<one line: exactly what will'
        ' change>", "details": "<where, who, current vs new>"}, and tell'
        f' {guest} you are checking with {owner}. The decision arrives as your next message: after "APPROVED" make'
        f' the change, check it worked and tell {guest}; after "REJECTED" change nothing. A newer approval.json'
        ' replaces the waiting one; if you drop the plan, write {"withdraw": "<one line: why>"} instead.'
    )
    return rules + (within_approval(guest, owner) if approved else '')


def within_approval(guest, owner):
    """An approved ask: follow-ups that leave it, or want sensitive information, go back to the owner first."""
    return (
        f'\n{owner} approved this request as {guest} asked it above, and only that. Small refinements are fine. A'
        ' follow-up that makes it a different or clearly bigger job, or asks for sensitive or confidential'
        ' information the request does not need, goes through approval.json first, with "details" saying how it'
        ' differs.'
    )


def follow_up_reminder(owner):
    return (
        f'\n\n(Reminder: if this goes beyond what {owner} approved or asks for sensitive information, check with'
        f' {owner} through approval.json first.)'
    )


def colleague_turn(guest, owner):
    """Tacked onto a colleague's follow-up: who hears what."""
    return f'\n\n({guest} hears only what you send with send.json; your final message goes to {owner}.)'


def side_answer(question, record):
    """For the quick model: a side question about a chat, answered from its record only."""
    return (
        "Someone asked about an AI agent's ongoing work. Answer from the record below only, in at most two short"
        ' sentences (under 40 words): where it is and what it is doing now, or the direct answer to the question.'
        ' No greeting, no preamble, no filler, no headings, no lists, no guessing beyond the record. If the record'
        ' does not say, say so in one sentence.\n\n'
        f'Question: {question}\n\nRecord:\n{record}'
    )


def owner_private(owner, guest, box, said, pending=''):
    """The owner's message in a case thread, for the agent."""
    hold = f' Your approval request ({pending}) still waits for their Approve or Reject: do not make that change.'
    return (
        f'{owner} (private, not {guest}): {said}\n\n---\nAnswer {owner} in your final message; {guest} sees none of'
        f' this. Send {guest} something only if {owner} tells you to, with {box}/send.json.' + (hold if pending else '')
    )


def sending(box, owner, channels, then, open_polls, here=False):
    """How the agent hands over messages, polls and files: send.json (outbox.py, posts.py)."""
    known = ', '.join(f'#{c["name"]}' for c in channels) or f'(none: {NAME} has to be invited first)'
    now = datetime.now().astimezone().isoformat(timespec='minutes')
    return (
        f'\n\n## Sending\nYou never post, send, email or upload anything yourself: {NAME} does, from {box}/send.json.'
        ' Write one message, or a list of them:'
        ' {"to": "<where>", "text": "<standard markdown>", "files": ["<names of files you put in the same folder>"]}'
        + ('\n- "to": "here": this thread, at once (e.g. files to go with your reply).' if here else '')
        + f'\n- "to": "#<channel>": a new message there. Channels {NAME} is in: {known}.'
        f'\n- "to": "<a person\'s name>" (or a list of up to 10): a DM from {NAME}, in {owner}\'s voice as relayed by'
        f' {NAME} ("{owner} asked me to let you know…").'
        f'\n{then} Write the way people talk there: short, clear, friendly. Once it is written, say so in one line.'
        '\nA poll: to a channel, add "poll": {"question": "...", "options": ["<2 to 10 short labels>"], "closes":'
        ' "<ISO 8601 with offset>", "multiple": <true if people may pick several>}. "text" introduces it, without'
        f' the closing time, which {NAME} shows itself. {NAME} runs it (buttons, live count, closing, the winner), so'
        f' you do not watch it. The time now is {now}; with no closing time given, pick a sensible one.'
        + editing(box, owner)
        + poll_changes(box, owner, open_polls)
    )


def editing(box, owner, sent=''):
    """How to edit a message the agent sent through send.json (posts.edit)."""
    return (
        (f'\nMessages you sent for this task so far (id: where: start):\n{sent}' if sent else '')
        + f'\nTo change a message you sent (when {owner} asks), write {box}/send.json with "edit": "<its id: 1, 2, 3'
        ' in the order they went out>" and the complete new "text", and no "to". Never send a correction as a new'
        ' message.'
    )


def poll_changes(box, owner, open_polls):
    """How to change an open poll (poll-change.json); nothing when none is open."""
    if not open_polls:
        return ''
    return (
        f'{open_polls}'
        f'\nTo change an open poll when {owner} asks (switch single / multiple choice, move the closing time), write'
        f' {box}/poll-change.json: {{"poll": "<poll id>", "multiple": true | false, "closes": "<ISO 8601>",'
        ' "text": "<a new intro>"}} with only'
        f' the fields that change. {NAME} applies it at once and says so in the thread; switching to single choice'
        " keeps each voter's latest pick. To vote for someone else (only when asked), add"
        ' "vote": {"for": "<their name as written>", "options": ["<option label>"]} (or "remove": true to take'
        f' their vote back); {NAME} finds the person and marks the vote as added by {owner}.'
    )


def ask(text, owner, channel, channels, folder, review, open_polls):
    """An ask the owner typed on the hub."""
    default = (
        f'It goes to channel {channel} ("to": "{channel}").'
        if channel
        else 'No channel was picked: take it from the words, and ask if it is unclear.'
    )
    then = default + (
        f' {NAME} shows {owner} a preview and posts it when they tap "Post it".'
        if review
        else f' {owner} said not to ask: {NAME} posts it as soon as you write the file, so get it right.'
    )
    return (
        f'{owner} asked from the dashboard:\n\n{text}\n\n---\n'
        f"This is for Slack: {NAME} ({owner}'s Slack assistant) posts as itself; your job is to prepare it. If it"
        ' needs facts (issue tracker, GitHub, the code, email), gather them first.'
        + sending(outbox(folder), owner, channels, then, open_polls)
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
        f'\n\nLanguage: everything for {owner} (your messages, progress, summaries, the approval "action" and'
        f' "details") is in English, whatever language {who} wrote in. Only the "reply" meant for {who} is in'
        f" {who}'s language." + TOOL_CHOICE + approvals(folder, who, owner) + handover(owner, folder)
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


def credentials(box, owner, guest=None):
    """The one way a password leaves: a new account's first-login password, through credential.json."""
    return (
        '\n\nNever put a password or code in a message or file, with one exception: a temporary first-login password'
        f' a service showed you for an account you just created for {guest or "the person who asked"} goes ONLY in'
        f' {box}/credential.json: {{"for": "<their name>", "service": "<name>", "url": "<sign-in address>",'
        ' "username": "...", "password": "...", "note": "<e.g. must be changed at first login>"}.'
        f' {NAME} asks {owner} and then DMs it to them privately. Never vault passwords or 2FA codes.'
    )


def handover(owner, folder):
    """An errand's files and reply: manifest.json (outbox._deliver), plus the owner's work tools."""
    box = outbox(folder)
    return (
        work_accounts(owner)
        + '\n\nNever send, email, upload or post anything to anyone yourself, and never put a password or code in a'
        ' reply or file.'
        f' To hand over files, put them in {box}/ and write {box}/manifest.json LAST:'
        f' {{"what": "<one line>", "files": ["name.png", ...]}}. {NAME} checks them and uploads them into this'
        ' thread (screenshots, recordings, documents, text).'
        '\nOne exception: a temporary first-login password that a service showed you for an account you just created'
        f' for the person who asked goes ONLY in {box}/credential.json: {{"for": "<their name>", "service": "<name>",'
        ' "url": "<sign-in address>", "username": "...", "password": "...", "note": "<e.g. must be changed at first'
        f' login>"}}. {NAME} asks {owner} and then DMs it to them privately. Never vault passwords or 2FA codes.'
    )


def approvals(folder, who, owner):
    box = outbox(folder)
    return (
        f"\n\nSensitive things need {owner}'s explicit approval first: permissions or access, money, deleting"
        ' anything, changing settings or data in any account, sharing anything confidential (contracts, HR,'
        f' salaries, customer data, credentials), and anything going outside {org()}. Routine documents (invoices,'
        f' receipts) and answers for the colleague who asked do NOT need approval: hand them over with'
        f' manifest.json as described below; {NAME} shows them to {owner} anyway. For the sensitive ones,'
        ' prepare everything WITHOUT changing anything (read-only: find the exact place, the person, the setting),'
        f' then write {box}/approval.json: {{"action": "<one line: exactly what will change>", "details": "<where,'
        f' who, current vs new, anything they should know>", "reply": "<what to tell {who} once it is done, in their'
        f' language>", "files": ["<files in {box}/ that would be sent, if any>"]}} and end your turn with one line'
        f' saying you are waiting for approval. {owner} sees those files as a preview and gets'
        ' Approve / Reject buttons; the decision arrives as your next message. Only after "APPROVED" make the'
        ' change, check it worked, and confirm in one line; after "REJECTED" change nothing.'
        f' For things that need no approval, just do them; if {who} should get an answer, put it as "reply" in'
        ' manifest.json (with "files" if any).'
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
