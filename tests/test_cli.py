"""Command flows against a fake incus: what gets called, in which order."""

import json
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


def test_new_records_the_recipe(fake):
    fake.snapshots.add(("pb-rocky", "clean"))
    fake.config["user.petribox.user"] = "petri"
    cli.main(["new", "dish", "--from", "rocky", "--no-dotfiles"])
    assert "user.petribox.recipe=rocky" in fake.calls[0]


def test_list_shows_only_petribox_dishes(fake, capsys):
    instances = [
        {"name": "lab", "type": "virtual-machine", "status": "Running", "ephemeral": True,
         "config": {"user.petribox.user": "petri", "user.petribox.recipe": "rocky"},
         "state": {"network": {"eth0": {"addresses": [{"family": "inet", "address": "10.0.0.5"}]}}}},
        {"name": "pb-rocky", "type": "virtual-machine", "status": "Stopped",
         "config": {"user.petribox.user": "petri"}},
        {"name": "other", "type": "container", "status": "Running", "config": {}},
    ]
    fake.run = lambda *a, **k: types.SimpleNamespace(returncode=0, stdout=json.dumps(instances), stderr="")
    incus.run = fake.run
    cli.main(["list"])
    out = capsys.readouterr().out
    assert "lab" in out and "10.0.0.5" in out and "ephemeral" in out
    assert "pb-rocky" not in out and "other" not in out
    cli.main(["list", "--bases"])
    assert "pb-rocky" in capsys.readouterr().out


def test_mount_shifts_only_for_containers(fake, tmp_path, monkeypatch):
    def run(*args, **kw):
        fake.calls.append(args)
        out = {"query": json.dumps({"type": "container"}),
               "exec": "petri:x:1000:1000::/home/petri:/bin/bash"}.get(args[0], "")
        if args[:2] == ("config", "get"):
            out = "petri"
        return types.SimpleNamespace(returncode=0, stdout=out, stderr="")
    monkeypatch.setattr(incus, "run", run)
    (tmp_path / "my src").mkdir()
    cli.main(["mount", "lab", str(tmp_path / "my src")])
    add = next(c for c in fake.calls if c[:3] == ("config", "device", "add"))
    assert add[3:6] == ("lab", "my-src", "disk")
    assert f"path=/home/petri/my src" in add and "shift=true" in add


def test_new_from_image_sets_up_the_user(fake):
    fake.config["user.petribox.user"] = "alice"
    cli.main(["new", "lab", "--image", "images:debian/13", "--user", "alice", "--disk", "40GiB",
              "--ephemeral", "--no-dotfiles"])
    init = fake.calls[0]
    assert init[:3] == ("init", "images:debian/13", "lab")
    assert "--vm" in init and "--ephemeral" in init and "root,size=40GiB" in init
    assert "user.petribox.user=alice" in init
    assert verbs(fake) == ["init", "config device", "start", "exec", "config get"]


def test_new_needs_a_source_when_not_interactive(fake, monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    with pytest.raises(SystemExit):
        cli.main(["new", "lab"])
    assert "--from RECIPE or --image" in capsys.readouterr().err


def test_wizard_prints_a_repeatable_command():
    from petribox import wizard
    args = cli.build_parser().parse_args(["new"])
    args.name, args.image, args.recipe, args.container = "lab", "images:debian/13", None, True
    args.disk, args.user, args.cpus, args.memory = "20GiB", "petri", 2, "4GiB"
    args.ephemeral, args.secret, args.share, args.no_dotfiles = True, ["API_KEY"], ["/tmp"], False
    line = wizard.command_line(args)
    assert cli.build_parser().parse_args(line.split()[1:]).container
    assert line == ("petribox new lab --image images:debian/13 --container --disk 20GiB --user petri "
                    "--cpus 2 --memory 4GiB --ephemeral --secret API_KEY --share /tmp")
