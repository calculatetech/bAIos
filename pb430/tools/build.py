"""Build the existing modular BIOS and extract its independently checked system ROM."""
import json
import hashlib
import argparse
from pathlib import Path
import sys

PORT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PORT.parent))
from shared.tools.rom import build, verify


SOURCE_HASHES={'pb430-m27c1001.bin':'c0874e34b6439de784036c35dbb95d8b8a33ed855d1c402ea7763a1be6fc574a','acc386.BIN':'0a6be5271310c4b72ff54fc47a6fc524b81bfdf3bc3aab97bb3063192b08fdd1'}
VGA60_HASH='a055782154f63644da7f04038f0a163b8925f136172a55aca35960150da1b2a8'


def validate(image, vga60=True):
    for name,expected in SOURCE_HASHES.items():
        assert hashlib.sha256((PORT/'reference'/name).read_bytes()).hexdigest()==expected,('Reference input changed',name)
    result=verify(PORT,image)
    raw=Path(image).read_bytes()
    retained=(PORT/'reference/gd542x-141-vga60.rom').read_bytes() if vga60 else (PORT/'reference/pb430-m27c1001.bin').read_bytes()[:32768]
    if vga60:
        assert hashlib.sha256(retained).hexdigest()==VGA60_HASH,'Presario VGA60 input changed'
        assert raw[0x1F065:0x1F070]==bytes.fromhex('80fc1d7305ea972800c0cf'),'VGA installer compatibility entry'
    assert len(retained)==32768 and retained[:3]==bytes.fromhex('55aa40') and sum(retained)%256==0,'VGA size/header/checksum'
    assert raw[:32768]==retained,'Selected VGA changed'
    assert raw[32768:65536]==bytes([255])*32768,'Unused retained image region changed'
    assert len(raw[65536:])==65536 and sum(raw[65536:])%256==0,'System ROM checksum/size'
    result['programmer_checksum_sum32']=f'{sum(raw)&0xFFFFFFFF:08X}'
    return result


def run(output='build', defines=(), vga60=True):
    result = build(PORT, output, tuple(defines)+(('PB430_VGA60',) if vga60 else ()))
    image = Path(result['path'])
    raw = image.read_bytes()
    retained = (PORT / 'reference/pb430-m27c1001.bin').read_bytes()[:32768]
    assert raw[:32768] == retained and raw[32768:65536] == bytes([255])*32768
    system = raw[65536:]
    assert len(system) == 65536 and sum(system) % 256 == 0
    if vga60:
        vga=(PORT/'reference/gd542x-141-vga60.rom').read_bytes()
        assert hashlib.sha256(vga).hexdigest()==VGA60_HASH
        image.write_bytes(vga+raw[32768:])
    image.with_name('baios-pb430-system.bin').write_bytes(system)
    checked=validate(image,vga60)
    image.with_name('rom-checksums.json').write_text(json.dumps(result|checked,indent=2)+'\n')
    return checked


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    group=parser.add_mutually_exclusive_group()
    group.add_argument('--vga60',action='store_true',help='Write the standard VGA60 image separately under build/vga60.')
    group.add_argument('--stock-vga',action='store_true',help='Use the original PB430 VGA ROM under build/stock-vga.')
    group.add_argument('--interleave',action='store_true',help='Experimental cold four-bank interleave image under build/interleave.')
    group.add_argument('--cache-burst',action='store_true',help='Experimental cache-to-L1 burst image under build/cache-burst.')
    args=parser.parse_args()
    result=run('build/cache-burst' if args.cache_burst else 'build/interleave' if args.interleave else 'build/stock-vga' if args.stock_vga else 'build/vga60' if args.vga60 else 'build',defines=('PB430_CACHE_BURST_PROBE',) if args.cache_burst else ('PB430_INTERLEAVE_PROBE',) if args.interleave else (),vga60=not args.stock_vga)
    result.pop('sha256',None)
    print(json.dumps(result, indent=2))
