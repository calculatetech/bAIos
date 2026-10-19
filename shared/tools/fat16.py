import struct

from .inspect_vhd import Vhd


class Fat16:
    def __init__(self, path):
        self.vhd = Vhd(path)
        mbr = self.vhd.sector(0)
        entry = next(mbr[n:n + 16] for n in range(446, 510, 16) if mbr[n] == 0x80)
        if entry[4] not in (4, 6, 14):
            raise ValueError("The active partition must be FAT16")
        self.start = struct.unpack_from("<I", entry, 8)[0]
        boot = self.vhd.sector(self.start)
        if struct.unpack_from("<H", boot, 11)[0] != 512:
            raise ValueError("Expected 512-byte sectors")
        self.spc = boot[13]
        fat = self.start + struct.unpack_from("<H", boot, 14)[0]
        fat_size = struct.unpack_from("<H", boot, 22)[0]
        self.root_lba = fat + boot[16] * fat_size
        self.root_size = (struct.unpack_from("<H", boot, 17)[0] * 32 + 511) // 512
        self.data_lba = self.root_lba + self.root_size
        self.fat = self.vhd.sectors(fat, fat_size)

    def clusters(self, first):
        seen = set()
        while 2 <= first < 0xFFF8:
            if first in seen or first * 2 + 2 > len(self.fat):
                raise ValueError("Invalid FAT chain")
            seen.add(first)
            yield first
            first = struct.unpack_from("<H", self.fat, first * 2)[0]

    def directory(self, first=0):
        if not first:
            sectors = range(self.root_lba, self.root_lba + self.root_size)
        else:
            sectors = [self.data_lba + (c - 2) * self.spc + s
                       for c in self.clusters(first) for s in range(self.spc)]
        for sector in sectors:
            data = self.vhd.sector(sector)
            for off in range(0, 512, 32):
                entry = data[off:off + 32]
                if entry[0] == 0:
                    return
                if entry[0] != 0xE5 and entry[11] != 0x0F:
                    yield sector, off, entry

    def find(self, name):
        directory = 0
        for part in name.replace("\\", "/").strip("/").split("/"):
            stem, _, ext = part.upper().partition(".")
            short = (stem.ljust(8) + ext.ljust(3)).encode("ascii")
            result = next(row for row in self.directory(directory) if row[2][:11] == short)
            directory = struct.unpack_from("<H", result[2], 26)[0]
        return result

    def read(self, name):
        entry = self.find(name)[2]
        first = struct.unpack_from("<H", entry, 26)[0]
        size = struct.unpack_from("<I", entry, 28)[0]
        return b"".join(self.vhd.sectors(self.data_lba + (c - 2) * self.spc, self.spc)
                        for c in self.clusters(first))[:size]

    def sector_offset(self, lba):
        v = self.vhd
        block, within = divmod(lba, v.sectors_per_block)
        v.file.seek(v.table_offset + block * 4)
        entry = struct.unpack(">I", v.file.read(4))[0]
        if entry == 0xFFFFFFFF:
            raise ValueError("Fixture changes require an allocated VHD block")
        v.file.seek(entry * 512 + within // 8)
        if not v.file.read(1)[0] & (0x80 >> (within & 7)):
            raise ValueError("Fixture changes require an allocated VHD sector")
        return entry * 512 + v.bitmap_size + within * 512

    def replace(self, output, name, data, rename=None):
        sector, off, entry = self.find(name)
        clusters = list(self.clusters(struct.unpack_from("<H", entry, 26)[0]))
        if len(data) > len(clusters) * self.spc * 512:
            raise ValueError("Replacement exceeds the existing allocation")
        remaining = data
        for c in clusters:
            for s in range(self.spc):
                if not remaining:
                    break
                lba = self.data_lba + (c - 2) * self.spc + s
                output.seek(self.sector_offset(lba))
                output.write(remaining[:512].ljust(512, b"\0"))
                remaining = remaining[512:]
        updated = bytearray(self.vhd.sector(sector))
        if rename:
            updated[off:off + 11] = rename
        struct.pack_into("<I", updated, off + 28, len(data))
        output.seek(self.sector_offset(sector))
        output.write(updated)
        output.flush()
        # Discard buffered directory sectors after each replacement.
        self.vhd.file.seek(0)
