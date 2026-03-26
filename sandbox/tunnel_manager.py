"""
Tunnel Manager - Track and manage SSH port-forward tunnels
"""

import json
import os
import subprocess
from pathlib import Path
from typing import Optional


class TunnelManager:
    """Manage SSH port-forward tunnels with file-based tracking"""

    def __init__(self):
        self.tunnel_dir = Path.home() / ".sandbox" / "tunnels"
        self.tunnel_dir.mkdir(parents=True, exist_ok=True)

    def _get_tunnel_file(self, sandbox_name: str, port: int) -> Path:
        """Get the tunnel tracking file path"""
        return self.tunnel_dir / f"{sandbox_name}_{port}.json"

    def _is_process_running(self, pid: int) -> bool:
        """Check if a process is still running"""
        try:
            os.kill(pid, 0)
            return True
        except (OSError, ProcessLookupError):
            return False

    def create_tunnel(
        self, sandbox_name: str, vm_port: int, local_port: int, pid: int, vm_ip: str, user: str
    ) -> None:
        """Create a tunnel tracking file"""
        tunnel_file = self._get_tunnel_file(sandbox_name, vm_port)
        data = {
            "sandbox_name": sandbox_name,
            "vm_port": vm_port,
            "local_port": local_port,
            "pid": pid,
            "vm_ip": vm_ip,
            "user": user,
        }
        with open(tunnel_file, "w") as f:
            json.dump(data, f, indent=2)

    def get_tunnel(self, sandbox_name: str, port: int) -> Optional[dict]:
        """Get tunnel info, returns None if tunnel doesn't exist or process is dead"""
        tunnel_file = self._get_tunnel_file(sandbox_name, port)
        if not tunnel_file.exists():
            return None

        with open(tunnel_file, "r") as f:
            data = json.load(f)

        # Check if process is still running
        if data.get("pid") and not self._is_process_running(data["pid"]):
            # Process is dead, clean up the file
            tunnel_file.unlink()
            return None

        return data

    def list_tunnels(self) -> list[dict]:
        """List all active tunnels"""
        tunnels = []
        for tunnel_file in self.tunnel_dir.glob("*.json"):
            with open(tunnel_file, "r") as f:
                data = json.load(f)

            # Check if process is still running
            if data.get("pid") and self._is_process_running(data["pid"]):
                tunnels.append(data)
            else:
                # Clean up stale file
                tunnel_file.unlink()

        return tunnels

    def remove_tunnel(self, sandbox_name: str, port: int) -> bool:
        """Remove a tunnel tracking file"""
        tunnel_file = self._get_tunnel_file(sandbox_name, port)
        if tunnel_file.exists():
            tunnel_file.unlink()
            return True
        return False

    def clean_stale(self) -> int:
        """Remove stale tunnel files (processes that are dead). Returns count of cleaned."""
        cleaned = 0
        for tunnel_file in self.tunnel_dir.glob("*.json"):
            with open(tunnel_file, "r") as f:
                data = json.load(f)

            if not data.get("pid") or not self._is_process_running(data["pid"]):
                tunnel_file.unlink()
                cleaned += 1

        return cleaned

    def kill_tunnel(self, sandbox_name: str, port: int) -> bool:
        """Kill a tunnel process and remove tracking file"""
        tunnel = self.get_tunnel(sandbox_name, port)
        if not tunnel:
            return False

        pid = tunnel.get("pid")
        if pid:
            try:
                # Kill the process group to ensure all child processes die
                os.killpg(os.getpgid(pid), 9)
            except (OSError, ProcessLookupError):
                # Process already dead, that's fine
                pass

        self.remove_tunnel(sandbox_name, port)
        return True

    def kill_all_for_sandbox(self, sandbox_name: str) -> int:
        """Kill all tunnels for a sandbox. Returns count of killed tunnels."""
        killed = 0
        for tunnel_file in self.tunnel_dir.glob(f"{sandbox_name}_*.json"):
            with open(tunnel_file, "r") as f:
                data = json.load(f)

            pid = data.get("pid")
            if pid:
                try:
                    os.killpg(os.getpgid(pid), 9)
                except (OSError, ProcessLookupError):
                    pass

            tunnel_file.unlink()
            killed += 1

        return killed
