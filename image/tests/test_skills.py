import os
import re

from conftest import IMAGE, load_script

agent_config = load_script('agent-config')
SKILLS = os.path.join(IMAGE, 'skills')


def test_every_skill_has_name_and_description_only():
    for name in os.listdir(SKILLS):
        with open(os.path.join(SKILLS, name, 'SKILL.md')) as f:
            front = re.match(r'^---\n(.*?)\n---\n', f.read(), re.S).group(1)
        keys = dict(line.split(':', 1) for line in front.splitlines())
        assert set(keys) == {'name', 'description'} and keys['name'].strip() == name  # Codex rejects other keys


def test_installed_for_both_clis_and_replaced_each_start(tmp_path, monkeypatch):
    monkeypatch.delenv('CODEX_HOME', raising=False)
    assert agent_config.install_skills(SKILLS, str(tmp_path)) == []
    for root in ('.claude/skills', '.codex/skills'):
        skill = tmp_path / root / 'companion'
        assert (skill / 'SKILL.md').exists() and (skill / '.agentlab-managed').exists()
        (skill / 'stale.md').write_text('old')
    agent_config.install_skills(SKILLS, str(tmp_path))
    assert not (tmp_path / '.claude/skills/companion/stale.md').exists()


def test_someone_elses_skill_and_other_skills_are_left_alone(tmp_path, monkeypatch):
    monkeypatch.setenv('CODEX_HOME', str(tmp_path / 'codex-home'))
    mine = tmp_path / '.claude/skills/companion'
    mine.mkdir(parents=True)
    (mine / 'SKILL.md').write_text('my own')
    other = tmp_path / '.claude/skills/other'
    other.mkdir()
    skipped = agent_config.install_skills(SKILLS, str(tmp_path))
    assert skipped == [str(mine)] and (mine / 'SKILL.md').read_text() == 'my own' and other.exists()
    assert (tmp_path / 'codex-home/skills/companion/SKILL.md').exists()
