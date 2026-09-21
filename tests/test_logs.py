import io
import logging
import sys

import pytest

from nttl.logs import configure_file_logging, ensure_streams, log_directory


@pytest.fixture(autouse=True)
def _clean_root_logger():
    root = logging.getLogger()
    before = list(root.handlers)
    yield
    for handler in list(root.handlers):
        if handler not in before:
            root.removeHandler(handler)
            handler.close()


def test_streams_are_left_alone_when_present(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "stdout", io.StringIO())
    monkeypatch.setattr(sys, "stderr", io.StringIO())
    assert ensure_streams(tmp_path / "nttl.log") is None
    assert not (tmp_path / "nttl.log").exists()


def test_missing_streams_are_redirected_to_a_log_file(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", None)
    path = ensure_streams(tmp_path / "logs" / "nttl.log")
    assert path == tmp_path / "logs" / "nttl.log"
    assert sys.stdout is not None and sys.stderr is not None
    print("hello from the tray")
    sys.stdout.flush()
    assert "hello from the tray" in path.read_text(encoding="utf-8")


def test_only_the_missing_stream_is_replaced(tmp_path, monkeypatch):
    kept = io.StringIO()
    monkeypatch.setattr(sys, "stdout", kept)
    monkeypatch.setattr(sys, "stderr", None)
    ensure_streams(tmp_path / "nttl.log")
    assert sys.stdout is kept
    assert sys.stderr is not None


def test_unwritable_location_falls_back_to_memory(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", None)
    blocked = tmp_path / "file"
    blocked.write_text("")
    assert ensure_streams(blocked / "nttl.log") is None
    assert sys.stdout is not None
    print("still works")


def test_log_directory_on_windows(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert log_directory() == tmp_path / "nttl" / "logs"


def test_log_directory_follows_xdg_state(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    assert log_directory() == tmp_path / "nttl" / "logs"


def test_file_logging_writes_records(tmp_path):
    path = tmp_path / "nttl.log"
    handler = configure_file_logging(path)
    try:
        logging.getLogger("nttl.test").warning("cooler failed")
        handler.flush()
        assert "cooler failed" in path.read_text(encoding="utf-8")
    finally:
        logging.getLogger().removeHandler(handler)
        handler.close()


def test_file_logging_without_a_path_is_a_no_op(tmp_path):
    assert configure_file_logging(None) is None


def test_file_logging_is_not_added_twice(tmp_path):
    path = tmp_path / "nttl.log"
    first = configure_file_logging(path)
    second = configure_file_logging(path)
    try:
        assert second is first
        assert sum(1 for h in logging.getLogger().handlers if h is first) == 1
    finally:
        logging.getLogger().removeHandler(first)
        first.close()


def test_switching_paths_replaces_the_handler(tmp_path):
    first = configure_file_logging(tmp_path / "one.log")
    second = configure_file_logging(tmp_path / "two.log")
    try:
        assert second is not first
        logging.getLogger("nttl.test").warning("second file")
        second.flush()
        assert "second file" in (tmp_path / "two.log").read_text(encoding="utf-8")
        assert sum(1 for h in logging.getLogger().handlers if h is first) == 0
    finally:
        logging.getLogger().removeHandler(second)
        second.close()
