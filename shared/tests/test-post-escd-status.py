"""Exercise resident notices and the returning console's real scroll tracking."""
import importlib.util
import json
from pathlib import Path
import struct
import sys

from unicorn import UC_HOOK_INTR
from unicorn import x86_const as x

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
spec = importlib.util.spec_from_file_location('pnp_escd_screen', Path(__file__).with_name('test-pnp.py'))
pnp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pnp)


def composed():
    """Real Summary/table/finalization, with only the external VGA/flash modeled."""
    from shared.tools.isa_pnp_proof import Bus, Card, serial
    spec = importlib.util.spec_from_file_location('escd_screen_flash', Path(__file__).with_name('test-escd.py'))
    escd = importlib.util.module_from_spec(spec);spec.loader.exec_module(escd)
    results = []
    for count, storage_failure in ((1, False), (8, False), (24, False), (1, True)):
        fixed = lambda base, size: b'\x4B' + struct.pack('<HB', base, size)
        device = b'\x15\x16\x73\x18\x68\0'
        resources = fixed(0x220, 16) + fixed(0x388, 4) + fixed(0x330, 2) + fixed(0x340, 2)
        stream = b'\x0A\x10\0\x82\x03\0ISA' + device + resources + device * (count-1)
        stream += b'\x79\0'
        card = Card(serial(b'\x41\xD0\xFF\xFF', 1), stream, ldns=count)

        class Screen(escd.Flash):
            def interrupt(self, cpu, vector, unused):
                if vector != 0x10:return super().interrupt(cpu, vector, unused)
                ax = cpu.reg_read(x.UC_X86_REG_AX)
                row, col = cpu.mem_read(0x451, 1)[0], cpu.mem_read(0x450, 1)[0]
                if ax >> 8 == 2:
                    row, col = cpu.reg_read(x.UC_X86_REG_DH), cpu.reg_read(x.UC_X86_REG_DL)
                elif ax >> 8 == 3:
                    cpu.reg_write(x.UC_X86_REG_DX, row << 8 | col)
                elif ax >> 8 == 0x0E:
                    char = ax & 255
                    if char == 13:col = 0
                    elif char == 10:row += 1
                    elif char == 8:col = max(0, col-1)
                    elif char != 7:
                        cpu.mem_write(0xB8000 + (row*80+col)*2, bytes((char, 7)))
                        col += 1
                        if col == 80:self.wraps += 1;col = 0;row += 1
                    if row == 25:
                        cpu.mem_write(0xB8000, bytes(cpu.mem_read(0xB80A0, 3840)) + b' \x07'*80)
                        self.scrolls += 1;row = 24
                cpu.mem_write(0x450, bytes((col, row)))

        m = Screen();m.listing.symbol = pnp.cache(m.listing.symbol)
        m.isa = Bus([card]);m.isa.pause = False
        m.wraps = m.scrolls = 0
        m.call('setup_defaults');m.draft()
        m.put('U_PNP', bytes(14)+b'\1');m.put('U_POST_DELAY', b'\0')
        assert m.call('settings_save');m.call('settings_load')
        if storage_failure:m.fail = ('cmos', 0x35)
        m.cpu.mem_write(0x413, struct.pack('<H', m.base >> 10))
        m.call('pnp_publish');assert m.call('pnp_module_install')
        m.call('pnp_post_invoke', BX=m.listing.symbol('pnp_prepare_video'))
        m.call('pnp_configure_isa')
        notices = [];pending = []
        at = 0xF0000 + m.listing.symbol('post_status')
        table = m.listing.symbol('pnp_post_table')
        invoke = 0xF0000 + m.listing.symbol('pnp_post_invoke')
        table_seen = []

        def observe(cpu, address, size, unused):
            if pending and address == pending[0][0]:
                _, before, row, notice = pending.pop()
                after = bytes(cpu.mem_read(0xB8000, 4000))
                if row == 255:assert after == before
                else:
                    start = (row-1)*160 if row else 22*160
                    assert after[:start] == before[:start] and after[start+160:] == before[start+160:]
                notices.append((notice, row))
            if address == invoke and cpu.reg_read(x.UC_X86_REG_BX) == table:table_seen.append(True)
            if address == at:
                notice = cpu.reg_read(x.UC_X86_REG_AL)
                if notice < 10:return
                row = cpu.mem_read((cpu.reg_read(x.UC_X86_REG_FS) << 4)+0x30F, 1)[0]
                sp = (cpu.reg_read(x.UC_X86_REG_SS) << 4)+cpu.reg_read(x.UC_X86_REG_SP)
                target = 0xF0000+int.from_bytes(cpu.mem_read(sp, 2), 'little')
                if notice > 10:assert table_seen, 'Late notice preceded real table'
                pending.append((target, bytes(cpu.mem_read(0xB8000, 4000)), row, notice))

        hook = m.cpu.hook_add(pnp.UC_HOOK_CODE, observe)
        m.cpu.ctl_flush_tb()
        try:m.call('pnp_publish_finish')
        finally:m.cpu.hook_del(hook)
        assert not pending and table_seen, (pending, table_seen, notices)
        m.base = int.from_bytes(m.cpu.mem_read(0x40E, 2), 'little') << 4
        assert [notice for notice, _ in notices] == ([10, 11, 13] if storage_failure else [10, 11, 12]), notices
        assert m.get('C_PNP', 15)[14] == int(storage_failure)
        text = bytes(m.cpu.mem_read(0xB8000, 4000))[::2]
        if count == 1:
            assert b'ISA PnP' in text and b'ESCD' in text
            assert m.wraps and b'IO 0220-022F' in text
        elif count == 8:assert m.scrolls and 1 < notices[-1][1] < 15
        else:assert m.scrolls and notices[-1][1] == 255
        results.append(dict(devices=count, storage_failure=storage_failure, notices=notices,
                            wraps=m.wraps, scrolls=m.scrolls, real_table_finish=True,
                            device_rows_preserved=True, pending_clear=int(storage_failure)))
    return results


def main():
    m = pnp.settings.Settings('m919', 'build')
    m.call('settings_load')
    table_entry = 0xF0000 + m.listing.symbol('.table', 'pnp_publish_finish')
    # Observe the actual notice before the unchanged private table consumes it.
    def before_table(cpu, address, size, unused):
        cpu.reg_write(x.UC_X86_REG_IP, 0xFFFF)
    table_hook = m.cpu.hook_add(pnp.UC_HOOK_CODE, before_table, None, table_entry, table_entry)
    try:
        for pending in (0, 1):
            m.put('C_POST_DELAY', b'\0')
            policy = bytearray(15);policy[14] = pending;m.put('C_PNP', policy)
            m.call('pnp_publish_finish')
            assert m.cpu.mem_read(m.base + 0x30F, 1)[0] == (15 if pending else 0)
            if pending:
                row = bytes(m.cpu.mem_read(0xB8000 + 14*160, 160))[::2]
                assert b'ESCD' in row
    finally:
        m.cpu.hook_del(table_hook)
    cells = b'X\x07' * 2000
    row_state = m.base + 0x30F
    for notice in (10, 11, 12, 13):
        for row in (14, 11, 0):
            m.cpu.mem_write(0xB8000, cells)
            m.cpu.mem_write(row_state, bytes((row + 1,)))
            m.call('post_status', AX=notice)
            actual = bytes(m.cpu.mem_read(0xB8000, 4000))
            assert actual[:row*160] == cells[:row*160]
            assert actual[(row+1)*160:] == cells[(row+1)*160:]
            text = actual[row*160:(row+1)*160:2].decode('ascii')
            assert 'ESCD' in text and 'XXX' not in text, (notice, row, text)
    m.cpu.mem_write(0xB8000, cells)
    m.cpu.mem_write(row_state, b'\xFF')
    m.call('post_status', AX=12)
    assert bytes(m.cpu.mem_read(0xB8000, 4000)) == cells
    # Enter through a real far CALL and return after the firmware's INT 10h.
    callback = m.listing.symbol('pnp_console_callback')
    m.cpu.mem_write(0x90000, b'\x9A' + struct.pack('<HH', callback, 0xF000))
    interrupts = []

    def interrupt(cpu, number, unused):
        assert number == 0x10
        interrupts.append((cpu.reg_read(x.UC_X86_REG_AX), cpu.reg_read(x.UC_X86_REG_BX)))

    hook = m.cpu.hook_add(UC_HOOK_INTR, interrupt)
    try:
        for cursor, char, before, after in ((0x1800, 10, 15, 14), (0x174F, 10, 15, 15),
                                          (0x184F, 65, 15, 14), (0x184F, 13, 15, 15),
                                          (0x1800, 10, 1, 255), (0x1800, 10, 255, 255),
                                          (0x1800, 10, 0, 0)):
            m.cpu.mem_write(0x450, struct.pack('<H', cursor))
            m.cpu.mem_write(row_state, bytes((before,)))
            for name, value in dict(CS=0x9000, IP=0, SS=0, SP=0x7000, AX=0x0E00+char,
                                    BX=7, FS=m.base>>4, EFLAGS=0x202).items():
                m.cpu.reg_write(getattr(x, 'UC_X86_REG_'+name), value)
            m.cpu.emu_start(0x90000, 0x90005, count=1000)
            assert m.cpu.mem_read(row_state, 1)[0] == after, (cursor, char, before, after)
            assert interrupts[-1] == (0x0E00+char, 7)
            assert m.cpu.reg_read(x.UC_X86_REG_SP) == 0x7000
    finally:
        m.cpu.hook_del(hook)
    print(json.dumps(composed(), indent=2))
    print('PASS ESCD success/failure notices preserve all device rows; scroll, wrap and far return')


if __name__ == '__main__':
    main()
