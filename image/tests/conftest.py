"""The image's modules run inside the agent container; tests import them from the source tree with a throwaway HOME."""

import importlib.machinery
import importlib.util
import os
import sys
import tempfile

IMAGE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ['HOME'] = tempfile.mkdtemp(prefix='agent-home-')  # before any module reads ~
sys.path.insert(0, os.path.join(IMAGE, 'accounts'))


def load_script(name):
    """Import an extension-less script (agent-config, ...) as a module."""
    path = os.path.join(IMAGE, name)
    loader = importlib.machinery.SourceFileLoader(name.replace('-', '_'), path)
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module
