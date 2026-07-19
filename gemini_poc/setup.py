from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENVS = [ROOT / '.venv', ROOT / 'venv']
RUSTUP_URL = 'https://static.rust-lang.org/rustup/dist/x86_64-pc-windows-msvc/rustup-init.exe'
NODE_URL = 'https://nodejs.org/dist/v20.13.0/node-v20.13.0-x64.msi'
VS_BUILD_TOOLS_ID = 'Microsoft.VisualStudio.2022.BuildTools'
TAURI_CLI_NAME = 'tauri-cli'


def find_windows_executable(name: str) -> Path | None:
    if path := shutil.which(name):
        return Path(path)

    if not sys.platform.startswith('win'):
        return None

    candidates: list[Path] = []
    if name == 'cargo':
        candidates = [Path.home() / '.cargo' / 'bin' / 'cargo.exe']
    elif name == 'git':
        candidates = [
            Path(r'C:\Program Files\Git\cmd\git.exe'),
            Path(r'C:\Program Files (x86)\Git\cmd\git.exe'),
        ]
    elif name == 'node':
        candidates = [
            Path(r'C:\Program Files\nodejs\node.exe'),
            Path(r'C:\Program Files (x86)\nodejs\node.exe'),
        ]
    elif name == 'npm':
        candidates = [
            Path(r'C:\Program Files\nodejs\npm.cmd'),
            Path(r'C:\Program Files (x86)\nodejs\npm.cmd'),
            Path.home() / 'AppData' / 'Roaming' / 'npm' / 'npm.cmd',
        ]
    elif name == 'pnpm':
        candidates = [Path.home() / 'AppData' / 'Roaming' / 'npm' / 'pnpm.cmd']
    elif name == 'yarn':
        candidates = [
            Path(r'C:\Program Files\nodejs\yarn.cmd'),
            Path.home() / 'AppData' / 'Roaming' / 'npm' / 'yarn.cmd',
        ]

    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def check_command(name: str) -> bool:
    return find_windows_executable(name) is not None


def add_cargo_to_path() -> None:
    cargo_dir = Path.home() / '.cargo' / 'bin'
    if cargo_dir.exists():
        os.environ['PATH'] = str(cargo_dir) + os.pathsep + os.environ.get('PATH', '')


def get_active_venv() -> Path | None:
    if venv := os.environ.get('VIRTUAL_ENV'):
        return Path(venv)
    if hasattr(sys, 'real_prefix') or sys.prefix != getattr(sys, 'base_prefix', sys.prefix):
        return Path(sys.prefix)
    return None


def configure_venv_activation_paths(venv_path: Path) -> None:
    cargo_dir = Path.home() / '.cargo' / 'bin'
    if not cargo_dir.exists():
        return

    cargo_dir_str = str(cargo_dir)

    if sys.platform.startswith('win'):
        activate_bat = venv_path / 'Scripts' / 'activate.bat'
        if activate_bat.exists():
            content = activate_bat.read_text(encoding='utf-8')
            marker = 'REM Added by AlienVox setup'
            if marker not in content:
                with open(activate_bat, 'a', encoding='utf-8') as f:
                    f.write('\n')
                    f.write(f'{marker}\n')
                    f.write(f'set "PATH={cargo_dir_str};%PATH%"\n')

        activate_ps1 = venv_path / 'Scripts' / 'Activate.ps1'
        if activate_ps1.exists():
            content = activate_ps1.read_text(encoding='utf-8')
            marker = '# Added by AlienVox setup'
            if marker not in content:
                with open(activate_ps1, 'a', encoding='utf-8') as f:
                    f.write('\n')
                    f.write(f'{marker}\n')
                    f.write('if ($env:Path -notlike "*{0}*") {{ $env:Path = "{0};" + $env:Path }}\n'.format(cargo_dir_str))
    else:
        activate_sh = venv_path / 'bin' / 'activate'
        if activate_sh.exists():
            content = activate_sh.read_text(encoding='utf-8')
            marker = '# Added by AlienVox setup'
            if marker not in content:
                with open(activate_sh, 'a', encoding='utf-8') as f:
                    f.write('\n')
                    f.write(f'{marker}\n')
                    f.write(f'export PATH="{cargo_dir_str}:$PATH"\n')


def run(cmd: list[str]) -> int:
    try:
        return subprocess.run(cmd, cwd=ROOT).returncode
    except FileNotFoundError:
        if sys.platform.startswith('win'):
            fallback = subprocess.list2cmdline(cmd)
            return subprocess.run(fallback, cwd=ROOT, shell=True).returncode
        print(f'Unable to execute command: {cmd[0]}')
        return 1


def check_tauri() -> bool:
    if not check_command('cargo'):
        return False
    cargo_cmd = cargo_executable()
    result = subprocess.run([cargo_cmd, 'tauri', '--version'], cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return result.returncode == 0


def download_rustup(destination: Path) -> None:
    print(f'Downloading rustup to {destination}')
    with urllib.request.urlopen(RUSTUP_URL) as response, open(destination, 'wb') as out_file:
        out_file.write(response.read())


def install_rustup(destination: Path) -> int:
    print('Installing Rust toolchain via rustup...')
    return run([str(destination), '-y'])


def download_file(destination: Path, url: str) -> None:
    print(f'Downloading {url} to {destination}')
    with urllib.request.urlopen(url) as response, open(destination, 'wb') as out_file:
        out_file.write(response.read())


def install_node_windows(destination: Path) -> int:
    print('Installing Node.js via MSI...')
    return run(['msiexec', '/i', str(destination), '/quiet', '/norestart'])


def install_git_windows() -> int:
    if check_command('winget'):
        print('Installing Git via winget...')
        return run(['winget', 'install', '--id', 'Git.Git', '-e', '--silent'])
    print('winget not available, cannot auto-install Git.')
    return 1


def install_vs_build_tools() -> int:
    if check_command('winget'):
        print('Installing Visual Studio Build Tools via winget...')
        return run(['winget', 'install', '--id', VS_BUILD_TOOLS_ID, '-e', '--silent'])
    print('winget not available, cannot auto-install Visual Studio Build Tools.')
    return 1


def install_tauri_cli() -> int:
    print('Installing Tauri CLI via cargo...')
    return run([cargo_executable(), 'install', TAURI_CLI_NAME])


def create_venv(target: Path) -> None:
    print(f'Creating Python virtual environment at {target}')
    run([sys.executable, '-m', 'venv', str(target)])


def venv_python(venv_dir: Path) -> str:
    if sys.platform.startswith('win'):
        return str(venv_dir / 'Scripts' / 'python.exe')
    return str(venv_dir / 'bin' / 'python')


def install_requirements(venv_dir: Path) -> int:
    req_file = ROOT / 'requirements.txt'
    if not req_file.exists():
        print('No requirements.txt found — skipping package install.')
        return 0
    python = venv_python(venv_dir)
    print(f'\nInstalling Python requirements from {req_file.name}…')
    print('(This may take several minutes on first run — torch alone is ~2 GB.)')
    rc = run([python, '-m', 'pip', 'install', '--upgrade', 'pip'])
    if rc != 0:
        print('pip upgrade failed — continuing anyway.')
    return run([python, '-m', 'pip', 'install', '-r', str(req_file)])


def remove_venv(target: Path) -> None:
    print(f'Removing existing virtual environment at {target}')
    if target.exists():
        shutil.rmtree(target)


def discover_cargo_executable() -> Path | None:
    if cargo_path := shutil.which('cargo'):
        return Path(cargo_path)
    expected = Path.home() / '.cargo' / 'bin' / 'cargo.exe'
    return expected if expected.exists() else None


def cargo_executable() -> str:
    if cargo_path := discover_cargo_executable():
        return str(cargo_path)
    return 'cargo'


def write_cargo_wrapper(cargo_path: Path) -> None:
    wrapper_path = ROOT / 'cargo.cmd'
    print(f'Creating local Cargo wrapper at {wrapper_path}')
    wrapper_content = (
        '@echo off\n'
        'setlocal\n'
        f'set "CARGO_BIN={cargo_path.parent}"\n'
        'if not exist "%CARGO_BIN%\\cargo.exe" (\n'
        '    echo Error: Cargo executable not found at "%CARGO_BIN%\\cargo.exe"\n'
        '    exit /b 1\n'
        ')\n'
        'set "PATH=%CARGO_BIN%;%PATH%"\n'
        '"%CARGO_BIN%\\cargo.exe" %*\n'
    )
    wrapper_path.write_text(wrapper_content, encoding='utf-8')


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='AlienVox gemini_poc bootstrap helper')
    parser.add_argument(
        '--full',
        action='store_true',
        help='Reset the local gemini_poc setup and recreate the Python virtual environment.',
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    print('AlienVox gemini_poc bootstrap')
    print('Python:', sys.version.splitlines()[0])
    print('Note: Python is only used for setup scripting and helper tasks. The core app is Rust + Tauri.')

    missing_required_tool = False
    is_windows = sys.platform.startswith('win')

    rust_installed = check_command('cargo')
    if not rust_installed and is_windows:
        print('\nRust cargo not found. Installing Rust toolchain via rustup automatically...')
        with tempfile.TemporaryDirectory() as temp_dir:
            installer = Path(temp_dir) / 'rustup-init.exe'
            download_rustup(installer)
            if install_rustup(installer) != 0:
                print('Rust installation failed. Please install rustup manually from https://rustup.rs/')
            else:
                print('Rust installer completed. Reloading Cargo path...')
                add_cargo_to_path()
        rust_installed = check_command('cargo')

    if rust_installed and is_windows:
        if cargo_path := discover_cargo_executable():
            write_cargo_wrapper(cargo_path)
            print('Created a local cargo.cmd wrapper so cargo can be launched from this folder in cmd.')
            print('If Cargo is not yet available in this shell, use `cargo.cmd <command>` from gemini_poc or reopen the shell.')

    if not rust_installed:
        missing_required_tool = True
        print('\nERROR: Rust cargo not found.')
        print('Install Rust using rustup: https://rustup.rs/')
        if is_windows:
            print('Installing Visual Studio Build Tools is also required for the MSVC toolchain.')
            if install_vs_build_tools() == 0:
                print('Visual Studio Build Tools install attempted; you may need to reboot.')
            else:
                print('Visual Studio Build Tools install failed or winget is unavailable.')
        print('If rustup is already installed, reopen your shell so Cargo is available on PATH.')
    else:
        print('\nRust toolchain detected:')
        run([cargo_executable(), '--version'])

    git_installed = check_command('git')
    if not git_installed and is_windows:
        print('\nGit not found. Attempting to install Git via winget...')
        if install_git_windows() == 0:
            git_installed = check_command('git')
    if not git_installed:
        missing_required_tool = True
        print('\nERROR: Git not found. Please install Git manually if winget is unavailable.')
    else:
        print('\nGit is available.')

    node_installed = check_command('npm') or check_command('pnpm') or check_command('yarn')
    if not node_installed and is_windows:
        print('\nNode.js not found. Installing Node.js automatically...')
        with tempfile.TemporaryDirectory() as temp_dir:
            node_installer = Path(temp_dir) / 'node-installer.msi'
            download_file(node_installer, NODE_URL)
            if install_node_windows(node_installer) != 0:
                print('Node.js installation failed. Please install Node.js manually from https://nodejs.org/')
        node_installed = check_command('npm') or check_command('pnpm') or check_command('yarn')
    if not node_installed:
        missing_required_tool = True
        print('\nERROR: Node.js not found. Please install Node.js manually if the installer failed.')

    if node_installed:
        if check_command('npm'):
            print('\nNode/npm toolchain detected:')
            run(['npm', '--version'])
        elif check_command('pnpm'):
            print('\npnpm toolchain detected:')
            run(['pnpm', '--version'])
        else:
            print('\nyarn toolchain detected:')
            run(['yarn', '--version'])

    if check_tauri():
        print('\nTauri command available.')
    else:
        if rust_installed:
            print('\nTauri CLI not found. Installing via cargo...')
            if install_tauri_cli() == 0:
                print('Tauri CLI installed successfully.')
            else:
                print('Failed to install Tauri CLI. You may need to run: cargo install tauri-cli')
        else:
            print('\nWARNING: Tauri command not found because Rust/Cargo is missing.')

    env_dir = next((p for p in VENVS if p.exists()), None)
    if args.full and env_dir is not None:
        active_venv = get_active_venv()
        if active_venv is not None and active_venv.resolve() == env_dir.resolve():
            print('\nERROR: Cannot remove the active virtual environment while it is activated.')
            print('Please deactivate the current shell and rerun with --full.')
            return 1
        remove_venv(env_dir)
        env_dir = None

    if env_dir is None:
        env_dir = ROOT / '.venv'
        create_venv(env_dir)
    else:
        print(f'Existing virtual environment found at {env_dir}')
        print('No changes made. Run with --full to reset the local setup if needed.')

    if env_dir is not None:
        configure_venv_activation_paths(env_dir)
        if install_requirements(env_dir) != 0:
            print('\nWARNING: Some Python requirements failed to install.')
            print('Run manually:  pip install -r requirements.txt')

    if missing_required_tool:
        print('\nBootstrap incomplete: required toolchain components are missing.')
        return 1

    print('\nBuilding Rust prototype...')
    build_result = run([cargo_executable(), 'build'])
    if build_result != 0:
        print('Rust build failed. Fix any errors and rerun this script.')
        return build_result

    if not check_tauri() and rust_installed:
        print('\nInstalling Tauri CLI via cargo...')
        if install_tauri_cli() != 0:
            print('Failed to install Tauri CLI. Please run: cargo install tauri-cli')
            return 1

    print('\nBootstrap complete. The prototype is built and ready to run.')
    print('Run the app with:')
    print('       cargo run')

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
