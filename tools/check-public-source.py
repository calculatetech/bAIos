"""Check public source without private ROM inputs."""
import ast
import json
from pathlib import Path
import re
import subprocess


ROOT = Path(__file__).resolve().parents[1]
PRIVATE = re.compile(
    r'(?i)(?:[a-z]:[/\\](?:users|backups|drivers|operating systems|software)[/\\]'
    r'|/[h]ome/[^/\s]+/|/[U]sers/[^/\s]+/'
    r'|gh[pousr]_[a-z0-9]{20,}|github_pat_[a-z0-9_]{20,}'
    r'|AKIA[A-Z0-9]{16}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----)')
TEXT = {'.md', '.py', '.ps1', '.asm', '.inc', '.json', '.yml', '.yaml'}


def main():
    files = subprocess.check_output(
        ['git', 'ls-files', '-z'], cwd=ROOT).decode('utf-8').split('\0')
    errors = []
    for name in filter(None, files):
        path = Path(name)
        if (set(path.parts) & {'reference', 'build', '.agent', '.repowise', '.vscode'}
                or path.name == '.mcp.json'
                or path.suffix.lower() in {'.exe', '.rom', '.pdf', '.vhd', '.iso', '.zip', '.jpg', '.png'}
                or (path.suffix.lower() == '.bin' and name != 'presario-800/tests/setup-default-screen.bin')):
            errors.append(f'{name}: private or generated input class')
        if path.suffix.lower() not in TEXT and path.name not in {'LICENSE', '.gitignore', '.gitattributes'}:
            continue
        try:
            text = (ROOT / path).read_text(encoding='utf-8')
            if PRIVATE.search(text):
                errors.append(f'{name}: credential or host-specific path pattern')
            if path.suffix == '.py':
                ast.parse(text, filename=name)
            elif path.suffix == '.json':
                json.loads(text)
        except (UnicodeError, SyntaxError, ValueError) as error:
            errors.append(f'{name}: {type(error).__name__}')
    if errors:
        raise SystemExit('\n'.join(errors))
    print('PASS public source paths, text patterns, Python syntax, and JSON syntax')


if __name__ == '__main__':
    assert PRIVATE.search('C:' + '/Us' + 'ers/example/private.txt')
    assert PRIVATE.search('ghp_' + 'x' * 36)
    assert not PRIVATE.search('reference/chipsets/acc/ACC2046.pdf')
    main()
