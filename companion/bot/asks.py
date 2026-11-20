"""Handles the hub's asks (see companion.py); an "ask" becomes a task in the owner's DM with the companion."""

from companion import HubAsk

from . import jobs, machine, polls, projects, prompts, publish, reviews, routing, slack, t3, tasks
from .config import COMP, OWNER, log
from .state import key, lock, new_task
from .text import first_sentence, quote


def tick() -> None:
    for ask in COMP.take_asks():
        if ask.get('type') == 'poll':
            with lock:
                polls.change(ask)
        elif ask.get('type') == 'replay':
            jobs.run_later(routing.replay, str(ask.get('channel') or ''))
        elif ask.get('type') == 'pulls':
            jobs.run_later(refresh_pulls)
        elif ask.get('type') == 'channels':
            jobs.run_later(refresh_channels)
        elif ask.get('type') == 'review':
            with lock:
                problem = reviews.request(str(ask.get('repo') or ''), int(ask.get('number') or 0))
            if problem:
                COMP.event(
                    'failed', f'Could not review {ask.get("repo")}#{ask.get("number")}', detail=problem, ok=False
                )
        else:
            jobs.run_later(start, ask)


def refresh_pulls() -> None:
    """Re-read open pull requests and publish them at once."""
    reviews.refresh()
    publish.now()


def refresh_channels() -> None:
    """Re-read the Slack channels (a hub search found none: maybe one it was just invited to) and publish at once."""
    slack.forget_channels()
    publish.now()


def start(ask: HubAsk) -> None:
    text = str(ask.get('text') or '').strip()[:4000]
    if not text:
        return
    channel = str(ask.get('channel') or '')
    review = ask.get('review') is not False
    where = f'<#{channel}>' if channel else 'a channel the agent picks'
    dm = slack.dm_owner()
    head = slack.post(
        dm,
        None,
        f'From the hub: {first_sentence(text, 120)}',
        md=f':inbox_tray: **From the hub** · for {where}\n' + quote(text),
        note='Working on it. '
        + ('You see the post here before it goes out.' if review else 'It goes out without asking you.'),
    )
    if not head:
        COMP.event('failed', f'Could not take: {first_sentence(text, 80)}', detail='Slack refused the DM', ok=False)
        return
    title = first_sentence(text, 70).rstrip('.')
    folder = f'ask-{head.replace(".", "")}'
    member = [c for c in slack.channels() if c['member']]
    prompt = prompts.ask(text, slack.name(OWNER), channel, member, folder, review, polls.for_prompt())
    where_to = projects.route('ask', text, '', slack.channel_name(channel) if channel else '')
    tid, err = t3.start_thread(where_to['project'], title, prompt)
    if not tid:
        slack.post(dm, head, f"Couldn't start: {err}", md=f":warning: I couldn't start on it: {err}")
        COMP.event('failed', f'Could not start: {title}', task=key(dm, head), detail=err, ok=False)
        return
    t = new_task(
        dm,
        head,
        tid,
        title,
        folder,
        head,
        tasks.post_line(dm, head, tasks.THINKING),
        where_to,
        preview=review,
        audit=tasks.audit(OWNER, 'from the hub'),
        party=machine.party_of(),
    )
    machine.begin_turn(t, 'owner', 'thread')
    log('ask started', tid)
    COMP.event('started', title, task=key(dm, head), detail='from the hub')
