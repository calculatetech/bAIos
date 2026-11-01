"""Compose the actual APM entries, board adapter, SMM and one OS IRQ return."""
import hashlib
import json
import struct
import os
import shutil
import subprocess
from pathlib import Path

from capstone import Cs, CS_ARCH_X86, CS_MODE_16, CS_MODE_32

import smm_activation_proof as smm
import importlib.util

spec = importlib.util.spec_from_file_location('clock_check', smm.PORT/'tools/test-clock-check.py')
clock = importlib.util.module_from_spec(spec)
spec.loader.exec_module(clock)
x, HB, SB = smm.x, smm.HB, smm.SB
OUT = smm.PORT/'build/tests/idle-check'


def descriptor(base, length, access, flags=0):
    limit = length-1
    return struct.pack('<HHBBBB', limit & 65535, base & 65535, base >> 16 & 255,
                       access, (limit >> 16 & 15) | flags, base >> 24)


class IdleBoard(clock.ClockBoard):
    def __init__(self, *, irq=0, when='request', **kwargs):
        self.trail=[]
        self.masks = {0x21: 0xF8, 0xA1: 0xFE}
        self.irq, self.when = irq, when
        self.wake_pending = False
        self.wakes = self.halts = 0
        self.context_before_smi = None
        self.entry92 = None
        self.watchdog = False
        self.mode = 1
        self.native_idle = True
        self.virtual = False
        self.decoders = {16:Cs(CS_ARCH_X86,CS_MODE_16),32:Cs(CS_ARCH_X86,CS_MODE_32)}
        self.selector = 0
        super().__init__(**kwargs)

    def inp(self, u, port, size, user):
        if port in (0x20,0xA0):
            value=self.rtc_in(u,port,size,user) if self.rtc_in else 0
            if self.wake_pending:
                value |= (1<<self.irq if self.irq<8 else 4) if port==0x20 else (1<<(self.irq-8) if self.irq>=8 else 0)
            if port==0x20 and self.when=='spurious':
                value |= 1
            if port==0x20 and self.when=='spurious-cascade':
                value |= 4
            return value
        if self.rtc_in:
            value=super().inp(u,port,size,user)
            if port in self.masks:
                self.masks[port]=value
            return value
        if port in self.masks:
            return self.masks[port]
        try:
            return super().inp(u, port, size, user)
        except AssertionError:
            raise AssertionError((hex(port),hex(u.reg_read(x.UC_X86_REG_CS)),hex(u.reg_read(x.UC_X86_REG_EIP)),self.trail[-12:]))

    def out(self, u, port, size, value, user):
        if self.rtc_out and port in (0x21,0xA1,0xA0,0x20,0x70,0x71):
            return super().out(u,port,size,value,user)
        if port in (0x20,0xA0):
            assert value==0x0A
            return
        # CLOCKCHK's RTC-specific request oracle does not define ordinary IRQ wake.
        request = (self.smm and port == 0xCFC and self.cf8 == SB | 0xA4
                   and value & 0x9C == 0x14 and not self.conf[SB][0xA4] & 0x10)
        if self.smm and port == 0x61:
            self.trial_writes.append((port, value))
        elif self.smm and 0xCFC <= port <= 0xCFF and self.cf8 & ~255 == SB:
            self.trial_writes.append(((self.cf8 & 0xFC)+port-0xCFC, value))
        if port == 0x61:
            self.port61 = value
        smm.Board.out(self, u, port, size, value, user)
        if request:
            assert self.conf[SB][0xA0] & 3==1
            assert self.conf[SB][0x80] & 0xC0==0x40
            assert self.conf[SB][0x92]==self.entry92
            assert self.conf[SB][0x90]==self.masks[0x21]^255
            assert self.conf[SB][0x91]==self.masks[0xA1]^255
            assert self.conf[SB][0x90] & (1 << self.irq) if self.irq < 8 else self.conf[SB][0x91] & (1 << (self.irq-8))
            self.clock_edges += 1
            if self.watchdog:
                self.clock_latch()
                self.wake_pending=True
            elif self.when == 'request' or (self.when.startswith('spurious') and self.clock_edges>=2):
                self.wake_pending = True

    def step(self, u, address, size, user):
        if self.smm:
            self.decoder = self.decoders[16]
        else:
            self.decoder = self.decoders[32 if self.mode == 3 and u.reg_read(x.UC_X86_REG_CS) != 0x28 else 16]
        if address == self.address('m919_idle_command'):
            self.entry92=self.conf[SB][0x92]
            self.command_cache = self.conf[HB][0x50]
            self.command_controls = (self.conf[SB][0xA0]&0xFC if self.deliver else self.conf[SB][0xA0]), self.conf[SB][0xA8]
            self.request_raised = False
        opcode = bytes(u.mem_read(address, min(size,15)))
        self.trail.append((hex(address),opcode.hex()))
        if self.virtual and not self.smm:
            ins = next(self.decoder.disasm(opcode,address))
            assert ins.mnemonic not in ('wbinvd','invd','rsm') and 'cr0' not in ins.op_str, ('privileged V86 caller',ins.mnemonic,ins.op_str)
        if not self.smm and opcode == b'\x0f\x09':
            self.guard, self.invalidated = True, False
        if not self.smm and opcode == b'\xf4':
            self.halts += 1
            if self.when == 'hlt':
                self.wake_pending = True
            assert self.wake_pending, 'No pending IRQ at atomic STI/HLT'
            assert u.reg_read(x.UC_X86_REG_EFLAGS) & 0x200
            assert not self.guard
            if self.clock_edges:
                assert self.conf[SB][0xA4] & 0x9C==0x90, 'IRQ before native full-on/latch state'
                assert self.conf[SB][0x80]&0xC0==0, 'Idle mode replayed after wake'
                assert self.conf[SB][0xA0]&3==0, 'Power request replayed after wake'
            if self.command_cache is not None:
                assert self.conf[HB][0x50] == self.command_cache
                assert (self.conf[SB][0xA0], self.conf[SB][0xA8]) == self.command_controls
            self.action = 'irq'
            u.emu_stop()
            return
        try:
            smm.Board.step(self, u, address, size, user)
        except StopIteration:
            raise AssertionError((self.mode,self.smm,hex(u.reg_read(x.UC_X86_REG_CS)),self.trail[-12:]))

    def enter(self):
        # CPU seam: retain real protected descriptor caches, then enter SMM's
        # architectural real-address environment. Production handler is unchanged.
        self.context_before_smi = self.u.context_save()
        if self.mode == 1 and not self.virtual:
            return super().enter()
        self.u.reg_write(x.UC_X86_REG_CR0, self.u.reg_read(x.UC_X86_REG_CR0) & ~0x80000001)
        super().enter()

    def resume(self):
        if self.mode == 1 and not self.virtual:
            return super().resume()
        self.context_before_smi_real = self.context_before_smi
        # Validate the same save-map and acknowledgement oracle in real mode.
        super().resume()
        reply = {name:self.u.reg_read(smm.REGS[name]) for name in ('EAX','EBX','ECX','EFLAGS')}
        self.u.context_restore(self.context_before_smi_real)
        for name,value in reply.items():
            self.u.reg_write(smm.REGS[name], value)

    def protected(self, mode, connection):
        self.mode = mode
        flags = 0x40 if mode == 3 else 0
        code32=connection['EAX'] & 65535
        code16=(connection['ECX'] if mode==3 else connection['EAX']) & 65535
        data_segment=(connection['EDX'] if mode==3 else connection['ECX']) & 65535
        length16=(connection['ESI']>>16 if mode==3 else connection['ESI']) & 65535
        length32=connection['ESI'] & 65535
        gdt = bytearray(64)
        gdt[8:16] = descriptor(0xE0000, 65536, 0x9A, flags)
        gdt[16:24] = descriptor(0, 0x100000, 0x92, flags)
        gdt[32:40] = descriptor((code32 if mode==3 else code16)<<4,(length32 if mode==3 else length16) or 65536,0x9A,flags)
        if mode == 3:
            gdt[40:48] = descriptor(code16<<4,length16 or 65536,0x9A)
        data = 48 if mode == 3 else 40
        gdt[data:data+8] = descriptor(data_segment<<4,connection['EDI'] & 65535,0x92)
        self.u.mem_write(0x7000, bytes(gdt))
        self.u.reg_write(x.UC_X86_REG_GDTR, (0, 0x7000, 63, 0))
        self.u.reg_write(x.UC_X86_REG_CR0, 0x11)
        self.u.reg_write(x.UC_X86_REG_CS, 8)
        loader = b'\xfa'+(b'\x66' if mode == 3 else b'')+b'\xb8\x10\x00\x8e\xd8\x8e\xc0\x8e\xe0\x8e\xe8\x8e\xd0'
        self.u.mem_write(0xEF000, loader)
        self.stop = 0xEF000+len(loader)
        self.u.reg_write(x.UC_X86_REG_EIP, 0xF000)
        self.u.emu_start(0xF080, 0, count=100)
        assert self.u.reg_read(x.UC_X86_REG_EIP) == 0xF000+len(loader)
        self.selector = 0x20

    def run_apm(self, mode, function=5, disabled=False, virtual=False, paged=False):
        connection=None
        if function>3:
            self.run_apm(1,function=mode,virtual=virtual,paged=paged)
            connection={name:self.u.reg_read(smm.REGS[name]) for name in ('EAX','EBX','ECX','EDX','ESI','EDI')}
            assert self.u.mem_read(self.ebda+0x27A,1)[0]==mode
        self.mode = 1
        self.virtual = virtual
        self.context(cached=True)
        if mode != 1:
            self.protected(mode,connection)
        else:
            self.u.reg_write(x.UC_X86_REG_CS, 0xF000)
        self.instructions.clear()
        self.u.reg_write(x.UC_X86_REG_ESP, 0x18800 if mode == 3 else 0x8800)
        if virtual:
            assert mode==1
            self.u.reg_write(x.UC_X86_REG_CR0,0x11)
            if paged:
                self.u.mem_write(0x180000,struct.pack('<I',0x181007)+bytes(4092))
                self.u.mem_write(0x181000,b''.join(struct.pack('<I',(page<<12)|7) for page in range(512))+bytes(2048))
                self.u.reg_write(x.UC_X86_REG_CR3,0x180000)
                self.u.reg_write(x.UC_X86_REG_CR0,0x80000011)
        self.u.reg_write(x.UC_X86_REG_EFLAGS, 0x23203 if virtual else 0x603)
        self.u.reg_write(x.UC_X86_REG_AX, 0x5300 | function)
        self.u.reg_write(x.UC_X86_REG_BX, 0)
        if function<=3:self.u.mem_write(self.ebda+0x27A,b'\0')
        self.u.mem_write(self.ebda+0x27B,bytes((2,int(disabled))))
        self.wake_pending = self.when == 'before'
        original = {name:self.u.reg_read(reg) for name,reg in smm.REGS.items()}
        if mode == 1:
            sp = self.u.reg_read(x.UC_X86_REG_SP)
            self.u.mem_write(sp, struct.pack('<4H', original['EBP'] & 65535, 0xFFF0, 0xF000, original['EFLAGS'] & 65535))
            self.u.reg_write(x.UC_X86_REG_BP, sp)
            entry, stop = self.address('board_apm_int15'), 0xFFFF0
        else:
            offset = connection['EBX'] & (0xFFFFFFFF if mode==3 else 65535)
            pointer = offset.to_bytes(4 if mode == 3 else 2, 'little') + struct.pack('<H', self.selector)
            self.u.mem_write(0xEF000, b'\x9A'+pointer+b'\x90')
            entry, stop = 0xF000, 0xEF001+len(pointer)
            self.u.reg_write(x.UC_X86_REG_EIP, entry)
        self.stop, self.action = stop, None
        for _ in range(16):
            if mode == 1 or self.smm:
                entry = self.u.reg_read(x.UC_X86_REG_CS)*16 + self.u.reg_read(x.UC_X86_REG_IP) if self.action else entry
            else:
                entry = self.u.reg_read(x.UC_X86_REG_EIP)+self.u.reg_read(x.UC_X86_REG_CS)*16
            self.action = None
            self.u.emu_start(entry, 0, count=50000)
            if self.action == 'enter':
                self.enter()
            elif self.action == 'resume':
                self.resume()
            elif self.action == 'irq':
                # OS owns its interrupt handler in protected mode. Execute IRET
                # with a real hardware frame, after checking restoration order.
                self.wakes += 1
                assert self.wakes == 1
                self.wake_pending = False
                width = 4 if mode == 3 else 2
                sp = self.u.reg_read(x.UC_X86_REG_ESP if width == 4 else x.UC_X86_REG_SP)
                frame = (self.u.reg_read(x.UC_X86_REG_EFLAGS), self.u.reg_read(x.UC_X86_REG_CS), self.u.reg_read(x.UC_X86_REG_EIP)+1)
                for value in frame:
                    sp -= width
                    self.u.mem_write(sp, (value & ((1 << width*8)-1)).to_bytes(width,'little'))
                self.u.reg_write(x.UC_X86_REG_ESP if width == 4 else x.UC_X86_REG_SP, sp)
                self.u.reg_write(x.UC_X86_REG_EFLAGS, frame[0] & ~0x300)
                handler = 0xEF100 if mode != 1 else 0xFF100
                self.u.mem_write(handler,b'\xCF')
                if mode == 1:
                    self.u.reg_write(x.UC_X86_REG_CS,0xF000)
                self.u.reg_write(x.UC_X86_REG_IP if mode != 3 else x.UC_X86_REG_EIP, 0xF100)
            elif self.action == 'stop':
                break
            else:
                raise AssertionError(('budget',mode,self.action,hex(self.u.reg_read(x.UC_X86_REG_EIP))))
        else:
            raise AssertionError('too many event boundaries')
        after = {name:self.u.reg_read(reg) for name,reg in smm.REGS.items()}
        assert after['ESP']==original['ESP']+(8 if mode==1 else 0), ('terminal stack',mode,original['ESP'],after['ESP'])
        if function>3:
            assert self.u.mem_read(self.ebda+0x27A,1)[0]==mode, 'Idle changed APM connection owner'
        for name in ('EAX','EBX','ECX','EDX','ESI','EDI','EBP','DS','ES','FS','GS','SS','CR0','CR3'):
            if function <= 3 and name in ('EAX','EBX','ECX','EDX','ESI','EDI'):
                continue
            assert after[name] == original[name], (mode,function,name,hex(original[name]),hex(after[name]))
        assert after['EFLAGS'] == original['EFLAGS'] & ~1
        if function == 0:
            assert after['EAX'] & 65535 == 0x102 and after['EBX'] & 65535 == 0x504D
            qualified=(self.u.mem_read(self.ebda+smm.STATUS,1)[0]==1 and
                       self.conf[SB][0x76] & 0x30==0)
            assert bool(after['ECX'] & 4)==qualified
        elif function in (2,3):
            assert after['EAX'] & 65535==0xE000 and after['EDI'] & 65535==0x1046
            if function==2:
                assert after['EBX'] & 65535==self.listing.symbol('apm_pm16')
                assert after['ECX'] & 65535==self.ebda>>4
                assert after['ESI'] & 65535==self.listing.symbol('apm16_end')
            else:
                assert after['EBX']==self.listing.symbol('apm_pm32')
                assert after['ECX'] & 65535==0xE000 and after['EDX'] & 65535==self.ebda>>4
                assert after['ESI']==self.listing.symbol('apm16_end')<<16 | self.listing.symbol('apm32_end')
        return self.wakes


def main():
    clock.build(smm.PORT, 'build/tests/idle-check')
    smm.ROM = OUT/'baios-m919.bin'
    rows=[]
    for mode in (1,2,3):
        wake_cases=[(irq,when,1) for irq,when in ((0,'request'),(1,'request'),(0,'before'),(1,'spurious'),(1,'spurious-cascade'),(8,'request'))]
        wake_cases += [(0,'request',divider) for divider in (0,2,3)]
        for irq,when,divider in wake_cases:
            b=IdleBoard(irq=irq,when=when)
            assert b.startup()==1
            if when=='spurious':
                b.masks[0x21] |= 1
            b.conf[HB][0x50]=0x85
            for offset,value in ((0xA0,0x81),(0xA8,0x42),(0xA4,0x60|divider),(0x56,0xB2),(0x80,0xD5),(0x90,0xA0),(0x91,0x6C),(0x92,0xB7)):
                b.conf[SB][offset]=value
            before=bytes(b.conf[SB]);cf8=b.cf8
            b.dirty={0x140000:b'copy-back must reach DRAM before SMM'}
            assert b.run_apm(mode)==1
            assert bytes(b.u.mem_read(0x140000,len(b'copy-back must reach DRAM before SMM')))==b'copy-back must reach DRAM before SMM'
            for offset in (0xA0,0xA8,0xA4,0x56,0x80,0x90,0x91,0x92):
                expected=((before[offset]&0x63)|0x90) if offset==0xA4 else before[offset]
                if offset==0x80:
                    expected &= 0x3F
                elif offset==0xA0:
                    expected &= 0xFC
                assert b.conf[SB][offset]==expected, (mode,offset)
            # AMI 437B..43B3 and helpers4579/458B/4593/45B1, excluding
            # its separate video/device and configured timer-policy owners.
            entry=b.trial_writes.index((0x80,(before[0x80]&0x3F)|0x40))
            clock_byte=(before[0xA4]&0x73)|4
            assert b.trial_writes[entry:entry+6]==[
                (0x80,(before[0x80]&0x3F)|0x40),
                (0xA0,((before[0xA0]|0x34)&0xFC)|1),
                (0x56,(before[0x56]&0xFC)|3),
                (0xA4,clock_byte),(0xA4,clock_byte&0xEF),(0xA4,clock_byte|0x10)]
            assert not any(register==0x92 for register,value in b.trial_writes)
            # Native4557..4567/459F/45B1: full-on selection then latch, with no
            # subsequent raw-byte replay of the dormant pre-request selector.
            a4_writes=[value for register,value in b.trial_writes if register==0xA4]
            assert all(value & 3 == divider for value in a4_writes), (mode,divider,a4_writes)
            assert a4_writes[-2:]==[(before[0xA4]&0x63)|0x80,(before[0xA4]&0x63)|0x90]
            expected_edges=2 if when.startswith('spurious') else 1
            assert len(a4_writes)==3*expected_edges+2
            assert b.cf8==cf8 and b.port61==0xA7 and b.clock_edges==expected_edges
            rows.append(dict(mode=mode,irq=irq,when=when,divider_encoding=divider,wakes=b.wakes,divider_preserved=True))
        for disabled in (False,True):
            b=IdleBoard();assert b.startup()==1
            b.conf[SB][0xA4]=1
            assert b.run_apm(mode,disabled=disabled)==int(not disabled)
            assert b.clock_edges==int(not disabled)
            rows.append(dict(mode=mode,disabled=disabled))
    for mode in (1,2,3):
        b=IdleBoard(family='Am5x86',bridge=0x888A1060,irq=1);assert b.startup()==1
        b.conf[SB][0xA4]=1
        assert b.run_apm(mode)==1 and b.clock_edges==1
        rows.append(dict(mode=mode,cpu='Am5x86',bridge='BF',irq=1))
    for function in (0,2,3):
        b=IdleBoard();assert b.startup()==1
        b.conf[SB][0xA4]=1
        assert b.run_apm(1,function=function)==0 and b.clock_edges==0
        rows.append(dict(public_function=function,extension='E000',no_clock_request=True))
    for divider in (0,2,3):
        b=IdleBoard();assert b.startup()==1
        b.conf[SB][0xA4]=divider
        assert b.run_apm(1,function=0)==0 and b.clock_edges==0
        rows.append(dict(public_function=0,divider_encoding=divider,clock_capability=True))
    for mode in (1,2,3):
        for reject in ('not-ready','interface','no-SMI'):
            b=IdleBoard(when='hlt');assert b.startup()==1
            b.conf[SB][0xA4]=1
            if reject=='not-ready':
                b.u.mem_write(b.ebda+smm.STATUS,b'\0')
            elif reject=='interface':
                b.conf[SB][0x76]=0x10
            else:
                b.deliver=False
                b.conf[SB][0xA0]=0x81
            assert b.run_apm(mode)==1 and b.clock_edges==0
            if reject=='no-SMI':
                assert b.conf[SB][0xA0]==0x81
            rows.append(dict(mode=mode,decline=reject,wakes=1,clock_edges=0))
    for deliver,paged in ((True,False),(False,False),(True,True),(False,True)):
        b=IdleBoard(when='request' if deliver else 'hlt');assert b.startup()==1
        b.conf[SB][0xA4]=1
        b.deliver=deliver
        b.conf[HB][0x50]=0x85
        b.dirty={0x140000:b'V86 dirty data'}
        assert b.run_apm(1,virtual=True,paged=paged)==1 and b.clock_edges==int(deliver)
        if deliver:
            assert not b.dirty and bytes(b.u.mem_read(0x140000,14))==b'V86 dirty data'
        else:
            assert b.dirty=={0x140000:b'V86 dirty data'}
        rows.append(dict(entry='virtual-8086 INT15',paged=paged,wakes=1,clock_edges=b.clock_edges))
    raw=smm.ROM.read_bytes()
    nasm=shutil.which('nasm') or str(Path(os.environ['LOCALAPPDATA'])/'bin/NASM/nasm.exe')
    config=json.loads((smm.PORT/'port.json').read_text())['platform']
    image=smm.PORT/'build/diagnostics/IDLECHK.COM'
    subprocess.run([nasm,'-w+error','-f','bin','-DIDLE_TRIAL',f'-DSMM_STATUS={smm.STATUS}',
                    f'-DSTATE_KIB={config["state_kib"]}',f'-DNMI_POLICY={config["rtc_nmi_mask"]}',
                    '-DIDLE_STATUS='+str(smm.constants(smm.PORT/'src/hardware/board-definition.inc')['HW_SMM_IDLE_STATUS']),
                    '-o',str(image),str(smm.PORT/'diagnostics/wake-check.asm')],check=True)
    listing=smm.Listing(smm.ROM.with_suffix('.lst'))
    symbols={name:listing.symbol(name) for name in ('int15','int70','RTC_INTERRUPT_LABEL')}
    for name,opts,expected in [('timer',{},'T0'),('keyboard',{'keyboard':True},'K0'),
                               ('no-SMI',{'no_smi':True},'T7'),
                               ('keyboard-watchdog',{'keyboard':True,'key_missing':True},'K6')]:
        b=IdleBoard(irq=8 if opts.get('key_missing') else (1 if opts.get('keyboard') else 0));assert b.startup()==1
        b.watchdog=bool(opts.get('key_missing'))
        b.conf[SB][0xA4]=1
        b.deliver=not opts.pop('no_smi',False)
        if not b.deliver:
            b.when='hlt'
        row=clock.wake.check(image.read_bytes(),raw,symbols,smm.STATUS,config['state_kib'],
                             config['rtc_nmi_mask'],name,board=b,idle=True,ebda=b.ebda>>4,
                             expected=expected,**opts)
        rows.append(row)
    result=dict(cases=rows,image=dict(size=len(raw),SUM32=f'{sum(raw):08X}',sha256=hashlib.sha256(raw).hexdigest()),
                physical_timer_keyboard_wake='not yet tested')
    (OUT/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(f'APM idle: {len(rows)} composed real/PM16/PM32 checks PASS')


if __name__=='__main__':
    main()
