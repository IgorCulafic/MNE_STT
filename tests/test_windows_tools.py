import threading
from pathlib import Path
import pytest
from stt.models import MODELS, model_cache
from tools.download_models import download_models, main as download_main
from tools.launch import open_when_ready, URL


def test_shared_model_cache_respects_overrides(monkeypatch, tmp_path):
    monkeypatch.delenv('STT_MODEL_CACHE', raising=False)
    monkeypatch.setenv('STT_DATA_DIR', str(tmp_path / 'projects'))
    assert model_cache() == tmp_path / 'projects' / 'models'
    assert model_cache(tmp_path / 'explicit') == tmp_path / 'explicit' / 'models'
    monkeypatch.setenv('STT_MODEL_CACHE', str(tmp_path / 'cache'))
    assert model_cache(tmp_path / 'explicit') == tmp_path / 'cache'


def model_files(tmp_path):
    for name in ('model.bin', 'config.json', 'tokenizer.json'):
        (tmp_path / name).write_bytes(b'example')
    return tmp_path


def test_download_retries_then_continues_to_next_model(tmp_path):
    model_files(tmp_path)
    attempts = []
    def download(name, **kwargs):
        attempts.append(name)
        assert kwargs['cache_dir'] == str(tmp_path)
        if name == 'tiny' and attempts.count(name) < 3:
            raise OSError('temporary failure')
        return tmp_path
    assert download_models(['tiny','base'],tmp_path,download=download,sleep=lambda _:None) == 0
    assert attempts == ['tiny','tiny','tiny','base']


def test_missing_download_fails_but_tries_remaining_models(tmp_path):
    attempts = []
    def download(name, **kwargs):
        attempts.append(name)
        return tmp_path  # Snapshot path exists, but files are incomplete.
    assert download_models(['tiny','base'],tmp_path,download=download,sleep=lambda _:None) == 1
    assert attempts == ['tiny']*3 + ['base']*3


def test_local_check_never_enables_network_or_retries(tmp_path):
    attempts = []
    def download(name, **kwargs):
        assert kwargs['local_files_only'] is True
        attempts.append(name)
        raise OSError('not cached')
    assert download_models(['tiny'],tmp_path,True,download=download) == 1
    assert attempts == ['tiny']


def test_list_needs_no_download(capsys):
    assert download_main(['--list']) == 0
    assert capsys.readouterr().out.splitlines() == list(MODELS)


def test_browser_only_opens_on_readiness_or_not_at_all():
    opened=[]
    stopped=threading.Event()
    open_when_ready(stopped,ready=lambda:True,open_url=opened.append,attempts=1)
    assert opened == [URL]
    stopped.set()
    open_when_ready(stopped,ready=lambda:True,open_url=opened.append,attempts=1)
    assert opened == [URL]
