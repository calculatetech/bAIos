"""Check board-selected definitions and calculated choices through real Setup."""
import argparse
import importlib
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import tempfile

from unicorn import UC_HOOK_CODE
from unicorn import x86_const as x

chip = importlib.import_module('test-chipset')
setup = chip.setup
ROOT, BUILD = chip.ROOT, chip.BUILD
ENTER_CHIPSET = [0x50] * 4 + [28]
DISCARD = [1, 1, 1, 28]
# Independent logical-color expectations from the approved nine-theme contract.
COLORS = {
    7: (7, 0x1F, 0x70, 0x1F, 0x1F, 0x57, 0x0E, 0x0F, 0x0E),
    8: (8, 0x18, 0x78, 0x18, 0x18, 0x58, 8, 8, 8),
    0x17: (0x17, 0x1F, 0x70, 0x1F, 0x1F, 0x67, 0x0E, 0x0F, 0x1E),
    0x1F: (0x1F, 0xE1, 0x1F, 0x5F, 0x30, 0x70, 0xE0, 0x70, 0x30),
    0x70: (0x70, 0xE1, 0x1F, 0x5F, 0x30, 0x70, 0xE0, 0x70, 0x30),
}


def expected(kind, index):
    # These rules describe the approved table strings, not candidate requests.
    if kind == 0:
        return f'{index << 16:06X}-{(index << 16) | 65535:06X}'
    if index < 32:
        return f'{index * 0x80000:07X} / 512 KB'
    if index < 48:
        return f'{(index - 32) * 0x800000:07X} / 8 MB'
    return f'{0xC0000 + (index - 48) * 0x4000:05X} / 16 KB'


def field_keys(field):
    return ENTER_CHIPSET + [0x50] * 3 + [28] + [0x50] * field


def numeric():
    for field, offset, kind, count, row in ((8, 7, 0, 256, 15), (9, 17, 1, 64, 5)):
        m = chip.Chipset()
        seen_page, seen_popup, pages = set(), set(), set()

        def observe(model):
            if model.cpu.mem_read(model.base + 0x278, 1) != b'\x04':
                return
            if model.cpu.mem_read(model.base + 0xF7, 1)[0] != field:
                return
            if model.text(8, 26, 12) == 'SELECT VALUE':
                selected = model.cpu.mem_read(model.base + 0x279, 1)[0]
                first = selected // 12 * 12
                pages.add(first // 12)
                for index in range(first, min(first + 12, count)):
                    text = expected(kind, index)
                    popup_row = 10 + index - first
                    assert model.text(popup_row, 26, len(text)) == text
                    attr = 0x70 if index == selected else 0x17
                    cells = bytes(model.cpu.mem_read(0xB8000 + popup_row * 160 + 26 * 2, len(text) * 2))
                    assert cells[1::2] == bytes([attr]) * len(text)
                    assert model.text(popup_row, 26 + len(text), 1) == ' '
                    seen_popup.add(index)
                # Final partial pages must retain empty rows below the collection.
                for blank in range(min(12, count - first), 12):
                    assert model.text(10 + blank, 26, 28) == ' ' * 28
            elif model.cpu.mem_read(model.base + 0xF6, 1) == b'\x01':
                index = model.record(True)[offset] & (255 if kind == 0 else 63)
                text = expected(kind, index)
                assert model.text(row, 49, 28) == text.ljust(28), (kind, index, model.text(row, 49, 28))
                cells = bytes(model.cpu.mem_read(0xB8000 + row * 160 + 49 * 2, 56))
                assert cells[1::2] == b'\x1f' * 28
                assert model.text(row, 48, 1) == ' ' and model.text(row, 77, 1) == ' '
                seen_page.add(index)

        m.observer = observe
        # Page changes commit immediately to the draft; popup changes are pending.
        m.open(field_keys(field) + [0x4D] * count + [28] + [0x50] * (count - 1) + [1] + DISCARD)
        assert seen_page == set(range(count)), (kind, 'page', seen_page)
        assert seen_popup == set(range(count)), (kind, 'popup', seen_popup)
        assert pages == set(range((count + 11) // 12))
        assert m.record(True)[offset] == 0, 'Cancel must preserve the page-selected draft'
    print('PASS real Setup -> both consumers, all 320 numeric choices, family transitions and final partial pages', flush=True)

    # Color contrasts use real Setup, with the same data and both actual consumers.
    for theme in range(9):
        m = chip.Chipset()
        states = set()

        def cells(model, row, col, text, logical, width=None):
            width = width or len(text)
            assert model.text(row, col, width) == text.ljust(width)
            actual = bytes(model.cpu.mem_read(0xB8000 + row * 160 + col * 2, width * 2))
            assert actual[1::2] == bytes([COLORS[logical][theme]]) * width, (theme, row, col, logical, actual)

        def colored(model):
            if model.cpu.mem_read(model.base + 0x278, 1) != b'\x04':
                return
            field = model.cpu.mem_read(model.base + 0xF7, 1)[0]
            popup = model.text(8, 26, 12) == 'SELECT VALUE'
            if popup and field == 8:
                index = model.cpu.mem_read(model.base + 0x279, 1)[0]
                row = 10 + index % 12
                cells(model, row, 25, ' ' + expected(0, index), 0x70, 52)
                normal = 0 if index != 0 else 1
                cells(model, 10 + normal, 26, expected(0, normal), 0x17)
                assert model.text(row, 23, 1) == model.text(row, 78, 1) == ' '
                states.update(('popup-selected', 'popup-normal', 'popup-padding'))
            elif not popup and field in (7, 8) and model.cpu.mem_read(model.base + 0xF6, 1) == b'\x01':
                index = model.record(True)[7]
                logical = 0x1F if field == 8 else 7
                cells(model, 15, 49, expected(0, index), logical, 28)
                assert model.text(15, 48, 1) == model.text(15, 77, 1) == ' '
                states.add('page-selected' if field == 8 else 'page-normal')

        m.observer = colored
        m.open([0x3F] * theme + field_keys(8) + [0x4D, 0x48, 0x50, 28, 0x50, 1] + DISCARD)
        assert states == {'page-normal', 'page-selected', 'popup-normal', 'popup-selected', 'popup-padding'}, (theme, states)

        m = chip.Chipset()
        states = set()

        def ordinary(model):
            if model.cpu.mem_read(model.base + 0x278, 1) != b'\x01':
                return
            field = model.cpu.mem_read(model.base + 0xF7, 1)[0]
            popup = model.text(8, 26, 12) == 'SELECT VALUE'
            if popup and field == 0:
                selected = model.cpu.reg_read(x.UC_X86_REG_BP)
                for index, text in enumerate(('25 MHz', '33 MHz')):
                    if index == selected:
                        cells(model, 10 + index, 25, ' ' + text, 0x70, 52)
                        assert model.text(10 + index, 23, 1) == model.text(10 + index, 78, 1) == ' '
                    else:
                        cells(model, 10 + index, 26, text, 0x17)
                states.add(f'ordinary-popup-{selected}')
            elif not popup and field in (0, 1):
                text = '33 MHz' if model.record(True)[23] & 2 else '25 MHz'
                cells(model, 5, 49, text, 0x1F if field == 0 else 7, 28)
                states.add('ordinary-selected' if field == 0 else 'ordinary-normal')
                # Normal profile locks access timings; both labels and values gray.
                for row in (10, 11, 12, 13, 14):
                    for col, width in ((24, 24), (49, 28)):
                        label = model.text(row, col, width).rstrip()
                        assert label
                        cells(model, row, col, label, 8)
                states.add('ordinary-locked')

        m.observer = ordinary
        m.open([0x3F] * theme + ENTER_CHIPSET + [28, 0x50, 0x48, 28, 0x48, 0x50, 1] + DISCARD)
        assert states == {'ordinary-normal', 'ordinary-selected', 'ordinary-popup-0', 'ordinary-popup-1', 'ordinary-locked'}, (theme, states)
    print('PASS real numeric/ordinary page and popup normal/selected colors, locked timing labels/values and selection padding in all nine themes', flush=True)


def abi():
    m = chip.Chipset(segment=0x97C0)
    m.cpu.mem_write(m.base + 0x278, b'\x01')
    m.cpu.mem_write(m.base + 0xF7, b'\x00')
    m.call('chipset_ui_descriptor')
    descriptor = m.cpu.reg_read(x.UC_X86_REG_SI)
    ordinary = struct.unpack('<H', m.cpu.mem_read(0xF0000 + descriptor + 7, 2))[0]
    inputs_to_check = [(kind, index, expected(kind, index)) for kind, index in
                       ((0, 0), (0, 255), (1, 31), (1, 32), (1, 47), (1, 48), (1, 63))]
    inputs_to_check += [(ordinary, 0, '25 MHz'), (ordinary, 1, '33 MHz')]
    for theme in range(9):
        m.cpu.mem_write(m.base + 0xFC, bytes((theme, 1)))
        for kind, index, text in inputs_to_check:
            for logical in COLORS:
                destination = 10 * 160 + 26 * 2
                m.cpu.mem_write(0xB8000 + destination - 2, b'X\x6d' * 30)
                inputs = {'EAX': 0xABCD0000 | index, 'EBX': 0xA1B20031 | (logical << 8),
                          'ECX': 0x12345678, 'EDX': 0x67891234, 'ESI': 0xCDEF0000 | kind,
                          'EDI': 0xBABE0000 | destination, 'EBP': 0x42345678,
                          'DS': 0xF000, 'ES': 0xB800, 'GS': 0x7A00}

                def seed(cpu, address, size, unused):
                    for name, value in inputs.items():
                        cpu.reg_write(getattr(x, 'UC_X86_REG_' + name), value)

                address = 0xF0000 + setup.rtc.symbol('chipset_ui_option_text')
                hook = m.cpu.hook_add(UC_HOOK_CODE, seed, None, address, address)
                try:
                    m.call('chipset_ui_option_text')
                finally:
                    m.cpu.hook_del(hook)
                assert all(m.cpu.reg_read(getattr(x, 'UC_X86_REG_' + name)) == value for name, value in inputs.items())
                assert m.cpu.reg_read(x.UC_X86_REG_FS) == m.segment
                assert m.text(10, 26, len(text)) == text
                actual = bytes(m.cpu.mem_read(0xB8000 + destination, len(text) * 2))
                assert actual[1::2] == bytes([COLORS[logical][theme]]) * len(text)
                assert m.cpu.mem_read(0xB8000 + destination - 2, 2) == b'X\x6d'
                assert m.cpu.mem_read(0xB8000 + destination + len(text) * 2, 2) == b'X\x6d'
    print('PASS relocated caller ABI, all colors, boundary values, and untouched neighboring cells', flush=True)


def saves():
    for field, offset, index, register in ((8, 7, 255, 0x0B), (9, 17, 63, 0x20), (19, 19, 32, 0x22)):
        m = chip.Chipset()
        initial = bytearray(m.record())
        initial[17], initial[19] = 0x41, 0x42
        initial[18] = initial[20] = 0  # Both ISA mappings stay disabled.
        m.draft(initial)
        m.call('chipset_settings_save')
        m.call('chipset_settings_load')  # POST loads saved policy before entering Setup.
        before = bytes(m.cmos)
        # Cancel one changed pending selection, reopen it, then choose a value.
        current = initial[offset] & (255 if offset == 7 else 63)
        m.open(field_keys(field) + [28, 0x50, 1, 28] + [0x50] * (index - current) + [28, 0x44, 28])
        assert m.warm and bytes(m.cmos) != before
        selected = bytearray(initial)
        selected[offset] = index | (initial[offset] & (0 if offset == 7 else 0x40))
        assert m.record(True) == selected
        m.startup(through_gate=True, expected_record=bytes(selected))
        assert m.record() == selected
        assert m.chipset[register] == selected[offset], (field, m.chipset[register], selected[offset])
        other = 19 if offset == 17 else 17
        assert m.record()[other] == initial[other]
        # Independent CMOS indices: offset7->72h, offset17->7Ch, offset19->7Eh.
        assert m.cmos[0x6B + offset] == selected[offset]
    print('PASS numeric popup Cancel/Apply -> actual F10 warm restart -> startup/load/application; both window identities and bit6 retained', flush=True)


def integration():
    work = BUILD / 'tmp'
    work.mkdir(parents=True, exist_ok=True)
    nasm = shutil.which('nasm') or str(Path(os.environ['LOCALAPPDATA']) / 'bin/NASM/nasm.exe')
    source = ROOT / 'src'
    with tempfile.TemporaryDirectory(prefix='modular-definitions-', dir=work) as name:
        directory = Path(name)
        assert directory.resolve().is_relative_to(BUILD.resolve())

        def assemble(board):
            subprocess.run([nasm, '-D', 'VGA_BIOS_141', '-D', f'BOARD_DEFINITION="{board}"',
                            '-f', 'bin', '-I', str(source.resolve()) + '/', '-l', str(directory / 'baios-presario800-system.lst'),
                            '-o', str(directory / 'baios-presario800-system.rom'), str(source / 'bios.asm')], check=True)
            binary = bytearray((directory / 'baios-presario800-system.rom').read_bytes())
            binary[-1] = -sum(binary[:-1]) & 255
            (directory / 'baios-presario800-system.rom').write_bytes(binary)
            return bytes(binary)

        assert assemble('boards/presario800.inc') == (BUILD / 'baios-presario800-system.rom').read_bytes()
        data = (source / 'chipsets/vl82c481/setup-data.inc').read_text()
        data = data.replace('chip_fields_end:', '    chipset_field fixture_name,7,0,255,128,CHIP_VALUES_FAST_REGION,uc_138,uc_139\nchip_fields_end:', 1)
        data = data.replace('    db 9,4\n    dw chip_rows_12,chip_headers_12', '    db 9,5\n    dw chip_rows_12,chip_headers_12', 1)
        data = data.replace('chip_rows_12 db 5,6,7,8', 'chip_rows_12 db 5,6,7,8,9', 1)
        data += "\nfixture_name db 'Fixture Range',0\n"
        (directory / 'setup-data.inc').write_text(data)
        board = (source / 'boards/presario800.inc').read_text().replace('"chipsets/vl82c481/setup-data.inc"', f'"{(directory / "setup-data.inc").as_posix()}"')
        board = board.replace("'Compaq Presario 800'", "'Fixture Board'")
        (directory / 'board.inc').write_text(board)
        assemble((directory / 'board.inc').as_posix())
        previous = setup.rtc.BUILD
        setup.rtc.BUILD = directory
        try:
            m = chip.Chipset()
            observed = set()

            def observe(model):
                if model.cpu.mem_read(model.base + 0x278, 1) == b'\x06':
                    observed.add(model.cpu.mem_read(model.base + 0xF7, 1)[0])
                    if model.cpu.mem_read(model.base + 0xF7, 1) == b'\x0d':
                        assert model.text(9, 24, 13) == 'Fixture Range'

            m.observer = observe
            m.open(ENTER_CHIPSET + [0x50] * 5 + [28] + [0x50] * 13 + [0x4D] * 127 + [0x44, 28])
            assert observed == set(range(14)), observed
            assert m.warm and m.record(True)[7] == 127
            selected = m.record(True)
            assert m.cmos[0x72] == 127 and m.cmos[0x69] == 0xC2
            m.startup(through_gate=True, expected_record=selected)
            assert m.record() == selected
            # Seed independent checksum-valid records and exercise the real loader.
            for value in (127, 128):
                loaded = chip.Chipset()
                record = bytearray(selected)
                record[7] = value
                indices = list(range(0x6B, 0x80)) + [0x33, 0x34, 0x35]
                for index, byte in zip(indices, record):
                    loaded.cmos[index] = byte
                loaded.cmos[0x69] = 0xC2
                loaded.cmos[0x6A] = -(0xC2 + sum(record)) & 255
                before = bytes(loaded.cmos)
                loaded.call('chipset_settings_load')
                assert bytes(loaded.cmos) == before, 'Loading must not rewrite persisted bytes'
                if value == 127:
                    assert loaded.record() == record
                else:
                    assert loaded.record() == chip.NORMAL, loaded.record().hex()
            m.draft(selected)  # Startup clears the UI draft; seed the separate component probe.
            m.cpu.reg_write(x.UC_X86_REG_SI, 0x260)
            m.call('chipset_valid')
            assert not m.cpu.reg_read(x.UC_X86_REG_EFLAGS) & 1
            m.cpu.mem_write(m.base + 0x267, b'\x80')
            m.cpu.reg_write(x.UC_X86_REG_SI, 0x260)
            m.call('chipset_valid')
            assert m.cpu.reg_read(x.UC_X86_REG_EFLAGS) & 1, '104th field must participate in persisted range validation'
            start, end = setup.rtc.symbol('chip_group_0'), setup.rtc.symbol('chip_fields_end')
            assert (end - start) // 14 == 104
            assert m.text(0, 3, 13) == 'Fixture Board'
        finally:
            setup.rtc.BUILD = previous
    print('PASS explicit equivalent board and synthetic data-only 104th field: navigation, identity and late selector validation', flush=True)


def budget():
    listing = (BUILD / 'baios-presario800-system.lst').read_text().splitlines()
    start = next(i for i, line in enumerate(listing) if line.rstrip().endswith('rom_code_end:'))
    used = next(int(m[1], 16) for line in listing[start + 1:] if (m := re.match(r'\s*\d+\s+([0-9A-F]{8})\s+', line)))
    rom = (BUILD / 'baios-presario800-system.rom').read_bytes()
    assert len(rom) == 65536 and sum(rom) & 255 == 0
    assert used < 60286
    assert rom[used:0xF065] == b'\xff' * (0xF065 - used)
    assert rom[0xF070:0xFFF0] == b'\xff' * (0xFFF0 - 0xF070)
    print(f'PASS occupancy {used} bytes; saved {60286-used}; available {0xF065-used+3968}', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    cases = {'numeric': numeric, 'abi': abi, 'save': saves, 'integration': integration, 'budget': budget}
    parser.add_argument('--case', choices=cases, action='append')
    args = parser.parse_args()
    for name in args.case or cases:
        cases[name]()
