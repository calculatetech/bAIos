"""Run Intel ICU's ROM scan and EMM386's reservation scan on the actual E bank."""
from pathlib import Path
import hashlib
import importlib.util
import json
import struct
import sys

from unicorn import Uc, UC_ARCH_X86, UC_MODE_16, UC_HOOK_CODE
from unicorn import x86_const as x

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
spec = importlib.util.spec_from_file_location('pci_calls', Path(__file__).with_name('test-pci-call-state.py'))
pci = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pci)


def intel_scan(image, legacy=False):
    pci.pnp.OUTPUT = 'build'
    caller = pci.Caller()
    cpu = caller.cpu
    cpu.mem_write(0xC0000, b'\xFF' * 0x20000)
    cpu.mem_write(0xE0000, image)
    if legacy:
        cpu.mem_write(0xE0002, b'\x80')
    driver = (ROOT / 'tools/deps/intel-pnp/extracted/DWCFGMG.SYS').read_bytes()
    assert hashlib.sha256(driver).hexdigest() == 'f779a54de16ac2ede65c062297b3b743b1920af5eb848182920d9f7f182083fc'
    cpu.mem_write(0x20000, driver)
    cpu.mem_write(0x203FA, struct.pack('<H', 8))
    caller.read_value = 0x673A1060
    stub = bytearray()
    for value in (0x5000, 0x200, 0x91, 0):
        stub += b'\x68' + struct.pack('<H', value)
    stub += b'\xE8' + struct.pack('<H', (0xCC48 - (0xFE00 + len(stub) + 3)) & 65535)
    stub += b'\x83\xC4\x08\xF4'
    cpu.mem_write(0x2FE00, bytes(stub))
    cpu.ctl_remove_cache(0x20000, 0x2FFFF)
    for name, value in dict(CS=0x2000, DS=0x2000, ES=0x5000, SS=0x3000,
                            ESP=0x7000, EFLAGS=0x202).items():
        cpu.reg_write(getattr(x, 'UC_X86_REG_' + name), value)
    scans, completed = [], []

    def checkpoint(cpu, address, size, unused):
        if address == 0x2CC90:
            bp = cpu.reg_read(x.UC_X86_REG_BP)
            scans.append(int.from_bytes(cpu.mem_read(0x30000 + bp - 0x36, 4), 'little'))
            if scans[-3:] == [0xE0000] * 3:
                cpu.emu_stop()
        if address == 0x2FE00 + len(stub) - 1:
            completed.append(True)
            cpu.emu_stop()

    cpu.hook_add(UC_HOOK_CODE, checkpoint)
    cpu.emu_start(0x2FE00, 0x30000, count=300000)
    if legacy:
        assert not completed and scans[-3:] == [0xE0000] * 3
    else:
        assert completed and scans[-3:] == [0xE0000, 0xE0800, 0xF0000], scans
        assert cpu.reg_read(x.UC_X86_REG_AX) == cpu.reg_read(x.UC_X86_REG_DX) == 0
    return {'completed': bool(completed), 'scan_tail': [f'{v:05X}' for v in scans[-3:]]}


def emm_scan(image):
    driver = (ROOT / 'tools/deps/ms-dos/EMM386.EXE').read_bytes()
    assert hashlib.sha256(driver).hexdigest() == 'd4a011769db9415402d7be129fffb762fa7d174096bcc921aa5ce85734072635'
    cpu = Uc(UC_ARCH_X86, UC_MODE_16)
    cpu.mem_map(0, 0x200000)
    cpu.mem_write(0x20000, driver[0x11657:0x116A2])
    cpu.mem_write(0xE0000, image)
    reached = []
    cpu.hook_add(UC_HOOK_CODE, lambda u, a, z, _: (reached.append(True), u.emu_stop()),
                 None, 0x20200, 0x20200)
    claims = []
    for segment, end, paragraphs in ((0xE000, 0xE080, 0x80), (0xE080, 0xF000, 0xF80)):
        for name, value in dict(CS=0x2000, SS=0x3000, SP=0x7000, AX=segment, EFLAGS=0x202).items():
            cpu.reg_write(getattr(x, 'UC_X86_REG_' + name), value)
        cpu.mem_write(0x37000, struct.pack('<H', 0x200))
        reached.clear()
        cpu.emu_start(0x20000, 0x30000, count=400000)
        assert reached and cpu.reg_read(x.UC_X86_REG_EFLAGS) & 1
        assert cpu.reg_read(x.UC_X86_REG_AX) == end
        assert cpu.reg_read(x.UC_X86_REG_DX) == paragraphs
        claims.append(f'{segment:04X}-{end:04X}')
    return claims


def main():
    raw = (ROOT / 'm919/build/baios-m919.bin').read_bytes()[:65536]
    result = {'old_64K_header': intel_scan(raw, legacy=True), 'visible_images': {}}
    for name in ('factory-cold', 'persisted-cold', 'persisted-warm'):
        image = (ROOT / f'm919/build/tests/video-first/{name}-visible-E.bin').read_bytes()
        result['visible_images'][name] = {'Intel': intel_scan(image), 'EMM386_claims': emm_scan(image)}
    result['limit'] = 'Exact vendor routines in a CPU fixture; physical driver boot still needs confirmation.'
    output = ROOT / 'm919/build/tests/icu-rom-scan'
    output.mkdir(parents=True, exist_ok=True)
    (output / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
