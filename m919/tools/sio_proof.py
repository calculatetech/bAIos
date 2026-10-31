"""UM8663 routing and later public UART/printer/FDC/IDE consumers."""
import hashlib
import json
import struct
from pathlib import Path
from unicorn import x86_const as x
from pci_proof import Hardware,compose
from cache_proof import post_module,guest,SRAM
from geometry_proof import invoke,mapped
from shared.tools.pci_proof import Endpoint,public_call
from shared.tools.peripheral_proof import UART,Printer
PORT=Path(__file__).resolve().parents[1]
REPOSITORY=PORT.parent


class SIO(Hardware):
    def __init__(self,onboard=(True,True,True),external_uarts=(),external_printers=(),ports=None,**options):
        super().__init__(**options)
        self.sio={0xC0:0xF0,0xC1:0x30,0xC2:0x7E,0xC3:0x5A,0xC4:0xA5};self.sio_open=False;self.sio_index=0
        self.onboard=onboard;self.uarts=[UART(),UART()];self.printer=Printer()
        self.external_uarts={base:UART() for base in external_uarts};self.external_printers={base:Printer() for base in external_printers}
        self.sio_writes=[];self.kbc_commands=[];self.fdc_accesses=[];self.settings=ports
    def uart(self,port):
        for index,bit,select,primary,secondary in ((0,2,2,0x3F8,0x3E8),(1,4,4,0x2F8,0x2E8)):
            base=primary if self.sio[0xC1]&select else secondary
            if self.onboard[index] and self.sio[0xC0]&bit and base<=port<base+8:return self.uarts[index],port-base
        for base,device in self.external_uarts.items():
            if base<=port<base+8:return device,port-base
        return None
    def parallel(self,port):
        base=0x378 if self.sio[0xC1]&8 else 0x278
        if self.onboard[2] and self.sio[0xC0]&8 and base<=port<base+3:return self.printer,port-base
        for base,device in self.external_printers.items():
            if base<=port<base+3:return device,port-base
        return None
    # Bit0 is a required reference initialization value; its electrical role is unknown.
    def fdc_on(self):return bool(self.sio[0xC0]&1 and self.sio[0xC2]&1 and not self.sio[0xC2]&0x20)
    def incoming(self,u,port,size):
        if port==0x109 and self.sio_open:return self.sio.get(self.sio_index,0xFF)
        endpoint=self.uart(port) or self.parallel(port)
        if endpoint:return endpoint[0].read(endpoint[1])
        if port in (*range(0x3F8,0x400),*range(0x2F8,0x300),*range(0x3E8,0x3F0),*range(0x2E8,0x2F0),
                    *range(0x378,0x37B),*range(0x278,0x27B),*range(0x3BC,0x3BF)):return 0xFF
        if port in (0x3F2,0x3F4,0x3F5,0x3F7):
            self.fdc_accesses.append(('in',port,self.fdc_on()))
            if not self.fdc_on():return 0xFF
        return super().incoming(u,port,size)
    def outgoing(self,u,port,size,value):
        if port==0x108:
            if value==0xAA:self.sio_open=True
            elif value==0x55:self.sio_open=False
            else:self.sio_index=value
        if port==0x109 and self.sio_open:
            self.sio[self.sio_index]=value;self.sio_writes.append((self.sio_index,value))
        endpoint=self.uart(port) or self.parallel(port)
        if endpoint:endpoint[0].write(endpoint[1],value)
        if port==0x64:self.kbc_commands.append(value)
        if port in (0x3F2,0x3F4,0x3F5,0x3F7):
            self.fdc_accesses.append(('out',port,self.fdc_on()))
            if not self.fdc_on():
                self.ports[port]=value
                return
        super().outgoing(u,port,size,value)


def cmos_ports(values):
    cmos=bytearray(post_module().nvram(types=0x40)[:128])
    cmos[0x5D:0x68]=b'P1\x01'+bytes(values);cmos[0x68]=(-sum(cmos[0x5D:0x68]))&255
    cmos[0x69]=0x55;cmos[0x6B]=0x40;cmos[0x6D]=1;cmos[0x6A]=(-0x55-0x41)&255
    return cmos


def transactions(fixture,hardware,expected_uart,expected_lpt):
    rows=[]
    for index,base in enumerate(expected_uart):
        device,_=hardware.uart(base);before=len(device.tx)
        initial,out=public_call(fixture,number=0x14,eax=0xABCD015A,edx=index)
        assert out[x.UC_X86_REG_EAX]&0xFFFF==0x615A,(base,hex(out[x.UC_X86_REG_EAX]))
        assert device.tx[before:]==[0x5A]
        initial,out=public_call(fixture,number=0x14,eax=0xABCD0200,edx=index)
        assert out[x.UC_X86_REG_EAX]&0xFFFF==0x00A6,(base,hex(out[x.UC_X86_REG_EAX]))
        rows.append({'uart':base,'index':index,'tx':0x5A,'rx':0xA6,'divisor':device.dll|(device.dlm<<8),'ier':device.regs[1],'lcr':device.regs[3]})
    for index,base in enumerate(expected_lpt):
        device,_=hardware.parallel(base);before=len(device.tx)
        initial,out=public_call(fixture,number=0x17,eax=0xABCD004B,edx=index)
        assert out[x.UC_X86_REG_EAX]&0xFFFF==0xD84B,(base,hex(out[x.UC_X86_REG_EAX]))
        assert device.tx[before:]==[0x4B]
        rows.append({'lpt':base,'index':index,'tx':0x4B,'strobe':True})
    return rows


def peripheral_fixture(image,initial_c2=0x7E):
    """Run late peripheral/public owners without the retired cache-POST observer."""
    class Peripheral(SIO):
        def prepare(self,u):pass
        observe=SRAM.observe
    hardware=Peripheral()
    hardware.sio[0xC2]=initial_c2
    hardware.initial_cmos=cmos_ports((1,2,1,2,0,1,0,1))
    hardware.qualifying=False
    row,fixture=mapped(hardware.modules,expected=16,memory=hardware,rom_image=image)
    u,d,listing,state,cmos,step=fixture
    hardware.registers[0x50]=1 # Valid geometry for the DMA model, with external cache disabled.
    for owner in ('settings_load','init_pic_pit','init_at_prerequisites','init_superio'):
        invoke(fixture,owner)
    d.write(0x9E000+state['C_IDE'],1,0)
    return hardware,fixture


def collection(image=None):
    rows=[]
    cases=[('empty',(False,False,False),(),(),(1,2,1,2,0,1,0,1),[],[]),
           ('one',(True,False,True),(),(),(3,4,1,3,0,1,0,1),[0x3E8],[0x278]),
           ('duplicates',(True,True,True),(0x3E8,),(0x278,),(1,2,1,2,0,1,0,1),[0x3F8,0x2F8,0x3E8],[0x378,0x278]),
           ('later',(False,False,False),(0x2E8,),(0x278,),(1,2,1,2,0,1,0,1),[0x2E8],[0x278])]
    for name,onboard,uart,lpt,ports,expected_uart,expected_lpt in cases:
        hardware=SIO(onboard=onboard,external_uarts=uart,external_printers=lpt)
        row,fixture=compose(hardware,saved=cmos_ports(ports));hardware.finish(fixture)
        u,d,listing,state,cmos,step=fixture
        bda=hardware.read(0x400,14);equipment=int.from_bytes(hardware.read(0x410,2),'little')
        assert list(struct.unpack('<4H',bda[:8]))==expected_uart+[0]*(4-len(expected_uart)),(name,bda.hex())
        assert list(struct.unpack('<3H',bda[8:]))==expected_lpt+[0]*(3-len(expected_lpt)),(name,bda.hex())
        assert (equipment>>9)&7==len(expected_uart) and equipment>>14==len(expected_lpt)
        transaction=transactions(fixture,hardware,expected_uart,expected_lpt)
        assert hardware.sio[0xC3]==0x5A and hardware.sio[0xC4]==0xA5
        assert hardware.sio_writes[:3]==[(0xC2,0xDF),(0xC0,0x0F),(0xC1,0x8F)]
        assert (hardware.sio[0xC2]&~0xA1)==(0x7E&~0xA1) and hardware.sio[0xC2]&0xA1==0x81
        assert not set(hardware.kbc_commands)&{0xA8,0xA9,0xD4}
        assert hardware.kbc_commands.count(0xA7)==1,'Retained startup disables the unused AUX clock once'
        rows.append({'case':name,'bda':bda.hex(),'equipment':equipment,'transactions':transaction,'sio':hardware.sio,'no_aux':True})
    return rows


def routing(image=None):
    if image:hardware,fixture=peripheral_fixture(image)
    else:
        hardware=SIO();row,fixture=compose(hardware);hardware.finish(fixture)
    u,d,listing,state,cmos,step=fixture;base=0x9E000;rows=[]
    for ports,low0,owned1 in (((1,2,1,2,0,1,0,1),15,0x8F),((3,4,1,3,1,0,0,1),14,0x41),
                            ((0,0,1,0,2,0,0,1),0,0xC1),((1,2,1,2,2,1,0,1),15,0xCF)):
        for policy in (0,1,2,3):
            d.write(base+state['C_CHIP']+22,1,policy)
            for i,b in enumerate(ports):d.write(base+state['C_PORTS']+i,1,b)
            hardware.sio[0xC0]=0xF0;hardware.sio[0xC1]=0x30;hardware.sio[0xC3]=0x5A
            u.reg_write(x.UC_X86_REG_FS,base>>4);u.reg_write(x.UC_X86_REG_CS,0xF000)
            invoke(fixture,'init_peripherals')
            assert hardware.sio[0xC0]==0xD0|low0 and hardware.sio[0xC1]==0x30|owned1,(ports,hardware.sio)
            assert hardware.sio[0xC3]==((0x1A|((policy&2)<<5)) if ports[3] and ports[4]==2 else 0x5A)
            assert hardware.sio[0xC4]==0xA5 and not hardware.sio_open
            expected_uart=[0x3F8,0x2F8] if ports[0]==1 else [0x3E8,0x2E8] if ports[0]==3 else []
            expected_lpt=[0x378] if ports[3]==2 else [0x278] if ports[3]==3 else []
            bda=d.read(0x400,14)
            assert list(struct.unpack('<4H',bda[:8]))==expected_uart+[0]*(4-len(expected_uart))
            assert list(struct.unpack('<3H',bda[8:]))==expected_lpt+[0]*(3-len(expected_lpt))
            for device in hardware.uarts:device.rx=[0xA6]
            transaction=transactions(fixture,hardware,expected_uart,expected_lpt)
            u.reg_write(x.UC_X86_REG_CS,0xF000);u.reg_write(x.UC_X86_REG_FS,base>>4)
            rows.append({'policy':policy,'ports':ports,'C0':hardware.sio[0xC0],'C1':hardware.sio[0xC1],'bda':bda.hex(),'transactions':transaction})
    # Awake/init RMW must precede the actual FDC command path.
    hardware.sio[0xC2]=0x7E;u.reg_write(x.UC_X86_REG_FS,base>>4)
    invoke(fixture,'floppy_controller_mode')
    assert hardware.sio[0xC2]==0xDF
    return rows


def saved_ide(image=None):
    rows=[]
    for initial,expected in ((1,0),(0,1)):
        keys=[0x50,28]+[0x50]*(4 if initial else 2)+[0x4D,0x44,28]
        bf=Endpoint(identity=0x673B1060,cls=0x01018F,pi_writable=5)
        hardware=SIO(endpoints={0x60:Endpoint(cls=0x030000),0x58:bf})
        saved=cmos_ports((3,4,1,3,0,1,0,1))
        saved[0x40:0x44]=b'ID\x01\0';saved[0x44]=initial
        saved[0x43]=(-sum(saved[0x40:0x5D]))&255
        row,fixture=compose(hardware,keys=keys,saved=saved)
        u,d,listing,state,cmos,step=fixture
        assert row['terminal']=='reset' and d.reset_requests==[0xFE] and not d.keys,(row['terminal'],d.keys)
        assert d.keys_sent==keys and cmos[0x44]==expected,(d.keys_sent,cmos[0x44],expected)
        assert sum(cmos[0x40:0x5D])&255==0
        assert bytes(cmos[0x5D:0x69])==bytes(saved[0x5D:0x69]),'IDE edit changed SIO settings'
        before_bda=d.read(0x400,14);before_sio=dict(hardware.sio);before_cmos=bytes(cmos)
        hardware.taskfiles=[];hardware.af=[];hardware.provider_calls=[];hardware.provider_events=[]
        hardware.ata_visits=[]
        reload,reloaded=compose(hardware,saved=before_cmos)
        hardware.finish(reloaded)
        assert hardware.read(0x9E000+state['C_IDE'],1)==bytes((expected,))
        assert bool(bf.read(4,2)&1)==bool(expected)
        assert bool(hardware.taskfiles)==bool(expected),(expected,len(hardware.taskfiles))
        assert not hardware.af
        assert hardware.ata_visits==['ata_detect_primary','ide_apply_controller']
        assert hardware.sio==before_sio and hardware.read(0x400,14)==before_bda
        services=transactions(reloaded,hardware,[0x3E8,0x2E8],[0x278])
        boot=hardware.boot(reloaded)
        if not expected:assert not hardware.taskfiles
        rows.append({'initial':initial,'saved':expected,'keys':keys,'reset':row['reset_requests'],'reload_terminal':reload['terminal'],
                     'command':bf.read(4,2),'taskfile_count':len(hardware.taskfiles),'af_writes':hardware.af,
                     'bda':before_bda.hex(),'sio':before_sio,'transactions':services,'boot':boot,
                     'saved_cmos':before_cmos.hex()})
    return rows


def fdc_and_keyboard(image=None,policy=3,initial_c2=0x7E):
    if image:hardware,fixture=peripheral_fixture(image,initial_c2)
    else:
        hardware=SIO();row,fixture=compose(hardware);hardware.finish(fixture)
    u,d,listing,state,cmos,step=fixture;base=0x9E000
    assert hardware.sio[0xC2]==(initial_c2&0xDF)|0x81,'Startup omitted reference FDC initialization'
    assert all(on for action,port,on in hardware.fdc_accesses if port==0x3F5),'FIFO accessed while asleep or disabled'
    d.write(base+state['C_CHIP']+22,1,policy)
    d.write(base+state['C_PORTS']+4,1,2)
    hardware.sio[0xC3]=0x1A
    invoke(fixture,'ports_apply')
    assert not hardware.sio[0xC0]&0x20
    assert bool(hardware.sio[0xC3]&0x40)==bool(policy&2) and hardware.sio[0xC4]==0xA5
    hardware.sio[0xC2]=initial_c2
    u.reg_write(x.UC_X86_REG_CS,0xF000);u.reg_write(x.UC_X86_REG_FS,base>>4)
    invoke(fixture,'init_floppy',count=300000)
    assert hardware.sio[0xC2]==0xDF and hardware.fdc_on()
    assert d.read(base+0x9B,1)==b'\x01' and d.read(base+0x85,1)==b'\x01'
    assert d.read(base+0x88,1)==b'\x00' and int.from_bytes(d.read(base+0x9C,2),'little')>0
    results=[]
    for name,operation in (('read',2),('write',3)):
        hardware.dma_events=[];hardware.fdc_accesses=[]
        body=f'''xor ax,ax
mov ds,ax
mov es,ax
mov di,0x8000
mov cx,512
mov al,0xB6
rep stosb
mov ax,0x{operation:02X}01
mov bx,0x8000
mov cx,1
xor dx,dx
int 0x13
mov [0x8500],ax
pushf
pop ax
mov [0x8502],ax
'''
        u.ctl_remove_cache(0x7000,0x8000)
        guest(fixture,'sio-fdc-'+name,body)
        returned=int.from_bytes(d.read(0x8500,2),'little');flags=int.from_bytes(d.read(0x8502,2),'little')
        assert returned==1 and not flags&1,(name,returned,flags)
        assert hardware.dma_mask and hardware.dma_events[-1]['mode']==(6 if operation==2 else 10),(name,hardware.dma_mask,[e['mode'] for e in hardware.dma_events])
        payload=bytes.fromhex(hardware.dma_events[-1]['payload'])
        assert payload==(bytes(hardware.disc[:512]) if operation==2 else b'\xB6'*512)
        assert all(on for action,port,on in hardware.fdc_accesses)
        results.append({'operation':name,'returned':returned,'carry':False,'masked':True,'dma':hardware.dma_events,'awake':True})
    d.write(base+state['C_PORTS']+5,1,0)
    u.reg_write(x.UC_X86_REG_FS,base>>4);u.reg_write(x.UC_X86_REG_CS,0xF000)
    invoke(fixture,'ports_apply');before=len(hardware.fdc_accesses);dma_before=len(hardware.dma_events)
    invoke(fixture,'init_floppy')
    assert len(hardware.fdc_accesses)==before and not hardware.fdc_on()
    _,out=public_call(fixture,number=0x13,eax=0xABCD0201,ebx=0x8000,ecx=1,edx=0,es=0)
    assert out[x.UC_X86_REG_EFLAGS]&1 and not len(hardware.dma_events)>dma_before
    assert len(hardware.fdc_accesses)==before
    # Late mouse and routing owners keep a pending keyboard make for the IRQ owner.
    hardware.ports[0x21]|=2
    hardware.queue=[0x1E];commands=len(hardware.kbc_commands)
    u.reg_write(x.UC_X86_REG_FS,base>>4);u.reg_write(x.UC_X86_REG_CS,0xF000)
    invoke(fixture,'board_mouse_no_aux')
    assert hardware.queue==[0x1E] and len(hardware.kbc_commands)==commands
    head=int.from_bytes(hardware.read(0x41C,2),'little')
    invoke(fixture,'board_keyboard_handoff',count=100000)
    assert not hardware.queue and hardware.read(0x400+head,2)==b'a\x1E'
    assert not set(hardware.kbc_commands[commands:])&{0xA7,0xA8,0xA9,0xD4}
    return {'policy':policy,'initial_C2':initial_c2,'startup_and_late_initialization':True,
            'reset_IRQ_received':True,'dma':results,'disabled_no_fdc_or_DMA2_transfer':True,'queued_make':'1E61','late_no_aux':True}


def run(image=None,output=None):
    image=image.resolve() if image else None
    payload=({'routing':routing(image),'fdc_keyboard':[fdc_and_keyboard(image,policy,initial) for policy in (0,3) for initial in (0x7E,0x7F)],'fixture':'bounded actual peripheral/public owners'}
             if image else {'collection':collection(),'routing':routing(),'saved_ide':saved_ide(),'fdc_keyboard':fdc_and_keyboard()})
    image=image or PORT/'build/hardware-tests/geometry/baios-m919.bin';payload['rom_sha256']=hashlib.sha256(image.read_bytes()).hexdigest()
    path=output.resolve() if output else (image.parent.parent if image.parent.name=='image' else PORT/'build/research/hardware')/'sio-proof.json'
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(payload,indent=2)+'\n')
    print('SIO routing, INT14/17, FDC DMA and keyboard: PASS',flush=True)
    return path


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image',type=Path)
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    run(args.image,args.output)
