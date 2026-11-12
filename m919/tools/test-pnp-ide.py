"""Check PCI-only IDE enumeration and the retained internal ISA reservations."""
import argparse
import hashlib
import importlib.util
from pathlib import Path
import struct
import sys

PORT = Path(__file__).resolve().parents[1]
ROOT = PORT.parent
sys.path.insert(0, str(ROOT))
spec = importlib.util.spec_from_file_location("pnp_ide", ROOT / "shared/tests/test-pnp.py")
pnp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pnp)
from shared.tools.isa_pnp_proof import Bus


def public_nodes(directory):
    pnp.OUTPUT = directory
    for mode in ("real", "ss16", "ss32"):
        caller = pnp.Caller("m919", mode)
        caller.cpu.mem_write(0x20100, b"\xCC" * 12)
        assert caller.far(0, [0x100, caller.buffer, 0x108, caller.buffer, caller.bios]) == 0
        count = caller.cpu.mem_read(0x20100, 1)[0]
        identities = []
        handle = 0
        for _ in range(count):
            status, node, handle = pnp.get_node(caller, handle)
            assert status == 0
            identity, _, blocks = pnp.decode(node)
            identities.append(identity)
            for tag, data in blocks[0]:
                if tag == 0x4B:
                    base, length = struct.unpack("<HB", data)
                    assert not any(base <= port < base + length for port in (0x1F0, 0x3F6, 0x170, 0x376))
                if tag == 0x22:
                    assert not int.from_bytes(data, "little") & 0xC000
        assert handle == 255
        assert identities == pnp.inventory("m919"), identities
        assert "PNP0600" not in identities and identities.count("PNP0A03") == 1
        assert "PNP0A00" not in identities, identities
        # The private IDE record cannot be read or configured as an OS device.
        assert pnp.get_node(caller, count)[0] == 0x83
        assert caller.far(2, [count, 0x200, caller.buffer, 1, caller.bios]) == 0x83
        print("PASS", mode, "public IDE owner is PCI", identities, flush=True)


def private_reservations(directory):
    for enabled in (False, True):
        for secondary in (False, True):
            machine = pnp.isa_machine("m919", Bus([]), directory)
            machine.call("settings_load")
            machine.put("C_PNP", bytes(15))
            machine.cpu.mem_write(machine.base + 0x1039, b"\x01")
            ide = bytearray(machine.get("C_IDE", 51))
            ide[0] = int(enabled)
            machine.put("C_IDE", ide)
            chip = bytearray(machine.get("C_CHIP", 24))
            chip[23] = (chip[23] & ~0x10) | (0 if secondary else 0x10)
            machine.put("C_CHIP", chip)
            machine.call("pnp_publish")
            assert machine.call("pnp_journal_begin")
            assert machine.call("pnp_work_begin") and machine.call("pnp_seed")
            for port, irq, active in ((0x1F0, 14, enabled), (0x170, 15, enabled and secondary)):
                assert machine.call("pnp_claim_query", AX=0x201, EDX=port, ECX=8) == (not active)
                control = 0x3F6 if port == 0x1F0 else 0x376
                assert machine.call("pnp_claim_query", AX=0x201, EDX=control, ECX=1) == (not active)
                assert machine.call("pnp_claim_query", AX=0x300, EDX=irq, ECX=1) == (not active)
            print("PASS internal IDE reservations", enabled, secondary, flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", default="build")
    args = parser.parse_args()
    public_nodes(args.directory)
    private_reservations(args.directory)
    raw = (PORT / args.directory / "baios-m919.bin").read_bytes()
    print("PASS exact candidate", hashlib.sha256(raw).hexdigest())


if __name__ == "__main__":
    main()
