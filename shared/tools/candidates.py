"""Record assembly identity and finish a port-local flash candidate."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def save(path, data):
    temporary = path.with_suffix(path.suffix+'.tmp')
    temporary.write_text(json.dumps(data, indent=2)+'\n', encoding='utf-8')
    temporary.replace(path)


def latest(build, data):
    previous = json.loads((build/'LATEST.json').read_text()) if (build/'LATEST.json').exists() else {}
    completed = data if data['state'] == 'completed candidate' else previous.get('completed')
    if completed is None and previous.get('state') == 'completed candidate':
        completed = previous
    data = dict(data)
    if completed:
        data['completed'] = {key:completed[key] for key in ('version','built_at','files')}
    save(build/'LATEST.json', data)
    lines = [f"State: {data['state']}", f"Version: {data['version']}",
             f"Built UTC: {data['built_at']}",
             'Physical hardware qualification is separate from this build record.', '']
    lines += [f"{row['name']}  {row['size']} bytes  SUM32 {row['sum32']}" for row in data['files']]
    if completed and data['state'] != 'completed candidate':
        lines += ['', 'Last completed candidate:']
        lines += [f"{row['name']}  {row['size']} bytes  SUM32 {row['sum32']}" for row in completed['files']]
    (build/'LATEST.txt').write_text('\n'.join(lines)+'\n', encoding='utf-8')


def record(port, images, version, built_at=None):
    port = Path(port).resolve()
    images = [Path(path).resolve() for path in images]
    folder = images[0].parent
    if not folder.is_relative_to(port/'build') or any(path.parent != folder for path in images):
        raise ValueError('Candidate images must share one directory inside their port build')
    if not re.fullmatch(r'\d+\.\d+\.\d+', version):
        raise ValueError('Expected a source version X.Y.Z')
    stamp = built_at or datetime.now(timezone.utc).isoformat(timespec='seconds')
    if datetime.fromisoformat(stamp).utcoffset() != timezone.utc.utcoffset(None):
        raise ValueError('Build timestamp must be UTC')
    manifest = folder/'build-info.json'
    previous = json.loads(manifest.read_text()) if manifest.exists() else {}
    rows = {row['name']:row for row in previous.get('files', [])
            if previous.get('version') == version and (folder/row['name']).is_file()
            and digest(folder/row['name']) == row['sha256']}
    for path in images:
        raw = path.read_bytes()
        rows[path.name] = dict(name=path.name, size=len(raw), sha256=hashlib.sha256(raw).hexdigest(),
                              sum32=f'{sum(raw):08X}', built_at=stamp)
    data = dict(schema=1, state='bench iteration', version=version, built_at=stamp,
                files=[rows[name] for name in sorted(rows)])
    save(manifest, data)
    if folder == port/'build':
        latest(folder, data)
    return data


def checked(port, directory=None):
    port = Path(port).resolve()
    build = port/'build'
    folder = (build if directory is None else Path(directory)).resolve()
    if not folder.is_relative_to(build):
        raise ValueError('Candidate source must be inside this port build')
    data = json.loads((folder/'build-info.json').read_text())
    version = data['version']  # Identity belongs to the assembly, not current source.
    if not re.fullmatch(r'\d+\.\d+\.\d+', version) or not data['files']:
        raise ValueError('Missing build identity or artifact group')
    contract = port/'validation.json'
    required = {row['name'] for row in json.loads(contract.read_text()).get('artifacts', [])} if contract.exists() else set()
    missing = required - {row['name'] for row in data['files']}
    if missing:
        raise ValueError('Incomplete artifact group: '+', '.join(sorted(missing)))
    members = []
    for row in data['files']:
        name = row['name']
        if Path(name).name != name or '/' in name or '\\' in name or name in ('.', '..'):
            raise ValueError('Artifact name must be a filename')
        source = folder/name
        if digest(source) != row['sha256'] or source.stat().st_size != row['size']:
            raise ValueError('Artifact changed since assembly: '+name)
        members.append(source)
    physical = [p for p in members if p.suffix == '.bin' and p.stat().st_size == 131072]
    if len(physical) > 1 and len({p.read_bytes()[65536:] for p in physical}) != 1:
        raise ValueError('VGA variants do not share the same system BIOS')
    systems = [p for p in members if p.stem.endswith('-system') and p.stat().st_size == 65536]
    if physical and any(system.read_bytes() != physical[0].read_bytes()[65536:] for system in systems):
        raise ValueError('System ROM does not match the physical image')
    lanes = {p.stem.rsplit('-',1)[-1]:p for p in members if p.stem.endswith(('-even','-odd'))}
    if lanes:
        if set(lanes) != {'even','odd'}:
            raise ValueError('Both programmer lanes are required')
        combined = folder/(lanes['even'].stem[:-5]+'.bin')
        if combined not in members:
            raise ValueError('Combined image is missing from the programmer group')
        low, high = lanes['even'].read_bytes(), lanes['odd'].read_bytes()
        if len(low) != len(high):
            raise ValueError('Programmer lanes have different sizes')
        raw = bytearray(len(low)*2)
        raw[::2], raw[1::2] = low, high
        if raw != combined.read_bytes():
            raise ValueError('Programmer lanes do not reconstruct the combined image')
    times = [datetime.fromisoformat(row['built_at']) for row in data['files']]
    if any(t.utcoffset() != timezone.utc.utcoffset(None) for t in times):
        raise ValueError('Build timestamp must be UTC')
    return data, members, max(times)


def finish(port, directory=None):
    port = Path(port).resolve()
    build = port/'build'
    data, members, built_at = checked(port,directory)
    version = data['version']
    stamp = built_at.strftime('%Y%m%dT%H%M%SZ')
    completed = []
    targets = [build/f'{source.stem}-v{version}-{stamp}{source.suffix}' for source in members]
    for row, target in zip(data['files'], targets):
        if target.exists() and digest(target) != row['sha256']:
            raise ValueError('Build identity already names different bytes: '+target.name)
    for row, source, target in zip(data['files'], members, targets):
        if not target.exists():
            shutil.copy2(source, target)
        completed.append(row|{'name':target.name})
    result = dict(schema=1, state='completed candidate', version=version,
                  built_at=built_at.isoformat(timespec='seconds'), files=completed)
    latest(build, result)
    return result
