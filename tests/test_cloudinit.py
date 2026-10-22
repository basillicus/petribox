"""Unit tests for cloud-init user-data generation."""

import yaml

from petribox import cloudinit, presets


def _doc(**kwargs):
    text = cloudinit.build_user_data(**kwargs)
    assert text.startswith("#cloud-config\n")
    return yaml.safe_load(text)


def test_key_only_locks_password():
    doc = _doc(hostname="lab", user="petri", ssh_key="ssh-ed25519 AAAA u@h")
    assert doc["users"][0]["lock_passwd"] is True
    assert doc["ssh_pwauth"] is False
    assert "chpasswd" not in doc
    assert doc["users"][0]["ssh_authorized_keys"] == ["ssh-ed25519 AAAA u@h"]


def test_password_uses_chpasswd_text_not_plaintext_field():
    doc = _doc(hostname="x", user="petri", ssh_key="k", password="hunter2")
    # A password must go through chpasswd, never as a plaintext `passwd:` field.
    assert "passwd" not in doc["users"][0]
    assert doc["users"][0]["lock_passwd"] is False
    assert doc["ssh_pwauth"] is True
    entry = doc["chpasswd"]["users"][0]
    assert entry == {"name": "petri", "password": "hunter2", "type": "text"}


def test_packages_deduped_and_build_deps_present():
    cfg = {"packages": ["vim", "vim", "jq"]}
    doc = _doc(hostname="x", user="petri", ssh_key="k", config=cfg)
    assert doc["packages"].count("vim") == 1
    assert "jq" in doc["packages"]
    for dep in cloudinit.MISE_BUILD_DEPS:
        assert dep in doc["packages"]


def test_preset_mise_and_pip_land_in_runcmd():
    doc = _doc(hostname="x", user="petri", ssh_key="k",
               config=presets.package_config("ai-researcher"))
    runcmd = " ".join(doc["runcmd"])
    assert "mise use -g python@3.12" in runcmd
    assert "pip3 install --break-system-packages" in runcmd
    assert "jupyterlab" in runcmd


def test_agent_install_script_runs():
    agent = {"name": "X", "install_script": "curl x | bash", "mise_packages": ["node@24"]}
    doc = _doc(hostname="x", user="petri", ssh_key="k", agent_config=agent)
    runcmd = " ".join(doc["runcmd"])
    assert "curl x | bash" in runcmd
    assert "mise use -g node@24" in runcmd


def test_zsh_shell_activates_via_zshrc():
    text = cloudinit.build_user_data(hostname="x", user="petri", ssh_key="k", shell="zsh")
    doc = yaml.safe_load(text)
    runcmd = " ".join(doc["runcmd"])
    assert doc["users"][0]["shell"] == "/bin/zsh"
    assert "https://mise.run" in runcmd
    assert "mise activate zsh" in runcmd and ".zshrc" in runcmd


def test_mise_runs_as_dish_user_not_root():
    doc = _doc(hostname="x", user="petri", ssh_key="k",
               config={"mise_packages": ["node@24"]})
    runcmd = " ".join(doc["runcmd"])
    # mise work is wrapped in `su - <user>` so files aren't root-owned
    assert "su - petri -c" in runcmd
    assert "export HOME=" not in runcmd  # old root+HOME approach is gone


def test_environment_never_in_user_data():
    # user-data is stored in the instance config and travels with exports.
    text = cloudinit.build_user_data(hostname="x", user="petri", ssh_key="k",
                                     config={"environment": {"OPENAI_API_KEY": "sk-secret"}})
    assert "sk-secret" not in text
    assert ".config/petribox/env" in text  # rc sources the env file pushed after boot


def test_network_config_names_interfaces_explicitly():
    # Rocky's sysconfig renderer ignores `match` globs, so each NIC is named.
    config = yaml.safe_load(cloudinit.build_network_config())
    ethernets = config["ethernets"]
    assert set(ethernets) == {"enp5s0", "eth0"}
    assert all(e["dhcp4"] and "match" not in e for e in ethernets.values())
