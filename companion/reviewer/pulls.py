"""Pull requests via the App: the open list, a review's starting facts, and publishing the result."""

import base64

from .github import GitHubError

LIST = """query($q: String!) { search(query: $q, type: ISSUE, first: 100) { nodes { ... on PullRequest {
  number title url isDraft additions deletions createdAt updatedAt headRefOid
  author { login avatarUrl } repository { nameWithOwner }
  labels(first: 12) { nodes { name color } }
  commits(last: 1) { nodes { commit { statusCheckRollup { state } } } } } } } }"""

THREADS = """query($owner: String!, $name: String!, $number: Int!) { repository(owner: $owner, name: $name) {
  pullRequest(number: $number) { reviewThreads(first: 100) { nodes { id isResolved isOutdated path line
    comments(first: 30) { nodes { id author { login } body createdAt
      reactionGroups { content reactors { totalCount } } } } } } } } }"""

CI = {'SUCCESS': 'passing', 'FAILURE': 'failing', 'ERROR': 'failing', 'PENDING': 'running', 'EXPECTED': 'running'}


def open_pulls(app):
    """Every open PR the App can see, newest activity first."""
    out = []
    for inst in app.installations():
        q = f'is:pr is:open archived:false sort:updated-desc user:{inst["account"]}'
        for n in app.graphql(LIST, inst['id'], q=q)['search']['nodes']:
            if not n:
                continue
            rollup = ((n['commits']['nodes'] or [{}])[0].get('commit') or {}).get('statusCheckRollup') or {}
            author = n.get('author') or {}
            out.append(
                {
                    'id': f'{n["repository"]["nameWithOwner"]}#{n["number"]}',
                    'repo': n['repository']['nameWithOwner'],
                    'number': n['number'],
                    'title': n['title'],
                    'url': n['url'],
                    'draft': n['isDraft'],
                    'author': author.get('login', 'ghost'),
                    'avatar': author.get('avatarUrl', ''),
                    'labels': [{'name': lb['name'], 'color': lb['color']} for lb in n['labels']['nodes']],
                    'additions': n['additions'],
                    'deletions': n['deletions'],
                    'created': n['createdAt'],
                    'updated': n['updatedAt'],
                    'head': n['headRefOid'],
                    'ci': CI.get(rollup.get('state', ''), ''),
                }
            )
    out.sort(key=lambda p: p['updated'], reverse=True)
    return out


def facts(app, repo, number):
    """What a review starts from: the PR, its changed files with patches, and its review threads."""
    inst = app.installation_for(repo)
    if inst is None:
        raise GitHubError(404, f'the App is not installed on {repo.split("/")[0]}')
    pr = app.call('GET', f'/repos/{repo}/pulls/{number}', installation=inst)
    files = app.pages(f'/repos/{repo}/pulls/{number}/files', inst)
    owner, name = repo.split('/', 1)
    threads = app.graphql(THREADS, inst, owner=owner, name=name, number=int(number))['repository']['pullRequest']
    bot = app.slug()
    return {
        'installation': inst,
        'repo': repo,
        'number': int(number),
        'title': pr['title'],
        'body': pr.get('body') or '',
        'url': pr['html_url'],
        'author': pr['user']['login'],
        'state': pr['state'],
        'draft': pr.get('draft', False),
        'head': pr['head']['sha'],
        'head_ref': pr['head']['ref'],
        'fork': (pr['head'].get('repo') or {}).get('full_name') != repo,
        'base': pr['base']['sha'],
        'repo_id': pr['base']['repo']['id'],
        'base_ref': pr['base']['ref'],
        'files': [
            {
                'path': f['filename'],
                'status': f['status'],
                'additions': f['additions'],
                'deletions': f['deletions'],
                'patch': f.get('patch') or '',
            }
            for f in files
        ],
        'threads': [_thread(t, bot) for t in threads['reviewThreads']['nodes']],
        'bot': bot,
    }


def _thread(t, bot):
    comments = t['comments']['nodes']
    first = comments[0] if comments else {}
    reactions = {g['content']: g['reactors']['totalCount'] for g in first.get('reactionGroups') or []}
    return {
        'id': t['id'],
        'path': t['path'],
        'line': t['line'],
        'resolved': t['isResolved'],
        'outdated': t['isOutdated'],
        'mine': ((first.get('author') or {}).get('login') or '').removesuffix('[bot]') == bot,
        'up': reactions.get('THUMBS_UP', 0),
        'down': reactions.get('THUMBS_DOWN', 0),
        'first_comment': first.get('id'),
        'comments': [{'by': (c.get('author') or {}).get('login', 'ghost'), 'body': c['body']} for c in comments],
    }


def post_review(app, f, head, body, comments):
    """Post one comment-only review on `head`, retrying with unplaceable comments moved to the body; returns its URL."""
    path = f'/repos/{f["repo"]}/pulls/{f["number"]}/reviews'
    payload = {'commit_id': head, 'event': 'COMMENT', 'body': body, 'comments': comments}
    try:
        r = app.call('POST', path, payload, installation=f['installation'])
    except GitHubError as e:
        if e.status != 422 or not comments:
            raise
        moved = [
            c['body'].split('\n```suggestion')[0]
            + f'\n\nhttps://github.com/{f["repo"]}/blob/{head}/{c["path"]}#L{c.get("start_line", c["line"])}-L{c["line"]}'
            for c in comments
        ]
        r = app.call(
            'POST',
            path,
            dict(payload, body='\n\n---\n\n'.join(x for x in (*moved, body) if x), comments=[]),
            installation=f['installation'],
        )
    return r.get('html_url', f['url'])


def thumbs_up(app, f):
    app.call(
        'POST', f'/repos/{f["repo"]}/issues/{f["number"]}/reactions', {'content': '+1'}, installation=f['installation']
    )


def close_thread(app, f, thread_id, note):
    """Reply to one of the companion's own threads and resolve it."""
    app.graphql(
        """mutation($id: ID!, $body: String!) { addPullRequestReviewThreadReply(input:
           {pullRequestReviewThreadId: $id, body: $body}) { clientMutationId } }""",
        f['installation'],
        id=thread_id,
        body=note,
    )
    app.graphql(
        'mutation($id: ID!) { resolveReviewThread(input: {threadId: $id}) { clientMutationId } }',
        f['installation'],
        id=thread_id,
    )


def update_comment(app, f, comment_id, body):
    """Rewrite one of the companion's own review comments in place."""
    app.graphql(
        """mutation($id: ID!, $body: String!) { updatePullRequestReviewComment(input:
           {pullRequestReviewCommentId: $id, body: $body}) { clientMutationId } }""",
        f['installation'],
        id=comment_id,
        body=body,
    )


EVIDENCE_BRANCH = 'main'
KEEP_DAYS = 60


def upload_images(app, evidence, f, paths, folder):
    """Commit screenshots to the `evidence` repo (never the product repo); returns {file name: commit-pinned raw url}."""
    inst = app.installation_for(evidence)
    if inst is None:
        raise GitHubError(404, f'the App is not installed on {evidence}')
    head = _evidence_head(app, evidence, inst)
    tree = []
    for p in paths:
        with open(p, 'rb') as fh:
            content = base64.b64encode(fh.read()).decode()
        blob = app.call(
            'POST', f'/repos/{evidence}/git/blobs', {'content': content, 'encoding': 'base64'}, installation=inst
        )
        tree.append({'path': f'{folder}/{p.rsplit("/", 1)[-1]}', 'mode': '100644', 'type': 'blob', 'sha': blob['sha']})
    base = app.call('GET', f'/repos/{evidence}/git/commits/{head}', installation=inst)['tree']['sha']
    new_tree = app.call('POST', f'/repos/{evidence}/git/trees', {'tree': tree, 'base_tree': base}, installation=inst)
    message = f'QA evidence for {f["repo"]}#{f["number"]}'
    commit = app.call(
        'POST',
        f'/repos/{evidence}/git/commits',
        {'message': message, 'tree': new_tree['sha'], 'parents': [head]},
        installation=inst,
    )['sha']
    app.call('PATCH', f'/repos/{evidence}/git/refs/heads/{EVIDENCE_BRANCH}', {'sha': commit}, installation=inst)
    return {t['path'].rsplit('/', 1)[-1]: f'https://github.com/{evidence}/raw/{commit}/{t["path"]}' for t in tree}


def _evidence_head(app, evidence, inst):
    """The evidence branch head; seeds an empty repo with a README (the Git Data API needs a first commit)."""
    try:
        return app.call('GET', f'/repos/{evidence}/git/ref/heads/{EVIDENCE_BRANCH}', installation=inst)['object']['sha']
    except GitHubError as e:
        if e.status not in (404, 409):
            raise
    readme = (
        'QA screenshots posted with pull request reviews, by repository/pr-number/run-time. Pruned automatically.\n'
    )
    try:
        r = app.call(
            'PUT',
            f'/repos/{evidence}/contents/README.md',
            {
                'message': 'Start the QA evidence',
                'content': base64.b64encode(readme.encode()).decode(),
                'branch': EVIDENCE_BRANCH,
            },
            installation=inst,
        )
        return r['commit']['sha']
    except GitHubError as e:
        if e.status != 422:  # 422: another writer made the first commit
            raise
    return app.call('GET', f'/repos/{evidence}/git/ref/heads/{EVIDENCE_BRANCH}', installation=inst)['object']['sha']


def prune_evidence(app, evidence, now):
    """Rewrite the evidence branch as one parentless commit without runs older than KEEP_DAYS; returns files dropped."""
    inst = app.installation_for(evidence)
    if inst is None:
        raise GitHubError(404, f'the App is not installed on {evidence}')
    head = _evidence_head(app, evidence, inst)
    base = app.call('GET', f'/repos/{evidence}/git/commits/{head}', installation=inst)['tree']['sha']
    entries = app.call('GET', f'/repos/{evidence}/git/trees/{base}?recursive=1', installation=inst)['tree']
    cutoff = now - KEEP_DAYS * 86400
    blobs = [e for e in entries if e['type'] == 'blob']
    kept = [e for e in blobs if _run_time(e['path']) >= cutoff]
    if len(kept) == len(blobs):
        return 0
    tree = app.call(
        'POST',
        f'/repos/{evidence}/git/trees',
        {'tree': [{'path': e['path'], 'mode': e['mode'], 'type': 'blob', 'sha': e['sha']} for e in kept]},
        installation=inst,
    )['sha']
    commit = app.call(
        'POST',
        f'/repos/{evidence}/git/commits',
        {'message': f'QA evidence of the last {KEEP_DAYS} days', 'tree': tree, 'parents': []},
        installation=inst,
    )['sha']
    app.call(
        'PATCH',
        f'/repos/{evidence}/git/refs/heads/{EVIDENCE_BRANCH}',
        {'sha': commit, 'force': True},
        installation=inst,
    )
    return len(blobs) - len(kept)


def _run_time(path):
    """The epoch of the path's run-<epoch> folder; inf outside runs, so they are always kept."""
    for part in path.split('/'):
        if part.startswith('run-') and part[4:].isdigit():
            return int(part[4:])
    return float('inf')


QA_MARK = '<!-- companion-qa-report -->'


def qa_comment(app, f, body):
    """Create or edit (found by QA_MARK) the PR's single QA report comment; returns its URL."""
    body = f'{QA_MARK}\n{body}'[:65000]
    bot = f'{app.slug()}[bot]'
    mine = [
        c
        for c in app.pages(f'/repos/{f["repo"]}/issues/{f["number"]}/comments', f['installation'], limit=500)
        if c['user']['login'] == bot and QA_MARK in (c.get('body') or '')
    ]
    if mine:
        r = app.call(
            'PATCH',
            f'/repos/{f["repo"]}/issues/comments/{mine[-1]["id"]}',
            {'body': body},
            installation=f['installation'],
        )
    else:
        r = app.call(
            'POST', f'/repos/{f["repo"]}/issues/{f["number"]}/comments', {'body': body}, installation=f['installation']
        )
    return r.get('html_url', f['url'])
