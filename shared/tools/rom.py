import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess


REPOSITORY = Path(__file__).resolve().parents[2]


def configuration(port):
    port = Path(port).resolve()
    data = json.loads((port / 'port.json').read_text(encoding='utf-8'))
    datetime.datetime.strptime(data['identity']['release_date'], '%m/%d/%Y')
    return port, data


def definitions(data):
    lines = []

    def visit(value, path):
        if isinstance(value, dict):
            for key, child in value.items():
                visit(child, path + [key.upper()])
        elif isinstance(value, (str, int, float)):
            token = json.dumps(value) if isinstance(value, str) else str(int(value) if isinstance(value, bool) else value)
            lines.append('%define CFG_' + '_'.join(path) + ' ' + token)

    visit(data, [])
    date = datetime.datetime.strptime(data['identity']['release_date'], '%m/%d/%Y')
    lines.append('%define CFG_BIOS_DATE ' + json.dumps(date.strftime('%m/%d/%y')))
    return '\n'.join(lines) + '\n'


def verify(port, image=None):
    port, data = configuration(port)
    image = Path(image) if image else port / 'build' / ('baios-' + port.name + '.bin')
    if not image.is_absolute():
        image = port / image
    raw = image.read_bytes()
    geometry = data['rom']
    if len(raw) != geometry['size']:
        raise ValueError('Incorrect ROM size')
    if sum(raw) & 255:
        raise ValueError('Incorrect ROM checksum')
    for region in data['rom'].get('checksum_regions', []):
        start, length, offset = region['start'], region['length'], region['offset']
        if not (0 <= start <= offset < start+length <= len(raw)):
            raise ValueError('Incorrect checksum region bounds')
        if sum(raw[start:start+length]) & 255:
            raise ValueError('Incorrect ROM region checksum')
    reset = geometry['reset_vector_offset']
    if geometry.get('reset_near', False):
        vector_ip = geometry['base'] + reset - (geometry['reset_segment'] << 4)
        target = (vector_ip + 3 + struct.unpack_from('<h', raw, reset + 1)[0]) & 0xFFFF
        if raw[reset] != 0xE9 or target != geometry['reset_entry_offset']:
            raise ValueError('Incorrect near reset target')
    elif raw[reset] != 0xEA or struct.unpack_from('<HH', raw, reset + 1) != (
            geometry['reset_entry_offset'], geometry['reset_segment']):
        raise ValueError('Incorrect reset target')
    entry = (geometry['reset_segment'] << 4) + geometry['reset_entry_offset'] - geometry['base']
    if not 0 <= entry < reset or raw[entry] != 0xFA:
        raise ValueError('Reset target is not the selected CLI startup entry')
    date = datetime.datetime.strptime(data['identity']['release_date'], '%m/%d/%Y').strftime('%m/%d/%y').encode('ascii')
    if raw[reset + 5:reset + 13] != date or raw[-2] != geometry['model_byte']:
        raise ValueError('Incorrect BIOS date or AT model byte')
    return {'path': str(image.resolve()), 'size': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def build(port, output='build', defines=()):
    port, data = configuration(port)
    output = (port / output).resolve()
    approved = (port / 'build').resolve()
    if not output.is_relative_to(approved):
        raise ValueError('Generated ROM output must stay under the selected port build directory')
    output.mkdir(parents=True, exist_ok=True)
    (output / 'configuration.inc').write_text(definitions(data), encoding='utf-8')
    nasm = shutil.which('nasm')
    if not nasm:
        nasm = str(Path(os.environ['LOCALAPPDATA']) / 'bin/NASM/nasm.exe')
    image = output / ('baios-' + port.name + '.bin')
    listing = output / ('baios-' + port.name + '.lst')
    command = [nasm, '-w+error', '-f', 'bin', '-I', str(port / 'src') + '/',
               '-I', str(REPOSITORY / 'shared/src') + '/', '-I', str(output) + '/',
               '-l', str(listing), '-o', str(image), str(port / 'src/bios.asm')]
    command[1:1] = ['-D' + value for value in defines]
    subprocess.run(command, check=True)
    raw = bytearray(image.read_bytes())
    if len(raw) != data['rom']['size']:
        raise ValueError('Assembler produced an incorrect ROM size')
    checksum = data['rom']['checksum_offset']
    for region in data['rom'].get('checksum_regions', []):
        start, length, offset = region['start'], region['length'], region['offset']
        if not (0 <= start <= offset < start+length <= len(raw)) or start <= checksum < start+length:
            raise ValueError('Incorrect checksum region bounds')
        raw[offset] = 0
        raw[offset] = (-sum(raw[start:start+length])) & 255
    raw[checksum] = 0
    raw[checksum] = (-sum(raw)) & 255
    image.write_bytes(raw)
    result = verify(port, image)
    from shared.tools.rom_footprint import write_report
    result['footprint']=write_report(image,listing,**({'module_offset':data['rom']['post_module']['offset'],'bank_bytes':data['rom']['post_module']['bank_bytes'],'transport':data['rom']['post_module']['transport']} if 'post_module' in data['rom'] else {}))
    result['identity'] = data['identity']
    (output / 'rom-checksums.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    return result
