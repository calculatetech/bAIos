#!/usr/bin/env python3
import argparse
import hashlib
import json
import struct
from pathlib import Path


class Vhd:
    def __init__(self, path: Path) -> None:
        self.file = path.open("rb")
        self.file.seek(-512, 2)
        footer = self.file.read(512)
        if footer[:8] != b"conectix":
            raise ValueError("not a VHD")
        self.size = struct.unpack_from(">Q", footer, 48)[0]
        self.disk_type = struct.unpack_from(">I", footer, 60)[0]
        if self.disk_type != 3:
            raise ValueError(f"expected a dynamic VHD, got type {self.disk_type}")
        header_offset = struct.unpack_from(">Q", footer, 16)[0]
        self.file.seek(header_offset)
        header = self.file.read(1024)
        if header[:8] != b"cxsparse":
            raise ValueError("dynamic VHD header is missing")
        self.table_offset = struct.unpack_from(">Q", header, 16)[0]
        self.entries = struct.unpack_from(">I", header, 28)[0]
        self.block_size = struct.unpack_from(">I", header, 32)[0]
        self.sectors_per_block = self.block_size // 512
        bitmap = (self.sectors_per_block + 7) // 8
        self.bitmap_size = (bitmap + 511) & ~511

    def close(self) -> None:
        self.file.close()

    def sector(self, lba: int) -> bytes:
        if lba < 0 or lba * 512 >= self.size:
            raise ValueError(f"LBA {lba} is outside the VHD")
        block = lba // self.sectors_per_block
        within = lba % self.sectors_per_block
        if block >= self.entries:
            return bytes(512)
        self.file.seek(self.table_offset + block * 4)
        entry = struct.unpack(">I", self.file.read(4))[0]
        if entry == 0xFFFFFFFF:
            return bytes(512)
        block_offset = entry * 512
        self.file.seek(block_offset + within // 8)
        if not (self.file.read(1)[0] & (0x80 >> (within & 7))):
            return bytes(512)
        self.file.seek(block_offset + self.bitmap_size + within * 512)
        data = self.file.read(512)
        if len(data) != 512:
            raise ValueError(f"short VHD block read at LBA {lba}")
        return data

    def sectors(self, lba: int, count: int) -> bytes:
        return b"".join(self.sector(lba + index) for index in range(count))


def chs(entry: bytes) -> dict[str, int]:
    sector = entry[2] & 0x3F
    cylinder = entry[3] | ((entry[2] & 0xC0) << 2)
    return {"cylinder": cylinder, "head": entry[1], "sector": sector}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("image", type=Path)
    args = parser.parse_args()
    vhd = Vhd(args.image)
    try:
        mbr = vhd.sector(0)
        if mbr[510:512] != b"\x55\xaa":
            raise ValueError("MBR signature is missing")
        partitions = []
        for index in range(4):
            entry = mbr[446 + index * 16 : 462 + index * 16]
            partitions.append({
                "index": index + 1,
                "active": entry[0] == 0x80,
                "type": entry[4],
                "start_chs": chs(entry),
                "end_chs": chs(entry[4:]),
                "start_lba": struct.unpack_from("<I", entry, 8)[0],
                "sectors": struct.unpack_from("<I", entry, 12)[0],
            })
        active = next((item for item in partitions if item["active"]), None)
        if not active:
            raise ValueError("no active MBR partition")
        boot = vhd.sector(active["start_lba"])
        if boot[510:512] != b"\x55\xaa":
            raise ValueError("active partition boot signature is missing")
        bps = struct.unpack_from("<H", boot, 11)[0]
        reserved = struct.unpack_from("<H", boot, 14)[0]
        fats = boot[16]
        root_entries = struct.unpack_from("<H", boot, 17)[0]
        sectors_per_fat = struct.unpack_from("<H", boot, 22)[0]
        root_lba = active["start_lba"] + reserved + fats * sectors_per_fat
        root_sectors = (root_entries * 32 + 511) // 512
        root = vhd.sectors(root_lba, root_sectors)
        entries = []
        for index in range(root_entries):
            entry = root[index * 32 : index * 32 + 32]
            if entry[0] == 0:
                break
            if entry[0] == 0xE5 or entry[11] == 0x0F:
                continue
            entries.append({
                "slot": index,
                "name": entry[:11].decode("ascii", "replace"),
                "attributes": entry[11],
                "cluster": struct.unpack_from("<H", entry, 26)[0],
                "size": struct.unpack_from("<I", entry, 28)[0],
            })
        with args.image.open("rb") as image_file:
            file_sha256 = hashlib.file_digest(image_file, "sha256").hexdigest().upper()
        result = {
            "image": str(args.image.resolve()),
            "file_sha256": file_sha256,
            "virtual_bytes": vhd.size,
            "virtual_sectors": vhd.size // 512,
            "mbr_sha256": hashlib.sha256(mbr).hexdigest().upper(),
            "partitions": partitions,
            "active_bpb": {
                "jump": boot[:3].hex().upper(),
                "bytes_per_sector": bps,
                "sectors_per_cluster": boot[13],
                "reserved_sectors": reserved,
                "fats": fats,
                "root_entries": root_entries,
                "sectors_per_fat": sectors_per_fat,
                "sectors_per_track": struct.unpack_from("<H", boot, 24)[0],
                "heads": struct.unpack_from("<H", boot, 26)[0],
                "hidden_sectors": struct.unpack_from("<I", boot, 28)[0],
                "root_lba": root_lba,
                "boot_sha256": hashlib.sha256(boot).hexdigest().upper(),
            },
            "root_entries": entries,
        }
        print(json.dumps(result, indent=2))
    finally:
        vhd.close()


if __name__ == "__main__":
    main()
