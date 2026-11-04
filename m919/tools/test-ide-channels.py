"""Exercise the saved channel switch, hardware decode and shared Setup owner."""
import argparse
import json
from pathlib import Path
from pio_proof import PIO, x
from tuning_proof import fixture, invoke


def policy(m, enabled, secondary):
    m.put('C_IDE', enabled)
    at = m.base + m.state['C_CHIP'] + 23
    m.cpu.mem_write(at, bytes(((m.cpu.mem_read(at, 1)[0] & 15) | secondary * 16,)))


def run(image, baseline=None):
    image = image.resolve()
    if baseline:
        baseline = baseline.resolve()
    rows = []
    choices = (b'Both Channels', b'Disabled', b'Primary Only')

    class Screen(PIO):
        popup_seen = False

        def interrupt(self, cpu, number, data):
            if number == 0x16 and cpu.reg_read(x.UC_X86_REG_AH) == 0:
                screen = bytes(cpu.mem_read(0xB8000, 4000))[::2]
                if all(value in screen for value in choices):
                    assert [screen.index(value) for value in choices] == sorted(screen.index(value) for value in choices)
                    self.popup_seen = True
            return super().interrupt(cpu, number, data)

    saved_records = []
    # Real keyboard edits and reloads must retain every physical device's policy.
    for method in ('arrow', 'popup'):
        for target in range(3):
            m = Screen(image, (None,)*4, requests=(5,)*4)
            before = bytes(m.cpu.mem_read(m.base + 0xA00, 51))
            chip = bytes(m.cpu.mem_read(m.base + m.state['C_CHIP'], 24))
            m.keys = [0x5000, 9] + [0x5000]*6
            if method == 'popup':
                m.keys += [13] + [0x5000]*target + [13]
            else:
                m.keys += [0x4D00]*target
            m.keys += [0x4400, ord('y')]
            m.call('setup_main', count=10000000)
            assert not m.keys and m.reset and not m.io
            assert method != 'popup' or m.popup_seen
            fresh = PIO(image)
            fresh.cmos[:] = m.cmos
            fresh.writes.clear()
            fresh.call('settings_load')
            expected = bytearray(before)
            expected[0] = int(target != 1)
            expected_chip = bytearray(chip)
            expected_chip[23] = (expected_chip[23] & 15) | (16 if target == 2 else 0)
            assert not fresh.writes
            assert fresh.cpu.mem_read(fresh.base + 0xA00, 51) == expected
            assert fresh.cpu.mem_read(fresh.base + fresh.state['C_CHIP'], 24) == expected_chip
            saved_records.append((method, target, bytes(m.cmos)))
            rows.append(dict(method=method, choice=target, save_reload=True, fixed_device_policies=True, setup_no_probe=True))

    # Execute the PCI function initializer and late RMW with nonzero peer fields.
    for method, target, saved_cmos in saved_records:
        enabled, secondary = int(target != 1), int(target == 2)
        gates = 0x80 if secondary else 0xC0 if enabled else 0
        d, f, base, state = fixture(image)
        d.devices[0x91] = {0:0x60, 1:0x10, 2:0x3A, 3:0x67, 0xB:1, 0xA:1, 9:0x8A, 0x42:0x40}
        f[4][:] = saved_cmos
        invoke(f, 'settings_load')
        assert d.read(base + state['C_IDE'], 1) == bytes((enabled,))
        assert bool(d.read(base + state['C_CHIP'] + 23, 1)[0] & 16) == bool(secondary)
        d.write(base + 0x1034, 2, 0xFFFF)
        f[0].reg_write(x.UC_X86_REG_BX, 0x91)
        invoke(f, 'board_pci_device')
        assert d.devices[0x91][0x41] == (0x89 if secondary else 0xC9)
        assert d.devices[0x91][0x42] == 0x30, 'Forbidden IDE bit retained'
        assert d.read(base + 0x1039, 1) == b'\x01'
        ide = d.devices[0x91]
        ide[0x41] = 0xED
        ide[4] = 0xA1
        peers = {n:ide.get(n, 0) for n in range(0x40, 0x50) if n != 0x41}
        invoke(f, 'ide_apply_controller')
        assert ide[0x41] == (0x2D | gates)
        assert ide[4] == (0xA0 | enabled)
        assert all(ide.get(n, 0) == value for n, value in peers.items())
        # Explicit IRQ14/15 requests distinguish reservation from route allocation.
        d.write(base + state['C_CHIP'] + 16, 1, 0x98)
        invoke(f, 'board_pci_runtime_policy', count=300000)
        links = list(d.read(base + 0x10A4, 2))
        assert links == ([14, 15] if not enabled else [255, 15] if secondary else [255, 255]), links
        rows.append(dict(enabled=enabled, secondary_disabled=secondary, decode=ide[0x41], peer_fields_unchanged=True, irq_links=links))

        m = PIO(image, ('ata', 'ata', 'packet', 'ata'))
        m.cmos[:] = saved_cmos
        m.call('settings_load')
        # Forward the actual PCI owner's decode/timing state into the ATA seam.
        for offset in range(0, 0x50, 4):
            m.config[0x80009100+offset] = sum(ide.get(offset+i, 0) << (8*i) for i in range(4))
        m.call('ata_detect_primary')
        allowed = [bool(enabled and (p < 2 or not secondary)) for p in range(4)]
        assert [bool(m.get('S_CONTROLLER', position=p)) for p in range(4)] == allowed
        assert all(allowed[pos] for _, _, pos in m.io)
        assert [m.get('S_PIO_MODE', position=p) for p in range(4)] == [4 if on else 0 for on in allowed]
        if enabled:
            assert not m.public(0x80)
            assert bytes(m.cpu.mem_read(0x21000, 512)) == m.payload(0, 0)
            m.cpu.mem_write(0x21000, b'Z'*512)
            assert not m.public(0x80, 3) and m.written[0] == b'Z'*512
        if secondary:
            before = dict(m.config)
            m.call('hardware_ata_pio_position', AX=4, BX=2)
            assert m.config == before, 'Disabled channel received timing writes'
        rows.append(dict(runtime=allowed, disabled_channels_untouched=True, primary_pio4_io=bool(enabled)))

    if baseline:
        # Earlier saved records retain both channels, including explicit global Off.
        for enabled in (0, 1):
            old = PIO(baseline, requests=(1, 2, 4, 5), controller=enabled)
            old.keys = [0x4400, ord('y')]
            old.call('setup_main', count=10000000)
            fresh = PIO(image)
            fresh.cmos[:] = old.cmos
            fresh.call('settings_load')
            assert fresh.get('C_IDE') == enabled
            assert fresh.cpu.mem_read(fresh.base + 0x60, 24) == old.cpu.mem_read(old.base + 0x60, 24)
            rows.append(dict(old_saved_record=True, controller=enabled, both_channels_preserved=True))
        old = PIO(baseline)
        policy(old, 1, 1)
        old.call('ata_detect_primary')
        assert any(pos >= 2 for _, _, pos in old.io), 'Prior candidate unexpectedly honored secondary disable'
        rows.append(dict(prior_image_rejected=True, reason='Secondary task-file traffic despite requested disable'))
    return rows


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('image', type=Path)
    parser.add_argument('--baseline', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    cases = run(args.image, args.baseline)
    args.output.write_text(json.dumps(cases, indent=2) + '\n')
    print(f'PASS: {len(cases)} focused IDE-channel cases; hardware performance untested')
