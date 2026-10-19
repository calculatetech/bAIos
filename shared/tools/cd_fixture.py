"""Synthetic El Torito fixtures, copied from the validated donor helper."""
import struct

def disc(media=2, segment=0, count=1):
    """Synthetic local-format proof; the supplied ISO is the compatibility oracle."""
    image = bytearray(64 * 2048)
    image[17*2048:17*2048+30] = b'\0CD001\1EL TORITO SPECIFICATION\0'
    struct.pack_into('<I', image, 17*2048+71, 20)
    catalog = 20 * 2048
    image[catalog:catalog+2] = b'\1\0'
    image[catalog+30:catalog+32] = b'\x55\xaa'
    struct.pack_into('<H', image, catalog+28, -sum(struct.unpack_from('<16H', image, catalog)) & 65535)
    struct.pack_into('<BBHBBHI', image, catalog+32, 0x88, media, segment, 0, 0, count, 21)
    for sector in range(64-21):
        image[(21+sector)*2048:(22+sector)*2048] = bytes((sector*17+i) & 255 for i in range(2048))
    image[21*2048:21*2048+4] = b'CDOK'
    return image

