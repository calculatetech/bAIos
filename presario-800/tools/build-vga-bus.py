"""Reproduce the physically validated bus07 ROM without rebuilding bAIos."""
from hashlib import sha256
from pathlib import Path


def main():
    root = Path(__file__).resolve().parents[1]
    baseline = root / 'reference/baios-presario800-vga141-bus07.bin'
    vga_input = root / 'reference/gd5428_1-41.bin'
    oem_input = root / 'reference/COMPAQ_PROLINEA_MT_05-02-94.BIN'
    image = baseline.read_bytes()
    vga = vga_input.read_bytes()
    oem = oem_input.read_bytes()
    assert sha256(image).hexdigest() == '98716a7cefc742047806c70a8cbea04a89648c5bf84859fa1cea269d791633b7', 'Validated bus07 reference changed'
    assert sha256(vga).hexdigest() == '72873e0bb9efda71d0b5819ce7b4201d8771c75473cd1170dcc6d2dfb794e0b6', 'Supplied VGA input changed'
    assert len(image) == len(oem) == 131072 and len(vga) == 32768
    assert image[32768:65536] == oem[32768:65536]
    system = image[65536:]
    assert len(system) == 65536 and sum(system) % 256 == 0
    assert system[0xfff0:0xfff5] == bytes.fromhex('ea000000f0')

    # Cirrus Jan 1994 manual 9.12: SR16[7:6]=01 selects one-clock I/O.
    # The startup table at 08B0 has its SR16 payload at 08E6. Mode tables
    # preserve the upper nibble (0958..0A03); retain memory-write delay and FIFO.
    assert vga[0x8d0:0x8d4] == bytes.fromhex('c4031600')
    assert vga[0x8de:0x8e9] == bytes.fromhex('004a2b5b2f421f00d81c01')
    assert vga[0x8d8:0x8dc] == bytes.fromhex('c40317fe')
    assert vga[0x8d4:0x8d8] == bytes.fromhex('c4031f00')
    assert vga[0x9fb:0xa00] == bytes.fromhex('80e4f00ae7')
    assert vga[0x9c3:0x9c8] == bytes.fromhex('80e4f00ae7')
    assert vga[0x12f1:0x12f7] == bytes.fromhex('80e4f080cc0a')
    tuned = bytearray(vga)
    tuned[0x8e6] = 0x48  # SR16: one-clock I/O, two-clock writes, FIFO8.
    tuned[0x8e7] = 0x22  # SR1F: 60.852 MHz, beyond the specified 1Ch maximum.
    tuned[0x8e8] = 0     # SR17[0]: complete DAC writes locally (manual 9.13).
    tuned[-1] = (tuned[-1] - sum(tuned)) & 255
    assert sum(tuned) % 256 == 0 and tuned[:3] == bytes.fromhex('55aa40')
    assert [i for i, pair in enumerate(zip(vga, tuned)) if pair[0] != pair[1]] == [0x8e6, 0x8e7, 0x8e8, 0x7fff]
    candidate = bytes(tuned) + image[32768:]
    assert candidate == image, 'Reproduction differs from validated reference'
    output = root / 'build/vga141/bus07'
    output.mkdir(parents=True, exist_ok=True)
    files = {'gd5428-141-bus07.rom': bytes(tuned),
             'baios-presario800-system.rom': system,
             'baios-presario800-vga141-bus07.bin': candidate}
    for name, contents in files.items():
        path = output / name
        path.write_bytes(contents)
        assert path.read_bytes() == contents
        print(f'{path}\n  {len(contents)} bytes; SHA256 {sha256(contents).hexdigest().upper()}')
    assert baseline.read_bytes() == image and vga_input.read_bytes() == vga and oem_input.read_bytes() == oem
    print('PASS: size, checksums, reset, selected VGA, retained resources, unchanged system and inputs')


if __name__ == '__main__':
    main()
