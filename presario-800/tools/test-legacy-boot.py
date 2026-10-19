"""Execute legacy ROM discovery and bootstrap continuation on production owners."""
import argparse
import importlib
from pathlib import Path
import shutil
import struct
import subprocess

from unicorn import UC_HOOK_CODE
from unicorn import x86_const as x

setup = importlib.import_module('test-setup')
rtc = setup.rtc
ROOT, BUILD = rtc.ROOT, rtc.BUILD


def assemble(name, source):
    work = BUILD / 'legacy-fixtures'
    work.mkdir(parents=True, exist_ok=True)
    asm, binary = work / (name+'.asm'), work / (name+'.bin')
    asm.write_bytes(source.encode())
    nasm = shutil.which('nasm') or str(Path.home() / 'AppData/Local/bin/NASM/nasm.exe')
    subprocess.run([nasm, '-f', 'bin', '-o', str(binary), str(asm)], check=True)
    return binary.read_bytes()


def rom(index, length=4, provider=False, dirty=False):
    body = f"""bits 16
org 0
db 55h,0AAh,{length}
jmp init
init:
    xor ax,ax
    mov ds,ax
    inc word [0x600+{index}*2]
    mov word [0x180+{index}*4], handler
    mov word [0x182+{index}*4],cs
"""
    if provider:
        body += "mov word [0x4C], handler\nmov word [0x4E],cs\nmov byte [0x475],1\n"
    if dirty:
        body += "pop si\npop di\nmov ax,0x1200\nmov ss,ax\nmov sp,0x1000\npush di\npush si\nmov ds,ax\nmov es,ax\nmov fs,ax\nmov gs,ax\nmov eax,0x12345678\nmov ebx,eax\nmov ecx,eax\nmov edx,eax\nmov esi,eax\nmov edi,eax\nmov ebp,eax\nstd\ncli\n"
    body += 'retf\nhandler:\npush bp\nmov bp,sp\n'
    if provider:
        body += "cmp ah,2\njne done\npush ds\npush si\npush di\npush cx\npush cs\npop ds\nmov si,sector\nmov di,bx\nmov cx,256\ncld\nrep movsw\npop cx\npop di\npop si\npop ds\n"
    body += "done:\nand word [ss:bp+6],0xFFFE\npop bp\niret\nsector:\ndb 'CARD'\ntimes 510-($-sector) db 0\ndw 0xAA55\n"
    body += f'times {length}*512-($-$$) db 0\n'
    data = bytearray(assemble(f'rom-{index}-{length}-{int(provider)}-{int(dirty)}',body))
    data[-1] = -sum(data[:-1]) & 255
    return data


def discovery():
    for cold in (False,True):
        m=setup.production_post_model();setup.schema2_fixture(m,types=0,flags=0x0B,order=(2,0,0))
        hooks=[]
        def empty(model,name):
            if name=='option_rom_discovery':
                assert model.cpu.mem_read(0xC8000,0x18000)==bytes(0x18000)
                hooks.append(bytes(model.cpu.mem_read(0x4C,0x20))+bytes(model.cpu.mem_read(0x180,16)))
            elif name=='post_debug_summary':
                assert hooks==[bytes(model.cpu.mem_read(0x4C,0x20))+bytes(model.cpu.mem_read(0x180,16))]
                assert model.cpu.mem_read(model.base+0x3D,1)==b'\x01'
                assert model.cpu.mem_read(0x475,1)==b'\x01'
                assert not model.cpu.mem_read(model.base+0x175,1)[0]&16
        m.startup_observer=empty;m.startup(reset=cold,production_controls=True,through_boot=True)
        assert hooks and m.cpu.mem_read(0x600,8)==bytes(8)
        assert m.cpu.mem_read(0x7C00,4)==b'BOOT'
    inputs = ((0xC8000,rom(0)), (0xC9000,rom(1)), (0xD0000,rom(2,128,provider=True,dirty=True)), (0xC0000,rom(3)))
    for cold,shadow in ((False,False),(True,False),(False,True),(True,True)):
        m=setup.production_post_model(kinds=('absent','absent'))
        setup.schema2_fixture(m,types=0,flags=0x0B,order=(2,0,0))
        policy=bytearray(importlib.import_module('test-chipset').NORMAL)
        if shadow:policy[21]|=0xF4  # C800 plus the full D000-DFFFF image.
        m.cmos[0x69],m.cmos[0x6A]=0xC2,-(0xC2+sum(policy))&255
        m.cmos[0x6B:0x80],m.cmos[0x33:0x36]=policy[:21],policy[21:]
        for address,data in inputs: m.cpu.mem_write(address,bytes(data))
        context=[]
        def entry_context(model,name):
            if name=='option_rom_discovery':
                assert model.cpu.mem_read(model.base+0x3D,1)==b'\0'
                context.append(tuple(model.cpu.reg_read(getattr(x,'UC_X86_REG_'+reg)) for reg in rtc.REGS)+
                               (model.cpu.reg_read(x.UC_X86_REG_CS),model.cpu.reg_read(x.UC_X86_REG_EFLAGS)))
                ss,sp=model.cpu.reg_read(x.UC_X86_REG_SS),model.cpu.reg_read(x.UC_X86_REG_SP)
                caller_stack=bytes(model.cpu.mem_read((ss<<4)+sp+2,16))
                context.append(caller_stack)
            elif name=='post_debug_summary':
                returned=tuple(model.cpu.reg_read(getattr(x,'UC_X86_REG_'+reg)) for reg in rtc.REGS)+(
                    model.cpu.reg_read(x.UC_X86_REG_CS),model.cpu.reg_read(x.UC_X86_REG_EFLAGS))
                assert returned==context[0], ('immediate scanner return',context[0],returned)
                ss,sp=model.cpu.reg_read(x.UC_X86_REG_SS),model.cpu.reg_read(x.UC_X86_REG_SP)
                assert bytes(model.cpu.mem_read((ss<<4)+sp+2,16))==context[1]
                assert model.cpu.mem_read(0x4E,2)==b'\0\xD0' and model.cpu.mem_read(0x475,1)==b'\x01'
                context.append(returned)
        m.startup_observer=entry_context
        m.startup(reset=cold,production_controls=True,through_boot=True)
        assert len(context)==3
        assert bytes(m.cpu.mem_read(0x600,8))==struct.pack('<4H',1,1,1,0)
        for i,segment in enumerate((0xC800,0xC900,0xD000)):
            assert int.from_bytes(m.cpu.mem_read(0x182+i*4,2),'little')==segment
        assert m.startup_hops.index('setup_post_gate') < m.startup_hops.index('chipset_late_cache') < m.startup_hops.index('option_rom_discovery') < m.startup_hops.index('post_debug_summary') < m.startup_hops.index('int19')
        assert m.cpu.mem_read(0x7C00,4)==b'CARD'
        assert m.cpu.reg_read(x.UC_X86_REG_DS)==m.cpu.reg_read(x.UC_X86_REG_ES)==m.cpu.reg_read(x.UC_X86_REG_SS)==0
        assert m.cpu.reg_read(x.UC_X86_REG_ESP)==0x7000
        assert m.cpu.reg_read(x.UC_X86_REG_EFLAGS)&0x600==0x200
        assert m.chipset[0x0F]&0x30==(0x20 if shadow else 0)
        assert m.chipset[0x10]==(0xAA if shadow else 0)
        assert m.cpu.mem_read(m.base+0x60+21,1)==bytes((policy[21],))
        m.call('option_rom_discovery',flags=0x602)
        assert m.cpu.reg_read(x.UC_X86_REG_EFLAGS)&0x600==0x600
        assert bytes(m.cpu.mem_read(0x600,8))==struct.pack('<4H',1,1,1,0)
    m=setup.production_post_model();setup.schema2_fixture(m,types=0,flags=0x0B,order=(2,0,0))
    data=rom(0,16);data[2048:4096]=rom(1);data[-1]=0;data[-1]=-sum(data)&255
    m.cpu.mem_write(0xC8000,bytes(data));m.startup(production_controls=True,through_boot=True)
    assert bytes(m.cpu.mem_read(0x600,4))==struct.pack('<2H',1,0)
    for kind in ('empty','signature','zero','checksum','extent'):
        m=setup.production_post_model();setup.schema2_fixture(m,types=0,flags=0x0B,order=(2,0,0))
        bad=rom(0)
        if kind=='signature': bad[0]=0
        elif kind=='zero': bad[2]=0
        elif kind=='checksum': bad[-1]^=1
        elif kind=='extent': bad[2]=193
        if kind!='empty': m.cpu.mem_write(0xC8000,bytes(bad))
        m.cpu.mem_write(0xD8000,bytes(rom(1)))
        m.startup(production_controls=True,through_boot=True)
        assert bytes(m.cpu.mem_read(0x600,4))==struct.pack('<2H',0,1)
        malformed=kind in ('zero','checksum','extent')
        assert ('Expansion ROM invalid; skipped.' in m.console)==malformed
        assert bool(m.cpu.mem_read(m.base+0x175,1)[0]&16)==malformed
        assert (m.text(13,49,3)=='ROM')==malformed
    m=setup.production_post_model(kinds=('absent','absent'))
    setup.schema2_fixture(m,types=0,flags=0x0B,order=(2,0,0))
    m.cpu.mem_write(0xC8000,bytes(rom(0,provider=True)))
    m.startup(reset=True,production_controls=True,through_boot=True)
    assert m.cpu.mem_read(m.base+0x20,1)==b'\0' and m.cpu.mem_read(0x7C00,4)==b'CARD'
    assert m.cpu.reg_read(x.UC_X86_REG_DL)==0x80
    for cold in (True,False):
        m=setup.production_post_model()
        setup.schema2_fixture(m,types=0,flags=0x13,order=(2,0,0))
        m.cpu.mem_write(0xC8000,b'\x55\xAA\0')
        noticed=[]
        def owner(model,name):
            if name=='post_notice_wait':
                assert model.cpu.mem_read(model.base+0x175,1)[0]&16
                assert model.cpu.mem_read(0x49E,1)==b'\x02'
                assert 'Expansion ROM invalid; skipped.' in model.console
                noticed.append(0)
        def event(model,address):
            if not noticed or model.cpu.mem_read(address,1)!=b'\xF4':return
            noticed[0]+=1
            assert model.cpu.mem_read(0x41A,2)==model.cpu.mem_read(0x41C,2)
            if noticed[0]==3:model.pending.append(0x1C)
        m.startup_observer=owner;m.event_observer=event
        m.startup(reset=cold,production_controls=True,through_boot=True)
        assert noticed and noticed[0]>=3 and m.text(13,49,3)=='ROM', (noticed,m.text(13,49,3))
        assert m.cpu.mem_read(0x7C00,4)==b'BOOT'
    print('Legacy ROM discovery: full set, bounds/checksum/covered extents, dirty return, hooks and ROM80h boot PASS',flush=True)


def failure_pair(model, row):
    for offset,text in enumerate(('No boot device available','Press any key to retry')):
        assert model.text(row+offset,0,len(text))==text


def retry():
    # Other invokes the installed ROM INT19; its dirty entry calls BIOS INT18
    # to continue with the selected Floppy/Hard Disk priorities.
    m=setup.production_post_model()
    setup.schema2_fixture(m,types=0x40,flags=0x0B,order=(1,2,0))
    m.cmos[0x3A],m.cmos[0x3C],m.cmos[0x3E],m.cmos[0x3F]=5,4,1,2
    m.cmos[0x3D]=-(sum(m.cmos[0x38:0x3D])+sum(m.cmos[0x3E:0x40])+m.cmos[0x10])&255
    image=bytearray(assemble('card-int18',"""bits 16
org 0
db 55h,0AAh,4
jmp init
init:
    xor ax,ax
    mov ds,ax
    mov word [0x64],entry
    mov word [0x66],cs
    inc word [0x620]
    retf
entry:
    xor ax,ax
    mov ds,ax
    inc word [0x622]
    mov ax,0x2222
    mov ds,ax
    mov es,ax
    mov fs,ax
    mov ss,ax
    mov esp,0x400
    std
    cli
    int 0x18
    hlt
times 2048-($-$$) db 0
"""))
    image[-1]=-sum(image[:-1])&255
    m.cpu.mem_write(0xC8000,bytes(image))
    m.startup(reset=True,production_controls=True,through_boot=True)
    assert m.boot_reads==['Floppy','Hard Disk']
    assert m.cpu.mem_read(0x620,2)==b'\x01\0'
    assert m.cpu.mem_read(0x7C00,4)==b'BOOT'
    assert m.cpu.reg_read(x.UC_X86_REG_ESP)==0x7000
    assert m.cpu.reg_read(x.UC_X86_REG_DS)==m.cpu.reg_read(x.UC_X86_REG_ES)==m.cpu.reg_read(x.UC_X86_REG_SS)==0
    assert m.cpu.reg_read(x.UC_X86_REG_EFLAGS)&0x600==0x200
    # The same installed card19->alien18 chain must reopen the full order.
    m=setup.production_post_model();setup.schema2_fixture(m,types=0x40,flags=0x0B,order=(1,2,0))
    m.cmos[0x3A],m.cmos[0x3C],m.cmos[0x3E],m.cmos[0x3F]=5,4,1,2
    m.cmos[0x3D]=-(sum(m.cmos[0x38:0x3D])+sum(m.cmos[0x3E:0x40])+m.cmos[0x10])&255
    m.cpu.mem_write(0xC8000,bytes(image));m.boot_sector[510:]=b'\0\0'
    m.startup(reset=True,production_controls=True,boot_failure=True)
    assert m.boot_reads==['Floppy','Hard Disk'] and m.cpu.mem_read(0x620,4)==struct.pack('<HH',1,1)
    summary=bytes(m.cpu.mem_read(0xB8000,13*160));wakes=[]
    first_row=m.cpu.mem_read(0x450,2)[1]
    m.pending.extend((0x1E,0x9E))
    m.irq1_pending = True  # Latched hardware IRQ1 owns the stale make.
    irq_delivered, previous_instruction = [], [None]
    m.cpu.mem_write(0x41E,b'\x61\x1E');m.cpu.mem_write(0x41A,b'\x1E\0');m.cpu.mem_write(0x41C,b'\x20\0')
    def card_retry(model,address):
        opcode = bytes(model.cpu.mem_read(address,1))
        ready = model.cpu.reg_read(x.UC_X86_REG_EFLAGS)&0x200 and previous_instruction[0] != b'\xfb'
        previous_instruction[0] = opcode
        if model.irq1_pending and ready:
            assert 'Press any key to retry' not in model.console, 'stale IRQ1 reached the fresh-key gate'
            model.irq1_pending = False
            irq_delivered.append(True)
            rtc.Clock.interrupt(model,model.cpu,9,None)  # Real vector/decoder, external IRQ delivery only.
            return
        if model.cpu.mem_read(address,1)!=b'\xF4':return
        assert model.boot_reads==['Floppy','Hard Disk']
        assert model.cpu.mem_read(0x620,4)==struct.pack('<HH',1,1)
        assert model.cpu.mem_read(0x41A,2)==model.cpu.mem_read(0x41C,2)
        failure_pair(model,first_row)
        assert model.cpu.mem_read(0x450,2)==bytes((0,first_row+2))
        assert bytes(model.cpu.mem_read(0xB8000,13*160))==summary
        assert model.cpu.reg_read(x.UC_X86_REG_SS)==0 and 0x6F00<=model.cpu.reg_read(x.UC_X86_REG_ESP)<=0x7000
        wakes.append(True)
        if len(wakes)==6:model.boot_sector[510:]=b'\x55\xAA';model.pending.append(0x1E)
    m.event_observer=card_retry
    stop=m.cpu.hook_add(UC_HOOK_CODE,lambda cpu,a,n,u:cpu.emu_stop(),None,0x7C00,0x7C00)
    try:
        m.cpu.reg_write(x.UC_X86_REG_CS,0xF000)
        m.cpu.emu_start(0xF0000+rtc.symbol('boot_retry'),0xFFFFFF,count=30000000)
    finally:m.cpu.hook_del(stop)
    assert irq_delivered == [True] and len(wakes)==6 and m.boot_reads==['Floppy','Hard Disk']*2
    assert m.cpu.mem_read(0x620,4)==struct.pack('<HH',1,2) and m.cpu.mem_read(0x7C00,4)==b'BOOT'
    assert m.cpu.reg_read(x.UC_X86_REG_ESP)==0x7000 and m.cpu.mem_read(0x41A,2)==m.cpu.mem_read(0x41C,2)
    assert m.cpu.mem_read(m.base+0xF4,1)==b'\0' and m.startup_hops.count('option_rom_discovery')==1
    for order in ((2,1,0),(1,2,0),(0,0,0)):
        m=setup.production_post_model()
        setup.schema2_fixture(m,types=0x40,flags=0x0B,order=order)
        m.boot_sector[510:]=b'\0\0'
        m.startup(reset=True,production_controls=True,boot_failure=True)
        assert m.startup_hops[-1]=='boot_retry'
        attempts=list(m.boot_reads)
        if order==(0,0,0): assert not attempts
        else: assert attempts==(['Hard Disk','Floppy'] if order[0]==2 else ['Floppy','Hard Disk'])
        chain=assemble('retry-chain',f"bits 16\norg 0\nxor ax,ax\nmov ds,ax\ninc word [0x620]\njmp 0xF000:{rtc.symbol('int19')}\n")
        m.cpu.mem_write(0xC9000,chain);m.cpu.mem_write(0x64,struct.pack('<HH',0,0xC900))
        m.pending.extend((0x1E,0x9E))
        m.cpu.mem_write(0x41E,b'\x61\x1E');m.cpu.mem_write(0x41A,b'\x1E\0');m.cpu.mem_write(0x41C,b'\x20\0')
        seen=[]
        def events(model,address):
            if model.cpu.mem_read(address,1)!=b'\xF4': return
            assert 'Press any key to retry' in model.console
            assert model.cpu.mem_read(0x41A,2)==model.cpu.mem_read(0x41C,2)
            assert model.cpu.mem_read(0x620,2)==b'\0\0'
            seen.append(model.cpu.reg_read(x.UC_X86_REG_ESP))
            assert 0x6F00 <= seen[-1] <= 0x7000
            if len(seen)==2: model.pending.extend((0xE1,0x1D,0x45,0xE1,0x9D,0xC5))
            if len(seen)==4: model.pending.append(0x1E)
            if len(seen)==10:
                assert len(model.boot_reads)==len(attempts)
                if order==(0,0,0): model.cpu.emu_stop();return
                model.boot_sector[510:]=b'\x55\xAA'
                model.pending.extend((0xE0,0x53) if order[0]==2 else (0x53,))
        m.event_observer=events
        stop=m.cpu.hook_add(UC_HOOK_CODE,lambda cpu,a,n,u:cpu.emu_stop(),None,0x7C00,0x7C00)
        try:
            m.cpu.reg_write(x.UC_X86_REG_CS,0xF000)
            m.cpu.emu_start(0xF0000+rtc.symbol('boot_retry'),0xFFFFFF,count=30000000)
        finally: m.cpu.hook_del(stop)
        assert len(seen)==10 and m.startup_hops.count('option_rom_discovery')==1
        if order!=(0,0,0):
            assert m.cpu.mem_read(0x7C00,4)==b'BOOT' and m.cpu.mem_read(0x620,2)==b'\x01\0'
            assert m.cpu.mem_read(0x41A,2)==m.cpu.mem_read(0x41C,2)
            assert m.cpu.reg_read(x.UC_X86_REG_ESP)==0x7000
            assert m.cpu.mem_read(m.base+0xF4,1)==b'\0', 'late navigation/decimal entered Setup'
    # Repeated fresh failures advance the cursor and naturally scroll the summary.
    m=setup.production_post_model();setup.schema2_fixture(m,types=0,flags=0x0B,order=(2,0,0))
    m.boot_sector[510:]=b'\0\0';m.startup(production_controls=True,boot_failure=True)
    failed=[]
    def repeat(model,address):
        if model.cpu.mem_read(address,1)!=b'\xF4':return
        assert model.cpu.reg_read(x.UC_X86_REG_SS)==0
        assert 0x6F00<=model.cpu.reg_read(x.UC_X86_REG_ESP)<=0x7000
        assert model.cpu.mem_read(0x41A,2)==model.cpu.mem_read(0x41C,2)
        count=len(model.boot_reads)
        failure_pair(model,min(13+2*(count-1),22))
        assert model.console.count('No boot device available\r\nPress any key to retry\r\n')==count
        if count==1: assert model.text(0,37,5)=='bAIos'
        if count>=6: assert 'bAIos' not in bytes(model.cpu.mem_read(0xB8000,4000))[::2].decode('cp437')
        failed.append(len(model.boot_reads))
        if len(failed)==18:model.cpu.emu_stop()
        elif len(failed)%2==0:model.pending.append(0x1E)
    m.event_observer=repeat
    m.cpu.reg_write(x.UC_X86_REG_CS,0xF000)
    m.cpu.emu_start(0xF0000+rtc.symbol('boot_retry'),0xFFFFFF,count=30000000)
    assert failed==[n for n in range(1,10) for _ in range(2)] and m.startup_hops.count('option_rom_discovery')==1
    # Ctrl+Alt+Del at the retry gate performs full warm POST and ROM init again.
    m=setup.production_post_model();setup.schema2_fixture(m,types=0,flags=0x0B,order=(2,0,0))
    m.cpu.mem_write(0xC8000,bytes(rom(0)))
    rom_calls=[]
    hook=m.cpu.hook_add(UC_HOOK_CODE,lambda cpu,a,n,u:rom_calls.append(a),None,0xC8003,0xC8003)
    try:
        m.boot_sector[510:]=b'\0\0';m.startup(reset=True,production_controls=True,boot_failure=True)
        assert len(rom_calls)==1
        sent=[]
        def cad(model,address):
            if not sent and model.cpu.mem_read(address,1)==b'\xF4':
                model.boot_sector[510:]=b'\x55\xAA'
                model.pending.extend((0x1D,0x38,0xE0,0x53));sent.append(True)
        m.event_observer=cad
        m.startup(entry='boot_retry',production_controls=True,through_boot=True)
        assert sent==[True] and len(rom_calls)==2
        assert 'init_memory' in m.startup_hops and m.cpu.mem_read(m.base+0x3D,1)==b'\x01'
        assert m.boot_reads==['Hard Disk','Hard Disk'] and m.cpu.mem_read(0x7C00,4)==b'BOOT'
    finally:m.cpu.hook_del(hook)
    m=setup.production_post_model();setup.schema2_fixture(m,types=0x40,flags=0x0B,order=(2,1,0))
    m.startup(production_controls=True,through_boot=True)
    assert m.cpu.mem_read(m.base+0x48,1)==b'\x01'
    m.cpu.mem_write(0x7C00,assemble('int18-sector',"bits 16\norg 0x7C00\nmov ax,0x2222\nmov ds,ax\nmov es,ax\nmov fs,ax\nmov ss,ax\nmov esp,0x400\nstd\ncli\nint 0x18\nhlt\n"))
    stop=m.cpu.hook_add(UC_HOOK_CODE,lambda cpu,a,n,u:cpu.emu_stop(),None,0xF0000+rtc.symbol('boot_retry'),0xF0000+rtc.symbol('boot_retry'))
    try:m.cpu.emu_start(0x7C00,0xFFFFFF,count=10000000)
    finally:m.cpu.hook_del(stop)
    assert m.boot_reads==['Hard Disk','Floppy'] and m.cpu.mem_read(m.base+0x48,1)==b'\x04'
    assert m.cpu.reg_read(x.UC_X86_REG_DS)==m.cpu.reg_read(x.UC_X86_REG_ES)==m.cpu.reg_read(x.UC_X86_REG_SS)==0
    assert m.cpu.reg_read(x.UC_X86_REG_ESP)==0x7000 and not m.cpu.reg_read(x.UC_X86_REG_EFLAGS)&0x400
    print('Boot retry: complete/reversed/Disabled order, stale/timer/Pause isolation, corrected media installed chain and alien INT18 stack PASS',flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case',choices=('discovery','retry'),action='append')
    args=parser.parse_args()
    for name in args.case or ('discovery','retry'): globals()[name]()
