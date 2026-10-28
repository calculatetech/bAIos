"""Check current port organization without building or booting firmware."""
import argparse
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILD_DIRECTORIES = {'diagnostics','tests','review','research','releases','tmp'}


def check(root=ROOT):
    errors = []
    ports = sorted(p for p in root.iterdir() if p.is_dir() and not p.name.startswith('.')
                   and p.name not in {'tools','shared','reference','docs','build'}
                   and ((p/'src/bios.asm').is_file() or (p/'build').is_dir()))
    for port in ports:
        for folder, directories, files in os.walk(port, followlinks=False):
            path = Path(folder)
            if '.git' in directories or '.git' in files:
                errors.append(f'{path.relative_to(root)}: repository copy belongs in .agent/worktrees/')
                directories[:] = []
            else:
                directories[:] = [d for d in directories if not (path/d).is_symlink()]
        build = port/'build'
        if not build.exists():
            continue
        for path in build.iterdir():
            if path.is_dir() and path.name not in BUILD_DIRECTORIES:
                errors.append(f'{path.relative_to(root)}: use a documented build category')
            elif path.is_file() and path.suffix.lower() in {'.com','.exe','.vhd','.iso','.img','.86f'}:
                errors.append(f'{path.relative_to(root)}: diagnostic, disposable media or permanent input at build root')
    return errors


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=ROOT)
    args = parser.parse_args()
    errors = check(args.root.resolve())
    for error in errors: print(error)
    if not errors: print('PASS port ownership and canonical build directories')
    raise SystemExit(bool(errors))
