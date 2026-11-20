import contextlib
import importlib.machinery
import importlib.util
import os
import sys
import tempfile

IMAGE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ['HOME'] = tempfile.mkdtemp(prefix='agent-home-')  # before any module reads ~
sys.path.insert(0, os.path.join(IMAGE, 'accounts'))
sys.path.append(IMAGE)  # t3schema, t3state: in the image they sit on the agent-t3 venv's path

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402
from t3schema import Base  # noqa: E402


def t3_db(path, *rows):
    """A T3 database at `path` with T3's tables (t3schema) and these model rows; -> its path."""
    engine = create_engine(f'sqlite:///{path}')
    try:
        Base.metadata.create_all(engine)
        with Session(engine) as s:
            s.add_all(rows)
            s.commit()
    finally:
        engine.dispose()
    return str(path)


@contextlib.contextmanager
def t3_write(path):
    """A session on a test database, committed and closed on the way out."""
    engine = create_engine(f'sqlite:///{path}')
    try:
        with Session(engine) as s:
            yield s
            s.commit()
    finally:
        engine.dispose()


def load_script(name):
    path = os.path.join(IMAGE, name)
    loader = importlib.machinery.SourceFileLoader(name.replace('-', '_'), path)
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module
