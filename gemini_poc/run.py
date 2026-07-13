from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def run_command(command: list[str], check: bool = True) -> int:
    print('> ' + ' '.join(command))
    result = subprocess.run(command, cwd=ROOT)
    if check and result.returncode != 0:
        raise SystemExit(result.returncode)
    return result.returncode


def setup() -> None:
    run_command([sys.executable, 'setup.py'])


def build() -> None:
    run_command(['cargo', 'build'])


def run() -> None:
    run_command(['cargo', 'run'])


def lint() -> None:
    run_command(['cargo', 'fmt', '--all', '--', '--check'])
    if shutil.which('cargo') is not None:
        run_command(['cargo', 'clippy', '--all-targets', '--all-features', '--', '-D', 'warnings'])


def test() -> None:
    run_command(['cargo', 'test'])


def clean() -> None:
    run_command(['cargo', 'clean'])


def check() -> None:
    run_command(['cargo', 'check'])


def tauri_dev() -> None:
    """Run the Tauri frontend dev server (Balabolka-style UI)."""
    TAURI_DIR = ROOT / 'src-tauri'
    print('> cargo tauri dev')
    result = subprocess.run(['cargo', 'tauri', 'dev'], cwd=TAURI_DIR)
    if result.returncode != 0:
        raise SystemExit(result.returncode)


def tauri_build() -> None:
    """Build the Tauri app for distribution."""
    TAURI_DIR = ROOT / 'src-tauri'
    print('> cargo tauri build')
    result = subprocess.run(['cargo', 'tauri', 'build'], cwd=TAURI_DIR)
    if result.returncode != 0:
        raise SystemExit(result.returncode)


def doc() -> None:
    run_command(['cargo', 'doc', '--no-deps'])


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='gemini_poc SDLC helper')
    parser.add_argument('command', nargs='?', help='Command to run', choices=['setup', 'build', 'run', 'lint', 'test', 'clean', 'check', 'doc', 'tauri-dev', 'tauri-build', 'all'])
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.command is None:
        print('Usage: python run.py <setup|build|run|lint|test|clean|check|doc|tauri-dev|tauri-build|all>')
        return 1

    if args.command == 'setup':
        setup()
    elif args.command == 'build':
        build()
    elif args.command == 'run':
        run()
    elif args.command == 'lint':
        lint()
    elif args.command == 'test':
        test()
    elif args.command == 'clean':
        clean()
    elif args.command == 'check':
        check()
    elif args.command == 'doc':
        doc()
    elif args.command == 'tauri-dev':
        tauri_dev()
    elif args.command == 'tauri-build':
        tauri_build()
    elif args.command == 'all':
        setup()
        build()
        lint()
        test()
    else:
        raise SystemExit(f'Unknown command: {args.command}')

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
