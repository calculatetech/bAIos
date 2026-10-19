"""Composed contrasts for timing selection, preservation and retained validation."""
import hashlib
import json
import sys
from unicorn import x86_const as x
from cache_proof import PORT, REPOSITORY, POSTHardware, composed, guest
from timing_proof import options, menu, active, ParityHardware, DOWN, RIGHT, ENTER, SAVE
from geometry_proof import Listing


class ClockUI(POSTHardware):
    def prepare(self, u):
        super().prepare(u)
        self.clock_help = None
        self.editing_clock = False
        self.clock_ports = set()
        listing=Listing(PORT/'build/hardware-tests/geometry/baios-m919.lst')
        self.profile_index_return=0xF0000+listing.symbol('.done','chipset_profile_index')
        self.profile_indices=set()
        self.help_wait=0xF0000+listing.symbol('.wait','setup_help')
        self.help_registered=False

    def observe(self, u, address, size):
        if self.continuing and not self.help_registered:
            self.key_points.add(self.help_wait);self.help_registered=True
        if self.continuing and address==self.profile_index_return:
            base=(u.reg_read(x.UC_X86_REG_FS)<<4)+u.reg_read(x.UC_X86_REG_SI)
            clock=self.read(base+7,1)[0];speed=(self.read(base+8,1)[0]>>4)&3
            index=u.reg_read(x.UC_X86_REG_BX)
            assert index==clock*2+(0 if speed==1 else 1), (clock,speed,index)
            self.profile_indices.add((clock,speed,index))
        if self.continuing and address in self.key_points:
            base = u.reg_read(x.UC_X86_REG_FS) << 4
            selected = tuple(self.read(base+self.state[n], 1)[0] for n in
                             ('U_PAGE', 'U_FOCUS', 'U_CHIP_SCREEN', 'U_FIELD'))
            self.editing_clock = selected == (5, 1, 1, 0)
            if self.editing_clock and address==self.help_wait and self.clock_help is None:
                cells = bytes(u.mem_read(0xB8000, 4000))
                lines = ('Select the bus speed set by the board jumpers.',
                         'This chooses timings. It does not change speed.')
                for row, line in zip((19, 20), lines):
                    actual = cells[row*160+50:row*160+50+2*len(line)]
                    assert actual[::2] == line.encode() and actual[1::2] == bytes([0x1F])*len(line), (row,actual.hex(),line)
                self.clock_help = lines
        if self.editing_clock:
            assert bytes(u.mem_read(address, size)) != b'\x0F\x30', 'Clock edit issued WRMSR'
        super().observe(u, address, size)

    def outgoing(self, u, port, size, value):
        if self.editing_clock:
            self.clock_ports.add(port)
            # Existing keyboard/PIC/RTC access and PCI address selection only.
            assert port in (0x20, 0x60, 0x64, 0x70, 0x71, 0xCF8), hex(port)
        super().outgoing(u, port, size, value)


def profiles():
    results = []
    for clock, speed, mode in ((0,0,0), (1,0,0), (1,2,0), (2,1,0), (3,2,1), (1,1,2), (2,0,3)):
        # Choose each field through its real popup, starting at the first item.
        keys = menu()+[0x3B,1,ENTER,0x48]+[DOWN]*clock+[ENTER,DOWN,ENTER]+[DOWN]*speed
        keys += [ENTER,DOWN,ENTER,0x48]+[DOWN]*((1,2,3,0)[mode])+[ENTER]+SAVE
        row, f = composed(chip=options(l2=0), keys=keys, hardware=ClockUI)
        assert row['terminal'] == 'reset' and not f[1].keys and f[1].keys_sent == keys
        assert f[1].clock_help and f[1].clock_ports
        help_lines, ports = f[1].clock_help, sorted(f[1].clock_ports)
        reload, g = composed(memory=f[1])
        expected = options(clock, speed, mode, l2=0)
        assert active(g)[:10] == expected[:10], (clock,speed,mode,active(g).hex(),expected.hex())
        if mode==2:
            assert not g[1].profile_indices, 'Manual must bypass preset row selection'
        else:
            assert (clock,speed,clock*2+(0 if speed==1 else 1)) in g[1].profile_indices
        assert reload['enabled'] and reload['terminal'] == 'POST FF'
        results.append(dict(row, clock_mhz=(25,33,40,50)[clock], speed=speed, mode=mode,
                            clock_help=help_lines, clock_ports=ports,
                            reload_profile_indices=sorted(g[1].profile_indices), reload=reload))
    return results


class Seeded(POSTHardware):
    def prepare(self, u):
        super().prepare(u)
        self.seeded = False

    def observe(self, u, address, size):
        if self.continuing and self.points.get(address) == 'chipset_apply' and not self.seeded:
            self.seeds = {0x51:0x0A, 0x5A:0x0B, 0x5D:0x6F, 0x61:0x07}
            for register, mask in self.seeds.items():
                self.registers[register] |= mask
            self.gates[0x61] |= 0x30
            self.geometry = (self.registers[0x52]&0x7F, self.registers[0x53]&0x3F)
            self.seeded = True
        super().observe(u, address, size)


def masks():
    results = []
    for chip in (options(l2=0), options(clock=3,mode=1,l2=0)):
        row, f = composed(chip=chip, hardware=Seeded)
        d=f[1]; r=d.registers
        expected=(chip[3]&0x70, chip[0]|1, chip[4], 0, 0)
        final=tuple(r[register]&mask for register,mask in
                    ((0x50,0x70),(0x51,0xF1),(0x5D,0x90),(0x61,0xC8),(0x5A,0x10)))
        assert d.qualification_policies == {expected} and final == expected
        assert all(r[register]&mask == mask for register,mask in d.seeds.items())
        assert (r[0x52]&0x7F,r[0x53]&0x3F) == d.geometry and d.gates[0x61]&0x30 == 0x30
        results.append(dict(row, seeds=d.seeds, qualification_policy=expected, final_policy=final,
                            unrelated_bits_preserved=True, port_B_preserved=True))
    return results


class BadChecksum(POSTHardware):
    def prepare(self, u):
        super().prepare(u)
        if not hasattr(self,'corrupted'):
            self.corrupted = False

    def observe(self, u, address, size):
        if self.continuing and self.points.get(address) == 'settings_load' and not self.corrupted:
            self.active_cmos[0x6A] ^= 1
            self.corrupted = True
        super().observe(u, address, size)


def checksums():
    results=[]
    for tag, chip in ((0x55,None),(0x56,options(l2=0))):
        row,f=composed(kib=128,chip=chip,hardware=BadChecksum)
        assert f[1].corrupted and row['terminal']=='reset' and not row['enabled']
        reload,g=composed(kib=128,memory=f[1])
        assert reload['terminal']=='POST FF' and reload['enabled']
        assert active(g)[:10]==options(l1=1,l2=0,wb=False)[:10]
        results.append(dict(row, input_tag=tag, checksum_corrupted=True, reload=reload))
    return results


class RAMDelete(POSTHardware):
    def prepare(self,u):
        super().prepare(u)
        self.ram_escape=False
        self.delete_sent=False

    def outgoing(self,u,port,size,value):
        if port==0x80 and value==0xCA:
            self.setup_requested=True  # Suppress the fixture's earlier automatic Delete.
        super().outgoing(u,port,size,value)

    def observe(self,u,address,size):
        if self.continuing and self.points.get(address)=='post_keyboard_wait' and not self.delete_sent:
            base=u.reg_read(x.UC_X86_REG_FS)<<4
            if self.read(base+self.state['P_RAM_FLAGS'],1)==b'\x01':
                self.queue.extend((0xE0,0x53));self.delete_sent=True
        super().observe(u,address,size)


def persistence():
    results=[]
    first,f=composed(chip=options(l2=0))
    d=f[1]
    # A disk translation save preserves memory/cache validation.
    before=d.saved_cmos
    keys=[DOWN,ENTER,DOWN,DOWN,ENTER,DOWN,DOWN,RIGHT]+SAVE
    edit,g=composed(memory=d,keys=keys)
    assert edit['terminal']=='reset' and not d.keys and d.keys_sent==keys
    assert d.saved_cmos[0x75:0x80]+d.saved_cmos[0x33:0x36]==before[0x75:0x80]+before[0x33:0x36]
    assert d.saved_cmos[0x40:0x5D]!=before[0x40:0x5D], 'Disk edit did not save'
    reload,g=composed(memory=d)
    assert reload['enabled'] and 'cache_qualify' not in reload['post_visits']
    results.append(dict(first,disk_save=edit,reload=reload))
    # The last option byte must invalidate, just as an early clock selector does.
    edit,g=composed(memory=d,keys=menu(2)+[DOWN,DOWN,RIGHT]+SAVE)
    assert d.saved_cmos[0x74]&4 and d.saved_cmos[0x75]==0
    reload,g=composed(memory=d)
    assert reload['enabled'] and 'cache_qualify' in reload['post_visits'] and d.saved_cmos[0x75]==0xA5
    results.append(dict(edit,late_option_changed=True,reload=reload))
    delete=RAMDelete(kib=64);delete.saved_cmos=d.saved_cmos
    edit,g=composed(memory=delete,keys=menu(2)+[DOWN,DOWN,RIGHT]+SAVE)
    assert delete.delete_sent and edit['terminal']=='reset' and delete.saved_cmos[0x75]==0
    assert not delete.saved_cmos[0x74]&4
    delete.ram_escape=True
    # Use the ordinary boot seam for the next cold reset, preserving only NVRAM.
    next_boot=POSTHardware(kib=64);next_boot.saved_cmos=delete.saved_cmos
    reload,g=composed(memory=next_boot)
    assert reload['enabled'] and 'cache_qualify' in reload['post_visits'] and next_boot.saved_cmos[0x75]==0xA5
    results.append(dict(edit,mid_RAM_Delete=True,changed_save_invalidated=True,reload=reload))
    return results


class HaltedParity(ParityHardware):
    def observe(self,u,address,size):
        if self.continuing and self.points.get(address)=='chipset_apply':
            self.gates[0x61]|=0x30
        if getattr(self,'checking_halt',False) and bytes(u.mem_read(address,size))==b'\xF4':
            assert not u.reg_read(x.UC_X86_REG_EFLAGS)&0x200
            self.halted=True;self.halt_address=address
        super().observe(u,address,size)


def parity_halt():
    chip=bytearray(options(l2=1));chip[6]=1
    row,f=composed(kib=64,ram=8,chip=bytes(chip),hardware=HaltedParity)
    u,d,_,_,_,_=f
    assert d.gates[0x61]&0x34==0x30
    d.gates[0x61]|=0x80;d.checking_halt=True;d.halted=False
    d.cpu_interrupt(u,2)
    u.emu_start((u.reg_read(x.UC_X86_REG_CS)<<4)+u.reg_read(x.UC_X86_REG_IP),0xFFFFF,count=200000)
    assert d.halted and d.ports[0x80]==0xE8 and b'RAM parity error' in bytes(u.report_output)
    assert (u.reg_read(x.UC_X86_REG_CS)<<4)+u.reg_read(x.UC_X86_REG_IP)==d.halt_address+1
    return [dict(row,installed_NMI_E8_message_and_halt=True)]


class TagAperture(POSTHardware):
    def cacheable(self,address):
        # Aperture is independent of tag width; truncation can expose an alias.
        return address<0x2000000 and not 0xA0000<=address<0x100000


def tag_range():
    results=[]
    body='''cli
lgdt [cs:gdtr]
mov eax,cr0
or al,1
mov cr0,eax
jmp 8:protected
protected:
mov ax,16
mov gs,ax
mov eax,cr0
and al,0xFE
mov cr0,eax
jmp 0:real
real:
mov dword [gs:dword 0x100000],0xC0DEFACE
mov eax,[gs:dword 0x900000]
mov ebx,eax
jmp finished
align 8
gdt: dq 0,0x00009A000000FFFF,0x00CF92000000FFFF
gdtr: dw 23
dd gdt
finished:
'''
    for ram,wb,enabled,alias in ((8,True,True,True),(8,False,True,False),(16,True,False,False)):
        row,f=composed(kib=64,ram=ram,chip=options(l1=0,l2=0,wb=wb),hardware=TagAperture)
        assert row['enabled']==enabled and ('cache_qualify' in row['post_visits'])==enabled
        guest(f,'tag-aperture',body)
        actual=f[0].reg_read(x.UC_X86_REG_EBX)
        assert (actual==0xC0DEFACE)==alias,(ram,wb,actual)
        results.append(dict(row, aperture_bytes=0x2000000, ram_mib=ram, wb=wb,
                            observed_high_address=f'{actual:08X}', truncated_tag_alias=alias))
    return results


def check(case):
    functions={'profiles':profiles,'masks':masks,'checksums':checksums,'persistence':persistence,
               'parity-halt':parity_halt,'tag-range':tag_range}
    result={'cases':functions[case]()}
    sources=('m919/tools/timing_boundaries.py','m919/tools/timing_proof.py','m919/tools/cache_proof.py',
             'm919/tools/geometry_proof.py','m919/src/hardware/chipset-core.inc','m919/src/hardware/timing.inc',
             'm919/src/hardware/cache-validation.inc','m919/src/hardware/cache.inc',
             'm919/src/hardware/chipset-ui.inc','m919/src/hardware/chipset-data.inc','shared/src/firmware/bios.asm')
    result['source_sha256']={p:hashlib.sha256((REPOSITORY/p).read_bytes()).hexdigest() for p in sources}
    target=PORT/'build/hardware-research'/f'timing-boundaries-{case}.json'
    target.write_text(json.dumps(result,indent=2)+'\n')
    print(f'timing-boundaries-{case}: {len(result["cases"])} cases PASS; {target}',flush=True)


if __name__=='__main__':
    for case in (('profiles','masks','checksums','persistence','parity-halt','tag-range')
                 if sys.argv[1]=='all' else (sys.argv[1],)):
        check(case)
