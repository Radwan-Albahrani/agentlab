"""Learned memory peaks per job signature."""

import json
import os

from .settings import DEFAULT_MB, DEFAULT_OTHER_MB, PEAK_HISTORY, PEAK_MARGIN, STATE_DIR

FILE = os.path.join(STATE_DIR, 'peaks.json')


class Peaks:
    def __init__(self):
        try:
            with open(FILE) as f:
                self.history = json.load(f)
        except (OSError, ValueError):
            self.history = {}

    def known(self, signature):
        return signature in self.history

    def estimate_mb(self, signature, tool):
        seen = self.history.get(signature)
        if seen:
            return round(max(seen) * PEAK_MARGIN)
        return DEFAULT_MB.get(tool, DEFAULT_OTHER_MB)

    def record(self, signature, peak_mb):
        self.history[signature] = [*self.history.get(signature, []), peak_mb][-PEAK_HISTORY:]
        os.makedirs(STATE_DIR, exist_ok=True)
        with open(FILE + '.tmp', 'w') as f:
            json.dump(self.history, f, indent=1, sort_keys=True)
        os.replace(FILE + '.tmp', FILE)
