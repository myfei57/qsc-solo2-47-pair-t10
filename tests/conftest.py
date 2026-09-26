"""Fixtures shared by the control service tests."""

import pytest

from paperops.config import Config
from paperops.store import Journal

from support import WEB_DIR, build


@pytest.fixture()
def data_dir(tmp_path):
    return str(tmp_path / "data")


@pytest.fixture()
def config(data_dir):
    return Config(data_dir=data_dir, web_dir=WEB_DIR)


@pytest.fixture()
def services(config):
    return build(config)


@pytest.fixture()
def console(services):
    return services.console


@pytest.fixture()
def journal(tmp_path):
    return Journal(str(tmp_path / "stream"))
