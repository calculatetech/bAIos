"""Build the existing modular BIOS and extract its independently checked system ROM."""
import json
import hashlib
import argparse
from pathlib import Path
import sys

PORT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PORT.parent))
from shared.tools.rom import build, verify
from shared.tools.candidates import record


SOURCE_HASHES={'pb430-m27c1001.bin':'c0874e34b6439de784036c35dbb95d8b8a33ed855d1c402ea7763a1be6fc574a','acc386.BIN':'0a6be5271310c4b72ff54fc47a6fc524b81bfdf3bc3aab97bb3063192b08fdd1'}
VGA60_HASH='a055782154f63644da7f04038f0a163b8925f136172a55aca35960150da1b2a8'


def selected_vga(clock=60):
    if clock not in (50, 60):
        raise ValueError('VGA clock must be 50 or 60 MHz')
    raw = (PORT/'reference/gd542x-141-vga60.rom').read_bytes()
    assert hashlib.sha256(raw).hexdigest() == VGA60_HASH, 'Presario VGA60 input changed'
    if clock == 50:
        changed = bytearray(raw)
        changed[0x08E7] = 0x1C
        changed[0x7FFF] = (-sum(changed[:0x7FFF])) & 255
        raw = bytes(changed)
    return raw


def validate(image, vga60=True, *, vga_clock=60):
    for name,expected in SOURCE_HASHES.items():
        assert hashlib.sha256((PORT/'reference'/name).read_bytes()).hexdigest()==expected,('Reference input changed',name)
    result=verify(PORT,image)
    raw=Path(image).read_bytes()
    retained=selected_vga(vga_clock) if vga60 else (PORT/'reference/pb430-m27c1001.bin').read_bytes()[:32768]
    if vga60:
        assert raw[0x1F065:0x1F070]==bytes.fromhex('80fc1d7305ea972800c0cf'),'VGA installer compatibility entry'
    assert len(retained)==32768 and retained[:3]==bytes.fromhex('55aa40') and sum(retained)%256==0,'VGA size/header/checksum'
    assert raw[:32768]==retained,'Selected VGA changed'
    assert raw[32768:65536]==bytes([255])*32768,'Unused retained image region changed'
    assert len(raw[65536:])==65536 and sum(raw[65536:])%256==0,'System ROM checksum/size'
    result['programmer_checksum_sum32']=f'{sum(raw)&0xFFFFFFFF:08X}'
    return result


def run(output='build', defines=(), vga60=True, *, vga_clock=60):
    result = build(PORT, output, tuple(defines)+(('PB430_VGA60',) if vga60 else ()))
    image = Path(result['path'])
    raw = image.read_bytes()
    retained = (PORT / 'reference/pb430-m27c1001.bin').read_bytes()[:32768]
    assert raw[:32768] == retained and raw[32768:65536] == bytes([255])*32768
    system = raw[65536:]
    assert len(system) == 65536 and sum(system) % 256 == 0
    if vga60:
        vga=selected_vga(vga_clock)
        image.write_bytes(vga+raw[32768:])
    image.with_name('baios-pb430-system.bin').write_bytes(system)
    checked=validate(image,vga60,vga_clock=vga_clock)
    image.with_name('rom-checksums.json').write_text(json.dumps(result|checked,indent=2)+'\n')
    images = [image, image.with_name('baios-pb430-system.bin')]
    if vga60:
        variant = image.with_name(f'baios-pb430-vga{vga_clock}.bin')
        variant.write_bytes(image.read_bytes())
        images.append(variant)
    record(PORT, images, result['identity']['version'])
    return checked


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    group=parser.add_mutually_exclusive_group()
    group.add_argument('--vga50',action='store_true',help='Write the VGA1.41 50 MHz image in the selected build directory.')
    group.add_argument('--vga60',action='store_true',help='Write the standard VGA60 image in the selected build directory.')
    group.add_argument('--stock-vga',action='store_true',help='Use the original PB430 VGA ROM in the selected build directory.')
    group.add_argument('--interleave',action='store_true',help='Experimental cold four-bank interleave image under build/diagnostics/interleave.')
    group.add_argument('--cache-burst',action='store_true',help='Experimental cache-to-L1 burst image under build/diagnostics/cache-burst.')
    parser.add_argument('--output',help='Output directory inside this port build tree; overrides the selected variant directory.')
    args=parser.parse_args()
    output=args.output or ('build/diagnostics/cache-burst' if args.cache_burst else 'build/diagnostics/interleave' if args.interleave else 'build')
    result=run(output,defines=('PB430_CACHE_BURST_PROBE',) if args.cache_burst else ('PB430_INTERLEAVE_PROBE',) if args.interleave else (),vga60=not args.stock_vga,vga_clock=50 if args.vga50 else 60)
    result.pop('sha256',None)
    print(json.dumps(result, indent=2))
