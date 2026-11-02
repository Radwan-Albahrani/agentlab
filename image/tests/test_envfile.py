import os

import envfile
import pytest


@pytest.fixture(autouse=True)
def env_file(tmp_path, monkeypatch):
    monkeypatch.setattr(envfile, 'ENV_FILE', str(tmp_path / 'env'))


def test_set_load_round_trip_keeps_value_exactly():
    value = 'it\'s $HOME and "quoted" spaces '
    assert envfile.apply('set', {'key': 'API_TOKEN', 'value': value}) == (True, [], 1)
    assert envfile.load() == {'API_TOKEN': value}
    assert oct(os.stat(envfile.ENV_FILE).st_mode & 0o777) == '0o600'


@pytest.mark.parametrize('key', ['1BAD', 'HAS-DASH', '', 'PATH', 'path', 'LD_PRELOAD'])
def test_rejected_keys_change_nothing(key):
    ok, errors, count = envfile.apply('set', {'key': key, 'value': 'x'})
    assert (ok, count) == (False, 0) and errors
    assert not os.path.exists(envfile.ENV_FILE)


def test_import_parses_dotenv_and_reports_bad_lines():
    text = '# comment\nexport A=1\nB="two words"\nC=\'3\'\nnot a line\nPATH=/x\n'
    ok, errors, count = envfile.apply('import', {'text': text})
    assert envfile.load() == {'A': '1', 'B': 'two words', 'C': '3'}
    assert not ok and count == 3 and len(errors) == 2


def test_delete_and_masked():
    envfile.apply('set', {'key': 'SHORT', 'value': 'abc'})
    envfile.apply('set', {'key': 'LONG', 'value': 'sk-1234567890'})
    assert envfile.masked() == {'SHORT': {'masked': '•••', 'length': 3}, 'LONG': {'masked': '…7890', 'length': 13}}
    envfile.apply('delete', {'key': 'SHORT'})
    assert set(envfile.load()) == {'LONG'}
