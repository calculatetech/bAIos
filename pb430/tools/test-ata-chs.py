"""Run actual cold/Save POST and installed INT13 against an independent CHS disk."""
import argparse
from functools import partial
import importlib
import json
from pathlib import Path
import struct
import sys

PORT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PORT.parent))

from core_proof import ACC

timing = importlib.import_module('test-timing-setup')
transitions = importlib.import_module('test-cache-transitions')
suite = importlib.import_module('test-port')


class ParameterDisk(ACC):
    def __init__(self, image, payload=None, *, chs=True, reject=False, media):
        self.chs, self.reject, self.media = chs, reject, media
        self.task = {0x1F6: 0xA0}
        self.initialized = False
        self.status, self.error = 0x50, 0
        self.fifo, self.position = b'', 0
        self.events, self.calls, self.terminal = [], [], None
        self.identify = bytearray(512)
        for word, value in ((0,0x40),(1,989),(3,15),(6,56),(49,0 if chs else 0x200),(60,0xAD28),(61,12)):
            struct.pack_into('<H', self.identify, word*2, value)
        name = b'WDC AC2420H'.ljust(40,b' ')
        self.identify[54:94] = b''.join(name[i:i+2][::-1] for i in range(0,40,2))
        super().__init__(image, payload)
        names = ('ata_identify_selected','ide_configure_disk','ide_initialize_geometry',
                 'ata_reset','ata_reset_bus','ata_transfer','ide_program_address','int13')
        points = {0xF0000+self.listing.symbol(name): name for name in names}
        self.code_observer = lambda model,address: self.calls.append(points[address]) if address in points else None

    def port_in(self, cpu, port, size, unused):
        if port in (0x1F7,0x3F6):
            assert size == 1
            return 0 if self.task[0x1F6]&0x10 else self.status
        if port == 0x1F0:
            assert size == 2 and self.status == 0x58 and self.position+2 <= len(self.fifo)
            value = int.from_bytes(self.fifo[self.position:self.position+2],'little')
            self.position += 2
            if self.position == len(self.fifo): self.status = 0x50
            return value
        if 0x1F1 <= port <= 0x1F6:
            assert size == 1
            return self.error if port == 0x1F1 else self.task.get(port,0)
        return super().port_in(cpu,port,size,unused)

    def port_out(self, cpu, port, size, value, unused):
        if port == 0xE9:
            assert size == 1 and value in (0x5A,0xEE), value
            self.terminal = value
            self.stopped, self.starting = True, False
            cpu.emu_stop()
            return
        if port == 0x3F6:
            assert size == 1
            if value&4:
                self.initialized = False
                self.fifo, self.position, self.status, self.error = b'',0,0x50,0
                self.events.append(('reset',))
            return
        if 0x1F1 <= port <= 0x1F6:
            assert size == 1
            self.task[port] = value
            return
        if port == 0x1F7:
            assert size == 1
            if self.task[0x1F6]&0x10:
                self.status = 0
                return
            self.error = 0
            if value == 0xEC:
                self.fifo, self.position, self.status = bytes(self.identify),0,0x58
            elif value == 0x91:
                assert self.chs and self.task[0x1F2] == 56 and self.task[0x1F6]&0x4F == 14
                self.initialized = not self.reject
                self.status, self.error = (0x51,4) if self.reject else (0x50,0)
                self.events.append(('parameters',not self.reject))
            elif value == 0x20:
                lba_mode = bool(self.task[0x1F6]&0x40)
                assert lba_mode != self.chs
                if lba_mode:
                    sector = sum(self.task.get(0x1F3+i,0)<<(8*i) for i in range(3)) | (self.task[0x1F6]&15)<<24
                else:
                    cylinder = self.task.get(0x1F4,0) | self.task.get(0x1F5,0)<<8
                    sector = (cylinder*15+(self.task[0x1F6]&15))*56+self.task.get(0x1F3,0)-1
                count = self.task.get(0x1F2,0) or 256
                self.events.append(('read',sector,count,lba_mode,self.initialized))
                assert not self.chs or self.initialized, 'CHS read before accepted parameters'
                assert 0 <= sector < sector+count <= 830760
                self.fifo = self.media[sector*512:(sector+count)*512].ljust(count*512,b'\0')
                self.position, self.status = 0,0x58
            else:
                raise AssertionError(('unexpected disk command',hex(value)))
            return
        return super().port_out(cpu,port,size,value,unused)


def phase(model, start, *, rejected=False):
    events = model.events[start:]
    reads = [event for event in events if event[0]=='read']
    parameters = [event for event in events if event[0]=='parameters']
    assert model.cpu.mem_read(0x13*4,4) == struct.pack('<HH',model.listing.symbol('int13'),0xF000)
    if rejected:
        assert not reads and parameters and all(not event[1] for event in parameters)
        assert model.cpu.mem_read(model.base+0x20,1) == b'\0' and model.cpu.mem_read(0x475,1) == b'\0'
        assert model.terminal is None
    else:
        assert model.terminal == 0x5A and model.cpu.mem_read(0x8000,4) == b'DATA'
        assert model.cpu.mem_read(model.base+0x20,1) == b'\1' and model.cpu.mem_read(0x475,1) == b'\1'
        assert model.cpu.mem_read(model.base+0x1E2,1) == bytes((int(model.chs),))
        assert {event[1] for event in reads} >= {0,1}
        ready = False
        for event in events:
            if event[0]=='reset': ready=False
            elif event[0]=='parameters': ready=event[1]
            elif event[0]=='read': assert not model.chs or ready
        assert bool(parameters) == model.chs
        assert all(event[3] != model.chs for event in reads)
    return dict(events=events,terminal=model.terminal,rejected=rejected)


def check(image):
    folder = PORT/'build/tests/results/ata-chs'
    folder.mkdir(parents=True,exist_ok=True)
    source, binary = folder/'boot.asm',folder/'boot.bin'
    source.write_text('''bits 16
org 0x7C00
cli
xor ax,ax
mov ss,ax
mov sp,0x7B00
mov ds,ax
mov es,ax
sti
cmp dl,0x80
jne failed
xor ax,ax
int 0x13
jc failed
mov bx,0x8000
mov ax,0x0201
mov cx,2
xor dh,dh
int 0x13
jc failed
cmp dword [0x8000],0x41544144
jne failed
mov al,0x5A
jmp done
failed:
mov al,0xEE
done:
out 0xE9,al
cli
hlt
times 510-($-$$) db 0
dw 0xAA55
''',encoding='ascii')
    suite.assemble(source,binary)
    media = binary.read_bytes()+b'DATA'+bytes(508)
    rows = []
    for chs,reject in ((True,False),(False,False),(True,True)):
        chip = bytearray(timing.DEFAULT);chip[6]=1
        model = timing.model(image,chip,partial(ParameterDisk,chs=chs,reject=reject,media=media))
        model.stop_address = 0xF0000+model.listing.symbol('.wait','boot_retry')
        model.cold_boot()
        cold = phase(model,0,rejected=reject)
        transitions.prepare_ui(model)
        start, resets = len(model.events),model.reset_count
        model.terminal = None
        model.open([0x44,28])
        assert model.reset_count == resets+1
        saved = phase(model,start,rejected=reject)
        if not reject:
            assert {'ata_identify_selected','ide_configure_disk','ata_reset','ata_reset_bus','ata_transfer','ide_program_address','int13'} <= set(model.calls)
        row = dict(chs=chs,cold=cold,save_reset=saved,actual_owners=sorted(set(model.calls)))
        if chs and not reject:
            model.reject = True
            start = len(model.events)
            ax,flags = model.public(0x13,0,dx=0x80)
            assert flags&1 and ax>>8
            events = model.events[start:]
            assert ('reset',) in events and ('parameters',False) in events
            assert not any(event[0]=='read' for event in events)
            row['rejected_restore'] = events
        rows.append(row)
        print('PASS actual cold/Save-reset CHS/LBA/rejection',chs,reject,flush=True)
    result = dict(cases=rows,scope='Actual PB430/shared firmware; synthetic ATA device. Physical hardware is unqualified.')
    (folder/'check.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image',type=Path,default=PORT/'build/baios-pb430.bin')
    check(parser.parse_args().image.resolve())
