"""Exercise El Torito firmware and boot the supplied Windows98 SE disc in86Box."""
import argparse
import hashlib
import importlib
import os
from pathlib import Path
import shutil
import struct
import subprocess

from unicorn import UC_HOOK_CODE
from unicorn import x86_const as x

setup = importlib.import_module('test-setup')
rtc = setup.rtc
ROOT, BUILD = rtc.ROOT, rtc.BUILD
TARGET = ROOT / 'reference/media/windows98se.iso'


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


Ide = importlib.import_module('test-ide-options')


class Packet(Ide.Disk):
    """Only external device behavior: IDENTIFY and PACKET task-file contracts."""
    def __init__(self, images, width=12, split=2048, attention=0, absent_media=False, ready_asc=0x28,
                 command_delay=0, phase_ack=False):
        super().__init__(tuple('packet' if data is not None else 'ata' for data in images))
        self.images, self.width, self.split = images, width, split
        self.attention, self.absent_media = attention, absent_media
        self.ready_asc = ready_asc
        self.packet = None
        self.reply = b''
        self.position = 0
        self.packet_log = []
        self.err = False
        self.command_delay, self.phase_ack = command_delay, phase_ack
        self.pending, self.acknowledged = 0, False
        self.ack_count = 0
        for data in self.payloads:
            if struct.unpack_from('<H', data)[0] & 0x8000:
                struct.pack_into('<H', data, 0, 0x8580 | (width == 16))

    def port_out(self, cpu, port, size, value, unused):
        if port == 0x1F7 and value == 0xA0:
            assert self.kinds[self.unit] == 'packet'
            assert self.ata.get(0x3F6) == 0x0A
            assert self.ata.get(0x1F1) == 0
            self.packet, self.reply, self.position, self.err = bytearray(), b'', 0, False
            self.pending, self.acknowledged = self.command_delay, False
            self.ata[port] = value
            return
        if port == 0x1F0 and self.packet is not None and len(self.packet) < self.width:
            assert size == 2
            assert not self.pending, 'CDB sent before command DRQ'
            assert not self.phase_ack or self.acknowledged, 'Command phase not acknowledged with Status read'
            self.packet.extend(value.to_bytes(2, 'little'))
            if len(self.packet) == self.width:
                cmd = self.packet[0]
                self.packet_log.append((self.unit, bytes(self.packet)))
                if cmd == 0:
                    self.err = bool(self.attention or self.absent_media)
                elif cmd == 3:
                    reply = bytearray(18)
                    reply[0], reply[2], reply[7] = 0x70, 6 if self.attention and self.ready_asc==0x28 else 2, 10
                    reply[12] = 0x3A if self.absent_media else self.ready_asc
                    self.attention = max(0, self.attention-1)
                    self.reply = bytes(reply)
                elif cmd == 0x25:
                    self.reply = struct.pack('>II', len(self.images[self.unit])//2048-1, 2048)
                elif cmd == 0x28:
                    lba = int.from_bytes(self.packet[2:6], 'big')
                    assert self.packet[7:9] == b'\0\1'
                    self.reply = self.images[self.unit][lba*2048:(lba+1)*2048]
                    self.err = len(self.reply) != 2048
                else:
                    raise AssertionError(('unexpected packet', self.packet.hex()))
                self.acknowledged = False
            return
        if port == 0x1F6:
            self.packet = None
        super().port_out(cpu, port, size, value, unused)

    def port_in(self, cpu, port, size, unused):
        if self.packet is None:
            return super().port_in(cpu, port, size, unused)
        if port in (0x1F7, 0x3F6):
            if self.pending:
                self.pending -= 1
                return 0x50          # Command accepted; DRQ is not asserted yet.
            if port == 0x1F7:
                self.acknowledged = True
                self.ack_count += 1
            return 0x51 if self.err else 0x58 if len(self.packet) < self.width or self.position < len(self.reply) else 0x50
        if port == 0x1F2:
            return 1 if len(self.packet) < self.width else 2 if self.position < len(self.reply) else 3
        if port in (0x1F4, 0x1F5):
            length = min(self.split, len(self.reply) - self.position//self.split*self.split)
            return length >> (8 * (port == 0x1F5)) & 255
        if port == 0x1F0:
            assert not self.phase_ack or self.acknowledged, 'Data phase not acknowledged with Status read'
            value = int.from_bytes(self.reply[self.position:self.position+2], 'little')
            self.position += 2
            if self.position % self.split == 0 or self.position == len(self.reply):
                self.acknowledged = False
            return value
        return super().port_in(cpu, port, size, unused)


def model(images=None, **kwargs):
    images = [None, disc()] if images is None else images
    m = setup.production_post_model()
    device = Packet(images, **kwargs)
    device.cpu = m.cpu
    m.disk_device, m.ata = device, device.ata
    cmos = bytearray((66, 56, 4, 1, 3, 0, 2, 0))
    cmos[5] = -(sum(cmos)+m.cmos[0x10]) & 255
    m.cmos[0x38:0x40] = cmos
    return m


def boot(m, segment=0x7C0, cold=False):
    # The established POST fixture uses a native-HDD-specific terminal assertion.
    # Stop at the image entry independently; execute the full production POST.
    address = segment * 16
    reached = []
    def terminal(cpu, where, size, unused):
        if m.cpu.mem_read(m.base+0x298, 1) == b'\1':
            reached.append(where)
            cpu.emu_stop()
    hook = m.cpu.hook_add(UC_HOOK_CODE, terminal, None, address, address)
    try:
        try:
            m.startup(reset=cold, production_controls=True, through_boot=True)
        except AssertionError:
            assert reached, ('POST failed before CD handoff', m.console)
        assert reached == [address]
        assert m.cpu.mem_read(address, 4) == b'CDOK'
        assert m.cpu.mem_read(0x475, 1) == bytes((sum(data is None for data in m.disk_device.images),))
    finally:
        m.cpu.hook_del(hook)


def api(m, ah, al=0, dl=0, cx=1, bx=0x1000, es=0x2000, si=0x500, ds=0):
    cpu = m.cpu
    for reg, value in ((x.UC_X86_REG_CS, 0x9000), (x.UC_X86_REG_IP, 0),
                       (x.UC_X86_REG_SS, 0), (x.UC_X86_REG_SP, 0x6FFE),
                       (x.UC_X86_REG_DS, ds), (x.UC_X86_REG_ES, es),
                       (x.UC_X86_REG_FS, 0x1234), (x.UC_X86_REG_EFLAGS, 0x602),
                       (x.UC_X86_REG_AX, ah<<8|al), (x.UC_X86_REG_BX, bx),
                       (x.UC_X86_REG_CX, cx), (x.UC_X86_REG_DX, dl), (x.UC_X86_REG_SI, si)):
        cpu.reg_write(reg, value)
    cpu.mem_write(0x90000, b'\xcd\x13\x90')
    for index,name in enumerate(('EAX','EBX','ECX','EDX','ESI','EDI','EBP','ESP')):
        reg = getattr(x,'UC_X86_REG_'+name)
        cpu.reg_write(reg,(0xA100+index)<<16 | cpu.reg_read(reg)&65535)
    before = {name:cpu.reg_read(getattr(x,'UC_X86_REG_'+name)) for name in rtc.REGS}
    cpu.emu_start(0x90000, 0x90002, count=4000000)
    assert cpu.reg_read(x.UC_X86_REG_CS) == 0x9000 and cpu.reg_read(x.UC_X86_REG_IP) == 2
    assert cpu.reg_read(x.UC_X86_REG_FS) == 0x1234
    assert cpu.reg_read(x.UC_X86_REG_EFLAGS) & 0x600 == 0x600
    changed = {'EAX'} | ({'EBX','ECX','EDX','EDI','ES'} if ah==8 else {'EBX','ECX'} if ah==0x41 else set())
    for name,value in before.items():
        result = cpu.reg_read(getattr(x,'UC_X86_REG_'+name))
        if name in changed:
            assert result>>16 == value>>16, (name,hex(value),hex(result))
        else:
            assert result == value, (name,hex(value),hex(result))
    return bool(cpu.reg_read(x.UC_X86_REG_EFLAGS) & 1), cpu.reg_read(x.UC_X86_REG_AX)


def emulation():
    for media, spt, kind in ((1, 15, 2), (2, 18, 4), (3, 36, 5)):
        for fdc in (False, True):
            m = model([None, disc(media)])
            if not fdc:
                ports = importlib.import_module('test-ports')
                # Existing verified peripheral CMOS extension, physical FDC disabled.
                payload = bytearray(ports.DEFAULT)
                payload[5] = 0
                ports.record(m,payload)
            boot(m)
            assert m.cpu.mem_read(m.base+0x1EB,1)[0] == int(fdc)
            before = list(m.fdc_log)
            assert api(m, 8)[0] is False
            assert m.cpu.reg_read(x.UC_X86_REG_CX) == 79<<8|spt
            assert m.cpu.reg_read(x.UC_X86_REG_BX) & 255 == kind
            assert m.cpu.reg_read(x.UC_X86_REG_DX) & 255 == (2 if fdc else 1)
            m.cpu.mem_write(0x21000-2, b'GG')
            m.cpu.mem_write(0x21000+5*512, b'GG')
            assert not api(m, 2, al=5, cx=2)[0]
            assert m.cpu.mem_read(0x21000, 5*512) == m.disk_device.images[1][21*2048+512:21*2048+6*512]
            assert m.cpu.mem_read(0x21000-2, 2) == m.cpu.mem_read(0x21000+5*512, 2) == b'GG'
            assert m.fdc_log == before
            assert api(m, 3, al=1)[0]
            assert api(m, 2, al=1, cx=0)[0]
            assert not api(m, 0x4B, al=1)[0]
            assert m.cpu.mem_read(0x500, 3) == bytes((19, media, 0))
            assert not api(m, 0x4B, al=0)[0]
            assert m.cpu.mem_read(m.base+0x298, 1) == b'\0'
            assert m.cpu.mem_read(0x4C, 4) == struct.pack('<HH', rtc.symbol('int13'), 0xF000)
    print('Floppy geometries, guarded partial/multi-block reads, disabled-FDC independence, read-only and termination: PASS')
    m = model()
    m.cmos[0x10] = 0x30         # Physical720-KB A differs from virtual1.44-MB A.
    m.cmos[0x3D] = -(sum(m.cmos[0x38:0x3D])+sum(m.cmos[0x3E:0x40])+m.cmos[0x10]) & 255
    boot(m)
    assert not api(m,8,dl=1)[0]
    assert m.cpu.reg_read(x.UC_X86_REG_CX) == 79<<8|9
    assert m.cpu.reg_read(x.UC_X86_REG_BX) & 255 == 3
    assert m.cpu.reg_read(x.UC_X86_REG_DL) == 2
    assert not api(m,0x15,dl=1)[0]
    assert m.cpu.reg_read(x.UC_X86_REG_AH) == 2
    assert m.cpu.reg_read(x.UC_X86_REG_DL) == 1
    assert not api(m,2,al=1,dl=0x80)[0] and m.cpu.mem_read(0x21000,4)==b'BOOT'
    m = model()
    card = importlib.import_module('test-legacy-boot').rom(0,provider=True)
    m.cpu.mem_write(0xC8000,bytes(card))
    boot(m)
    assert m.cpu.mem_read(m.base+0x296,2) == b'\0\xC8'
    assert not api(m,2,al=1,dl=1)[0] and m.cpu.mem_read(0x21000,4)==b'CARD'
    assert m.cpu.reg_read(x.UC_X86_REG_DL) == 1
    assert not api(m,0x4B,al=0)[0]
    assert m.cpu.mem_read(0x4E,2) == b'\0\xC8'
    print('Native displaced-A geometry and installed ROM forwarding/restoration preserve all caller registers: PASS')


def boot_keys():
    m = model()
    boot(m)
    # AT BIOS key codes: plain, Shift, Ctrl and Alt F1..F12. Exercise real
    # IRQ1 makes/breaks and public INT16, after the actual CD handoff.
    scans = (*range(0x3B,0x45),0x57,0x58)
    for modifiers,base,extra in (((),0x3B,0x85),((0x2A,),0x54,0x87),
                                ((0x36,),0x54,0x87),((0x1D,),0x5E,0x89),
                                ((0x38,),0x68,0x8B),((0x2A,0x1D),0x5E,0x89),
                                ((0x2A,0x1D,0x38),0x68,0x8B)):
        m.scans(modifiers)
        for index,scan in enumerate(scans):
            m.scans((scan,scan|0x80))
            for function in (1,0):      # Peek, then consume the same legacy key.
                cpu = m.cpu
                for reg,value in ((x.UC_X86_REG_CS,0x9000),(x.UC_X86_REG_IP,0),
                                  (x.UC_X86_REG_SS,0),(x.UC_X86_REG_SP,0x7000),
                                  (x.UC_X86_REG_AX,function<<8),(x.UC_X86_REG_EFLAGS,0x202)):
                    cpu.reg_write(reg,value)
                cpu.mem_write(0x90000,b'\xcd\x16\x90')
                cpu.emu_start(0x90000,0x90002,count=100000)
                expected = ((base+index) if index<10 else extra+index-10)<<8
                assert cpu.reg_read(x.UC_X86_REG_AX)==expected, (modifiers,hex(scan),hex(cpu.reg_read(x.UC_X86_REG_AX)),hex(expected))
                assert cpu.reg_read(x.UC_X86_REG_CS)==0x9000 and cpu.reg_read(x.UC_X86_REG_IP)==2
        m.scans(tuple(scan|0x80 for scan in reversed(modifiers)))
        assert not m.cpu.mem_read(0x417,1)[0] & 15
    print('Runtime F1..F12 modifiers, priority, make/break and INT16 peek/read: PASS')


def physical_floppy():
    m = model()
    boot(m)
    native = setup.legacy.floppy_buffer_model(m.segment)
    # Continue the real CD handoff's vector/BDA/EBDA using the retained external
    # ISA DMA/FDC media model. Product hook, mapping and FDC code stay unchanged.
    native.cpu.mem_write(0,bytes(m.cpu.mem_read(0,0x500)))
    native.cpu.mem_write(m.base,bytes(m.cpu.mem_read(m.base,1024)))
    native.fdc_dor, native.positions = m.fdc_dor, list(m.positions)
    native.cpu.mem_write(0x20FFE,b'GG'+b'\xCC'*512+b'GG')
    assert not api(native,2,al=1,dl=1)[0]
    assert native.cpu.mem_read(0x21000,512) == b'\x5A\xA5'*256
    assert native.cpu.mem_read(0x20FFE,2) == native.cpu.mem_read(0x21200,2) == b'GG'
    assert native.fdc_log[-1][0] == 0x46 and native.fdc_log[-1][1] & 3 == 0
    print('Displaced floppy B: real BIOS hook/native FDC, physical unit A, DMA bytes/guards and register preservation: PASS')


def packet():
    for kwargs in ({'command_delay':20}, {'phase_ack':True,'split':512}):
        m = model(**kwargs)
        boot(m)
        assert not api(m,2,al=4)[0]   # Same delayed/acknowledged transport after handoff.
        assert m.cpu.mem_read(0x21000,4) == b'CDOK'
        assert m.disk_device.ata.get(0x3F6) == 0
        if kwargs.get('phase_ack'):
            assert m.disk_device.ack_count > len(m.disk_device.packet_log)
    print('Delayed command DRQ and per-phase Status acknowledgement, boot and runtime reads: PASS')
    for width, split, attention in ((12, 2048, 0), (16, 512, 1)):
        m = model(width=width, split=split, attention=attention)
        boot(m)
        assert all(len(command) == width for _, command in m.disk_device.packet_log)
        assert m.disk_device.ata.get(0x3F6) == 0
    m = model(attention=1,ready_asc=4)
    boot(m)
    m = model(absent_media=True)
    m.startup(production_controls=True, through_boot=True)
    assert m.cpu.mem_read(0x7C00, 4) == b'BOOT'
    assert m.cpu.mem_read(m.base+0x298, 1) == b'\0'
    assert m.disk_device.ata.get(0x3F6) == 0
    print('12/16-byte packet, split phases, unit attention, empty-media fallback and released IRQ policy: PASS')


def catalog():
    mutations = ((17*2048, 1), (17*2048+1, ord('X')), (17*2048+6, 2),
                 (17*2048+7, ord('X')), (20*2048, 2),
                 (20*2048+1, 1), (20*2048+30, 0), (20*2048+28, 0),
                 (20*2048+32, 0), (20*2048+33, 4))
    good = model()
    boot(good)
    for offset, value in mutations:
        image = disc()
        image[offset] = value
        if offset in (20*2048,20*2048+1,20*2048+30):
            struct.pack_into('<H',image,20*2048+28,0)
            struct.pack_into('<H',image,20*2048+28,-sum(struct.unpack_from('<16H',image,20*2048)) & 65535)
        m = model([None, image])
        m.startup(production_controls=True, through_boot=True)
        assert m.cpu.mem_read(0x7C00, 4) == b'BOOT'
        assert m.cpu.mem_read(m.base+0x298,1) == b'\0'
        assert m.cpu.mem_read(0x4C,4) == struct.pack('<HH',rtc.symbol('int13'),0xF000)
        assert not any(cmd[0]==0x28 and int.from_bytes(cmd[2:6],'big')==21
                       for _,cmd in m.disk_device.packet_log)
    print('Independent descriptor/catalog acceptance predicates and unsupported-media fallback: PASS')


def load():
    for count, segment in ((1, 0), (1, 0x7C0), (5, 0x1000), (129, 0x1000)):
        image = disc(count=count, segment=segment)
        # Extend synthetic media for the over64-KB case.
        if count > 128:
            image.extend(bytes(2048))
        m = model([None, image])
        destination = (segment or 0x7C0)*16
        guards = (destination-2,destination+count*512)
        def seed(current,name):
            if name=='int19':
                for address in guards: current.cpu.mem_write(address,b'GG')
        m.startup_observer=seed
        boot(m, segment or 0x7C0)
        assert m.cpu.mem_read(destination, count*512) == image[21*2048:21*2048+count*512]
        assert all(m.cpu.mem_read(address,2)==b'GG' for address in guards)
    for count, segment in ((0, 0x7C0), (1, 0x6F0), (5, 0x9FB0), (1,0xA000)):
        m = model([None, disc(count=count, segment=segment)])
        # Observe after POST, before real boot dispatch. Exclude the live stack
        # and legitimate HDD fallback write at7C00; protect refused destinations
        # and the unused EBDA tail independently of mutable CD packet fields.
        guards = (0x7E00 if segment==0x7C0 else segment*16, m.base+0x300)
        def seed(current,name):
            if name=='int19':
                for address in guards: current.cpu.mem_write(address,b'G'*16)
        m.startup_observer=seed
        m.startup(production_controls=True, through_boot=True)
        assert m.cpu.mem_read(0x7C00, 4) == b'BOOT'
        assert all(m.cpu.mem_read(address,16)==b'G'*16 for address in guards)
        assert m.cpu.mem_read(m.base+0x298,1)==b'\0'
        assert not any(cmd[0]==0x28 and int.from_bytes(cmd[2:6],'big')==21
                       for _,cmd in m.disk_device.packet_log)
    print('Default/custom load segment, exact512-byte count,64-KB crossing and stack/EBDA rejection: PASS')


def devices():
    bad = disc(); bad[20*2048+32] = 0
    for images, selected in (([disc(), None], 0), ([None, disc()], 1), ([bad, disc()], 1)):
        m = model(images)
        boot(m)
        assert m.cpu.mem_read(m.base+0x299, 1) == bytes((selected*16,))
    m = model([None,None])
    m.startup(production_controls=True,through_boot=True)
    assert not m.disk_device.packet_log and m.cpu.mem_read(0x7C00,4) == b'BOOT'
    m = model([bad,bad])
    m.startup(production_controls=True,boot_failure=True)
    assert {unit for unit,_ in m.disk_device.packet_log} == {0,1}
    for gate in ('none','controller','non-cd'):
        m = model()
        if gate == 'none':
            m.cmos[0x3B] |= 0x40  # Slave None, ordinary ATA master still enabled.
            m.cmos[0x3D] = -(sum(m.cmos[0x38:0x3D])+sum(m.cmos[0x3E:0x40])+m.cmos[0x10]) & 255
        elif gate == 'controller':
            payload = bytearray(Ide.DEFAULT); payload[0] = 0
            Ide.saved(m,payload)
        else:
            struct.pack_into('<H',m.disk_device.payloads[1],0,0x8080)
        m.startup(production_controls=True,through_boot=gate!='controller',boot_failure=gate=='controller')
        assert not m.disk_device.packet_log
    print('Master/slave and unbootable-prefix followed by later valid CD: PASS')


def edd():
    m = model([None, disc(media=0)])
    boot(m)
    assert not api(m, 0x41, dl=0xE0, bx=0x55AA)[0]
    assert m.cpu.reg_read(x.UC_X86_REG_BX) == 0xAA55
    for lba, count, offset, failure in ((22,1,0x1000,False), (63,1,0xF800,False),
                                      (64,1,0x1000,True), (22,1,0xF801,True), (22,0,0x1000,True)):
        m.cpu.mem_write(0x500, struct.pack('<BBHHHQ',16,0,count,offset,0x2000,lba))
        destination = 0x20000+offset
        m.cpu.mem_write(destination-2,b'GG')
        m.cpu.mem_write(destination+2048,b'GG')
        before = len(m.disk_device.packet_log)
        result = api(m,0x42,dl=0xE0)
        assert result[0] == failure, (lba,count,offset,result)
        assert result[1]>>8 == (4 if failure else 0)
        if failure:
            assert len(m.disk_device.packet_log) == before
            assert m.cpu.mem_read(0x502,2) == b'\0\0'
        else:
            assert m.cpu.mem_read(0x502,2) == struct.pack('<H',count)
            assert m.cpu.mem_read(0x20000+offset,2048) == m.disk_device.images[1][lba*2048:(lba+1)*2048]
        assert m.cpu.mem_read(destination-2,2) == m.cpu.mem_read(destination+2048,2) == b'GG'
    for size,reserved,lba in ((15,0,22),(16,1,22),(16,0,(1<<32)|22)):
        m.cpu.mem_write(0x500,struct.pack('<BBHHHQ',size,reserved,1,0x1000,0x2000,lba))
        before = len(m.disk_device.packet_log)
        result=api(m,0x42,dl=0xE0)
        assert result[0] and result[1]>>8==4
        assert m.cpu.mem_read(0x502,2) == b'\0\0' and len(m.disk_device.packet_log) == before
    m.cpu.mem_write(0x500,b'\x1A\0')
    assert not api(m,0x48,dl=0xE0)[0]
    assert struct.unpack('<QH',m.cpu.mem_read(0x510,10)) == (64,2048)
    equipment=bytes(m.cpu.mem_read(0x410,2))
    disks=bytes(m.cpu.mem_read(0x475,1))
    hook=bytes(m.cpu.mem_read(0x4C,4))
    assert api(m,0x4B,al=1,dl=0xE0)==(False,1)
    expected=struct.pack('<BBBBIHHHHBBB',19,0,0xE0,0,21,1,0,0x7C0,1,0,0,0)
    assert m.cpu.mem_read(0x500,19)==expected
    assert m.cpu.mem_read(m.base+0x298,1)==b'\1'
    assert m.cpu.mem_read(0x410,2)==equipment and m.cpu.mem_read(0x475,1)==disks
    assert m.cpu.mem_read(0x4C,4)==hook
    print('No-emulation2048-byte absolute EDD reads and packet/range/buffer refusal: PASS')


def settings():
    scripts = ([], [0x50,0x4D], [0x50,0x50,0x4D,0x4D,0x4D],
               [0x50,0x50,0x50,0x4D,0x4D,0x4D])
    for slot, edits in enumerate(scripts):
        m = model()
        m.cmos[0x3C] |= 8<<2
        m.cmos[0x3D] = -(sum(m.cmos[0x38:0x3D])+sum(m.cmos[0x3E:0x40])+m.cmos[0x10]) & 255
        m.call('settings_load')
        m.open([0x50,0x50,15,*edits,0x44,28])
        order = (m.cmos[0x3C]&7,m.cmos[0x3E]&7,m.cmos[0x3F],m.cmos[0x3E]>>3)
        assert order[slot] == 3 and order.count(3) == 1, order
        snapshot = bytes(m.cmos)
        for cold in (False,True):
            post = model()
            post.cmos[:] = snapshot
            post.boot_sector[510:] = b'\0\0'  # An earlier HDD must fail before a later CD slot.
            boot(post,cold=cold)
            assert post.cpu.mem_read(post.base+0x172,1)[0] == order[0]
            assert tuple(post.cpu.mem_read(post.base+0x189,2)) == order[1:3]
            assert post.cpu.mem_read(post.base+0x1F6,1)[0] == order[3]
            assert post.cpu.mem_read(post.base+0x13C,1) == b'\x08'
    m = model()
    m.call('settings_load')
    seen = []
    def popup(current):
        text = bytes(current.cpu.mem_read(0xB8000,4000))[::2]
        if b'SELECT VALUE' in text:
            start = 0
            while (at := text.find(b'CD-ROM',start)) >= 0:
                seen.append(current.cpu.mem_read(0xB8000+at*2+1,1)[0])
                start = at+1
    m.observer = popup
    m.open([0x50,0x50,15,0x50,28,0x50,28,0x44,28])
    assert 0x18 not in seen and 0x17 in seen, seen
    assert (m.cmos[0x3C]&7,m.cmos[0x3E],m.cmos[0x3F]) == (2,3,0)
    for order in ((5,2,0,0),(3,3,0,0),(2,0,0,0)):
        m=model()
        record=bytearray((66,56,5,1,order[0],0,order[1]|order[3]<<3,order[2]))
        record[5]=-(sum(record)+m.cmos[0x10])&255
        m.cmos[0x38:0x40]=record
        notices=[]
        def recovery(current,name):
            if order[0]==2: return
            if name=='post_clock_alert' and not notices:
                assert current.cpu.mem_read(current.base+0x17C,1)==b'\0'
                assert current.cmos[0x38:0x40]==record
                assert not current.disk_device.packet_log
                notices.append('rejected')
            elif name=='post_notice_wait' and notices==['rejected']:
                assert 'Enter/D: Load defaults' in current.console
                current.pending.append(28)  # Fresh actual key accepts existing recovery.
                notices.append('accepted')
        m.startup_observer=recovery
        m.startup(production_controls=True,through_boot=True)
        loaded=(m.cpu.mem_read(m.base+0x172,1)[0],*m.cpu.mem_read(m.base+0x189,2),
                m.cpu.mem_read(m.base+0x1F6,1)[0])
        assert loaded==((2,0,0,0) if order[0]==2 else (1,2,0,0))
        assert m.cpu.mem_read(m.base+0x17C,1)==b'\x01'
        assert notices==([] if order[0]==2 else ['rejected','accepted'])
        if order[0]==2: assert m.cmos[0x38:0x40]==record
        else: assert not (sum(m.cmos[0x38:0x40])+m.cmos[0x10])&255
        assert m.cpu.mem_read(0x7C00,4)==b'BOOT'
        assert not m.disk_device.packet_log and m.cpu.mem_read(m.base+0x298,1)==b'\0'
    print('Real Setup quick/popup selectors, allocated-device moves and saved four-slot cold/warm CD boot: PASS')


def boot_order():
    import itertools
    m = setup.Setup()
    offsets = (0x182,0x18E,0x18F,0x1F7)
    for order in itertools.product(range(5),repeat=4):
        if len([v for v in order if v]) != len(set(v for v in order if v)):
            continue
        for slot in range(4):
            for target in range(5):
                for offset,value in zip(offsets,order):
                    m.cpu.mem_write(m.base+offset,bytes((value,)))
                m.cpu.mem_write(m.base+0xF5,b'\x02')
                m.cpu.mem_write(m.base+0xF7,bytes((slot,)))
                m.cpu.reg_write(x.UC_X86_REG_AX,target)
                m.cpu.reg_write(x.UC_X86_REG_BX,offsets[slot])
                expected = list(order)
                if target and target in expected:
                    old = expected.index(target)
                    expected.pop(old)
                    expected.insert(slot,target)
                else:
                    expected[slot]=target
                m.call('setup_enum_store')
                assert [m.cpu.mem_read(m.base+i,1)[0] for i in offsets]==expected,(order,slot,target,expected)
    m = model()
    m.call('settings_load')
    m.open([0x50,0x50,15,0x4D,0x44,28])
    assert m.cmos[0x3A]==5 and m.cmos[0x3C]&7==4
    snapshot=bytes(m.cmos)
    m.call('settings_load')
    assert m.cpu.mem_read(m.base+0x172,1)==b'\x04'
    assert bytes(m.cmos)==snapshot
    other_snapshot=snapshot
    # Actual quick/popup allocation moves and insertion retain all four slots.
    for edits,expected in (([0x4D],(2,1,0,0)),
                           ([0x50]*3+[28,0x50,0x50,28],(1,0,0,2)),
                           ([28,0x50,0x50,0x50,28],(4,2,0,0))):
        ui=setup.Setup()
        ui.open([0x50,0x50,15,*edits,0x44,28])
        saved=bytes(ui.cmos)
        ui.call('settings_load')
        assert (ui.cpu.mem_read(ui.base+0x172,1)[0],*ui.cpu.mem_read(ui.base+0x189,2),
                ui.cpu.mem_read(ui.base+0x1F6,1)[0])==expected
        assert bytes(ui.cmos)==saved
    # Allocate all four targets through the actual page, then reload.
    m=setup.Setup()
    m.open([0x50,0x50,15,0x50,0x50,28]+[0x50]*3+[28,0x50,28]+[0x50]*4+[28,0x44,28])
    assert (m.cmos[0x3C]&7,m.cmos[0x3E]&7,m.cmos[0x3F],m.cmos[0x3E]>>3)==(1,2,3,4)
    m.call('settings_load')
    assert (m.cpu.mem_read(m.base+0x172,1)[0],*m.cpu.mem_read(m.base+0x189,2),
            m.cpu.mem_read(m.base+0x1F6,1)[0])==(1,2,3,4)
    # Nonzero fourth targets cannot duplicate another slot or use reserved bits.
    for packed in (0x0A,0x12,0x1A,0x2A,0x42,0x82):
        invalid=setup.Setup();invalid.cmos[:]=m.cmos
        invalid.cmos[0x3E]=packed
        invalid.cmos[0x3D]=-(sum(invalid.cmos[0x38:0x3D])+sum(invalid.cmos[0x3E:0x40])+invalid.cmos[0x10])&255
        invalid.call('settings_load')
        assert invalid.cpu.mem_read(invalid.base+0x17C,1)==b'\0',packed
    print('Four-slot insertion in both directions, Disabled, every valid order and all four targets save/reload: PASS')

    legacy=importlib.import_module('test-legacy-boot')
    for action,order,expected,count,cold in (('success',(4,2,0,0),b'ROM!',1,False),
                                        ('success',(4,2,0,0),b'ROM!',1,True),
                                        ('success',(0,0,0,4),b'ROM!',1,False),
                                        ('chain',(4,2,0,0),b'BOOT',1,False),
                                        ('return',(4,2,0,0),b'BOOT',1,False),
                                        ('success',(2,4,0,0),b'BOOT',0,False),
                                        ('none',(4,2,0,0),b'BOOT',0,False)):
        m=model()
        if action!='none':
            body="""bits 16
org 0
db 0x55,0xAA,4
jmp init
init:
    xor ax,ax
    mov ds,ax
    mov eax,[0x64]
    mov [0x580],eax
    mov word [0x64],handler
    mov [0x66],cs
    retf
handler:
    xor ax,ax
    mov ds,ax
    inc byte [0x584]
"""
            if action=='success':
                body+="mov dword [0x7C00],'ROM!'\njmp 0:0x7C00\n"
            elif action=='chain':
                body+="mov fs,ax\nmov ax,0x1200\nmov ss,ax\nmov sp,0x1000\nmov ds,ax\nstd\ncli\njmp far [fs:0x580]\n"
            else:
                body+='iret\n'
            body+='times 2048-($-$$) db 0\n'
            card=bytearray(legacy.assemble('other-'+action,body))
            card[-1]=-sum(card[:-1])&255
            m.cpu.mem_write(0xC8000,bytes(card))
        record=bytearray((66,56,5,1,order[0],0,order[1]|order[3]<<3,order[2]))
        record[5]=-(sum(record)+m.cmos[0x10])&255
        m.cmos[0x38:0x40]=record
        if action=='success' and order==(4,2,0,0):
            m.cmos[:]=other_snapshot  # Real saved Setup choice through POST -> ROM.
        reached=[]
        def terminal(cpu,address,size,unused):
            reached.append(address);cpu.emu_stop()
        hook=m.cpu.hook_add(UC_HOOK_CODE,terminal,None,0x7C00,0x7C00)
        try:
            try:
                m.startup(reset=cold,production_controls=True,through_boot=True)
            except AssertionError:
                assert reached, m.console
            assert reached and m.cpu.mem_read(0x7C00,4)==expected,(action,m.console)
            assert m.cpu.mem_read(0x584,1)==bytes((count,))
            assert m.cpu.mem_read(0x64,4)==struct.pack('<HH',rtc.symbol('int19'),0xF000)
            assert m.cpu.mem_read(m.base+0x298,1)==b'\0'
        finally:
            m.cpu.hook_del(hook)
    print('Other uses initialized ROM chain at selected priority; dirty chained/returning failures and absent ROM continue: PASS')


def lifecycle():
    # A bootloader can retain its own disk hook across INT19. Reopening must
    # reuse the wrapper already below that hook, without making a cycle.
    m = model(); boot(m)
    predecessor = bytes(m.cpu.mem_read(m.base+0x294,4))
    wrapper = bytes(m.cpu.mem_read(0x4C,4))
    external = struct.pack('<HH',0,0x8000)
    m.cpu.mem_write(0x80000,b'\xEA'+wrapper)
    m.cpu.mem_write(0x4C,external)
    m.cpu.mem_write(0x91000,b'\xCD\x19')
    m.cpu.reg_write(x.UC_X86_REG_CS,0x9100)
    m.cpu.reg_write(x.UC_X86_REG_IP,0)
    reached=[]
    hook=m.cpu.hook_add(UC_HOOK_CODE,lambda cpu,a,s,u:(reached.append(a),cpu.emu_stop()),None,0x7C00,0x7C00)
    m.cpu.emu_start(0x91000,0xFFFFFF,count=4000000)
    m.cpu.hook_del(hook)
    assert reached and m.cpu.mem_read(0x7C00,4)==b'CDOK'
    assert not api(m,2,al=1,dl=0x80)[0]
    assert m.cpu.mem_read(0x21000,4)==b'BOOT'
    assert m.cpu.mem_read(0x4C,4)==external
    assert m.cpu.mem_read(m.base+0x294,4)==predecessor
    assert not api(m,2,al=1)[0]
    assert m.cpu.mem_read(0x21000,512)==m.disk_device.images[1][21*2048:21*2048+512]
    assert not api(m,0x4B,al=0)[0]
    assert m.cpu.mem_read(0x4C,4)==external and m.cpu.mem_read(m.base+0x298,1)==b'\0'
    assert not api(m,2,al=1,dl=0x80)[0] and m.cpu.mem_read(0x21000,4)==b'BOOT'
    print('Retained bootloader hook, INT19 CD reopening, virtual/native reads and termination: PASS')
    def native_restored(current):
        assert current.cpu.mem_read(current.base+0x298,1)==b'\0'
        assert current.cpu.mem_read(0x410,2)==current.cpu.mem_read(current.base+0x27E,2)
        assert current.cpu.mem_read(0x4C,4)==struct.pack('<HH',rtc.symbol('int13'),0xF000)
        assert current.cpu.mem_read(current.base+0x294,4)==bytes(4)
        assert current.cpu.mem_read(0x475,1)==b'\1'
    m = model()
    boot(m)
    original_equipment = struct.unpack_from('<H',m.cpu.mem_read(m.base+0x27E,2))[0]
    equipment=bytes(m.cpu.mem_read(0x410,2))
    hook=bytes(m.cpu.mem_read(0x4C,4))
    assert not api(m,0x4B,al=1)[0]
    assert m.cpu.mem_read(m.base+0x298,1) == b'\1'
    assert m.cpu.mem_read(0x410,2)==equipment and m.cpu.mem_read(0x4C,4)==hook
    assert m.cpu.mem_read(0x475,1)==b'\1'
    # OS relocation copies the whole existing EBDA and publishes its new owner.
    old = m.base
    m.base,m.segment = 0x9EC00,0x9EC0
    m.cpu.mem_write(m.base,bytes(m.cpu.mem_read(old,1024)))
    m.cpu.mem_write(old,bytes([0xA5])*1024)
    m.cpu.mem_write(0x40E,struct.pack('<H',m.segment))
    m.cpu.mem_write(m.base+0x300,b'G'*16)
    assert not api(m,2,al=1)[0]
    assert m.cpu.mem_read(0x21000,512) == m.disk_device.images[1][21*2048:21*2048+512]
    # INT19 must protect the relocated record even when BDA RAM size is unchanged.
    struct.pack_into('<H',m.disk_device.images[1],20*2048+34,m.segment)
    m.cpu.mem_write(0x90000,b'\xcd\x19')
    m.cpu.reg_write(x.UC_X86_REG_CS,0x9000)
    m.cpu.reg_write(x.UC_X86_REG_IP,0)
    reached=[]
    hook=m.cpu.hook_add(UC_HOOK_CODE,lambda cpu,a,s,u:(reached.append(a),cpu.emu_stop()),None,0x7C00,0x7C00)
    m.cpu.emu_start(0x90000,0xFFFFFF,count=4000000)
    m.cpu.hook_del(hook)
    assert reached and m.cpu.mem_read(0x7C00,4) == b'BOOT'
    assert m.cpu.mem_read(m.base,1) == b'\1'
    assert m.cpu.mem_read(m.base+0x298,1) == b'\0'
    native_restored(m)
    assert m.cpu.mem_read(m.base+0x300,16)==b'G'*16
    assert m.cpu.mem_read(old,1024)==bytes([0xA5])*1024
    # A fresh active instance also exercises the direct termination operation.
    m = model(); boot(m)
    assert not api(m,0x4B,al=0)[0]
    assert struct.unpack('<H',m.cpu.mem_read(0x410,2))[0] == original_equipment
    native_restored(m)
    # A new boot starts with the saved next target; dirty failed-image context
    # is discarded by the actual INT18 continuation owner.
    m = model(); boot(m)
    m.cpu.reg_write(x.UC_X86_REG_CS,0x9000)
    m.cpu.reg_write(x.UC_X86_REG_SS,0x1200)
    m.cpu.reg_write(x.UC_X86_REG_SP,0x3456)
    m.cpu.mem_write(0x90000,b'\xcd\x18')
    reached=[]
    hook=m.cpu.hook_add(UC_HOOK_CODE,lambda cpu,a,s,u:(reached.append(a),cpu.emu_stop()),None,0x7C00,0x7C00)
    m.cpu.emu_start(0x90000,0xFFFFFF,count=4000000)
    m.cpu.hook_del(hook)
    assert reached and m.cpu.mem_read(0x7C00,4) == b'BOOT'
    assert m.cpu.reg_read(x.UC_X86_REG_DL) == 0x80
    assert m.cpu.mem_read(m.base+0x298,1) == b'\0'
    assert m.cpu.reg_read(x.UC_X86_REG_SS) == 0
    native_restored(m)
    # INT19 also clears active mapping before resetting the installed handlers.
    m = model(); boot(m)
    m.disk_device.images[1][20*2048+32] = 0
    m.cpu.mem_write(0x90000,b'\xcd\x19')
    m.cpu.reg_write(x.UC_X86_REG_CS,0x9000)
    m.cpu.reg_write(x.UC_X86_REG_IP,0)
    reached=[]
    hook=m.cpu.hook_add(UC_HOOK_CODE,lambda cpu,a,s,u:(reached.append(a),cpu.emu_stop()),None,0x7C00,0x7C00)
    m.cpu.emu_start(0x90000,0xFFFFFF,count=4000000)
    m.cpu.hook_del(hook)
    assert reached and m.cpu.mem_read(0x7C00,4) == b'BOOT'
    assert m.cpu.mem_read(m.base+0x298,1) == b'\0'
    native_restored(m)
    # Fresh media alone and timer wakes do not leave the retry gate. Only a new
    # keyboard event re-enters INT19 and re-reads the disc through the real owner.
    m = model(absent_media=True)
    m.cmos[0x3E] = 0
    m.cmos[0x3D] = -(sum(m.cmos[0x38:0x3D])+sum(m.cmos[0x3E:0x40])+m.cmos[0x10]) & 255
    m.startup(production_controls=True,boot_failure=True)
    requests = len(m.disk_device.packet_log)
    wake=[]
    def events(current,address):
        if current.cpu.mem_read(address,1) != b'\xF4': return
        wake.append(address)
        assert 'Press any key to retry' in current.console
        assert len(current.disk_device.packet_log) == requests
        if len(wake)==2: current.disk_device.absent_media=False
        if len(wake)==4: current.pending.append(0x1E)
    m.event_observer=events
    reached=[]
    hook=m.cpu.hook_add(UC_HOOK_CODE,lambda cpu,a,s,u:(reached.append(a),cpu.emu_stop()),None,0x7C00,0x7C00)
    m.cpu.reg_write(x.UC_X86_REG_CS,0xF000)
    m.cpu.emu_start(0xF0000+rtc.symbol('boot_retry'),0xFFFFFF,count=4000000)
    m.cpu.hook_del(hook)
    assert reached and len(wake)==4 and m.cpu.mem_read(0x7C00,4)==b'CDOK'
    assert m.startup_hops.count('option_rom_discovery') == 1
    assert len(m.disk_device.packet_log) > requests
    print('Relocated state, termination, INT18/19 continuation, changed-media/timer/fresh-key CD retry: PASS')


def integrity():
    system = (BUILD/'baios-presario800-system.rom').read_bytes()
    assert len(system) == 65536 and sum(system)&255 == 0
    assert system[0xFFF0:0xFFF5] == b'\xea\0\0\0\xf0'
    for speed in (50,60):
        physical = (BUILD/f'baios-presario800-vga{speed}.bin').read_bytes()
        assert len(physical) == 131072 and physical[65536:] == system
        reference = bytearray((ROOT/'reference/baios-presario800-vga141-bus07.bin').read_bytes()[:32768])
        reference[0x8E7] = 0x1C if speed == 50 else 0x22
        reference[-1] = -sum(reference[:-1])&255
        assert physical[:32768] == reference
        assert physical[32768:65536] == (ROOT/'reference/COMPAQ_PROLINEA_MT_05-02-94.BIN').read_bytes()[32768:65536]
    print('Both64-KB systems/128-KB layouts, checksums, VGA inputs, retained OEM region and reset vector: PASS')


def native(iso=TARGET, clock=60):
    matrix = importlib.import_module('floppy-matrix')
    work = BUILD / 'cd-review'
    work.mkdir(exist_ok=True)
    # A fresh VM avoids inherited CMOS boot order. Do not overwrite an active VM.
    import tempfile
    vm = Path(tempfile.mkdtemp(prefix='win98-', dir=work))
    disk = vm / 'scratch.img'
    with disk.open('xb') as out:
        out.truncate(64 * 1024 * 1024)
    matrix.config(vm, disk, 0, 0, vm / 'a.img', vm / 'b.img', seek=False)
    nvr = vm / 'nvr/d824.nvr'
    cmos = bytearray(nvr.read_bytes())
    record = bytearray((66, 56, 4, 1, 3, 0, 2, 0))
    record[5] = -(sum(record) + cmos[0x10]) & 255
    cmos[0x38:0x40] = record
    # d824 has no matching VL82C481 L2 SRAM model. Use saved Setup policy;
    # the production ROM and all CD boot/INT13 paths remain unmodified.
    policy = bytearray(importlib.import_module('test-chipset').NORMAL)
    policy[9] &= ~1
    cmos[0x69], cmos[0x6A] = 0xC2, -(0xC2 + sum(policy)) & 255
    cmos[0x6B:0x80], cmos[0x33:0x36] = policy[:21], policy[21:]
    nvr.write_bytes(cmos)
    config = vm / '86box.cfg'
    settings = config.read_text().replace('mem_size = 4096', 'mem_size = 16384')
    settings = settings.replace('[Floppy and CD-ROM drives]',
        '[Floppy and CD-ROM drives]\ncdrom_01_parameters = 1, atapi\n'
        'cdrom_01_ide_channel = 0:1\ncdrom_01_type = 86cd\n'
        f'cdrom_01_image_path = {iso.resolve().as_posix()}\n')
    config.write_text(settings)
    roms = BUILD / f'86box/vga{clock}/roms'
    wrapper = roms / 'machines/d824/fts-biosupdated824noflashbiosepromv320-320334-160.bin'
    physical = BUILD / f'baios-presario800-vga{clock}.bin'
    assert wrapper.read_bytes() == physical.read_bytes()
    exe = shutil.which('86Box.exe') or str(Path(os.environ['LOCALAPPDATA']) /
        'Microsoft/WinGet/Packages/86Box.86Box_Microsoft.Winget.Source_8wekyb3d8bbwe/86Box.exe')
    process = subprocess.Popen([exe, '-P', str(vm), '-R', str(roms), '-L', str(vm / '86box.log'), '-N'])
    (work / 'preview.pid').write_text(str(process.pid))
    print(f'Production vga{clock}: {hashlib.sha256(physical.read_bytes()).hexdigest()}\n'
          f'ISO (read-only): {iso}\nPID {process.pid}, profile {vm}', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--86box', dest='emulator', action='store_true')
    parser.add_argument('--preview', action='store_true')
    parser.add_argument('--iso', type=Path, default=TARGET)
    parser.add_argument('--vga-clock', type=int, choices=(50, 60), default=60)
    cases = dict(settings=settings,catalog=catalog,load=load,packet=packet,boot_keys=boot_keys,
                 physical_floppy=physical_floppy,boot_order=boot_order,edd=edd,
                 emulation=emulation,lifecycle=lifecycle,devices=devices,integrity=integrity)
    parser.add_argument('--case',action='append',choices=tuple(cases))
    args = parser.parse_args()
    if args.case or not (args.emulator or args.preview):
        for name in args.case or cases:
            print('START '+name,flush=True)
            cases[name]()
    if args.emulator or args.preview:
        native(args.iso, args.vga_clock)
