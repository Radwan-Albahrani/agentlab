"""Asks from the hub: the owner writes what they want in a channel (an announcement, a poll, anything) and
The companion gets the agent on it. Each ask gets a thread in the owner's DM with the companion, where they follow the work and can
reply to steer it; whatever the agent prepares for the channel comes back through the outbox as post.json.
The page also changes polls this way (type "poll": single / multiple choice, closing time, close now), re-reads the
open pull requests (type "pulls") and asks for a review of one (type "review")."""

from . import jobs, polls, prompts, reviews, slack, t3, tasks
from .config import COMP, OWNER, default_project, log
from .state import key, lock, new_task
from .text import first_sentence, quote


def tick():
    for ask in COMP.take_asks():
        if ask.get('type') == 'poll':  # a change to one of its polls, made on the page
            with lock:
                polls.change(ask)
        elif ask.get('type') == 'pulls':
            jobs.run_later(reviews.refresh)
        elif ask.get('type') == 'review':
            with lock:
                problem = reviews.request(str(ask.get('repo') or ''), int(ask.get('number') or 0))
            if problem:
                COMP.event(
                    'failed', f'Could not review {ask.get("repo")}#{ask.get("number")}', detail=problem, ok=False
                )
        else:
            jobs.run_later(start, ask)


def start(ask):
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
    tid, err = t3.start_thread(default_project(), title, prompt)
    if not tid:
        slack.post(dm, head, f"Couldn't start: {err}", md=f":warning: I couldn't start on it: {err}")
        COMP.event('failed', f'Could not start: {title}', task=key(dm, head), detail=err, ok=False)
        return
    new_task(dm, head, tid, title, folder, head, slack.note_only(dm, head, tasks.THINKING), review=review)
    log('ask started', tid)
    COMP.event('started', title, task=key(dm, head), detail='from the hub')
