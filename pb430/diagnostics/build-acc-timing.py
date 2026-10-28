"""Build and exercise the bounded PB430 timing probe; timings here are synthetic."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

from capstone import Cs, CS_ARCH_X86, CS_MODE_16
from unicorn import Uc, UC_ARCH_X86, UC_MODE_16, UC_HOOK_INSN, UC_HOOK_INTR, UC_HOOK_MEM_READ, UC_HOOK_MEM_WRITE
from unicorn import x86_const as x

PORT = Path(__file__).resolve().parents[1]
BASELINE = {0: 0xA9, 1: 0xBF, 4: 0x15, 5: 0x9C, 6: 0xB7, 0x0B: 0x15, 0x12: 9, 0x18: 0,
            0x19: 0, 0x1A: 0x24, 0x1D: 0xF0, 0x1E: 0x7B}


def check(raw, cases=None, profile=False):
    rows = []
    decoder = Cs(CS_ARCH_X86, CS_MODE_16)
    decoder.detail = True
    for label in cases or ('trial05', 'trial04', 'trial-cas', 'trial-cas-lower',
                 'fast-trial-sampling', 'fast-trial-hidden', 'fast-trial-reference',
                 'fast-trial-refresh8', 'fast-trial-timing', 'fast-hidden-ram',
                 'fast-trial-sampling-128', 'fast-trial-sampling-restore-retry',
                 'fast-sampling-output', 'fast-sampling-readback',
                 'fast-trial-sampling-slow', 'fast-trial-hidden-slow',
                 'fast-wrong-write', 'fast-wrong-refresh', 'fast-0b-refused',
                 'fast-refresh-slow-refused',
                 'write-trial05', 'write-trial04', 'write-trial-lower', 'write-trial-128',
                 'write-trial-restore-retry', 'write-bad-readback', 'write-bad-ram',
                 'write-data', 'write-short-output', 'write-output-error',
                 'write-no-choice', 'write-bad-choice', 'write-trailing', 'write-burst-baseline',
                 'trial-sampling', 'trial-sampling-lower', 'trial-sampling-128',
                 'trial-sampling-restore-retry', 'sampling-readback', 'sampling-ram',
                 'sampling-output', 'sampling-wrong-state', 'sampling-trailing',
                 'trial-dram', 'trial-dram-lower', 'trial-dram-128',
                 'trial-dram-restore-retry', 'dram-readback', 'dram-ram',
                 'dram-output', 'dram-wrong-state', 'dram-trailing',
                 'trial-hidden', 'trial-hidden-lower', 'trial-hidden-128',
                 'trial-hidden-restore-retry', 'hidden-readback', 'hidden-ram',
                 'hidden-retention', 'hidden-output', 'hidden-wrong-state',
                 'hidden-trailing', 'hidden-wrong-refresh', 'trial-hidden-reserved19',
                 'retired-cas1', 'retired-cas1-lower', 'retired-cas1-128',
                 'retired-cas1-restore-retry',
                 'cas1-bad-suffix', 'cas1-bad-choice', 'cas1-wrong-state',
                 'trial-refresh2', 'trial-refresh4', 'trial-refresh8', 'trial-refresh-lower',
                 'trial-timing', 'trial-timing-lower', 'refresh-readback', 'refresh-ram',
                 'refresh-retention', 'refresh-output', 'timing-readback', 'timing-ram', 'timing-output',
                 'refresh-wrong-state', 'timing-wrong-state', 'refresh-no-divider', 'refresh-bad-divider', 'refresh-trailing',
                 'trial-reference', 'trial-reference-128', 'trial-reference-lower',
                 'reference-readback', 'reference-ram', 'reference-output',
                 'reference-wrong-01', 'reference-wrong-size', 'trial-reference-restore-retry',
                 'reference-wrong-128-pair', 'reference-wrong-512-pair',
                 'cas-readback', 'cas1-readback', 'cas-ram', 'cas1-ram', 'cas-output', 'cas1-output', 'bad-argument', 'v86', 'xms', 'little-memory',
                 'wrong-cache', 'already-tuned', 'wrong-timer', 'bad-readback',
                 'bad-ram', 'bad-a20', 'bad-ticks', 'short-output', 'output-error'):
        profile_fault = None
        profile_restore = None
        profile_wrong = None
        if profile and label.startswith('profile-readback-'):profile_fault=int(label.rsplit('-',1)[1],16)
        if profile and label.startswith('profile-restore-'):profile_restore=int(label.rsplit('-',1)[1],16)
        if profile and label.startswith('profile-wrong-'):profile_wrong=int(label.rsplit('-',1)[1],16)
        fast = label.startswith('fast-')
        writing = label.startswith('write-')
        sampling = 'sampling' in label
        dram = 'dram' in label
        hidden = 'hidden' in label
        case = label.replace('sampling', 'timing').replace('dram', 'timing').replace('hidden', 'timing')
        if fast:case=case.removeprefix('fast-')
        if writing:case=case.removeprefix('write-')
        if profile_fault is not None:case='bad-readback'
        if profile_restore is not None:case='trial-restore-retry'
        u = Uc(UC_ARCH_X86, UC_MODE_16)
        u.mem_map(0, 0x1000000)
        u.mem_write(0x20100, raw)
        cas1 = 'cas1' in case
        cas = 'cas' in case
        reference = 'reference' in case
        refresh = 'refresh' in case
        if hidden:refresh=False
        retention = refresh or hidden
        timing = 'timing' in case
        target = 5 if refresh else 0x18 if timing else 1 if reference else 0x0B
        stock = 0x9C if refresh else 0 if timing else 0x93 if reference else 0x15
        chosen = (0x9E if case == 'trial-refresh4' else 0x9F if case == 'trial-refresh8' else 0x9D) if refresh else (0x20 if sampling else 0x10) if timing else 0x92 if reference else 0x11 if cas1 else 0x19 if cas else 4 if case == 'trial04' else 5
        readback_or = 0x2C if reference else 0
        if dram:target,stock,chosen=4,0x15,5
        if hidden:target,stock,chosen=0x18,0,2
        if profile:
            target,stock,chosen=0x0B,4,0
            retention=True
        argument = (b' c' if case == 'trial-cas-lower' else b' C') if cas else b' 4' if case == 'trial04' else b' 5x' if case == 'bad-argument' else b''
        if cas1:
            argument = b' c1' if case == 'retired-cas1-lower' else b' C11' if case == 'cas1-bad-suffix' else b' C2' if case == 'cas1-bad-choice' else b' C1'
        if reference:
            argument = b' r' if case == 'trial-reference-lower' else b' R'
        if timing:
            argument = b' t' if case == 'trial-timing-lower' else b' T'
            if sampling:argument=argument.replace(b't',b's').replace(b'T',b'S')
            if dram:argument=argument.replace(b't',b'd').replace(b'T',b'D')
            if hidden:argument=argument.replace(b't',b'h').replace(b'T',b'H')
            if case=='timing-trailing':argument+=b'x'
        if refresh:
            argument = b' f2' if case == 'trial-refresh-lower' else b' F4' if case == 'trial-refresh4' else b' F8' if case == 'trial-refresh8' else b' F' if case == 'refresh-no-divider' else b' F1' if case == 'refresh-bad-divider' else b' F22' if case == 'refresh-trailing' else b' F2'
        if writing:
            argument=b' w5' if case=='trial-lower' else b' W4' if case=='trial04' else b' W5'
            argument={'no-choice':b' W','bad-choice':b' W1','trailing':b' W55'}.get(case,argument)
        if fast and case in ('wrong-write','wrong-refresh'):argument=b' S'
        u.mem_write(0x20080, bytes([len(argument)]) + argument + b'\r')
        for reg in (x.UC_X86_REG_CS, x.UC_X86_REG_DS, x.UC_X86_REG_ES, x.UC_X86_REG_SS):
            u.reg_write(reg, 0x2000)
        u.reg_write(x.UC_X86_REG_SP, 0xFFFE)
        flags = 0x23202 if case == 'v86' else 0x202
        cr0 = 0x11 if case == 'v86' else 0x10
        u.reg_write(x.UC_X86_REG_EFLAGS, flags)
        u.reg_write(x.UC_X86_REG_CR0, cr0)
        gdtr = (0, 0x900, 0x47, 0)
        u.reg_write(x.UC_X86_REG_GDTR, gdtr)
        u.mem_write(0xFFFFC, b'LOW!')
        u.mem_write(0x500000, b'HIGH')
        u.mem_write(0x500, b'GATE')
        u.mem_write(0x100500, b'TEST')
        registers = dict(BASELINE)
        if fast:
            registers[0x0B]=0x11 if case=='wrong-write' else 4
            if case.endswith('-slow') or case=='refresh-slow-refused':registers[5]=0x9F
            if case=='wrong-refresh':registers[5]=0x9D
        if hidden and case=='timing-wrong-refresh':registers[0x19]=0x10
        if hidden and case=='trial-timing-reserved19':registers[0x19]=8
        if case in ('refresh-wrong-state', 'timing-wrong-state', 'cas1-wrong-state'):
            registers[target] = chosen
        if case in ('trial-reference-128', 'retired-cas1-128', 'trial-timing-128', 'trial-128'):
            registers.update({0x1D: 0xFC, 0x1E: 0x79})
        if case == 'reference-wrong-128-pair':
            registers[0x1D] = 0xFC
        if case == 'reference-wrong-512-pair':
            registers[0x1E] = 0x79
        if case == 'reference-wrong-01':
            registers[1] = 0xBE
        if case == 'reference-wrong-size':
            registers[0x1D] = 0xF8
        if case == 'wrong-cache':
            registers[4] = 0x14
        if case == 'burst-baseline':registers[4]=0x1D
        if case == 'already-tuned':
            registers[0x0B] = 5
        if profile:
            registers.update({5:0x9F,0x0B:4,0x14:6,0x16:0,0x19:8})
            if profile_wrong is not None:registers[profile_wrong]^=1
        original_registers = dict(registers)
        selector, a20, parity = 0xA7, 0xFC, 0x22
        pit_bytes = []
        pit_counter = 0xFFFE
        output, exits, writes = bytearray(), [], []
        injection = []
        restore_retry = []
        counts = {stock: 0, chosen: 0}
        latch_run = 0
        dwells = []
        timed_stores = []

        def input_port(machine, port, size, _):
            assert not (cas1 or dram), 'Withdrawn trial accessed hardware'
            assert size == 1
            if port == 0xF2:
                return selector
            if port == 0xF3:
                value = registers.get(selector, 0)
                if profile_fault is not None and selector==profile_fault:
                    trial={1:0xAF,0x0B:0,0x16:3,0x19:0x28}[selector]
                    if value==trial:return original_registers[selector]
                if not profile and case == 'bad-readback' and selector == 0x0B and value == 5:
                    return 4
                if case in ('cas-readback', 'cas1-readback') and selector == 0x0B and value == chosen:
                    return 0x15
                if case == 'reference-readback' and selector == 1 and value == 0xBE:
                    return 0xBF
                if case in ('refresh-readback', 'timing-readback') and selector == target and value == chosen:
                    return stock
                return value
            if port == 0x78:
                return 0x1D
            if port == 0x92:
                return a20
            if port == 0x61:
                return parity
            assert port == 0x40 and pit_bytes, (port, pit_bytes)
            return pit_bytes.pop(0)

        def output_port(machine, port, size, value, _):
            nonlocal selector, a20, parity, pit_counter, latch_run
            assert not (cas1 or dram), 'Withdrawn trial accessed hardware'
            assert size == 1
            assert not machine.reg_read(x.UC_X86_REG_EFLAGS) & 0x200
            if port == 0xF2:
                selector = value
            elif port == 0xF3:
                if profile and selector in (1,0x16,0x19):
                    assert machine.reg_read(x.UC_X86_REG_CR0)&1
                    normal,trial={1:(0x93,0x83),0x16:(0,3),0x19:(8,0x28)}[selector]
                    assert value in (normal,trial)
                    if value==normal:assert registers[0x0B]==4,'Restore CAS before its extension'
                    if selector==profile_restore and value==normal and registers[selector]!=(normal | (0x2C if selector==1 else 0)) and not restore_retry:
                        restore_retry.append(stock)
                    else:registers[selector]=value | (0x2C if selector==1 else 0)
                    return
                assert selector == target and value in counts
                if profile and value==chosen:
                    assert (registers[1],registers[0x16],registers[0x19])==(0xAF,3,0x28),'Complete profile before short CAS'
                assert machine.reg_read(x.UC_X86_REG_CR0) & 1
                if latch_run > 2:
                    dwells.append((registers[target], latch_run))
                latch_run = 0
                # Simulate one ignored restoration write; no interrupt may escape it.
                if case in ('trial-reference-restore-retry', 'retired-cas1-restore-retry', 'trial-timing-restore-retry', 'trial-restore-retry') and (not profile or profile_restore==target) and value == stock and registers[target] == chosen | readback_or and not restore_retry:
                    restore_retry.append(value)
                else:
                    registers[selector] = value | readback_or
                writes.append(value)
            elif port == 0x80:
                assert value in (0xB0,0xB1,0xB2,0xB3,0xB4,0xBE,0xBF)
                assert registers == original_registers, 'Progress output before stock restoration'
            elif port == 0x92:
                assert value in (0xFC, 0xFE)
                a20 = value
            elif port == 0x61:
                assert value in (0x22, 0x2E)
                parity = value
            elif port == 0x43:
                assert not pit_bytes
                if value == 0xE2:
                    pit_bytes.append(0x34 if case == 'wrong-timer' else 0x36)
                else:
                    assert value == 0
                    current = registers[target] & ~readback_or
                    counts[current] += 1
                    latch_run += 1
                    if writing and case=='data' and current==chosen and counts[current]==2048:
                        machine.mem_write(0x4FFFFC,bytes([machine.mem_read(0x4FFFFC,1)[0]^1]))
                        injection.append(0x4FFFFC)
                    if case in ('refresh-retention','timing-retention') and current == chosen and not injection:
                        machine.mem_write(0x100000, bytes([machine.mem_read(0x100000, 1)[0] ^ 1]))
                        injection.append(0x100000)
                    delta = 0 if case == 'bad-ticks' else 2000 if current == stock else 2400 if cas and not cas1 else 1600
                    pit_counter = (pit_counter - delta) & 0xFFFF
                    pit_bytes.extend((pit_counter & 255, pit_counter >> 8))
            else:
                assert port == 0xED, hex(port)

        def interrupt(machine, number, _):
            ax = machine.reg_read(x.UC_X86_REG_AX)
            assert registers == original_registers, (case, number, registers)
            assert not machine.reg_read(x.UC_X86_REG_CR0) & 1 or case == 'v86'
            if number == 0x2F:
                assert ax == 0x4300
                machine.reg_write(x.UC_X86_REG_AX, 0x4380 if case == 'xms' else 0x4300)
            elif number == 0x15:
                assert ax >> 8 == 0x88
                machine.reg_write(x.UC_X86_REG_AX, 3072 if case == 'little-memory' else 15360)
                machine.reg_write(x.UC_X86_REG_EFLAGS, machine.reg_read(x.UC_X86_REG_EFLAGS) & ~1)
            else:
                assert number == 0x21, (case, hex(number), hex(machine.reg_read(x.UC_X86_REG_IP)))
                assert a20 == 0xFC and parity == 0x22
                assert machine.reg_read(x.UC_X86_REG_GDTR) == gdtr
                assert machine.reg_read(x.UC_X86_REG_EFLAGS) & 0x200
                if ax >> 8 == 0x40:
                    assert machine.reg_read(x.UC_X86_REG_BX) == 1
                    length = machine.reg_read(x.UC_X86_REG_CX)
                    address = (machine.reg_read(x.UC_X86_REG_DS) << 4) + machine.reg_read(x.UC_X86_REG_DX)
                    message = bytes(machine.mem_read(address, length))
                    output.extend(message)
                    machine.reg_write(x.UC_X86_REG_AX, length - (case == 'short-output'))
                    current_flags = machine.reg_read(x.UC_X86_REG_EFLAGS) & ~1
                    trial_output_error = case in ('cas-output', 'cas1-output', 'reference-output', 'refresh-output', 'timing-output') and message.startswith(f'{target:02X}={chosen:02X}'.encode())
                    machine.reg_write(x.UC_X86_REG_EFLAGS, current_flags | (case == 'output-error' or trial_output_error))
                else:
                    assert ax >> 8 == 0x4C
                    exits.append(ax & 255)
                    machine.emu_stop()

        def memory_read(machine, access, address, size, value, _):
            if case == 'bad-a20':
                if not injection and machine.mem_read(0x100500, 4) == b'\xff' * 4:
                    machine.mem_write(0x500, b'\xff' * 4)
                    injection.append(address)
                return
            if registers[target] == chosen | readback_or and not injection:
                assert a20 == 0xFE
                machine.mem_write(address, bytes([machine.mem_read(address, 1)[0] ^ 1]))
                injection.append(address)

        def local_write(machine, access, address, size, value, _):
            # Failure evidence must not be saved while the rejected timing is live.
            if (profile and registers != original_registers) or registers[target] != original_registers[target]:
                raise AssertionError('Diagnostic store before stock timing restoration')
            if not machine.reg_read(x.UC_X86_REG_CR0) & 1:
                return
            ip = machine.reg_read(x.UC_X86_REG_IP)
            instruction = next(decoder.disasm(bytes(machine.mem_read(0x20000 + ip, 15)), ip, count=1))
            # Unicorn does not enforce the 486's code-segment write protection.
            assert 0x2E not in instruction.prefix, f'#GP: write through CS at {instruction.address:04X}'
            if 0x3E in instruction.prefix:
                selector = machine.reg_read(x.UC_X86_REG_DS)
                descriptor = bytes(machine.mem_read(machine.reg_read(x.UC_X86_REG_GDTR)[1] + selector, 8))
                assert descriptor[5] & 0x9A == 0x92, 'Local state needs a present writable data segment'

        def timed_store(machine, access, address, size, value, _):
            if latch_run==1:
                assert writing and size==4 and value==0x5AA55AA5
                timed_stores.append(registers[target])

        u.hook_add(UC_HOOK_INSN, input_port, None, 1, 0, x.UC_X86_INS_IN)
        u.hook_add(UC_HOOK_INSN, output_port, None, 1, 0, x.UC_X86_INS_OUT)
        u.hook_add(UC_HOOK_INTR, interrupt)
        u.hook_add(UC_HOOK_MEM_WRITE, local_write, begin=0x20100, end=0x20100+len(raw)-1)
        # The measurement and recovery windows must not push return addresses.
        u.hook_add(UC_HOOK_MEM_WRITE, local_write, begin=0x2F000, end=0x2FFFF)
        u.hook_add(UC_HOOK_MEM_WRITE, timed_store, begin=0x100000, end=0x100003)
        if case in ('bad-ram', 'cas-ram', 'cas1-ram', 'reference-ram', 'refresh-ram', 'timing-ram'):
            u.hook_add(UC_HOOK_MEM_READ, memory_read, begin=0x100000, end=0x100003)
        elif case == 'bad-a20':
            u.hook_add(UC_HOOK_MEM_READ, memory_read, begin=0x500, end=0x503)
        u.emu_start(0x20100, 0x30000, count=150000000)
        expected = 2 if cas1 or dram else 0 if case.startswith('trial') else 1 if case in ('bad-readback', 'bad-ram', 'bad-a20', 'bad-ticks', 'cas-readback', 'cas1-readback', 'cas-ram', 'cas1-ram', 'reference-readback', 'reference-ram', 'refresh-readback', 'refresh-ram', 'refresh-retention', 'timing-readback', 'timing-ram', 'timing-retention') else 3 if case in ('short-output', 'output-error', 'cas-output', 'cas1-output', 'reference-output', 'refresh-output', 'timing-output') else 2
        if writing and case=='data':expected=1
        assert exits == [expected], (case, exits, output)
        assert registers == original_registers and selector == 0xA7
        assert a20 == 0xFC and parity == 0x22
        assert u.reg_read(x.UC_X86_REG_CR0) == cr0
        assert u.reg_read(x.UC_X86_REG_GDTR) == gdtr
        assert u.mem_read(0xFFFFC, 4) == b'LOW!' and u.mem_read(0x500000, 4) == b'HIGH'
        stock_latches = 2048 + (2 * 1195 if retention else 0)
        trial_latches = 2048 + (2 * 1493 if retention else 0)
        if expected == 0:
            expected_counts = dict.fromkeys(counts, 0)
            expected_counts.update({stock: 2 * stock_latches, chosen: trial_latches})
            assert counts == expected_counts, counts
            lines = output.decode('ascii').splitlines()
            direction='Write' if writing else 'Read '
            baseline_result = f'{target:02X}={stock:02X}  {direction}    18.6 MiB/s  RAM check OK; baseline restored.'
            results = [baseline_result]
            rate = '15.5' if cas and not cas1 else '23.3'
            results += [
                f'{target:02X}={chosen:02X}  {direction}    {rate} MiB/s  RAM check OK; baseline restored.',
                baseline_result]
            assert [line for line in lines if 'MiB/s  RAM check OK' in line] == results, lines
            assert [line for line in lines if line.startswith('Testing ')] == [f'Testing {target:02X}={v:02X}' for v in (stock,chosen,stock)]
            cache_size = 128 if case in ('trial-reference-128', 'retired-cas1-128', 'trial-timing-128', 'trial-128') else 512
            assert f'L2 configuration: {cache_size} KiB.' in lines
            suffix='Combined profile shown above.' if profile else 'Only the selected register changes.'
            assert f'Starting settings: 0B={original_registers[0x0B]:02X} 05={original_registers[5]:02X}. {suffix}' in lines
            assert set(writes) == {stock, chosen}
            if retention:
                assert dwells == [(stock,1195)]*2 + [(chosen,1493)]*2 + [(stock,1195)]*2, dwells
            else:
                assert not dwells
            if case in ('trial-reference-restore-retry', 'retired-cas1-restore-retry', 'trial-timing-restore-retry', 'trial-restore-retry'):
                assert restore_retry == [stock]
            assert timed_stores==([stock]*4+[chosen]*4+[stock]*4 if writing else [])
            if writing:
                for at in (0x100000,0x100004,0x2FFFFC,0x4FFFFC):
                    assert int.from_bytes(u.mem_read(at,4),'little')==0x5AA55AA5
        elif expected == 1:
            assert 'FAILED' in output.decode() and writes[-1] == stock
            expected_stock = 65537 if profile and case=='bad-ticks' else 0 if case=='bad-a20' else stock_latches
            assert counts[stock] == expected_stock and counts[chosen] == (2048 if writing and case=='data' else 1493 if retention and (case in ('refresh-retention', 'refresh-ram', 'timing-retention', 'timing-ram') or (profile and case=='bad-ram')) else 0), counts
            if writing and case=='data':
                assert injection==[0x4FFFFC]
                assert 'FAILED at 0B=05: RAM mismatch at 004FFFFC' in output.decode()
                assert 'Expected 5AA55AA5, read 5AA55AA4.' in output.decode()
            elif case in ('bad-ram', 'cas-ram', 'cas1-ram', 'reference-ram', 'refresh-ram', 'refresh-retention', 'timing-ram', 'timing-retention'):
                assert injection == [0x100000]
                expected_word = 0x100000 ^ 0xA55AA55A
                assert f'FAILED at {target:02X}={chosen:02X}: RAM mismatch at 00100000' in output.decode()
                assert f'Expected {expected_word:08X}, read {expected_word ^ 1:08X}.' in output.decode()
            elif case == 'bad-a20':
                assert injection == [0x500] and writes == [stock]
                assert f'FAILED at 0B={stock:02X}: A20 address check.' in output.decode()
                assert u.mem_read(0x500, 4) == b'GATE'
                assert u.mem_read(0x100500, 4) == b'TEST'
                assert u.mem_read(0x100000, 4) == bytes(4)
            elif case == 'bad-ticks':
                assert f'FAILED at 0B={stock:02X}: timer did not advance.' in output.decode()
            elif profile_fault is not None:
                wanted={1:0xAF,0x0B:0,0x16:3,0x19:0x28}[profile_fault]
                actual=original_registers[profile_fault]
                assert f'register {profile_fault:02X} readback; wanted {wanted:02X}, read {actual:02X}.' in output.decode()
                assert counts[chosen]==0
                if profile_fault!=0x0B:assert chosen not in writes,'Rejected prerequisite reached shorter CAS'
            else:
                actual = 4 if case == 'bad-readback' else stock | readback_or
                assert f'FAILED at {target:02X}={chosen:02X}: register readback; wanted {chosen | readback_or:02X}, read {actual:02X}.' in output.decode()
        elif expected == 3 and case in ('cas-output', 'cas1-output', 'reference-output', 'refresh-output', 'timing-output'):
            assert counts[stock] == stock_latches and counts[chosen] == trial_latches
            assert set(writes) == {stock, chosen} and writes[-1] == stock
        else:
            assert not writes
        if cas1 and case != 'cas1-bad-choice':
            assert 'C1 withdrawn after hardware failure.' in output.decode()
        if dram:
            assert 'D withdrawn after hardware lock.' in output.decode()
        if hidden and case=='timing-wrong-refresh':
            assert 'H refused: register19=10.' in output.decode()
        rows.append({'case': label, 'exit': expected, 'timing_writes': len(writes), 'read_latches': counts})
        print(f'{label}: PASS', flush=True)
    return rows


def main():
    output = PORT / 'build/diagnostics'
    output.mkdir(parents=True, exist_ok=True)
    nasm = shutil.which('nasm') or str(Path(os.environ['LOCALAPPDATA']) / 'bin/NASM/nasm.exe')
    image = output / 'ACCPROBE.COM'
    subprocess.run([nasm, '-w+error', '-f', 'bin', '-o', str(image), str(PORT / 'diagnostics/acc-timing.asm')], check=True)
    raw = image.read_bytes()
    tests = check(raw)
    # Exercise the escaped CPU fault on both the normal and failure paths.
    decoder = Cs(CS_ARCH_X86, CS_MODE_16)
    decoder.detail = True
    local_stores = [i for i in decoder.disasm(raw, 0x100) if 0x3E in i.prefix]
    assert local_stores[0].mnemonic == 'add' and local_stores[-1].mnemonic == 'mov'
    for instruction, case in zip((local_stores[0], local_stores[-1]), ('trial05', 'bad-readback')):
        broken = bytearray(raw)
        offset = instruction.address - 0x100
        assert broken[offset] == 0x3E
        broken[offset] = 0x2E
        try:
            check(bytes(broken), (case,))
        except AssertionError as error:
            assert str(error).startswith('#GP: write through CS'), error
        else:
            raise AssertionError(f'Code-segment write escaped on {case}')
        tests.append({'case': 'reject-cs-write-' + case, 'result': 'PASS'})
        print(f'reject-cs-write-{case}: PASS', flush=True)
    result = {'path': str(image), 'size': len(raw), 'sum32': f'{sum(raw):08X}',
              'sha256': hashlib.sha256(raw).hexdigest(), 'checks': tests,
              'scope': 'Synthetic machine-code/device checks, not physical timing or stability proof.'}
    (output / 'acc-timing-checks.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(f'{image}: {len(raw)} bytes, SUM32 {result["sum32"]}')


if __name__ == '__main__':
    main()
