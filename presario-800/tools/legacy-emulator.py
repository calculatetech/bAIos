"""Private, qualified 86Box range correction for the native network fixture."""
import hashlib
from pathlib import Path
import shutil

SOURCE_SHA256 = '034e876d37afc6d9b42e4055a0bb4bb122948131b185203d67c98274553c56c9'
OUTPUT_SHA256 = '7408b232268ea7f600a2d55f923248d57d543fe54a5ec51145e0dff2081d2e07'
PATCHES = (
    (0x40AE57, bytes.fromhex('4d39e34d0f47dc'), bytes.fromhex('e93a0300009090')),
    (0x40B194, bytes.fromhex('66662e0f1f84000000000066662e0f1f840000000000'),
     bytes.fromhex('eb144839d1480f42ca4d39e34d0f47dce9b5fcffff90')),
    (0x412641, bytes.fromhex('4839ce480f46ce'), bytes.fromhex('e91f0900009090')),
    (0x412F63, bytes.fromhex('0f1f800000000066662e0f1f84000000000066662e0f1f840000000000'),
     bytes.fromhex('eb1b4c8b9424c00000004d39d14d0f42ca4839ce480f46cee9c8f6ffff')),
)


def prepare(source, destination):
    source, destination = Path(source), Path(destination)
    original = source.read_bytes()
    if hashlib.sha256(original).hexdigest() != SOURCE_SHA256:
        raise ValueError('Network fixture requires the retained 86Box b10408 executable.')
    for offset, before, after in PATCHES:
        if len(before) != len(after) or original[offset:offset+len(before)] != before:
            raise ValueError('Qualified 86Box instruction span does not match.')
    # Keep the original runtime and companions untouched; this VM owns the copy.
    shutil.copytree(source.parent, destination)
    target = destination/source.name
    result = bytearray(original)
    for offset, before, after in PATCHES:
        result[offset:offset+len(before)] = after
    if hashlib.sha256(result).hexdigest() != OUTPUT_SHA256:
        raise ValueError('Qualified 86Box output identity does not match.')
    target.write_bytes(result)
    if target.read_bytes() != result:
        raise ValueError('Private 86Box output verification failed.')
    print(f'Network emulator source SHA256 {SOURCE_SHA256}; private SHA256 {OUTPUT_SHA256}: {target}',flush=True)
    return target
