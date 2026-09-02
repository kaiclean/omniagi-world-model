"""Tests for the atomic, lock-guarded persistence primitives."""

from __future__ import annotations

import json
import threading
import time

import pytest

from omniagi import persistence


def test_atomic_write_text_replaces_content(tmp_path):
    target = tmp_path / "note.txt"
    persistence.atomic_write_text(target, "first")
    persistence.atomic_write_text(target, "second")
    assert target.read_text(encoding="utf-8") == "second"


def test_atomic_write_text_leaves_no_temp_files(tmp_path):
    target = tmp_path / "note.txt"
    persistence.atomic_write_text(target, "payload")
    leftovers = [p.name for p in tmp_path.iterdir() if p.name != "note.txt"]
    assert leftovers == []


def test_atomic_write_json_roundtrips(tmp_path):
    target = tmp_path / "data.json"
    persistence.atomic_write_json(target, {"b": 1, "a": 2}, sort_keys=True)
    assert json.loads(target.read_text(encoding="utf-8")) == {"a": 2, "b": 1}
    assert target.read_text(encoding="utf-8").endswith("\n")


def test_atomic_write_creates_parent_dirs(tmp_path):
    target = tmp_path / "nested" / "deep" / "data.json"
    persistence.atomic_write_json(target, [1, 2, 3])
    assert json.loads(target.read_text(encoding="utf-8")) == [1, 2, 3]


def test_locked_json_update_uses_default_when_absent(tmp_path):
    target = tmp_path / "counter.json"

    def bump(doc):
        doc["count"] += 1
        return doc

    result = persistence.locked_json_update(target, bump, default={"count": 0})
    assert result == {"count": 1}
    assert json.loads(target.read_text(encoding="utf-8")) == {"count": 1}


def test_locked_json_update_serialises_concurrent_writers(tmp_path):
    target = tmp_path / "counter.json"
    persistence.atomic_write_json(target, {"count": 0})

    def bump(_):
        def mutate(doc):
            value = doc["count"]
            time.sleep(0.01)  # widen the read-modify-write window
            doc["count"] = value + 1
            return doc

        persistence.locked_json_update(target, mutate)

    threads = [threading.Thread(target=bump, args=(i,)) for i in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert json.loads(target.read_text(encoding="utf-8")) == {"count": 8}


def test_file_lock_times_out_when_held(tmp_path):
    if persistence.fcntl is None:  # pragma: no cover - POSIX only
        pytest.skip("advisory locks require fcntl")
    target = tmp_path / "resource"
    started = threading.Event()
    release = threading.Event()

    def hold():
        with persistence.file_lock(target, timeout=5):
            started.set()
            release.wait(timeout=5)

    holder = threading.Thread(target=hold)
    holder.start()
    assert started.wait(timeout=5)
    try:
        with pytest.raises(persistence.PersistenceError), persistence.file_lock(
            target, timeout=0.2
        ):
            pass  # pragma: no cover - lock is held by the other thread
    finally:
        release.set()
        holder.join()
