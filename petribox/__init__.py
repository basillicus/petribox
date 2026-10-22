"""
petribox - Incus sandboxes ("dishes") built from recipes.

A recipe is a plain Incus image plus a provisioning script. `petribox build`
turns it into a stopped base instance with a `clean` snapshot; `petribox new`
copies that snapshot into a dish and hands it secrets and dotfiles. Everything
else (list, stop, delete, snapshots, mounts, ports, export, move) is plain Incus.
"""

__version__ = "0.2.0"
