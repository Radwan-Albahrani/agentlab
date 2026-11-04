from bot import config
from conftest import set_settings


def test_defaults():
    assert config.mode() == 'tag'
    assert config.auto_retry() is True
    assert config.publish_channel() == 'C_UPDATES'


def test_a_change_on_the_page_is_picked_up_without_a_restart():
    set_settings({'mode': 'team', 'auto_retry': False, 'publish_channel': 'C123'})
    assert (config.mode(), config.auto_retry(), config.publish_channel()) == ('team', False, 'C123')


def test_an_invalid_choice_falls_back_to_the_default():
    set_settings({'mode': 'bogus'})
    assert config.mode() == 'tag'


def test_an_empty_channel_is_no_channel():
    set_settings({'publish_channel': '  '})
    assert config.publish_channel() == ''
