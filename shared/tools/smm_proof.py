"""Execute SMM firmware with independent save-map and SMI/RSM boundary models.

Intel 241731-002 Table 8-2 and AMD 19751C Table 10 supply the maps below.
The model preserves restart words; it does not emulate I/O replay, AutoHALT,
physical SMRAM protection, cache coherency, or electrical SMI delivery.
"""
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess

from capstone import Cs, CS_ARCH_X86, CS_MODE_16
from unicorn import Uc, UC_ARCH_X86, UC_MODE_16, UC_HOOK_CODE, UC_HOOK_INSN, UC_HOOK_MEM_WRITE
from unicorn import x86_const as x


ROOT = Path(__file__).resolve().parents[2]
REQUEST, REPLY = 0x534D4D51, 0x534D4D52
TARGET = 0xA0000
REGS = {name: getattr(x, 'UC_X86_REG_'+name) for name in (
    'EAX', 'EBX', 'ECX', 'EDX', 'ESI', 'EDI', 'EBP', 'ESP', 'EIP', 'EFLAGS',
    'CS', 'DS', 'ES', 'FS', 'GS', 'SS', 'CR0', 'CR3', 'DR6', 'DR7')}
# Separate transcriptions make either primary table independently reviewable.
MAPS = {
    'Intel486': {
        'ES':0xFFA8, 'CS':0xFFAC, 'SS':0xFFB0, 'DS':0xFFB4, 'FS':0xFFB8, 'GS':0xFFBC,
        'DR7':0xFFC8, 'DR6':0xFFCC, 'EAX':0xFFD0, 'ECX':0xFFD4, 'EDX':0xFFD8,
        'EBX':0xFFDC, 'ESP':0xFFE0, 'EBP':0xFFE4, 'ESI':0xFFE8, 'EDI':0xFFEC,
        'EIP':0xFFF0, 'EFLAGS':0xFFF4, 'CR3':0xFFF8, 'CR0':0xFFFC},
    'Am5x86': {
        'ES':0xFFA8, 'CS':0xFFAC, 'SS':0xFFB0, 'DS':0xFFB4, 'FS':0xFFB8, 'GS':0xFFBC,
        'DR7':0xFFC8, 'DR6':0xFFCC, 'EAX':0xFFD0, 'ECX':0xFFD4, 'EDX':0xFFD8,
        'EBX':0xFFDC, 'ESP':0xFFE0, 'EBP':0xFFE4, 'ESI':0xFFE8, 'EDI':0xFFEC,
        'EIP':0xFFF0, 'EFLAGS':0xFFF4, 'CR3':0xFFF8, 'CR0':0xFFFC},
}
SEGMENTS = {'CS', 'DS', 'ES', 'FS', 'GS', 'SS'}


def machine(raw):
    u = Uc(UC_ARCH_X86, UC_MODE_16)
    u.mem_map(0, 0x200000)
    u.mem_write(0xE0000, raw)
    return u


def install(u, raw, *, profile=1, gate=1, destination=0x3000, di=0x8000,
            si=None, length=None, df=False, expected=0, corrupt=False):
    entry, image, image_length = struct.unpack_from('<HHH', raw, 4)
    si = image if si is None else si
    length = image_length if length is None else length
    original = {name: 0x12340000+index*0x110000 for index, name in
                enumerate(('EAX', 'EBX', 'ECX', 'EDX', 'ESI', 'EDI', 'EBP'))}
    original.update(EAX=original['EAX']|profile, ECX=original['ECX']|length,
                    EDX=original['EDX']|gate, ESI=original['ESI']|si, EDI=original['EDI']|di,
                    ESP=0xCAFEFF00, CS=0xE000, DS=0xE000, ES=destination,
                    SS=0x7000, FS=0x2400, GS=0x2500,
                    EFLAGS=0x246|(0x400 if df else 0)|(1 if expected==0 else 0))
    for name, value in original.items():
        u.reg_write(REGS[name], value)
    u.mem_write(0x7FF00, struct.pack('<H', 0xFFF0))
    base = destination << 4
    before = bytes(u.mem_read(base, 0x10000))
    source = bytes(u.mem_read(0xE0000+si, length))
    writes, injected = [], [False]

    def write(uc, access, address, size, value, user):
        if 0x7FE00<=address and address+size<=0x7FF02:
            return
        assert base<=address and address+size<=base+0x10000, ('installer outside write',address,size)
        writes.append((address, size))

    def step(uc, address, size, user):
        # External storage failure between the real copy and real verification.
        if corrupt and not injected[0] and bytes(uc.mem_read(address, size)) == b'\xf3\xa6':
            uc.mem_write(base+di, bytes([source[0]^0x80]))
            injected[0] = True

    hooks = [u.hook_add(UC_HOOK_MEM_WRITE, write), u.hook_add(UC_HOOK_CODE, step)]
    try:
        u.emu_start(0xE0000+entry, 0xEFFF0, count=200000)
    finally:
        for hook in hooks:
            u.hook_del(hook)
    assert u.reg_read(x.UC_X86_REG_IP)==0xFFF0, 'installer did not return'
    for name, value in original.items():
        wanted = value
        if name=='EAX':
            wanted = (value & 0xFFFF0000)|expected
        elif name=='ESP':
            wanted += 2
        elif name=='EFLAGS':
            wanted = (value & ~1)|bool(expected)
        assert u.reg_read(REGS[name])==wanted, (name, hex(u.reg_read(REGS[name])), hex(wanted))
    after = bytes(u.mem_read(base, 0x10000))
    if expected in (1, 2):
        assert not writes and after==before, 'rejected installation wrote SMRAM'
    else:
        assert writes and all(base+di<=a and a+s<=base+di+length for a,s in writes)
        assert after[:di]==before[:di] and after[di+length:]==before[di+length:]
        if expected==0:
            assert after[di:di+length]==source
        else:
            assert expected==3 and injected[0] and after[di:di+length]!=source


class SmiModel:
    """Only architectural SMI save and RSM are modeled; handler code executes."""

    def __init__(self, raw, family):
        self.u, self.raw, self.layout = machine(raw), raw, MAPS[family]
        self.base, self.entries = 0x30000, []
        self.image, self.length = struct.unpack_from('<HH', raw, 6)
        for base in (self.base, TARGET):
            install(self.u, raw, profile=1 if family=='Intel486' else 2, destination=base>>4, df=True)
            assert bytes(self.u.mem_read(base+0x8000, self.length))==raw[self.image:self.image+self.length]
        self.protected = {self.base, TARGET}

    def enter(self, *, command=0, request=REQUEST, source=1, revision=0x20001,
              target=TARGET, status=0, handled=True, relocate=False, continuation=True, pending=False):
        u, base = self.u, self.base
        assert base in self.protected
        self.entries.append(base+0x8000)
        context = dict(EAX=0x800090C0, EBX=request, ECX=0x12340000|command, EDX=0xCFF,
                       ESI=0x10203040, EDI=target, EBP=0x31415926, ESP=0x6FF0,
                       CS=0x1200, DS=0x2200, ES=0x2300, FS=0x2400, GS=0x2500, SS=0x2600,
                       EIP=0x3400, EFLAGS=0x646 if status else 0x647, CR0=0x10, CR3=0x18000,
                       DR6=0xFFFF0FF0, DR7=0x400)
        if pending:
            # No caller instruction or manufactured register changes precede a pending SMI.
            context = {name:u.reg_read(REGS[name]) for name in self.layout}
        saved = bytearray((i*73+19)&0xFF for i in range(0x200))
        for name, offset in self.layout.items():
            struct.pack_into('<H' if name in SEGMENTS else '<I', saved, offset-0xFE00, context[name])
        struct.pack_into('<II', saved, 0xF8, base, revision)
        # Both restart low bits remain set; replay/AutoHALT behavior is outside this model.
        struct.pack_into('<HHH', saved, 0x100, 0xA501, 0x5A01, 0xBEEF)
        expected = bytearray(saved)
        if handled:
            for name,value in [('EAX', status), ('ECX', revision), ('EBX', REPLY),
                               ('EFLAGS', (context['EFLAGS']&~1)|bool(status))]:
                struct.pack_into('<I', expected, self.layout[name]-0xFE00, value)
            if relocate:
                assert status==0 and target in self.protected
                struct.pack_into('<I', expected, 0xF8, target)
        u.mem_write(base+0xFE00, bytes(saved))
        for name,value in context.items():
            u.reg_write(REGS[name], value)
        u.reg_write(x.UC_X86_REG_CS, base>>4)
        u.reg_write(x.UC_X86_REG_IP, 0x8000)
        u.reg_write(x.UC_X86_REG_EFLAGS, 2)
        ports, writes, resumed = [], [], [False]

        def inp(uc, port, size, user):
            assert (port,size)==(0xB2,1)
            ports.append(('read',source))
            return source

        def out(uc, port, size, value, user):
            assert (port,size,value)==(0xB2,1,source)
            ports.append(('ack',value))

        def write(uc, access, address, size, value, user):
            allowed = [self.layout[name] for name in ('EAX','ECX','EBX','EFLAGS')]
            if relocate:
                allowed.append(0xFEF8)
            assert handled and any(base+offset<=address and address+size<=base+offset+4 for offset in allowed), ('handler undocumented write',address,size)
            writes.append((address,size))

        decoder = Cs(CS_ARCH_X86, CS_MODE_16)

        def step(uc, address, size, user):
            assert base+0x8000<=address<base+0x8000+self.length, ('escaped handler',hex(address))
            # Unicorn does not execute RSM; its code-hook size can be invalid here.
            if bytes(uc.mem_read(address,2))==b'\x0F\xAA':
                resumed[0] = True
                uc.emu_stop()
                return
            instruction = next(decoder.disasm(bytes(uc.mem_read(address,size)),address))
            assert instruction.mnemonic not in ('push','pushf','pushfd','pusha','pushal','call','lcall',
                                                'pop','popf','popfd','ret','retf','hlt','invd','wbinvd')

        hooks = [u.hook_add(UC_HOOK_CODE,step), u.hook_add(UC_HOOK_MEM_WRITE,write),
                 u.hook_add(UC_HOOK_INSN,inp,None,1,0,x.UC_X86_INS_IN),
                 u.hook_add(UC_HOOK_INSN,out,None,1,0,x.UC_X86_INS_OUT)]
        try:
            u.emu_start(base+0x8000, base+0xFE00, count=1000)
        finally:
            for hook in hooks:
                u.hook_del(hook)
        actual = bytes(u.mem_read(base+0xFE00,0x200))
        assert resumed[0] and ports==[('read',source),('ack',source)], (resumed,ports)
        assert actual==expected, ('save map mismatch', [(hex(0xFE00+i),a,b) for i,(a,b) in enumerate(zip(actual,expected)) if a!=b])
        assert bool(writes)==handled
        restored = {name:struct.unpack_from('<H' if name in SEGMENTS else '<I',actual,offset-0xFE00)[0]
                    for name,offset in self.layout.items()}
        for name,value in restored.items():
            u.reg_write(REGS[name],value)
        self.base = struct.unpack_from('<I',actual,0xF8)[0]
        for name,value in restored.items():
            assert u.reg_read(REGS[name])==value, ('RSM restoration',name)
        if continuation:
            address = (restored['CS']<<4)+restored['EIP']
            # A real caller instruction proves execution continues with restored CS:EIP.
            u.mem_write(address,b'\x2E\xC6\x06\x00\x35\x5A')
            u.mem_write((restored['CS']<<4)+0x3500,b'\0')
            u.emu_start(address,address+6,count=10)
            assert bytes(u.mem_read((restored['CS']<<4)+0x3500,1))==b'\x5A'
            for name,value in restored.items():
                assert u.reg_read(REGS[name])==value+(6 if name=='EIP' else 0), ('continuation context',name)


def main():
    output = ROOT/'shared/build/tests/smm-proof'
    output.mkdir(parents=True,exist_ok=True)
    nasm = shutil.which('nasm') or str(Path(os.environ.get('LOCALAPPDATA',''))/'bin/NASM/nasm.exe')
    paths = [output/f'{os.getpid()}-{name}.bin' for name in ('normal','maximum','invalid')]
    rows = []
    try:
        for target,path in zip((TARGET,0xF0000,0xF8000),paths):
            result = subprocess.run([nasm,'-f','bin',f'-DSMM_TARGET={target}',
                                     'shared/tests/smm.asm','-o',str(path)],cwd=ROOT,capture_output=True,text=True)
            if target==0xF8000:
                assert result.returncode and 'SMM relocation target' in result.stderr, result.stderr
            else:
                assert result.returncode==0,result.stderr
            rows.append(f'compile-{target:05X}')
        raw = paths[0].read_bytes()
        assert raw[:4]==b'SMM1'
        cases = [
            ('unqualified',dict(gate=0,expected=1)),
            ('unrelated-gate-bit',dict(gate=2,expected=1)),
            ('qualified-with-other-bit',dict(gate=3)),
            ('profile-unknown',dict(profile=0,expected=1)),
            ('profile-unsupported',dict(profile=3,expected=1)),
            ('destination-before',dict(di=0x7FFF,expected=2)),
            ('destination-after',dict(di=0x8001,expected=2)),
            ('length-zero',dict(length=0,expected=2)),
            ('length-one',dict(length=1,expected=2)),
            ('length-two',dict(length=2)),
            ('maximum',dict(si=0x8200,length=0x7E00)),
            ('oversize',dict(length=0x7E01,expected=2)),
            ('source-exact-end',dict(si=0xFFFE,length=2)),
            ('source-crossing',dict(si=0xFFFF,length=2,expected=2)),
            ('large-source-crossing',dict(si=0x8201,length=0x7E00,expected=2)),
            ('profile-amd',dict(profile=2)),
            ('external-verification-failure',dict(corrupt=True,expected=3)),
        ]
        for name,case in cases:
            for df in (False,True):
                u = machine(raw)
                u.mem_write(0xE8200,bytes((i*29+7)&0xFF for i in range(0x7E00)))
                install(u,raw,df=df,**case)
                rows.append(f'installer-{name}-df{int(df)}')
        for family in MAPS:
            model = SmiModel(raw,family)
            scenarios = [
                ('ping',dict()),
                ('unrelated-source',dict(source=7,handled=False)),
                ('missing-request',dict(request=0,handled=False)),
                ('stale-reply',dict(request=REPLY,handled=False)),
                ('unknown-command',dict(command=2,status=1)),
                ('unsupported-relocation',dict(command=1,revision=1,status=2)),
                ('target-mismatch',dict(command=1,target=0xB0000,status=3)),
                ('relocation',dict(command=1,relocate=True,continuation=False)),
                ('pending-after-relocation',dict(pending=True,handled=False)),
                ('ping-after-relocation',dict()),
            ]
            for name,case in scenarios:
                model.enter(**case)
                rows.append(f'{family}-{name}')
            assert model.entries[-3:]==[0x38000,0xA8000,0xA8000],model.entries
        print(json.dumps({'result':'pass','cases':len(rows),'checks':rows,
                          'limit':'Synthetic SMI/RSM boundaries; no physical protection, coherency, I/O replay, AutoHALT or timing qualification.'}))
    finally:
        for path in paths:
            path.unlink(missing_ok=True)
        if not any(output.iterdir()):
            output.rmdir()


if __name__=='__main__':
    main()
