"""Parameterize the proved Presario RTC/UI machinery with opaque ACC devices.
Only device I/O, VGA provider calls and reset pulses are external responses.
No PB430/shared firmware owner is skipped or replaced.
"""
import importlib
import struct
import sys
from pathlib import Path
from unicorn import UC_HOOK_CODE,UC_HOOK_MEM_READ
from unicorn import x86_const as x
from shared.tools.ram_proof import Listing
from shared.tools.peripheral_proof import UART, Printer
PORT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PORT.parent/'presario-800/tools'))
rtc=importlib.import_module('test-rtc')
setup=importlib.import_module('test-setup')


def configure(image):
    image=Path(image);folder=image.parent/'fixture-alias';folder.mkdir(exist_ok=True)
    # The donor runner's filename is a fixture API; bytes come from this candidate.
    (folder/'baios-presario800-system.rom').write_bytes(image.read_bytes()[65536:])
    rtc.BUILD=folder
    listing=Listing(image.with_suffix('.lst'))
    def symbol(name):
        if name=='int1a':name='RTC_INTERRUPT_LABEL'
        if name=='.warm_start':return listing.symbol('startup')
        return listing.symbol(name)
    rtc.symbol=symbol
    return listing


class ACC(setup.Setup):
    def __init__(self,image,payload=None,font_offset=None,video_vector=(0x100,0xC000),external_video=False):
        self.listing=configure(image)
        self.provider_font_offset=font_offset if font_offset is not None else Path(image).read_bytes()[:32768].find((PORT/'reference/pb430-m27c1001.bin').read_bytes()[28169:32265])
        self.provider_vector=video_vector
        self.registers=bytearray([0xA5])*256;self.registers[2]=0xB9
        self.acc_index=0;self.acc_writes=[];self.delay_writes=[];self.sys_flag=4;self.power_low=False;self.jumper=4;self.keyboard_silent=False;self.keyboard_bad_bat=False
        self.devices_uart=[UART(),UART()];self.extra_uarts={};self.printer=Printer()
        self.port92=0x40;self.kbc_output=0xCF;self.a20_writes=[];self.port78_writes=[]
        self.kbc_cb=0x45;self.kbc_p1=0;self.kbc_next=None;self.aux_reply=[];self.aux_present=True;self.device_commands=[];self.ata_commands=[]
        self.reset_pending=False;self.continue_reset=False;self.starting=False;self.trace_seen=set();self.after_reset_script=[]
        self.stopped=False;self.visits=[];self.reset_count=0
        self.trace_owners={0xF0000+self.listing.symbol(name):name for name in ('startup','init_pic_pit','init_rtc','init_superio','initialize_video','init_keyboard','board_a20_handoff','settings_load','chipset_apply','init_peripherals','init_floppy','ata_detect_primary','init_mouse','init_fpu','setup_main','warm_reset','cache_initialize','cache_initial_policy','chipset_late_cache','option_rom_discovery','post_debug_summary','int19','boot_retry')}
        self.code_observer=None
        super().__init__(segment=0x9E00)
        self.stop_address=0xF0000+rtc.symbol('init_fpu')
        self.cpu.mem_map(0x200000,62*1024*1024)
        raw=Path(image).read_bytes();self.cpu.mem_write(0xE0000,raw)
        self.cpu.mem_write(0xC0000,raw[:32768])
        self.vga_input=raw[:32768]
        self.external_video=external_video
        self.cpu.hook_add(UC_HOOK_MEM_READ,self.video_read,begin=0xC0000,end=0xE7FFF)
        self.cpu.mem_write(0x40,struct.pack('<HH',0x100,0xC000))
        self.cpu.mem_write(self.base+0xD0,struct.pack('<H',15360))
        self.cpu.mem_write(self.base+0xD8,struct.pack('<II',15360,15360))
        self.cpu.mem_write(self.base+0x1007,b'\x01')
        self.cpu.mem_write(0x413,struct.pack('<H',632))
        self.cpu.mem_write(0x508,struct.pack('<H',640))
        self.cpu.mem_write(0x49E,b'\x01')
        self.code_observer=None
        self.cpu.hook_del(self.code_hook)
        self.cpu.hook_add(UC_HOOK_CODE,self.code,begin=1,end=0xF0000+rtc.symbol('chipset_visible_ram_test')-1)
        self.cpu.hook_add(UC_HOOK_CODE,self.code,begin=0xF0000+rtc.symbol('chipset_runtime_ram_check'),end=0xFFFFFFFF)
        if payload is not None:self.cmos[:]=payload[:128]
        self.call('settings_load')

    def video_read(self,cpu,access,address,size,value,unused):
        # ACC2168 disables onboard C000 decode until the retained E000 ROM is copied.
        if not self.external_video and 0xC0000<=address<0xC8000 and not self.registers[2]&1:
            cpu.mem_write(address,bytes([255])*size)
        elif 0xE0000<=address<0xE8000 and not self.registers[2]&8:
            cpu.mem_write(address,self.vga_input[address-0xE0000:address-0xE0000+size])

    def uart_mapping(self):
        r=self.registers; result={}
        for n,idx,mask in ((0,0xDC,0x18),(1,0xDD,3)):
            if not r[0xDB]&mask:result[(r[idx]&0xFE)<<2]=self.devices_uart[n]
        result.update(self.extra_uarts)
        return result

    def irq_sources(self):
        # ACC3221 data sheet pp18-19: IRQ3 bits7:6, IRQ4 bits5:4.
        de=self.registers[0xDE]
        return {3:(de>>6)&3,4:(de>>4)&3}

    def port_in(self,cpu,port,size,unused):
        if port in (0x3F4,0x3F5,0x3F7) and self.registers[0xFB]&2:return 255
        if port==0x71 and self.index==0xD and self.power_low:
            super().port_in(cpu,port,size,unused);return 0
        if port==0xF3:return self.registers[self.acc_index]
        if port==0xED:return 0
        if port==0x78:return self.jumper
        if port==0x92:return self.port92
        if port in (0x3BA,0x3DA,0x3C0,0x3CC):return 1 if port==0x3CC else 0
        for base,uart in self.uart_mapping().items():
            if base<=port<base+8:return uart.read(port-base)
        lp=self.registers[0xBF]<<2
        if not self.registers[0xBE]&0x18 and lp<=port<lp+3:return self.printer.read(port-lp)
        if any(base<=port<base+8 for base in (0x3F8,0x2F8,0x3E8,0x2E8)) or any(base<=port<base+3 for base in (0x3BC,0x378,0x278)):return 255
        if port==0x64:return 0x21 if self.aux_reply else self.sys_flag|int(bool(self.pending))
        if port==0x60 and self.aux_reply:return self.aux_reply.pop(0)
        if port==0x60 and not self.pending:return 255
        if port in (0x1F7,0x3F6):return 0
        if port in (0x1F1,0x1F2,0x1F3,0x1F4,0x1F5):return 0
        return super().port_in(cpu,port,size,unused)

    def port_out(self,cpu,port,size,value,unused):
        if port==0x8F:
            assert size==1 and value==0,('refresh page register',size,value)
            return
        if port==0x78:self.port78_writes.append(value);return
        if port in (0x60,0x64):self.device_commands.append((port,value))
        if port==0x1F7:self.ata_commands.append(value)
        if port in (0x3F2,0x3F5,0x3F7) and self.registers[0xFB]&2:return
        if port==0x3F5 and value==0x10 and not self.fdc_command:self.fdc_fifo.append(0x80);return
        if port==0xF2:self.acc_index=value;return
        if port==0xF3:self.registers[self.acc_index]=value;self.acc_writes.append((self.acc_index,value));return
        if port==0xED:self.delay_writes.append(value);self.delayed=True;return
        if port==0x92:
            self.port92=value&0xFE;self.a20_writes.append((port,value))
            if value&1:self.reset_count+=1;self.reset_pending=True;cpu.emu_stop()
            return
        for base,uart in self.uart_mapping().items():
            if base<=port<base+8:uart.write(port-base,value);return
        lp=self.registers[0xBF]<<2
        if not self.registers[0xBE]&0x18 and lp<=port<lp+3:self.printer.write(port-lp,value);return
        if any(base<=port<base+8 for base in (0x3F8,0x2F8,0x3E8,0x2E8)) or any(base<=port<base+3 for base in (0x3BC,0x378,0x278)):return
        if port in (0x3B8,0x3D8,0x3C0,0x3C2,0x0D,0xDA,0x41,0x84,0xF0,0xF1,0xF4,0xF5,0x1F1,0x1F2,0x1F3,0x1F4,0x1F5,0x1F6,0x1F7,0x3F6):return
        if port==0x40:self.pit_counter=0xFFFF;return
        if port==0x64:
            if value==0xFE:
                self.reset_count+=1;self.reset_pending=True;cpu.emu_stop();return
            if value in (0x60,0xD4,0xD1,0xC7):self.kbc_next=value;return
            if value==0x20:self.pending.insert(0,self.kbc_cb);return
            if value==0xD0:self.pending.insert(0,self.kbc_output);return
            if value==0xAA:self.pending.insert(0,0x55);return
            if value==0xAD:self.kbc_cb|=0x10;return
            if value==0xAE:self.kbc_cb&=~0x10;return
            if value==0xA7:self.kbc_cb|=0x20;return
            if value==0xA8:self.kbc_cb&=~0x20;return
        if port==0x60 and self.kbc_next:
            mode=self.kbc_next;self.kbc_next=None
            if mode==0x60:
                self.kbc_cb=value
                self.sys_flag=value&4 # Command-byte bit2 is the 8042 system flag.
            elif mode==0xC7:self.kbc_p1|=value
            elif mode==0xD1:self.kbc_output=value;self.a20_writes.append((port,value))
            elif mode==0xD4 and self.aux_present:
                self.aux_reply.append(0xFA)
                if value==0xFF:self.aux_reply.extend((0xAA,0))
            return
        if port==0x60 and value==0xFF and self.starting:
            if not self.keyboard_silent:self.pending.extend((0xFA,0xFC if self.keyboard_bad_bat else 0xAA))
            return
        return super().port_out(cpu,port,size,value,unused)

    def code(self,cpu,address,size,unused):
        if self.code_observer:self.code_observer(self,address)
        if self.starting and address in self.trace_owners and address not in self.trace_seen:
            self.trace_seen.add(address)
        if self.starting and address==0xC0003:
            # Only the opaque retained video provider far entry is modeled.
            cpu.mem_write(0x40,struct.pack('<HH',*self.provider_vector))
            ss=cpu.reg_read(x.UC_X86_REG_SS);sp=cpu.reg_read(x.UC_X86_REG_SP)
            ip,cs=struct.unpack('<HH',cpu.mem_read(ss*16+sp,4))
            cpu.reg_write(x.UC_X86_REG_SP,sp+4);cpu.reg_write(x.UC_X86_REG_CS,cs);cpu.reg_write(x.UC_X86_REG_IP,ip);return
        if self.starting and address==self.stop_address:
            self.stopped=True;self.starting=False;cpu.emu_stop();return
        if self.starting:
            if address==self.warm_entry:self.visits.append('startup')
            # Setup's warm_entry stop is not active in this continuation.
            if address==self.warm_entry:return
        super().code(cpu,address,size,unused)

    def call(self,name,flags=0x202,count=300000000):
        cpu=self.cpu
        for reg,value in ((x.UC_X86_REG_CS,0xF000),(x.UC_X86_REG_IP,rtc.symbol(name)),(x.UC_X86_REG_DS,0),(x.UC_X86_REG_ES,0),(x.UC_X86_REG_FS,self.segment),(x.UC_X86_REG_SS,0),(x.UC_X86_REG_SP,0x6FFE),(x.UC_X86_REG_EFLAGS,flags)):
            cpu.reg_write(reg,value)
        cpu.mem_write(0x6FFE,b'\xff\xff')
        cpu.emu_start(0xF0000+rtc.symbol(name),0xFFFFF,count=count)
        if self.reset_pending:self.complete_reset(count)
        else:assert cpu.reg_read(x.UC_X86_REG_IP)==0xFFFF,(name,hex(cpu.reg_read(x.UC_X86_REG_IP)))

    def complete_reset(self,count=100000000):
        cpu=self.cpu
        while self.reset_pending:
            assert self.continue_reset,'unexpected reset pulse'
            self.reset_pending=False;self.starting=True;self.stopped=False
            self.script=self.after_reset_script.copy();self.after_reset_script=[]
            for reg,value in ((x.UC_X86_REG_CR0,0x60000010),(x.UC_X86_REG_EFLAGS,2),(x.UC_X86_REG_CS,0xF000),(x.UC_X86_REG_IP,0xFFF0),(x.UC_X86_REG_DS,0),(x.UC_X86_REG_ES,0),(x.UC_X86_REG_FS,0),(x.UC_X86_REG_GS,0),(x.UC_X86_REG_SS,0),(x.UC_X86_REG_EDX,0x403),(x.UC_X86_REG_ESP,0)):
                cpu.reg_write(reg,value)
            cpu.emu_start(0xFFFF0,0x100000,count=count)
            assert self.stopped or self.reset_pending,('reset continuation failed',hex(cpu.reg_read(x.UC_X86_REG_IP)))

    def public(self,vector,ax,dx=0,cx=0,bx=0):
        cpu=self.cpu
        for reg,value in ((x.UC_X86_REG_CS,0x9000),(x.UC_X86_REG_IP,0),(x.UC_X86_REG_AX,ax),(x.UC_X86_REG_BX,bx),(x.UC_X86_REG_CX,cx),(x.UC_X86_REG_DX,dx),(x.UC_X86_REG_SS,0),(x.UC_X86_REG_SP,0x7000),(x.UC_X86_REG_EFLAGS,0x202)):
            cpu.reg_write(reg,value)
        cpu.mem_write(0x90000,bytes((0xCD,vector,0x90)))
        cpu.emu_start(0x90000,0x90002,count=12000000)
        assert cpu.reg_read(x.UC_X86_REG_CS)==0x9000 and cpu.reg_read(x.UC_X86_REG_IP)==2
        return cpu.reg_read(x.UC_X86_REG_AX),cpu.reg_read(x.UC_X86_REG_EFLAGS)

    def interrupt(self,cpu,vector,unused):
        if vector in (0x10,0x42) and cpu.reg_read(x.UC_X86_REG_AX)==0x1130:
            target=bytes(cpu.mem_read(vector*4,4))
            if vector==0x42 and target==struct.pack('<HH',0xF065,0xF000):
                assert bytes(cpu.mem_read(0xFF065,11))==bytes.fromhex('80fc1d7305ea972800c0cf')
            else:
                assert target==bytes(cpu.mem_read(0x40,4))
            offset,segment=struct.unpack('<HH',cpu.mem_read(0x40,4))
            assert segment*16+offset==0xC0100 # The same opaque handler under far aliases.
            cpu.reg_write(x.UC_X86_REG_ES,0xC000);cpu.reg_write(x.UC_X86_REG_BP,self.provider_font_offset)
            cpu.reg_write(x.UC_X86_REG_CX,16);cpu.reg_write(x.UC_X86_REG_DX,24)
            return
        super().interrupt(cpu,vector,unused)

    def irq_scans(self,scans):
        """Opaque PIC/8042 raises IRQ1; guest executes the installed IRQ owner."""
        for scan in scans:
            self.pending.append(scan)
            u=self.cpu
            u.reg_write(x.UC_X86_REG_CS,0x9000);u.reg_write(x.UC_X86_REG_IP,0)
            u.reg_write(x.UC_X86_REG_SS,0);u.reg_write(x.UC_X86_REG_SP,0x7000);u.reg_write(x.UC_X86_REG_EFLAGS,0x202)
            u.mem_write(0x90000,b'\x90')
            rtc.Clock.interrupt(self,u,9,None)
            begin=u.reg_read(x.UC_X86_REG_CS)*16+u.reg_read(x.UC_X86_REG_IP)
            u.emu_start(begin,0x90000,count=1000000) # CAD now executes the stock131064-read teardown.
            if self.reset_pending:break
            assert u.reg_read(x.UC_X86_REG_CS)==0x9000 and u.reg_read(x.UC_X86_REG_IP)==0

    def irq_current(self,scan):
        """Deliver an external IRQ1 while preserving the production continuation."""
        u=self.cpu;pc=u.reg_read(x.UC_X86_REG_CS)*16+u.reg_read(x.UC_X86_REG_IP)
        assert u.reg_read(x.UC_X86_REG_EFLAGS)&0x200
        self.pending.append(scan);rtc.Clock.interrupt(self,u,9,None)
        begin=u.reg_read(x.UC_X86_REG_CS)*16+u.reg_read(x.UC_X86_REG_IP)
        u.emu_start(begin,pc,count=100000)
        assert u.reg_read(x.UC_X86_REG_CS)*16+u.reg_read(x.UC_X86_REG_IP)==pc

    def cold_boot(self):
        self.sys_flag=0;self.cpu.mem_write(0x472,b'\0\0')
        self.reset_pending=True;self.continue_reset=True;self.complete_reset(count=300000000)
