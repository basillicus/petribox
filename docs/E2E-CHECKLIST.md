# Manual end-to-end checklist

Run on a Linux host with Incus. Either drive it through the CLI by hand, or run
the gated automated test: `PETRIBOX_E2E=1 pytest -m e2e` (add `PETRIBOX_E2E_VM=1`
to also exercise the VM path).

## 0. Setup
```bash
pixi run petribox initial-setup      # installs/initialises Incus, checks group
```
- [ ] After joining the `incus`/`incus-admin` group and re-login, no command prompts for sudo.
- [ ] `incus admin init --minimal` ran (storage pool + `incusbr0` present).

## 1. Create
```bash
pixi run petribox create lab --preset dev
pixi run petribox create fast --container --preset minimal
```
- [ ] `lab` is a VM, `fast` is a container (boots in seconds).
- [ ] `petribox list` shows both with status/type/RAM/CPU/IP/preset.

## 2. Connect & run
```bash
pixi run petribox connect lab
pixi run petribox connect lab -- mise --version
```
- [ ] Shell opens via `incus exec` (no SSH/IP needed).
- [ ] mise and preset packages are present (allow 1-3 min for cloud-init on first boot).

## 3. Mounts (real virtiofs)
```bash
mkdir -p ~/data && echo hi > ~/data/marker
pixi run petribox mount lab ~/data /data
pixi run petribox connect lab -- cat /data/marker     # -> hi
pixi run petribox umount lab /data
```
- [ ] Host file is visible inside the dish; umount detaches it.

## 4. Port forward (proxy device)
```bash
pixi run petribox connect lab -- sh -c "python3 -m http.server 8888 &"
pixi run petribox port-forward lab 8888
curl -s localhost:8888 >/dev/null && echo OK
pixi run petribox port-forward-list
pixi run petribox port-forward-stop lab 8888
```
- [ ] `localhost:8888` reaches the dish; listed; stoppable; survives a host shell restart.

## 5. Install an agent
```bash
pixi run petribox install lab --agent hermes
```
- [ ] Installer runs via `incus exec`; follow-up setup command is printed.

## 6. Portability (breed -> carry)
```bash
pixi run petribox down lab
pixi run petribox export lab -o lab.tar.gz
pixi run petribox delete lab -f
pixi run petribox import lab.tar.gz
pixi run petribox up lab
```
- [ ] Exported tarball is self-contained; re-imported dish boots and is intact.
- [ ] (Multi-host) `petribox remote-add cloud <url>` then `petribox move lab cloud` migrates it.

## 7. Comms readiness
```bash
pixi run petribox create a --preset minimal
pixi run petribox create b --preset minimal
pixi run petribox comms a --expose
pixi run petribox comms b
pixi run petribox connect a -- getent hosts b.incus
```
- [ ] `a` can resolve `b.incus`; comms port recorded in `user.petribox.comms_port`.

## 8. Teardown
```bash
pixi run petribox delete lab -f
pixi run petribox delete fast -f
```
- [ ] Instances and their proxy/disk devices are gone; `~/.petribox` has no residue.
