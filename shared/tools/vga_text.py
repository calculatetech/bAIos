"""Render captured VGA cells with the font returned by the actual VGA BIOS."""
import struct
import zlib

PALETTE=((0,0,0),(0,0,170),(0,170,0),(0,170,170),(170,0,0),(170,0,170),
         (170,85,0),(170,170,170),(85,85,85),(85,85,255),(85,255,85),
         (85,255,255),(255,85,85),(255,85,255),(255,255,85),(255,255,255))

def render(cells,font,output,columns=80,rows=25,width=9):
    if len(cells)!=columns*rows*2 or len(font)!=4096:
        raise ValueError('Expected full 80x25 cells and the installed 8x16 font')
    stride=columns*width*3
    pixels=bytearray(stride*rows*16)
    for index in range(columns*rows):
        char,attribute=cells[index*2:index*2+2]
        foreground=PALETTE[attribute&15];background=PALETTE[(attribute>>4)&7]
        left=(index%columns)*width;top=(index//columns)*16
        for y,bits in enumerate(font[char*16:char*16+16]):
            for x in range(width):
                on=bits&(0x80>>x) if x<8 else bits&1 if 0xC0<=char<=0xDF else 0
                offset=(top+y)*stride+(left+x)*3
                pixels[offset:offset+3]=bytes(foreground if on else background)
    def chunk(kind,data):
        return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data))
    scanlines=b''.join(b'\0'+pixels[y*stride:(y+1)*stride] for y in range(rows*16))
    header=struct.pack('>IIBBBBB',columns*width,rows*16,8,2,0,0,0)
    output.write_bytes(b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',header)+chunk(b'IDAT',zlib.compress(scanlines))+chunk(b'IEND',b''))
