"""Every message the companion writes for the agent (or the triage model), in one place so the wording is easy to
review."""

from datetime import datetime

from .config import AGENT_FILES, NAME, org, work_tools


def outbox(folder):
    return f'{AGENT_FILES}/outbox/{folder}'


def task(ask, owner, where, lines, files, folder, channel, channels, open_polls):
    """A task the owner gave the companion in Slack (channel: the channel it came from, '' for a DM)."""
    p = ask + f'\n\n---\nThe Slack thread this came from ({owner} asked in {where}), complete:\n'
    p += '\n'.join(lines[-60:]) or '(no other messages)'
    if files:
        p += '\n\nIts attachments, already downloaded for you:\n' + '\n'.join(f'- {f}' for f in files)
    p += (
        '\n\nThat is the whole thread, so there is no need to open Slack in the browser; if you need more from'
        ' Slack, use your Slack tools with the channel and thread above.'
        '\nYour replies are posted back to that Slack thread, so make your final message readable on its own.'
        ' Gather whatever else you need (issue tracker, GitHub, error monitoring, the code) before you start.'
    )
    default = (
        f'With no "channel" it goes to this channel ({channel}) as a new message, right away: {owner} asked here.'
        if channel
        else 'Name the channel.'
    )
    then = 'Any other channel gets a preview they approve first.' if channel else f'{owner} approves a preview first.'
    return p + posting(outbox(folder), owner, channels, default, then, open_polls) + work_accounts(owner, folder)


def posting(box, owner, channels, default, then, open_polls):
    """How the agent hands the companion a message or poll for a channel (it posts it; see bot/posts.py)."""
    known = '\n'.join(f'- #{c["name"]} (id {c["id"]})' for c in channels) or f'(none: {NAME} has to be invited first)'
    now = datetime.now().astimezone().isoformat(timespec='minutes')
    return (
        f'\n\nTo post a message or run a poll in Slack, write {box}/post.json:'
        ' {"channel": "<channel id>", "text": "<the message, standard markdown>",'
        ' "poll": {"question": "...", "options": ["...", "..."], "closes": "<ISO 8601 time with offset>",'
        ' "multiple": <true when people may pick several options, e.g. "multi choice" or "pick all that work">}}'
        f'\n{default} Channels {NAME} can post in:\n{known}'
        f'\nTo message people directly instead (when {owner} asks to tell, notify or ping someone in their DMs), use'
        ' "to": "<their name as written, or @mention>" (or a list of up to 10) in place of "channel";'
        f' {NAME} finds each person and sends it to them from its own DM, after {owner} approves a preview. Write it'
        f' to them, in {owner}\'s voice as relayed by {NAME} (e.g. "{owner} asked me to let you know…"). No polls by'
        ' DM.'
        '\nLeave "poll" out for a plain message. A poll is a new message of its own: "text" introduces it and carries'
        ' the details (links, descriptions, one line per option) but never the closing time, which'
        f' {NAME} shows itself and keeps current; the "options" are short button labels (2 to 10,'
        f' at most 75 characters, e.g. "Fatto (Italian)"). The time now is {now}; read "ends at 2pm" as today in'
        ' this time zone (tomorrow if that has passed), and with no closing time pick a sensible one (e.g. the end of'
        f' the working day). {NAME} runs the poll itself: voting buttons, the live count, closing on time and'
        f' announcing the winner in the channel, so you do not watch it. {then} Never post to Slack yourself, and'
        ' write it the way people talk in that channel: short, clear, friendly. If you are asked for changes, write'
        ' post.json again. Once it is written, end with one short line.' + poll_changes(box, owner, open_polls)
    )


def poll_changes(box, owner, open_polls):
    """How to change an open poll; also added to a later message about a poll, for chats started before polls."""
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
    """The owner typed this on the hub: something for a Slack channel (an announcement, a poll, …)."""
    default = (
        f'It goes to channel {channel}.'
        if channel
        else 'No channel was picked: take it from the words, and ask if it is unclear.'
    )
    then = (
        f'{NAME} shows {owner} a preview and posts it when they tap "Post it".'
        if review
        else f'{owner} said not to ask: {NAME} posts it as soon as you write the file, so get it right.'
    )
    return (
        f'{owner} asked from the dashboard:\n\n{text}\n\n---\n'
        f"This is for Slack: {NAME} ({owner}'s Slack assistant) posts as itself; your job is to prepare it. If it"
        ' needs facts (issue tracker, GitHub, the code, email), gather them first.'
        + posting(outbox(folder), owner, channels, default, then, open_polls)
    )


def errand(who, how, owner, asked, lines, files, folder):
    """Someone asked the owner for something; the agent handles it as them."""
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
        f" {who}'s language." + TOOL_CHOICE + approvals(folder, who, owner) + work_accounts(owner, folder)
    )


# Connected tools (MCP) are exact and audited; the browser is the fallback.
TOOL_CHOICE = (
    '\n\nTools: check which connected (MCP) tools this chat has before opening the browser, and use a matching one'
    ' for lookups and approved changes alike. Use the browser only when no tool covers it or the tool is down,'
    ' never to get around a tool that refused. After a change, read the state back to confirm it; if the result'
    ' is unclear, check before retrying so nothing happens twice.'
)


def work_accounts(owner, folder):
    """How the agent hands files and logins back through the gate, plus whatever work tools the owner set up
    (the optional work-tools.md secret, e.g. read-only mail search or a password vault CLI)."""
    box = outbox(folder)
    tools = work_tools()
    return (
        (f"\n\nIf this needs something from {owner}'s work accounts:\n{tools}" if tools else '')
        + '\n\nNever send, email, upload or post anything to anyone yourself, and never put a password or code in a'
        ' reply or file.'
        f' To hand over files, put them in {box}/ and write {box}/manifest.json LAST:'
        f' {{"for": "<who needs it>", "what": "<one line>", "files": ["name.pdf", ...]}}. {NAME} checks and'
        ' delivers them.'
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
    """Team mode: what does a colleague's message to the owner need? Errand is the strict one."""
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


def revise_draft(folder, key, owner, feedback, next_revision):
    return (
        f'Revise the product update draft in {folder}/{key}/ (update.md, the screenshots listed in '
        f'ready.json). Feedback from {owner}:\n\n{feedback}\n\n'
        'Keep everything else as it is. The screenshots are attached as files, so never reference them inside '
        'update.md (no ![...](...) lines). Rewrite update.md (standard markdown) and any screenshots you '
        f'change, then rewrite ready.json LAST with "revision": {next_revision}. Do not post anything '
        'to Slack; the new draft is previewed for approval automatically.'
    )
