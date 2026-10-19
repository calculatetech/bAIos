"""Verify original AMI inputs, startup tables and optional native comparisons."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

PORT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PORT.parent))
REGISTER_MAP = bytes.fromhex('40 41 42 43 44 45 46 47 50 51 52 53 54 55 56 57 70 71 72 73 74 75 76 80 81 90 91 92 A0 A1 A2 A3 A4 A5 A6 A7 A8 50 51 52 53 54 55 56 57 58 59 5A 5B 5C 5D 5E 5F 60 61')


def native(raw, name):
    from capstone import Cs, CS_ARCH_X86, CS_MODE_16, CS_GRP_JUMP, CS_GRP_CALL
    from shared.tools.ami94 import decode

    expected = {
        '9190506.BIN': ('05/06/1996',0xFC7A,0x29A0,'3311121e2f9d251d121c84213a9d2478163921110691b0398690ee7e24a1f690'),
        '3-6-96.BIN': ('03/06/1996',0xFC7A,0x296D,'0b9aad7961b3484879594c686162ef50016ab990a18fea57a8627ac700200017'),
        '9191016s.rom': ('10/16/1996',0xFC7A,0x297F,'279d07ecdedb2e2d4a86341438bcbe46cacdd4f9f60d554310a5a39b9c3fb43b'),
        '9190914S.ROM': ('09/15/1998',0xFCAA,0x297A,'d0ab89248c1e0156882f4f7bc0d110bb96c2afdf5ee18968a1b0a96911d72e6c'),
    }
    date,early,start,main_hash = expected[name]
    main,modules = decode(raw)
    assert hashlib.sha256(main).hexdigest() == main_hash,name
    assert main[0x813A:0x8144].decode('ascii') == date,name
    assert hashlib.sha256(raw[early:early+254]).hexdigest() == 'ed43826bd55dee679ee3809f028a25008a8161c8479a298f18f0694f08b518c7',name
    loop = start+0xB3
    assert main[loop:loop+12] == bytes.fromhex('66 BE 00 00 02 00 66 BB 00 00 02 00'),name
    for relative in (0x2C,0x3D,0x4D,0x5E,0x6E):
        assert main[loop+relative] == 0x49,name  # DEC CX, not DEC ECX.

    def target(at):
        assert main[at] == 0xE8
        return (at+3+struct.unpack_from('<h',main,at+1)[0]) & 0xFFFF
    reader,writer,rmw = (target(start+relative) for relative in (0x0C,0x24,0x3E))
    helpers = {reader:'HB-read',writer:'HB-write',rmw:'HB-RMW',
               reader+0x2E:'PCI-read',writer+0x2E:'PCI-write'}
    helper_bytes = {label:main[at:at+(17 if label=='HB-RMW' else 16)]
                    for at,label in helpers.items()}
    md = Cs(CS_ARCH_X86,CS_MODE_16)
    md.detail = True
    normalized = []
    descriptors = []
    for insn in md.disasm(main[start:start+0x178],start):
        operand = insn.op_str
        if insn.group(CS_GRP_JUMP) or insn.group(CS_GRP_CALL):
            if operand.startswith('0x') and ':' not in operand:
                address = int(operand,16) & 0xFFFF
                operand = (f'local+{address-start:04X}' if start<=address<=start+0x178
                           else helpers.get(address,f'call_{address:04X}'))
        elif insn.mnemonic=='mov' and operand.startswith(('di, 0x','ax, 0x')):
            address = int(operand.split('0x')[1],16)
            if start<=address<=start+0x178:
                operand = operand.replace(hex(address),f'local+{address-start:04X}')
        elif insn.mnemonic=='lgdt':
            address = insn.operands[0].mem.disp
            limit,base = struct.unpack_from('<HI',main,address)
            if 0x66 not in insn.prefix:
                base &= 0xFFFFFF  # A 16-bit LGDT loads only the low 24 base bits.
            assert 0xF0000<=base and base+limit<0x100000 and limit<=0x3FF,name
            descriptors.append(main[base-0xF0000:base-0xF0000+limit+1])
            operand = 'cs:[cache-gdt]'
        normalized.append((insn.address-start,insn.mnemonic,operand))
    return {'release_date':date,'main_sha256':main_hash,'cache_probe_offset':f'{early:04X}',
            'late_cache_offset':f'{start:04X}','native_module_hashes':{f'{key:02X}':value['sha256'] for key,value in modules.items() if 'sha256' in value},
            'checksum_limit':'Native placement/signatures and known outputs verified; original module checksum remains unknown'}, (normalized,helper_bytes,descriptors)


def native_bounds():
    from shared.tools.ami94 import decode
    raw = (PORT/'reference/9190506.BIN').read_bytes()
    malformed = [raw[:-1],b'INVALID!'+raw[8:]]
    for offset,value,form in ((0x10,8,'H'),(0x30,0x20000,'I'),(0x34,0x10001,'I')):
        altered = bytearray(raw)
        struct.pack_into('<'+form,altered,offset,value)
        malformed.append(bytes(altered))
    for altered in malformed:
        try:
            decode(altered)
        except ValueError:
            pass
        else:
            raise AssertionError('AMI94 decoder accepted malformed input bounds')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--native',action='store_true')
    args = parser.parse_args()
    images = {}
    algorithms = {}
    for image in (PORT/'reference').iterdir():
        if image.suffix.lower() not in ('.bin','.rom'):
            continue
        raw = image.read_bytes()
        assert len(raw) == 131072 and raw.startswith(b'AMIBIOSC10/10/94'),image.name
        assert raw[0x1FFF0:0x1FFF5] == bytes.fromhex('EA 5B E0 00 F0'),image.name
        module = raw.find(b'AMIBIOS ')
        assert module in (0xE770,0xE7A0),image.name
        start,end = struct.unpack_from('<HH',raw,module+0x44)
        table = raw[module+start:module+end]
        assert len(table) == 110,image.name
        mapping = raw.find(REGISTER_MAP,module)
        assert mapping in (0xF52B,0xF55B),image.name
        registers = {'HB':{},'SB':{}}
        for index in range(55):
            encoded,value = table[index*2:index*2+2]
            assert encoded == 0x40+index,image.name
            registers['SB' if index<37 else 'HB'][f'{REGISTER_MAP[index]:02X}'] = f'{value:02X}'
        assert list(registers['HB'].values()) == '00 00 01 00 00 00 FF 0F FF 0F 00 00 00 20 00 FF 00 02'.split()
        recovery = 0x1ECC7 if image.name in ('9190506.BIN','3-6-96.BIN') else 0x1ED29
        assert raw[recovery:recovery+3] == bytes.fromhex('B8 47 40')
        assert raw[recovery+15:recovery+18] == bytes.fromhex('B8 57 20')
        images[image.name] = {'sha256':hashlib.sha256(raw).hexdigest(), 'module':f'{module:X}',
            'table_start':f'{module+start:X}','table_end_exclusive':f'{module+end:X}',
            'register_map':f'{mapping:X}','registers':registers,
            'recovery_sha256':hashlib.sha256(raw[0x1E000:]).hexdigest()}
        if args.native:
            images[image.name]['native'],algorithms[image.name] = native(raw,image.name)
    assert len(images) == 4 and len({image['sha256'] for image in images.values()}) == 4
    assert len({image['recovery_sha256'] for image in images.values()}) == 2
    if args.native:
        native_bounds()
        assert all(value == algorithms['9190506.BIN'] for value in algorithms.values()),'Later cache instructions, helper bodies or GDT differ'
        for name in images:
            raw = (PORT/'reference'/name).read_bytes()
            assert (bytes.fromhex('B0 F6') in raw[0xFDA8:0xFDCC]) == (name!='9190914S.ROM'),name
    record = PORT.parent/'.agent/test-results/m919-hardware.json'
    record.parent.mkdir(parents=True,exist_ok=True)
    data = json.loads(record.read_text(encoding='utf-8')) if record.exists() else {}
    data['AMI_reference_checks'] = images
    record.write_text(json.dumps(data,indent=2)+'\n',encoding='utf-8')
    print('Four unique original AMI inputs, startup maps/tables, and two recovery layouts: PASS')
    if args.native:
        print('Native output/date/probe provenance; identical later cache algorithms/helper bodies/GDT; later CMOS F6 save removed: PASS')


if __name__ == '__main__':
    main()
