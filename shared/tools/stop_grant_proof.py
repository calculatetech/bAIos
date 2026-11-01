"""Run shared Idle/APM against a synthetic STPCLK provider and IRQ boundary."""
import os
from pathlib import Path
import shutil
import struct
import subprocess

from unicorn import Uc, UC_ARCH_X86, UC_MODE_16, UC_HOOK_CODE, UC_HOOK_INSN, UC_HOOK_INTR
from unicorn import x86_const as x


ROOT = Path(__file__).resolve().parents[2]
CODE = 0xF0000
REGS = ('EAX', 'EBX', 'ECX', 'EDX', 'ESI', 'EDI', 'EBP', 'ESP',
        'DS', 'ES', 'FS', 'GS', 'SS', 'EFLAGS')
NAMES = ('query16', 'idle16', 'query32', 'idle32', 'int15', 'apm_pm16', 'apm_pm32', 'irq16', 'irq32')


def descriptor(base, length, access, flags=0):
    limit = length - 1
    return struct.pack('<HHBBBB', limit & 65535, base & 65535, base >> 16 & 255,
                       access, (limit >> 16 & 15) | flags, base >> 24)


class Idle:
    def __init__(self, raw, bits, qualified=1, enter=1, state_base=0x30000):
        self.symbols = dict(zip(NAMES, struct.unpack_from('<9I', raw)))
        self.cpu = Uc(UC_ARCH_X86, UC_MODE_16)
        self.cpu.mem_map(0, 0x200000)
        self.cpu.mem_write(CODE, raw)
        self.bits = bits
        self.qualified = qualified
        self.enter = enter
        self.state_base = state_base
        self.cpu.mem_write(0x40E, struct.pack('<H', state_base >> 4))
        self.events = []
        self.pending = False
        self.halted = False
        self.stop = None
        self.cpu.hook_add(UC_HOOK_CODE, self.step)
        self.cpu.hook_add(UC_HOOK_INTR, self.interrupt)
        self.cpu.hook_add(UC_HOOK_INSN, self.port_in, None, 1, 0, x.UC_X86_INS_IN)
        self.cpu.hook_add(UC_HOOK_INSN, self.port_out, None, 1, 0, x.UC_X86_INS_OUT)
        if bits == 32:
            self.protected(3)
        else:
            self.cpu.reg_write(x.UC_X86_REG_CS, CODE >> 4)

    def protected(self, mode):
        self.mode = mode
        gdt = bytearray(64)
        gdt[8:16] = descriptor(CODE, 65536, 0x9A, 0x40 if mode == 3 else 0)
        gdt[16:24] = descriptor(0, 0x100000, 0x92, 0x40 if mode == 3 else 0)
        selector = 0x20 if mode == 3 else 0x30
        gdt[selector:selector+8] = descriptor(CODE, 65536, 0x9A, 0x40 if mode == 3 else 0)
        data = selector + (16 if mode == 3 else 8)
        gdt[data:data+8] = descriptor(self.state_base, 0x300, 0x92)
        self.cpu.mem_write(0x7000, bytes(gdt))
        self.cpu.reg_write(x.UC_X86_REG_GDTR, (0, 0x7000, len(gdt)-1, 0))
        self.cpu.reg_write(x.UC_X86_REG_CR0, 1)
        self.cpu.reg_write(x.UC_X86_REG_CS, 8)
        # MODE16 register setters retain real-mode data bases; load OS selectors in code.
        loader = b'\xfa'+(b'\x66' if mode == 3 else b'')+b'\xb8\x10\x00\x8e\xd8\x8e\xc0\x8e\xe0\x8e\xe8\x8e\xd0'
        self.cpu.mem_write(CODE+0x9400, loader)
        self.stop = CODE+0x9400+len(loader)
        self.cpu.emu_start(0x9480, 0, count=100)
        assert self.cpu.reg_read(x.UC_X86_REG_EIP) == 0x9400+len(loader)
        self.stop = None
        return selector

    def step(self, cpu, address, size, unused):
        if address == self.stop or self.pending:
            cpu.emu_stop()
        elif cpu.mem_read(address, 1) == b'\xf4':
            self.halted = True
            self.events.append('hlt')

    def port_in(self, cpu, port, size, unused):
        assert size == 1 and port in (0xE0, 0xE1), (port, size)
        self.events.append('query' if port == 0xE0 else 'idle')
        return self.qualified if port == 0xE0 else self.enter

    def port_out(self, cpu, port, size, value, unused):
        assert (port, size, value) == (0xE2, 1, 1), (port, size, value)
        assert not self.pending and cpu.reg_read(x.UC_X86_REG_EFLAGS) & 0x200
        # Intel 241731 sections9.3.4/9.6: hardware acknowledges before stopping.
        self.events.extend(('stpclk-low', 'stop-grant-ack'))
        self.pending = True

    def frame(self, target, width):
        cpu = self.cpu
        spreg = x.UC_X86_REG_ESP if width == 4 else x.UC_X86_REG_SP
        stack = cpu.reg_read(spreg)
        for value in (cpu.reg_read(x.UC_X86_REG_EFLAGS), cpu.reg_read(x.UC_X86_REG_CS),
                      cpu.reg_read(x.UC_X86_REG_EIP)):
            stack -= width
            cpu.mem_write(stack, (value & ((1 << (8*width))-1)).to_bytes(width, 'little'))
        cpu.reg_write(spreg, stack)
        cpu.reg_write(x.UC_X86_REG_EFLAGS, cpu.reg_read(x.UC_X86_REG_EFLAGS) & ~0x300)
        cpu.reg_write(x.UC_X86_REG_CS, 8 if cpu.reg_read(x.UC_X86_REG_CR0) & 1 else CODE >> 4)
        cpu.reg_write(x.UC_X86_REG_EIP, target)

    def interrupt(self, cpu, vector, unused):
        assert vector == 0x15, ('Unexpected exception/interrupt', vector, self.bits,
                               cpu.reg_read(x.UC_X86_REG_CS), hex(cpu.reg_read(x.UC_X86_REG_EIP)),
                               hex(cpu.reg_read(x.UC_X86_REG_ESP)),
                               bytes(cpu.mem_read(cpu.reg_read(x.UC_X86_REG_SP), 12)).hex(), self.events)
        self.frame(self.symbols['int15'], 2)

    def run(self, entry, end=0x9000):
        cpu = self.cpu
        self.stop = CODE + end
        cpu.reg_write(x.UC_X86_REG_EIP, entry)
        wakes = 0
        while True:
            ip = cpu.reg_read(x.UC_X86_REG_EIP)
            # Unicorn MODE16 subtracts visible CS*16, also for protected CS.
            cpu.emu_start(ip + cpu.reg_read(x.UC_X86_REG_CS)*16, 0, count=10000)
            if not self.pending and not self.halted:
                break
            assert cpu.reg_read(x.UC_X86_REG_EFLAGS) & 0x200
            if self.pending:
                self.events.extend(('irq-assert', 'stpclk-high'))
                self.pending = False
            self.halted = False
            self.events.append('irq-delivery')
            self.frame(self.symbols['irq32' if self.bits == 32 else 'irq16'], self.bits // 8)
            wakes += 1
            assert wakes == 1, self.events
        assert cpu.reg_read(x.UC_X86_REG_EIP) == end, (hex(cpu.reg_read(x.UC_X86_REG_EIP)), self.events)
        assert struct.unpack('<I', cpu.mem_read(CODE+0x6000, 4))[0] == wakes
        return wakes

    def seed(self, flags):
        for i, name in enumerate(REGS[:7]):
            self.cpu.reg_write(getattr(x, 'UC_X86_REG_'+name), 0xA0001234 + i*0x10001)
        self.cpu.reg_write(x.UC_X86_REG_ESP, 0x8800)
        self.cpu.reg_write(x.UC_X86_REG_EFLAGS, flags)

    def state(self):
        return {name: self.cpu.reg_read(getattr(x, 'UC_X86_REG_'+name)) for name in REGS}

    def macro(self, name, flags):
        self.seed(flags)
        width = self.bits // 8
        self.cpu.mem_write(0x8800, (0x9000).to_bytes(width, 'little'))
        before = self.state()
        wakes = self.run(self.symbols[name+str(self.bits)])
        after = self.state()
        before['ESP'] += width
        if name == 'query':
            before['EFLAGS'] = (before['EFLAGS'] & ~1) | int(not self.qualified)
        assert before == after, (name, self.bits, before, after)
        return wakes

    def apm(self, mode, function, flags=0x603, disabled=False):
        if mode > 1:
            selector = self.protected(mode)
        self.seed(flags)
        self.cpu.mem_write(self.state_base+0x27A, bytes((mode if function else 0, 2, int(disabled))))
        self.cpu.reg_write(x.UC_X86_REG_AX, 0x5300 | function)
        self.cpu.reg_write(x.UC_X86_REG_BX, 0)
        if mode == 1:
            self.cpu.mem_write(CODE+0x9000, b'\xcd\x15\x90')
            end = 0x9002
        else:
            offset = self.symbols['apm_pm32' if mode == 3 else 'apm_pm16']
            pointer = offset.to_bytes(self.bits//8, 'little') + struct.pack('<H', selector)
            self.cpu.mem_write(CODE+0x9000, b'\x9a'+pointer+b'\x90')
            end = 0x9001+len(pointer)
        before = self.state()
        wakes = self.run(0x9000, end)
        after = self.state()
        before['EFLAGS'] &= ~1
        if function == 0:
            before['EAX'] = before['EAX'] & 0xFFFF0000 | 0x0102
            before['EBX'] = before['EBX'] & 0xFFFF0000 | 0x504D
            before['ECX'] = before['ECX'] & 0xFFFF0000 | 3 | (4 if self.qualified else 0) | (8 if disabled else 0)
        assert before == after, (mode, function, before, after)
        return wakes


def check():
    nasm = shutil.which('nasm') or str(Path(os.environ['LOCALAPPDATA'])/'bin/NASM/nasm.exe')
    # Temporary output stays under the repository's shared test owner.
    output = ROOT/'shared/build/tests'
    output.mkdir(parents=True, exist_ok=True)
    directory = output/'stop-grant-proof'
    directory.mkdir(exist_ok=True)
    binary = directory/'proof.bin'
    loader = directory/'load-bios-state.inc'
    try:
        bodies = []
        for source in ('shared/src/firmware/bios.asm', 'presario-800/src/bios.asm'):
            text = (ROOT/source).read_text()
            assert text.count('\nload_bios_state:\n') == 1, source
            bodies.append('load_bios_state:\n'+text.split('\nload_bios_state:\n')[1].split('\n\n')[0]+'\n')
        assert bodies[0] == bodies[1], 'State-loader owners differ; exercise each production body'
        loader.write_text(bodies[0])
        command = [nasm, '-I'+str(directory)+'/', '-I'+str(ROOT/'shared/src')+'/', '-f', 'bin', '-o', str(binary),
                   str(ROOT/'shared/tests/stop-grant.asm')]
        for late in ([], ['-DLATE_PROVIDER']):
            for partial in ('ONLY_QUERY', 'ONLY_IDLE'):
                result = subprocess.run(command+['-DPROVIDER', '-D'+partial]+late, capture_output=True, text=True)
                assert result.returncode != 0 and 'requires both' in result.stderr, result.stderr
        for defines in ([], ['-DPROVIDER'], ['-DPROVIDER', '-DLATE_PROVIDER']):
            provider = bool(defines)
            subprocess.run(command+defines, check=True)
            raw = binary.read_bytes()
            for bits in (16, 32):
                if not provider:
                    symbols = dict(zip(NAMES, struct.unpack_from('<9I', raw)))
                    expected = b'\x9c\xfb\xf4\x9d\xc3'
                    start = symbols['idle'+str(bits)]
                    assert raw[start:start+len(expected)] == expected
                for qualified in ((0, 1) if provider else (0,)):
                    for flags in (3, 0x203, 0x603, 0x8D7):
                        model = Idle(raw, bits, qualified)
                        assert model.macro('query', flags) == 0
                        assert model.events == (['query'] if provider else [])
                        for enter in (0, 1):
                            model = Idle(raw, bits, qualified, enter)
                            assert model.macro('idle', flags) == 1
                            expected = ['query'] if provider else []
                            if qualified:
                                expected += ['idle']
                            expected += (['stpclk-low', 'stop-grant-ack', 'irq-assert', 'stpclk-high']
                                         if qualified and enter else ['hlt'])
                            assert model.events == expected+['irq-delivery'], model.events
                for mode in ((1, 2) if bits == 16 else (3,)):
                    for qualified in ((0, 1) if provider else (0,)):
                        if mode == 1:
                            for state_base in (0x30000, 0x34000):
                                for disabled in (False, True):
                                    model = Idle(raw, bits, qualified, state_base=state_base)
                                    assert model.apm(mode, 0, disabled=disabled) == 0
                                    assert model.events == (['query'] if provider else [])
                        for disabled in (False, True):
                            for enter in (0, 1):
                                model = Idle(raw, bits, qualified, enter)
                                assert model.apm(mode, 5, disabled=disabled) == int(not disabled)
                                if disabled:
                                    assert not model.events, model.events
                                elif qualified and enter:
                                    assert model.events == ['query', 'idle', 'stpclk-low', 'stop-grant-ack',
                                                            'irq-assert', 'stpclk-high', 'irq-delivery']
                                else:
                                    expected = ['query'] if provider else []
                                    if qualified:
                                        expected += ['idle']
                                    assert model.events == expected+['hlt', 'irq-delivery'], model.events
                        if mode == 1:
                            for disabled in (False, True):
                                for enter in (0, 1):
                                    model = Idle(raw, bits, qualified, enter, state_base=0x34000)
                                    assert model.apm(mode, 5, disabled=disabled) == int(not disabled)
                                    if disabled:
                                        assert not model.events, model.events
                                    elif qualified and enter:
                                        assert model.events == ['query', 'idle', 'stpclk-low', 'stop-grant-ack',
                                                                'irq-assert', 'stpclk-high', 'irq-delivery']
                                    else:
                                        expected = ['query'] if provider else []
                                        if qualified:
                                            expected += ['idle']
                                        assert model.events == expected+['hlt', 'irq-delivery'], model.events
    finally:
        binary.unlink(missing_ok=True)
        loader.unlink(missing_ok=True)
        directory.rmdir()
    print('PASS 16/32-bit Idle provider pairing, qualification, exact HLT default, decline fallback, caller state, '
          'Stop Grant acknowledgment/release/IRQ, production BDA state loader, and public real/PM16/PM32 APM policy')


if __name__ == '__main__':
    check()
