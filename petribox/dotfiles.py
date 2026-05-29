"""
Dotfiles management - apply user configurations to dishes via incus.

Sources: a git URL, a local directory, or a built-in preset. Scripts run as
root inside the dish (incus exec) and write into the target user's home, then
chown so the user owns them.
"""

import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from rich.console import Console

from . import incus

console = Console()


def _run_script(name: str, script: str) -> None:
    """Push a script into the dish and execute it; raise on failure."""
    with tempfile.NamedTemporaryFile("w", suffix=".sh", delete=False) as handle:
        handle.write(script)
        local = handle.name
    try:
        remote = "/tmp/petribox-dotfiles.sh"
        incus.file_push(name, local, remote, mode="0755")
        proc = incus.exec_capture(name, ["bash", remote])
        if proc.returncode != 0:
            raise RuntimeError((proc.stderr or proc.stdout or "dotfiles script failed").strip())
    finally:
        import os

        os.unlink(local)


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
    name = Petri User
    email = petri@dish
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
    name: str,
    user: str,
    source: str,
    preset_name: Optional[str] = None,
):
    """Apply dotfiles to a dish.

    Args:
        name: dish (instance) name
        user: target username inside the dish
        source: git URL, local path, or preset name
        preset_name: explicit preset name override
    """
    if source.startswith(("http://", "https://", "git@")):
        _apply_git_dotfiles(name, user, source)
    elif source.startswith(("/", "~", "./")):
        _apply_local_dotfiles(name, user, source)
    elif source in DOTFILE_PRESETS or preset_name:
        _apply_preset_dotfiles(name, user, preset_name or source)
    elif Path(source).expanduser().exists():
        _apply_local_dotfiles(name, user, source)
    else:
        raise ValueError(f"Unknown dotfiles source: {source}")


def _home_prelude(user: str) -> str:
    return f'set -e\nH="/home/{user}"\nmkdir -p "$H"\n'


def _chown_coda(user: str) -> str:
    return f'\nchown -R {user}:{user} "$H"\necho "Dotfiles applied."\n'


def _apply_git_dotfiles(name: str, user: str, git_url: str):
    console.print(f"[dim]Cloning dotfiles from {git_url}...[/dim]")
    script = _home_prelude(user) + f"""
cd "$H"
if [ -d "$H/.dotfiles" ]; then
    git -C "$H/.dotfiles" pull
else
    git clone {git_url} "$H/.dotfiles"
fi
if [ -f "$H/.dotfiles/install.sh" ]; then
    cd "$H/.dotfiles" && bash install.sh
elif [ -f "$H/.dotfiles/Makefile" ]; then
    cd "$H/.dotfiles" && make install
else
    for file in "$H"/.dotfiles/.*; do
        base=$(basename "$file")
        [ "$base" = ".dotfiles" ] && continue
        [ "$base" = ".git" ] && continue
        [ "$base" = "." ] && continue
        [ "$base" = ".." ] && continue
        ln -sf "$file" "$H/$base"
    done
fi
""" + _chown_coda(user)
    _run_script(name, script)


def _apply_local_dotfiles(name: str, user: str, local_path: str):
    local_path = Path(local_path).expanduser()
    if not local_path.exists():
        raise FileNotFoundError(f"Dotfiles path not found: {local_path}")
    console.print(f"[dim]Copying dotfiles from {local_path}...[/dim]")

    with tempfile.TemporaryDirectory() as tmpdir:
        tarball = Path(tmpdir) / "dotfiles.tar.gz"
        subprocess.run(
            ["tar", "-czf", str(tarball), "-C", str(local_path.parent), local_path.name],
            check=True,
        )
        incus.file_push(name, str(tarball), "/tmp/petribox-dotfiles.tar.gz")

    script = _home_prelude(user) + """
mkdir -p "$H/.dotfiles_local"
tar -xzf /tmp/petribox-dotfiles.tar.gz -C "$H/.dotfiles_local" --strip-components=1
rm -f /tmp/petribox-dotfiles.tar.gz
for file in "$H"/.dotfiles_local/.*; do
    base=$(basename "$file")
    [ "$base" = ".git" ] && continue
    [ "$base" = "." ] && continue
    [ "$base" = ".." ] && continue
    ln -sf "$file" "$H/$base"
done
""" + _chown_coda(user)
    _run_script(name, script)


def _apply_preset_dotfiles(name: str, user: str, preset_name: str):
    if preset_name not in DOTFILE_PRESETS:
        raise ValueError(f"Unknown preset: {preset_name}")
    preset = DOTFILE_PRESETS[preset_name]
    console.print(f"[dim]Applying preset: {preset_name} - {preset['description']}[/dim]")

    files_script = ""
    for filename, content in preset["files"].items():
        dir_path = str(Path(filename).parent)
        if dir_path != ".":
            files_script += f'mkdir -p "$H/{dir_path}"\n'
        files_script += f'cat > "$H/{filename}" << \'DOTFILE_EOF\'\n{content}\nDOTFILE_EOF\n'

    if ".bashrc_extra" in preset["files"]:
        files_script += """
if ! grep -q "bashrc_extra" "$H/.bashrc" 2>/dev/null; then
    printf '\\n# petribox extra config\\n[ -f ~/.bashrc_extra ] && . ~/.bashrc_extra\\n' >> "$H/.bashrc"
fi
"""

    script = _home_prelude(user) + "\n" + files_script + _chown_coda(user)
    _run_script(name, script)
