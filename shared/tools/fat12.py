"""Replace allocated root files in a disposable FAT12 image."""
from pathlib import Path
import struct


class Fat12:
    def __init__(self, path):
        self.path = Path(path).resolve()
        self.image = self.path.read_bytes()
        self.bps = struct.unpack_from('<H', self.image, 11)[0]
        self.spc = self.image[13]
        self.reserved, self.entries, self.spf = (struct.unpack_from('<H', self.image, n)[0] for n in (14,17,22))
        if self.bps != 512 or not self.spc or self.image[510:512] != b'\x55\xaa':
            raise ValueError('Expected a bootable FAT12 sector image')
        self.root = (self.reserved + self.image[16]*self.spf)*self.bps
        self.data = self.root + ((self.entries*32+self.bps-1)//self.bps)*self.bps
        if (len(self.image)-self.data)//(self.spc*self.bps) >= 4085:
            raise ValueError('Image is not FAT12')

    def entry(self, name):
        stem, _, suffix = name.upper().partition('.')
        short = (stem.ljust(8)+suffix.ljust(3)).encode('ascii')
        for offset in range(self.root,self.root+self.entries*32,32):
            if self.image[offset:offset+11] == short:
                return offset
        raise FileNotFoundError(name)

    def clusters(self, name):
        offset = self.entry(name)
        cluster = struct.unpack_from('<H',self.image,offset+26)[0]
        seen = set()
        while 2 <= cluster < 0xFF8:
            if cluster in seen or self.data+(cluster-1)*self.spc*self.bps > len(self.image):
                raise ValueError('Invalid FAT12 allocation chain')
            seen.add(cluster)
            yield self.data+(cluster-2)*self.spc*self.bps
            packed = struct.unpack_from('<H',self.image,self.reserved*self.bps+cluster*3//2)[0]
            cluster = packed >> 4 if cluster & 1 else packed & 0xFFF

    def read(self, name):
        size = struct.unpack_from('<I',self.image,self.entry(name)+28)[0]
        data = b''.join(self.image[offset:offset+self.spc*self.bps] for offset in self.clusters(name))
        if len(data) < size:
            raise ValueError('File size exceeds its allocation')
        return data[:size]

    def replace(self, output, name, data, rename=None):
        output = Path(output).resolve()
        if output == self.path:
            raise ValueError('Write only to a disposable image copy')
        current = output.read_bytes() if output.exists() else self.image
        if len(current) != len(self.image):
            raise ValueError('Disposable image geometry differs')
        raw = bytearray(current)
        chain = list(self.clusters(name))
        if len(data) > len(chain)*self.spc*self.bps:
            raise ValueError('Replacement exceeds the existing allocation')
        padded = data.ljust(len(chain)*self.spc*self.bps,b'\0')
        for index, offset in enumerate(chain):
            raw[offset:offset+self.spc*self.bps] = padded[index*self.spc*self.bps:(index+1)*self.spc*self.bps]
        entry = self.entry(name)
        if rename:
            if len(rename) != 11:
                raise ValueError('Rename requires an eleven-byte DOS short name')
            raw[entry:entry+11] = rename
        struct.pack_into('<I',raw,entry+28,len(data))
        output.write_bytes(raw)
