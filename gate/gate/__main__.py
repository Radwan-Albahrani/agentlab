"""Start the gate; auth.mode "none" needs GATE_ALLOW_NONE=1 so a test config can't open a real server."""

import logging
import os
import sys

from .app import none_allowed, serve
from .config import Config
from .oidc import SignIn
from .onboarding import Onboarding
from .tokens import Keys


def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s', stream=sys.stdout)
    log = logging.getLogger('gate')
    config = Config(os.environ.get('GATE_CONFIG', '/etc/agentlab/cluster.json')).fresh()
    if config.mode == 'none':
        if not none_allowed():
            log.error('auth.mode is "none" but GATE_ALLOW_NONE is not 1: refusing to start')
            return 2
        log.warning('!!! auth.mode none: EVERY request is allowed as %s. Local testing only. !!!', 'local@localhost')
    elif config.mode == 'cloudflare-access' and (not config.team or not config.audience):
        log.warning('auth.cloudflare.team / audience missing: every request will be denied until cluster.json has them')
    folder = os.environ.get('GATE_SECRETS', '')
    signin = SignIn(folder) if folder else None
    if config.https and not (signin and signin.ready()):
        log.warning('HTTPS sign-in has no client yet: HTTPS requests are refused until agentctl cloudflare setup ran')
    port = int(os.environ.get('GATE_PORT', '8080'))
    log.info('gate listening on :%d', port)
    serve(config, Keys(), Onboarding(), port, signin).serve_forever()
    return 0


if __name__ == '__main__':
    sys.exit(main())
