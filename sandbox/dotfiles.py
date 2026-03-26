"""
Dotfiles Management - Apply user configurations to sandboxes
"""

import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from rich.console import Console

from .ssh_ops import ssh_connect, ssh_copy_file, ssh_run_script

console = Console()


# Built-in dotfile presets
DOTFILE_PRESETS = {
    "minimal": {
        "description": "Basic vim and shell configuration",
        "files": {
            ".vimrc": """set number
set expandtab
set tabstop=4
set shiftwidth=4
set smartindent
set hlsearch
set incsearch
set ignorecase
set smartcase
set mouse=a
set cursorline
set colorcolumn=100
""",
            ".inputrc": """set editing-mode emacs
set show-mode-in-prompt on
set vi-cmd-mode-string \\1\\033[1m\\2
set vi-ins-mode-string \\1\\033[0m\\2
""",
        },
    },
    "dev": {
        "description": "Developer configuration with enhanced tools",
        "files": {
            ".vimrc": """set number
set expandtab
set tabstop=4
set shiftwidth=4
set smartindent
set hlsearch
set incsearch
set ignorecase
set smartcase
set mouse=a
set cursorline
set colorcolumn=100
set splitright
set splitbelow
set termguicolors

" Better splitting
nnoremap <C-h> <C-w>h
nnoremap <C-j> <C-w>j
nnoremap <C-k> <C-w>k
nnoremap <C-l> <C-w>l
""",
            ".tmux.conf": """set -g mouse on
set -g base-index 1
setw -g pane-base-index 1
set -g status-keys emacs
bind C-a send-prefix
bind C-s split-window -v
bind C-v split-window -h
""",
            ".gitconfig": """[user]
    name = Sandbox User
    email = sandbox@local
[core]
    editor = vim
[init]
    defaultBranch = main
[push]
    default = simple
[pull]
    rebase = false
""",
        },
    },
    "ai-researcher": {
        "description": "AI/ML researcher setup with Jupyter config",
        "files": {
            ".vimrc": """set number
set expandtab
set tabstop=4
set shiftwidth=4
set smartindent
set hlsearch
set incsearch
set ignorecase
set smartcase
set mouse=a
set cursorline
set colorcolumn=100
set termguicolors
""",
            ".jupyter/jupyter_notebook_config.py": """c = get_config()
c.NotebookApp.ip = '0.0.0.0'
c.NotebookApp.port = 8888
c.NotebookApp.open_browser = False
c.NotebookApp.allow_remote_access = True
""",
            ".bashrc_extra": """# AI/ML aliases
alias jupyter='jupyter notebook --ip=0.0.0.0 --port=8888 --no-browser --allow-root'
alias lab='jupyter lab --ip=0.0.0.0 --port=8888 --no-browser --allow-root'
alias py='python3'
alias pip='pip3'
""",
        },
    },
}


def apply_dotfiles(
    vm_name: str,
    vm_ip: str,
    vm_user: str,
    source: str,
    preset_name: Optional[str] = None,
):
    """
    Apply dotfiles to a sandbox

    Args:
        vm_name: VM name
        vm_ip: VM IP address
        vm_user: VM username
        source: Source specification (git URL, local path, or preset name)
        preset_name: Optional preset name for built-in presets
    """
    # Determine source type
    if source.startswith("http://") or source.startswith("https://"):
        # Git repository
        _apply_git_dotfiles(vm_ip, vm_user, source)
    elif source.startswith("/") or source.startswith("~"):
        # Local path
        _apply_local_dotfiles(vm_ip, vm_user, source)
    elif source in DOTFILE_PRESETS or preset_name:
        # Built-in preset
        preset = preset_name or source
        _apply_preset_dotfiles(vm_ip, vm_user, preset)
    else:
        # Try as preset first, then as local path
        if source in DOTFILE_PRESETS:
            _apply_preset_dotfiles(vm_ip, vm_user, source)
        elif Path(source).exists():
            _apply_local_dotfiles(vm_ip, vm_user, source)
        else:
            raise ValueError(f"Unknown dotfiles source: {source}")


def _apply_git_dotfiles(vm_ip: str, vm_user: str, git_url: str):
    """Apply dotfiles from a git repository"""
    console.print(f"[dim]Cloning dotfiles from {git_url}...[/dim]")

    script = f"""#!/bin/bash
set -e

# Clone dotfiles repo
cd ~
if [ -d .dotfiles ]; then
    echo "Dotfiles directory already exists, pulling updates..."
    cd .dotfiles && git pull
else
    git clone {git_url} .dotfiles
fi

# Install dotfiles (common patterns)
if [ -f .dotfiles/install.sh ]; then
    echo "Running install script..."
    cd .dotfiles && bash install.sh
elif [ -f .dotfiles/Makefile ]; then
    echo "Running Makefile..."
    cd .dotfiles && make install
else
    echo "Symlinking dotfiles..."
    for file in .dotfiles/.*; do
        if [ -f "$file" ] || [ -d "$file" ]; then
            base=$(basename "$file")
            if [ "$base" != ".dotfiles" ] && [ "$base" != ".git" ]; then
                ln -sf "$file" ~/"$base"
            fi
        fi
    done
fi

echo "Dotfiles applied successfully!"
"""

    ssh_run_script(vm_ip, vm_user, script)


def _apply_local_dotfiles(vm_ip: str, vm_user: str, local_path: str):
    """Apply dotfiles from a local directory"""
    local_path = Path(local_path).expanduser()

    if not local_path.exists():
        raise FileNotFoundError(f"Dotfiles path not found: {local_path}")

    console.print(f"[dim]Copying dotfiles from {local_path}...[/dim]")

    # Create tarball of dotfiles
    with tempfile.TemporaryDirectory() as tmpdir:
        tarball = Path(tmpdir) / "dotfiles.tar.gz"

        # Create tarball
        subprocess.run(
            ["tar", "-czf", str(tarball), "-C", str(local_path.parent), local_path.name],
            check=True,
        )

        # Copy to VM
        ssh_copy_file(vm_ip, vm_user, tarball, "/tmp/dotfiles.tar.gz")

    # Extract and install in VM
    script = f"""#!/bin/bash
set -e

cd ~
mkdir -p .dotfiles_local
tar -xzf /tmp/dotfiles.tar.gz -C .dotfiles_local --strip-components=1
rm /tmp/dotfiles.tar.gz

# Symlink dotfiles
for file in .dotfiles_local/.*; do
    if [ -f "$file" ] || [ -d "$file" ]; then
        base=$(basename "$file")
        if [ "$base" != ".git" ]; then
            ln -sf "$file" ~/"$base"
        fi
    fi
done

echo "Dotfiles applied successfully!"
"""

    ssh_run_script(vm_ip, vm_user, script)


def _apply_preset_dotfiles(vm_ip: str, vm_user: str, preset_name: str):
    """Apply built-in dotfile preset"""
    if preset_name not in DOTFILE_PRESETS:
        raise ValueError(f"Unknown preset: {preset_name}")

    preset = DOTFILE_PRESETS[preset_name]
    console.print(f"[dim]Applying preset: {preset_name} - {preset['description']}[/dim]")

    # Create script to apply dotfiles
    files_script = ""
    for filename, content in preset["files"].items():
        # Escape content for shell
        escaped_content = content.replace("'", "'\"'\"'")
        dir_path = str(Path(filename).parent)
        if dir_path != ".":
            files_script += f"mkdir -p ~/{dir_path}\n"
        files_script += f"cat > ~/{filename} << 'DOTFILE_EOF'\n{content}\nDOTFILE_EOF\n"

    # Add bashrc sourcing if extra bashrc exists
    if ".bashrc_extra" in preset["files"]:
        files_script += """
# Source extra bashrc
if [ -f ~/.bashrc_extra ]; then
    if ! grep -q "bashrc_extra" ~/.bashrc; then
        echo '' >> ~/.bashrc
        echo '# Sandbox extra config' >> ~/.bashrc
        echo '[ -f ~/.bashrc_extra ] && . ~/.bashrc_extra' >> ~/.bashrc
    fi
fi
"""

    script = f"""#!/bin/bash
set -e

{files_script}

echo "Preset '{preset_name}' applied successfully!"
"""

    ssh_run_script(vm_ip, vm_user, script)
