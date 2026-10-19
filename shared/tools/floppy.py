import struct

TYPES = {0: "none", 1: "525_2dd", 2: "525_2hd", 3: "35_2dd", 4: "35_2hd", 5: "35_2ed"}
GEOMETRY = {1: (40, 9, 2, 0, 0), 2: (80, 15, 0, 1, 1),
            3: (80, 9, 2, 0, 0), 4: (80, 18, 0, 1, 0), 5: (80, 36, 3, 2, 0)}


def blank_86f(path, media):
    # 86Box qt_newfloppydialog.cpp:create86f, version 2.12, MFM, two sides.
    tracks, _, rate, hole, rpm = GEOMETRY[media]
    size = 50000 if hole == 2 else 25000
    count = (tracks * 2) << (1 if tracks <= 43 else 0)
    offsets = [2056 + i * (size + 6) for i in range(count)]
    with path.open("xb") as disk:
        disk.write(struct.pack("<IHH", 0x46423638, 0x020C, (hole << 1) | 8))
        disk.write(struct.pack("<512I", *(offsets + [0] * (512 - count))))
        track = struct.pack("<HI", rate | 8 | (rpm << 5), 0) + bytes(size)
        for _ in offsets:
            disk.write(track)
