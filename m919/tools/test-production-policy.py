"""Execute production startup and verify the completed lab cannot erase settings."""
import json
from pathlib import Path
from unicorn import x86_const as x
from tuning_proof import Bus, fixture
from geometry_proof import mapped, invoke, PORT
from shared.tools.checkpoint_proof import run as shared_defaults
from cache_proof import POSTHardware, post_module


def run(image):
    normal_defaults = shared_defaults(image.resolve())
    owner, saved, base, state = fixture(image)
    defaults = owner.read(base+state['C_CHIP'], 24)
    assert defaults == bytes.fromhex('000100400000000800000060000000000000000000000000')
    # A real save supplies both supported CMOS layouts; startup must retain them.
    rows = []
    for packed in (False, True, None):
        saved[4][:] = post_module().nvram()[:128]
        invoke(saved, 'setup_defaults')
        owner.write(base+state['U_BOOT'], 1, 2)
        owner.write(base+state['U_BOOT_SECOND'], 1, 1)
        owner.write(base+state['U_BOOT_THIRD'], 1, 3)
        expected_ide=owner.read(base+state['U_IDE'],51)
        expected_ports=owner.read(base+state['U_PORTS'],8)
        draft = bytearray(defaults)
        draft[10], draft[12], draft[23] = 12, 1, 0x10 if packed else 0
        for i, value in enumerate(draft):
            owner.write(base+state['U_CHIP']+i, 1, value)
        if packed:
            invoke(saved,'settings_save')
        else:
            saved[4][0x69]=0x57
            saved[4][0x6A]=(-0x57-sum(draft))&255
            saved[4][0x6B:0x80],saved[4][0x33:0x36]=draft[:21],draft[21:]
            invoke(saved,'chipset_settings_load')
            assert owner.read(base+state['C_CHIP'],24)==draft
            saved[0].reg_write(x.UC_X86_REG_SI,state['C_CHIP'])
            invoke(saved,'chipset_valid')
        if packed is None:
            saved[4][0x38]=0
            saved[4][0x69]=0
        assert not saved[0].reg_read(x.UC_X86_REG_EFLAGS)&1
        for warm in (False, True):
            for initial in (0, 0xFF):
                class Startup(Bus):
                    def incoming(self, cpu, port, size):
                        if port == 0x64:
                            return (4 if warm else 0) | int(bool(self.queue))
                        return super().incoming(cpu, port, size)
                bus = Startup()
                bus.composed = True
                bus.rom_image=image
                bus.prepare = lambda cpu: POSTHardware.prepare(bus,cpu)
                bus.initial_cmos = bytes(saved[4])
                bus.devices[0x90].update({0x41: initial, 0x45: initial, 0x83: initial})
                _, execution = mapped(bus.modules, expected=16, memory=bus, rom_image=image)
                cpu, _, listing, _, cmos, step = execution
                assert bytes(cmos) == bus.initial_cmos, 'Startup erased saved CMOS'
                assert bus.read(base+state['C_CHIP'], 24) == (defaults if packed is None else draft), (packed,warm,initial,bus.read(base+state['C_CHIP'], 24).hex(),draft.hex(),cmos.hex())
                assert bus.devices[0x90][0x83] == initial & ~0x40
                # Keep the mapped CPU/stack through the real peripheral calls.
                bus.continuing = True
                begin = 0xF0000+listing.symbol('.pci_policy', 'board_smm_startup')
                step.execute((cpu.reg_read(x.UC_X86_REG_CS)<<4)+cpu.reg_read(x.UC_X86_REG_IP), begin, 1000000)
                assert cpu.reg_read(x.UC_X86_REG_IP) == begin-0xF0000
                before = dict(bus.devices[0x90])
                end = 0xF0000+listing.symbol('pci_initialize')
                step.execute(begin, end, 1000000)
                assert cpu.reg_read(x.UC_X86_REG_IP) == end-0xF0000,(hex(cpu.reg_read(x.UC_X86_REG_CS)),hex(cpu.reg_read(x.UC_X86_REG_IP)),hex(end))
                assert bus.devices[0x90][0x41] == before[0x41] | 1
                assert bus.devices[0x90][0x45] == before[0x45] | 8
                assert bus.devices[0x90][0x83] & 0x40 == 0
                assert cmos[0x10:] == bus.initial_cmos[0x10:]
                end=0xF0000+listing.symbol('chipset_cyrix_apply')
                step.execute((cpu.reg_read(x.UC_X86_REG_CS)<<4)+cpu.reg_read(x.UC_X86_REG_IP),end,3000000)
                assert cpu.reg_read(x.UC_X86_REG_IP)==end-0xF0000
                assert bus.read(base+state['C_CHIP'],24)==(defaults if packed is None else draft),(packed,bus.read(base+state['C_CHIP'],24).hex(),draft.hex())
                assert cmos[0x10:]==bus.initial_cmos[0x10:]
                order=[bus.read(base+state['C_'+suffix],1)[0] for suffix in ('BOOT','BOOT_SECOND','BOOT_THIRD','BOOT_FOURTH')]
                assert order==([3,1,2,0] if packed is None else [2,1,3,0] if packed else [2,1,0,0]),order
                if packed:
                    assert bus.read(base+state['C_IDE'],51)==expected_ide
                    assert bus.read(base+state['C_PORTS'],8)==expected_ports
                rows.append(dict(packed=packed, warm=warm, incoming=initial,
                                 saved_settings_retained=True, bridge_policy_preserves_peers=True))
    raw = image.read_bytes()
    assert b'Register Lab' not in raw
    for name in ('lab_boot', 'lab_ui', 'lab_defaults_entry'):
        try:
            saved[2].symbol(name)
        except StopIteration:
            pass
        else:
            raise AssertionError(name+' remains in production')
    return dict(startup=rows, shared_defaults=normal_defaults)


if __name__ == '__main__':
    rows = run(PORT/'build/baios-m919.bin')
    target = PORT/'build/tests/production-policy.json'
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(rows, indent=2)+'\n')
    print(f"PASS: {len(rows['startup'])} production startup cases; shared boot defaults; no lab")
