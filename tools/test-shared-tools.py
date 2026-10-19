"""Check shared helper ownership and existing port entry points."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import socket
import struct
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from shared.tools.fat16 import Fat16
from shared.tools.floppy import GEOMETRY, blank_86f
from shared.tools.inspect_vhd import Vhd, chs
from shared.tools.network_fixture import CLIENT, GROUP, MAC, SERVER, Peer, checksum


def network_check(peer_type, fail):
    # Synthetic Local Switch traffic proves helper preservation, not iPXE boot.
    payload = b"shared fixture payload"
    client_mac = bytes.fromhex("020000123456")
    responses = []
    with peer_type(payload, fail) as peer, socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        probe.bind(("", GROUP[1]))
        probe.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP,
                         socket.inet_aton(GROUP[0]) + socket.inet_aton("0.0.0.0"))
        probe.settimeout(2)

        def exchange(sport, dport, body):
            udp = struct.pack("!HHHH", sport, dport, len(body) + 8, 0) + body
            ip = struct.pack("!BBHHHBBH4s4s", 0x45, 0, 20 + len(udp), 0, 0, 64, 17, 0, CLIENT, SERVER)
            ip = ip[:10] + struct.pack("!H", checksum(ip)) + ip[12:]
            probe.sendto(b"\xff" * 6 + client_mac + b"\x08\x00" + ip + udp, GROUP)
            while True:
                data, _ = probe.recvfrom(65536)
                if data[6:12] == MAC:
                    responses.append(data)
                    at = 14 + (data[14] & 15) * 4
                    return data[at + 8:]

        bootp = bytearray(236)
        bootp[:4] = bytes((1, 1, 6, 0))
        bootp[4:8] = bytes.fromhex("12345678")
        bootp[28:34] = client_mac
        for kind in (1, 3):
            response = exchange(68, 67, bytes(bootp) + bytes.fromhex("63825363") + bytes((53, 1, kind, 255)))
            assert response[0] == 2 and response[16:20] == CLIENT
            assert bytes((53, 1, 2 if kind == 1 else 5)) in response[240:]
        response = exchange(1234, 69, b"\x00\x01baios.nbp\x00octet\x00")
        assert response == (b"\x00\x05\x00\x01Fixture unavailable\x00" if fail else b"\x00\x03\x00\x01" + payload)
    expected = ["OFFER", "ACK", "RRQ:baios.nbp"] + (["ERROR"] if fail else [])
    assert peer.events == expected and len(responses) == 3
    return {"events": peer.events, "responses": [data.hex() for data in responses]}


def compatibility(relative, name):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main(image):
    image = image.resolve()
    with image.open("rb") as source:
        before = hashlib.file_digest(source, "sha256").hexdigest().upper()
    scratch = ROOT / "build/shared-tools-validation"
    scratch.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="helpers-", dir=scratch) as directory:
        work = Path(directory).resolve()
        assert work.is_relative_to(scratch.resolve())

        def run(relative, *args, ok=True):
            result = subprocess.run(
                [sys.executable, "-B", str(ROOT / relative), *map(str, args)],
                cwd=work, capture_output=True, text=True)
            assert (result.returncode == 0) == ok, result.stdout + result.stderr
            return result

        entries = ("shared/tools/inspect_vhd.py", "presario-800/tools/inspect-vhd.py",
                   "m919/tools/inspect-vhd.py")
        summaries = [json.loads(run(entry, image).stdout) for entry in entries]
        assert summaries[0] == summaries[1] == summaries[2]
        assert summaries[0]["file_sha256"] == before
        for index, entry in enumerate(entries[1:]):
            module = compatibility(entry, f"inspect_compat_{index}")
            assert module.Vhd is Vhd and module.chs is chs

        fixture = compatibility("presario-800/tools/memory-fixture.py", "fixture_compat")
        assert fixture.Fat16 is Fat16 and fixture.Vhd is Vhd
        network = compatibility("presario-800/tools/legacy-network-fixture.py", "network_compat")
        assert network.Peer is Peer and network.checksum is checksum
        matrix = compatibility("presario-800/tools/floppy-matrix.py", "matrix_compat")
        assert matrix.blank_86f is blank_86f and matrix.GEOMETRY is GEOMETRY
        print("PASS single helper owners and inspector CLI from unrelated cwd")
        for fail in (False, True):
            network_check(network.Peer, fail)
        print("PASS synthetic Local Switch DHCP/TFTP payload and error terminals")

        fat = Fat16(image)
        try:
            config = fat.read("CONFIG.SYS")
        finally:
            fat.vhd.close()
        output = run("presario-800/tools/memory-fixture.py", image, "--read", "CONFIG.SYS")
        expected = (config.decode("cp437") + "\n").replace("\n", os.linesep)
        expected = expected.replace("\r\n", "\n").replace("\r", "\n")
        assert output.stdout == expected

        port_scratch = ROOT / "presario-800/build/tmp"
        port_scratch.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="shared-fixture-", dir=port_scratch) as directory:
            port_work = Path(directory).resolve()
            assert port_work.is_relative_to(port_scratch.resolve())
            guest = port_work / "guest.com"
            guest.write_bytes(bytes.fromhex("b8004ccd21"))
            existing = port_work / "existing.vhd"
            existing.write_bytes(b"Existing output")
            for target in (image, work / "outside.vhd", existing):
                result = run("presario-800/tools/memory-fixture.py", image,
                             "--output", target, "--guest", guest, ok=False)
                assert "Use a new disposable output inside presario-800/build" in result.stderr
            assert existing.read_bytes() == b"Existing output"
            copied = port_work / "fixture.vhd"
            run("presario-800/tools/memory-fixture.py", image, "--output", copied, "--guest", guest)
            fat = Fat16(copied)
            try:
                assert fat.read("XMSTEST.COM") == guest.read_bytes()
                assert b"EMM386.EXE" in fat.read("CONFIG.SYS")
                assert b"XMSTEST.COM" in fat.read("AUTOEXEC.BAT")
                with copied.open("r+b", buffering=0) as disk:
                    fat.replace(disk, "CONFIG.SYS", b"REM shared helper check\r\n")
                assert fat.read("CONFIG.SYS") == b"REM shared helper check\r\n"
            finally:
                fat.vhd.close()
        print("PASS FAT16 reads/replacements and original disposable-output guards")

        media_hashes = {}
        for media in GEOMETRY:
            path = work / f"media-{media}.86f"
            matrix.blank_86f(path, media)
            data = path.read_bytes()
            assert data[:6] == bytes.fromhex("383642460c02")
            try:
                blank_86f(path, media)
            except FileExistsError:
                pass
            else:
                raise AssertionError("86F writer overwrote an existing image")
            assert path.read_bytes() == data
            media_hashes[str(media)] = hashlib.sha256(data).hexdigest()
        print(json.dumps({"media_hashes": media_hashes, "vhd_sha256": before}))

    with image.open("rb") as source:
        assert hashlib.file_digest(source, "sha256").hexdigest().upper() == before
    print("PASS original VHD unchanged")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
