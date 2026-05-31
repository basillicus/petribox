"""petribox commands package.

Re-exports every cmd_* entry point so cli.py can import them from one place
regardless of which submodule they live in.
"""

from .access import cmd_console, cmd_ssh
from .forward import (
    cmd_port_forward,
    cmd_port_forward_list,
    cmd_port_forward_stop,
)
from .install import cmd_install
from .lifecycle import (
    cmd_config,
    cmd_create,
    cmd_delete,
    cmd_down,
    cmd_list,
    cmd_status,
    cmd_up,
)
from .mounts import cmd_mount, cmd_umount
from .portability import (
    cmd_export,
    cmd_import,
    cmd_move,
    cmd_remote_add,
    cmd_remote_list,
)
from .comms import cmd_comms
from .env import cmd_env_list, cmd_env_set, cmd_env_unset
from .setup import cmd_initial_setup
from .ssh_config import cmd_ssh_config

__all__ = [
    "cmd_console",
    "cmd_ssh",
    "cmd_port_forward",
    "cmd_port_forward_list",
    "cmd_port_forward_stop",
    "cmd_install",
    "cmd_config",
    "cmd_create",
    "cmd_delete",
    "cmd_down",
    "cmd_list",
    "cmd_status",
    "cmd_up",
    "cmd_mount",
    "cmd_umount",
    "cmd_export",
    "cmd_import",
    "cmd_move",
    "cmd_remote_add",
    "cmd_remote_list",
    "cmd_comms",
    "cmd_env_set",
    "cmd_env_list",
    "cmd_env_unset",
    "cmd_ssh_config",
    "cmd_initial_setup",
]
