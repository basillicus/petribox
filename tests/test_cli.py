"""Command flows against a fake incus: what gets called, in which order."""

import types

import pytest

from petribox import cli, incus


class FakeIncus:
    def __init__(self, existing=(), snapshots=(), config=None):
        self.calls, self.existing, self.snapshots = [], set(existing), set(snapshots)
        self.config = config or {}

    def run(self, *args, **kw):
        self.calls.append(args)
        stdout = self.config.get(args[3], "") if args[:2] == ("config", "get") else ""
        return types.SimpleNamespace(returncode=0, stdout=stdout, stderr="")


@pytest.fixture
def fake(monkeypatch):
    f = FakeIncus()
    monkeypatch.setattr(incus, "run", f.run)
    monkeypatch.setattr(incus, "exists", lambda n: n in f.existing)
    monkeypatch.setattr(incus, "has_snapshot", lambda n, s: (n, s) in f.snapshots)
    monkeypatch.setattr(incus, "wait_for_agent", lambda n, timeout=300: None)
    return f


def verbs(fake):
    return [c[0] if c[0] not in ("config", "snapshot") else " ".join(c[:2]) for c in fake.calls]


def test_build_provisions_then_snapshots(fake):
    cli.main(["build", "rocky"])
    init = fake.calls[0]
    assert init[:3] == ("init", "images:rockylinux/9", "pb-rocky") and "--vm" in init
    assert "user.petribox.user=petri" in init
    assert verbs(fake) == ["init", "config device", "start", "exec", "exec", "stop", "snapshot create"]


def test_build_refuses_existing_base(fake):
    fake.existing.add("pb-rocky")
    with pytest.raises(SystemExit):
        cli.main(["build", "rocky"])
    assert fake.calls == []


def test_new_copies_clean_snapshot(fake):
    fake.snapshots.add(("pb-rocky", "clean"))
    fake.config["user.petribox.user"] = "petri"
    cli.main(["new", "lab", "--from", "rocky", "--ephemeral", "--memory", "8GiB", "--no-dotfiles"])
    copy = fake.calls[0]
    assert copy[:3] == ("copy", "pb-rocky/clean", "lab")
    assert "--ephemeral" in copy and "limits.memory=8GiB" in copy


def test_new_needs_a_built_recipe(fake):
    with pytest.raises(SystemExit):
        cli.main(["new", "lab", "--from", "rocky"])
    assert fake.calls == []
