"""Component-only fixture preparation for the real private POST transport.

Full startup fixtures never call this preparation. They execute the actual
startup installer. No private code or installed pointer is synthesized here.
"""
from functools import cache
from pathlib import Path
import re
from unicorn import UC_HOOK_CODE, UC_HOOK_MEM_READ, UC_HOOK_MEM_WRITE
from unicorn import x86_const as x

ROOT=Path(__file__).resolve().parents[2]

def execute_real(cpu,entry,end,count):
    """Existing geometry executor's16-bit RETF correction, with one budget.

    Unicorn can retain the old IP after a nested private/resident return. Read
    the actual caller frame; never substitute a firmware function or its result.
    """
    executed=0;returned=False
    def step(u,address,size,_):
        nonlocal executed,returned
        executed+=1
        if size==1 and bytes(u.mem_read(address,1))==b'\xCB' and not u.reg_read(x.UC_X86_REG_CR0)&1:
            sp=u.reg_read(x.UC_X86_REG_SP);ss=u.reg_read(x.UC_X86_REG_SS)
            frame=bytes(u.mem_read((ss<<4)+sp,4))
            ip=int.from_bytes(frame[:2],'little');segment=int.from_bytes(frame[2:],'little')
            u.reg_write(x.UC_X86_REG_SP,(sp+4)&65535)
            u.reg_write(x.UC_X86_REG_CS,segment);u.reg_write(x.UC_X86_REG_IP,ip)
            returned=True;u.emu_stop()
    hook=cpu.hook_add(UC_HOOK_CODE,step)
    try:
        while executed<count:
            returned=False
            cpu.emu_start(entry,end,count=count-executed)
            if not returned:break
            entry=(cpu.reg_read(x.UC_X86_REG_CS)<<4)+cpu.reg_read(x.UC_X86_REG_IP)
        else:raise AssertionError('Instruction budget exhausted across real far returns')
    finally:cpu.hook_del(hook)

def migrated_base(port,old_base):
    """Independent expected encoding after a committed schema5-to-6 Save."""
    expected=bytearray(old_base)
    if old_base[2]<6:
        expected[2]=6
        expected[7]=(old_base[7]&7)|8|(32 if port=='m919' else 0)
        expected[5]=-(ord('B')+sum(value for i,value in enumerate(expected) if i!=5))&255
    return bytes(expected)

@cache
def exports():
    return frozenset(re.findall(r'^post_ui_export (\w+)',(ROOT/'shared/src/firmware/post-ui-api.inc').read_text(),re.M))


def needs_module(owner):
    # Existing resident facades whose POST-only callees are not UI exports.
    return owner in exports() or owner in {'setup_post_gate','init_peripherals','post_numlock_apply',
        'post_clock_alert','publish_memory_cmos','post_early_setup','post_summary_pause'}


def ensure_module(listing,owner,read,call):
    if not needs_module(owner):return
    try:listing.symbol('pnp_module_install')
    except StopIteration:return # The same component bodies are inline on MP.
    base=int.from_bytes(read(0x40E,2),'little')<<4
    if not any(read(base+0x33A,2)):
        call('pnp_module_install')
        assert any(read(base+0x33A,2)),'Component POST transport did not install'


def installed_address(listing,read,name,owner=None):
    base=int.from_bytes(read(0x40E,2),'little')<<4
    segment=int.from_bytes(read(base+0x33A,2),'little')
    assert segment,'Private entry requested without an installed POST module'
    private='post_ui_'+owner if owner in exports() else owner
    target='post_ui_'+name if owner is None and name in exports() else name
    return (segment<<4)+listing.symbol(target,private)


class ComponentROM:
    """Only external source mapping for existing board loaders, not POST state."""
    def __init__(self,cpu,image):
        self.cpu=cpu;self.acc_index=0;self.acc={2:0xB9};self.payload=None
        image=Path(image);raw=image.read_bytes()
        if len(raw)==0x20000 and raw[0x8000:0x8008]==b'BAIPNP2\0':
            self.payload=raw[0x8000:0x10000];self.shadow=bytearray(b'\xD6'*0x8000)
            cpu.hook_add(UC_HOOK_MEM_READ,self.read,None,0xE8000,0xEFFFF)
            cpu.hook_add(UC_HOOK_MEM_WRITE,self.write,None,0xE8000,0xEFFFF)
        elif image.name=='baios-presario800-system.rom':
            physical=image.with_name('baios-presario800-vga60.bin').read_bytes()
            assert len(physical)==0x20000
            cpu.mem_map(0xFFFC0000,0x40000);cpu.mem_write(0xFFFC0000,physical+physical)

    def input(self,port):
        if self.payload is not None and port==0xF3:return self.acc.get(self.acc_index,0)
        return None

    def output(self,port,value):
        if self.payload is None:return False
        if port==0xF2:self.acc_index=value;return True
        if port==0xF3:self.acc[self.acc_index]=value;return True
        return False

    def read(self,cpu,access,address,size,value,unused):
        offset=address-0xE8000;source=self.shadow if self.acc[2]&8 else self.payload
        cpu.mem_write(address,bytes(source[offset:offset+size]))

    def write(self,cpu,access,address,size,value,unused):
        if not self.acc[2]&0x20:
            offset=address-0xE8000;self.shadow[offset:offset+size]=value.to_bytes(size,'little')


def bind_rtc_candidate(rtc,image):
    """Bind inherited external device constructors to this candidate's bytes."""
    from shared.tools.ram_proof import Listing,fixture_directory
    image=Path(image);listing=Listing(image.with_suffix('.lst'))
    folder=image.parent if image.name=='baios-presario800-system.rom' else fixture_directory(image,'runtime-media')
    if image.name!='baios-presario800-system.rom':
        (folder/'baios-presario800-system.rom').write_bytes(image.read_bytes()[-65536:])
    rtc.BUILD=folder
    def symbol(name):
        if name=='int1a':name='RTC_INTERRUPT_LABEL'
        try:return listing.symbol(name)
        except StopIteration:
            if name=='.warm_start':return listing.symbol('startup')
            raise
    rtc.symbol=symbol
    return listing
