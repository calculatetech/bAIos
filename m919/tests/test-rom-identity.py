"""Check the ROM banner and execute the relocated SMM installation/command."""
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import sys

PORT=Path(__file__).resolve().parents[1]
ROOT=PORT.parent
sys.path.insert(0,str(ROOT))
from shared.tools.rom import verify
from shared.tools.ram_proof import Listing
from unicorn import UC_HOOK_CODE
from unicorn import x86_const as x


def main():
    image=PORT/'build/baios-m919.bin'
    raw=image.read_bytes();listing=Listing(image.with_suffix('.lst'))
    identity=json.loads((PORT/'port.json').read_text())['identity']
    assert raw[:4]==b'\x55\xAA\x04\xCB' and sum(raw[:65536])%256==0
    assert raw[0x800:0x804]==b'\x55\xAA\x7C\xCB'
    assert sum(raw[:0x800])%256==sum(raw[0x800:65536])%256==0
    assert raw[8:16]==b'BAICLK1\0' and raw[0x14:0x1C]==b'BAISMM1\0'
    assert struct.unpack_from('<HH',raw,0x10)==(listing.symbol('board_clock_command'),0xF000)
    begin=listing.symbol('rom_identification');end=listing.symbol('rom_identification_end')
    assert (begin,end)==(0x20,0x60)
    assert raw[begin:begin+16].decode('ascii').rstrip()=='bAIos '+identity['model']
    assert raw[begin+16:begin+32].decode('ascii').rstrip()=='v'+identity['version']
    assert raw[begin+32:end]==b'    [o_o]           /|_|\\       '
    rom=json.loads((PORT/'port.json').read_text())['rom']
    config=rom['post_module']
    assert listing.symbol('pnp_module_start')==config['offset']
    boundary=32768
    assert boundary==32768 and config['offset']+config['bank_bytes']==boundary
    assert raw[boundary:65536]==b'\xFF'*(65536-boundary),'factory ESCD region is not erased'
    assert raw[config['offset']:config['offset']+8]==b'BAIPNP2\0'

    spec=importlib.util.spec_from_file_location('identity_smm',PORT/'tools/smm_activation_proof.py')
    smm=importlib.util.module_from_spec(spec);spec.loader.exec_module(smm)
    smm.OUTPUT=image.parent;smm.ROM=image
    rows=[]
    for family in smm.MAPS:
        for warm in (False,True):
            board=smm.Board(family=family,warm=warm,decoded=False)
            def no_banner_execution(cpu,address,size,user):
                assert not 0xE0014<=address<0xE0060,hex(address)
            board.u.hook_add(UC_HOOK_CODE,no_banner_execution,None,0xE0014,0xE005F)
            assert board.early_startup()==1
            board.call('board_smm_command')
            assert board.u.reg_read(x.UC_X86_REG_AX)==0
            assert not board.u.reg_read(x.UC_X86_REG_EFLAGS)&1
            rows.append({'CPU':family,'warm':warm,'install_and_command':'PASS'})
    result={'integrity':verify(PORT,image),'SUM32':f'{sum(raw)&0xFFFFFFFF:08X}',
            'banner_rows':[raw[i:i+16].decode('ascii') for i in range(begin,end,16)],
            'fixed_diagnostic_header':'PASS','private_module_binding':'PASS','SMM':rows,
            'SMM_handler_SHA256':hashlib.sha256(board.handler).hexdigest(),
            'limit':'Modeled SMM/PCI/save/RSM seams; physical hardware remains untested.'}
    out=PORT/'build/tests/rom-identity';out.mkdir(parents=True,exist_ok=True)
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
