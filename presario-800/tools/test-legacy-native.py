"""Boot retained ISA ROM providers on the installed d824 86Box model."""
import argparse
import hashlib
import importlib
import os
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import zlib

legacy = importlib.import_module('test-legacy-boot')
matrix = importlib.import_module('floppy-matrix')
ROOT, BUILD = legacy.ROOT, legacy.BUILD


def sector(mixed=False, shadow=False):
    return legacy.assemble('native-mixed' if mixed else 'native-scsi-shadow' if shadow else 'native-scsi', f"""bits 16
org 0x7C00
    cld
    xor ax,ax
    mov ds,ax
    mov es,ax
    mov [bootdrive],dl
    cmp dl,0x80
    jne fail
    cmp byte [0x475],{2 if mixed else 1}
    jne fail
    cmp word [0x4E],0xC800
    jne fail
    {'mov fs,[0x40E]' if shadow else ''}
    {'cmp byte [fs:0x75],7' if shadow else ''}
    {'jne fail' if shadow else ''}
    mov ax,0x0201
    mov bx,0x8000
    mov cx,2
    mov dx,{0x81 if mixed else 0x80}
    int 0x13
    jc fail
    cmp dword [0x8000],0x49534353
    jne fail
    mov ax,0x0308
    mov bx,0
    mov cx,32
    mov dl,[bootdrive]
    xor dh,dh
    push es
    push word 0xB800
    pop es
    int 0x13
    pop es
    jc fail
    mov al,0x68
    jmp exit
fail:
    mov al,0x69
exit:
    mov bl,al
    mov dx,0x80
    mov si,magic
.magic:
    lodsb
    out dx,al
    cmp si,magicend
    jb .magic
    mov dx,0x501
    mov al,4
    out dx,al
    inc dx
    mov al,bl
    out dx,al
    cli
    hlt
magic db '86Box',1,5
magicend:
bootdrive db 0
times 510-($-$$) db 0
dw 0xAA55
""")


def scsi(mixed=False, timeout=180, observe=False, shadow=False):
    inputs = ROOT.parent/'tools/86box/roms/scsi/adaptec'
    provider = inputs/'aha1540b320_330.bin'
    expected = 'f1dbbe110fa60535828d31d1dad384ca3085199616c3b888e285776561036f38'
    assert hashlib.sha256(provider.read_bytes()).hexdigest()==expected
    private = BUILD/'86box/roms/scsi/adaptec'
    private.mkdir(parents=True,exist_ok=True)
    for name in ('aha1540b320_330.bin','aha1540b320_bios.bin','aha1540b320_mcode.bin'):
        if (inputs/name).exists(): shutil.copyfile(inputs/name,private/name)
    scratch=(BUILD/'tmp').resolve();scratch.mkdir(exist_ok=True)
    vm=Path(tempfile.mkdtemp(prefix='legacy-mixed-' if mixed else 'legacy-scsi-',dir=scratch))
    disk=vm/'scsi.img'
    with disk.open('xb') as out:
        out.write(sector(False,shadow));out.write(b'SCSI'+bytes(508));out.truncate(64*1024*1024)
    ata=vm/'ata.img'
    with ata.open('xb') as out:
        out.write(sector(True));out.truncate(64*1024*1024)
    roms=matrix.config(vm,ata,0,0,vm/'none-a',vm/'none-b')
    # Independent schema1 input remains; BIOS migrates old HDD-only selection.
    cfg=(vm/'86box.cfg').read_text()
    cfg=cfg.replace('hdc_1 = ide_isa','hdc_1 = ide_isa\nscsicard_1 = aha154xb')
    if not mixed:
        start=cfg.index('[Hard disks]');end=cfg.index('[Floppy and CD-ROM drives]')
        cfg=cfg[:start]+'[Hard disks]\n'+cfg[end:]
    cfg+=f'\n[Adaptec AHA-154xB #1]\nbase = 0330\nirq = 11\ndma = 6\nhostid = 7\nbios_rev = v3_20\nbios_addr = C8000\n'
    cfg=cfg.replace('[Hard disks]\n',f'[Hard disks]\nhdd_02_parameters = 32, 4, 1024, 0, scsi\nhdd_02_fn = {disk.as_posix()}\nhdd_02_speed = ramdisk\nhdd_02_scsi_location = 0:0\n')
    (vm/'86box.cfg').write_text(cfg)
    if shadow:
        # Independent saved C2 input: shadow only the card's C8000-CBFFF extent.
        policy=bytes.fromhex('96160000883830000031285555555555aa00000000070003')
        nvram=vm/'nvr/d824.nvr';cmos=bytearray(nvram.read_bytes())
        cmos[0x69:0x80]=bytes((0xC2,-(0xC2+sum(policy))&255))+policy[:21]
        cmos[0x33:0x36]=policy[21:];nvram.write_bytes(cmos)
    exe=shutil.which('86Box.exe') or str(Path(os.environ['LOCALAPPDATA'])/'Microsoft/WinGet/Packages/86Box.86Box_Microsoft.Winget.Source_8wekyb3d8bbwe/86Box.exe')
    print(f'START retained AHA154xB {"mixed" if mixed else "SCSI-only"}: {vm}',flush=True)
    wrapper=roms/'machines/d824/fts-biosupdated824noflashbiosepromv320-320334-160.bin'
    original=wrapper.read_bytes()
    if observe:
        # Observation only: all production startup/scan/summary owners execute.
        # Return code40+published count is not a successful disk-boot proof.
        source=(ROOT/'src/bios.asm').read_text()
        observation="""    xor ax,ax
    mov ds,ax
    mov bl,[0x475]
    add bl,0x40
    mov ax,0xC800
    mov es,ax
    cmp word [es:0],0xAA55
    jne .no_header
    or bl,8
.no_header:
    call load_bios_state
    test byte [fs:C_ERROR],16
    jz .no_warning
    or bl,16
.no_warning:
    cmp word [0x4E],0xC800
    jne .no_hook
    or bl,32
.no_hook:
    mov dx,0x80
    mov al,'8'
    out dx,al
    mov al,'6'
    out dx,al
    mov al,'B'
    out dx,al
    mov al,'o'
    out dx,al
    mov al,'x'
    out dx,al
    mov al,1
    out dx,al
    mov al,5
    out dx,al
    mov dx,0x501
    mov al,4
    out dx,al
    inc dx
    mov al,bl
    out dx,al
    cli
    hlt
"""
        source=source.replace('    call post_debug_summary\n','    call post_debug_summary\n'+observation,1)
        asm=vm/'observe.asm';binary=vm/'observe.rom'
        asm.write_text(source)
        nasm=shutil.which('nasm') or str(Path.home()/'AppData/Local/bin/NASM/nasm.exe')
        subprocess.run([nasm,'-f','bin','-DVGA_BIOS_141','-I',str(ROOT/'src')+'/', '-o',str(binary),str(asm)],check=True)
        data=bytearray(binary.read_bytes());data[-1]=-sum(data[:-1])&255
        wrapper.write_bytes(original[:65536]+data)
    try:
        result=matrix.run_hidden([exe,'-P',str(vm),'-R',str(roms),'-L',str(vm/'86box.log'),'-N'],timeout=timeout)
    finally:
        wrapper.write_bytes(original)
    if observe:
        value=result.returncode
        print(f'OBSERVATION retained AHA154xB actual summary; exit={value:#x}, count={value&7}, header={bool(value&8)}, ROMwarning={bool(value&16)}, INT13C800={bool(value&32)}: {vm}',flush=True)
        return vm
    if result.returncode!=0x68:
        raise RuntimeError(f'retained AHA154xB exit {result.returncode:#x}: {vm}')
    boot=ata if mixed else disk
    with boot.open('rb') as inp:inp.seek(31*512);screen=inp.read(4000)
    text=screen[::2].decode('cp437')
    lines=[text[i:i+80].rstrip() for i in range(0,2000,80)]
    capture=BUILD/('legacy-mixed-post.txt' if mixed else 'legacy-scsi-shadow-post.txt' if shadow else 'legacy-scsi-post.txt')
    capture.write_text('\n'.join(lines),encoding='utf-8')
    assert 'bAIos' in text and 'Compaq Presario 800' in text
    assert hashlib.sha256(provider.read_bytes()).hexdigest()==expected
    if shadow:
        retained=nvram.read_bytes()
        assert bytes(retained[0x6B:0x80]+retained[0x33:0x36])==policy
    print(f'PASS retained AHA154xB {"ATA80/SCSI81" if mixed else "SCSI80"} real installed INT13 signed boot/read; summary {capture}',flush=True)
    return vm


def network(fail=False,timeout=120):
    provider=ROOT.parent/'tools/86box/roms/network/ne2000/ne2000.rom'
    expected='c5ab8f6af709eaa0f550e94607c1f75477de9d61b0d58a31d2c9fb034954d120'
    assert hashlib.sha256(provider.read_bytes()).hexdigest()==expected
    private=BUILD/'86box/roms/network/ne2000';private.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(provider,private/provider.name)
    scratch=(BUILD/'tmp').resolve();scratch.mkdir(exist_ok=True)
    vm=Path(tempfile.mkdtemp(prefix='legacy-pxe-fail-' if fail else 'legacy-pxe-ok-',dir=scratch))
    def endpoint(name,result,signed=False):
        capture="""    mov ax,0x0308
    mov bx,0
    mov cx,32
    mov dx,0x80
    push word 0xB800
    pop es
    int 0x13
    xor ax,ax
    mov es,ax
    mov eax,[0x64]
    mov [0x8000],eax
    mov ax,[0x475]
    mov [0x8004],ax
    mov ax,[0x40E]
    mov fs,ax
    mov al,[fs:0x175]
    mov [0x8006],al
    mov ax,0xD000
    mov es,ax
    xor si,si
.header:
    mov al,[es:si]
    mov [0x8010+si],al
    inc si
    cmp si,32
    jb .header
    xor ax,ax
    mov es,ax
    mov ax,0x0301
    mov bx,0x8000
    mov cx,31
    mov dx,0x80
    int 0x13
""" if signed else ''
        return legacy.assemble(name,f"""bits 16
org 0x7C00
    xor ax,ax
    mov ds,ax
    mov es,ax
    cld
{capture}
    mov dx,0x80
    mov si,magic
.magic:
    lodsb
    out dx,al
    cmp si,magicend
    jb .magic
    mov dx,0x501
    mov al,4
    out dx,al
    inc dx
    mov al,{result}
    out dx,al
    cli
    hlt
magic db '86Box',1,5
magicend:
times 510-($-$$) db 0
dw {0xAA55 if signed else 0}
""")
    payload=endpoint('native-pxe-payload',0x6A)
    disk=vm/'hdd.img'
    with disk.open('xb') as out:out.write(endpoint('native-pxe-fallback',0x6B,True));out.truncate(64*1024*1024)
    roms=matrix.config(vm,disk,0,0,vm/'none-a',vm/'none-b')
    cfg=(vm/'86box.cfg').read_text().replace('net_01_card = none','net_01_card = novell_ne2k\nnet_01_net_type = nlswitch')
    cfg+='\n[Novell NE2000 #1]\nbase = 0300\nirq = 3\nmac = 86:86:10\nbios_addr = D0000\n'
    (vm/'86box.cfg').write_text(cfg)
    exe=shutil.which('86Box.exe') or str(Path(os.environ['LOCALAPPDATA'])/'Microsoft/WinGet/Packages/86Box.86Box_Microsoft.Winget.Source_8wekyb3d8bbwe/86Box.exe')
    peer=importlib.import_module('legacy-network-fixture').Peer
    print(f'START retained iPXE {"failure" if fail else "payload"}: {vm}',flush=True)
    with peer(payload,fail) as server:
        try:
            result=matrix.run_hidden([exe,'-P',str(vm),'-R',str(roms),'-L',str(vm/'86box.log'),'-N'],timeout=timeout)
        finally:
            (vm/'network-events.txt').write_text('\n'.join(server.events))
            print('Local Switch events: '+', '.join(server.events),flush=True)
    assert result.returncode==(0x6B if fail else 0x6A),(result.returncode,vm)
    assert 'OFFER' in server.events and 'ACK' in server.events and 'RRQ:baios.nbp' in server.events
    assert ('ERROR' in server.events)==fail
    assert hashlib.sha256(provider.read_bytes()).hexdigest()==expected
    print(f'PASS retained iPXE {"TFTP failure -> BIOS signed disk" if fail else "DHCP/TFTP -> distinct NBP endpoint"}',flush=True)
    return vm


def retry(timeout=120):
    """Synthetic external ROM supplies stimulus; all BIOS decisions are real."""
    guest=legacy.assemble('native-retry-sector',"""bits 16
org 0x7C00
    xor ax,ax
    mov ds,ax
    mov es,ax
    cmp word [0x600],1
    jne fail
    cmp word [0x602],3
    jne fail
    cmp byte [0x604],12
    jne fail
    cmp dl,0x80
    jne fail
    cmp sp,0x7000
    jne fail
    mov ax,[0x41A]
    cmp ax,[0x41C]
    jne fail
    ; Real OS-style output inherits the summary cursor and ordinary VGA scroll.
    cmp word [0x450],0x1100
    jne fail
    mov bp,27
.os_line:
    mov si,os_text
.os_char:
    lodsb
    test al,al
    jz .os_next
    mov ah,0x0E
    mov bx,7
    int 0x10
    jmp .os_char
.os_next:
    dec bp
    jnz .os_line
    push word 0xB800
    pop es
    cmp dword [es:0],0x0753074F ; OS output replaced the old header.
    jne fail
    mov ax,0x0308
    mov bx,0
    mov cx,32
    mov dx,0x80
    push word 0xB800
    pop es
    int 0x13
    jc fail
    mov bl,0x68
    jmp exit
fail:
    mov bl,0x69
exit:
    xor ax,ax
    mov ds,ax
    mov dx,0x80
    mov si,magic
.magic:
    lodsb
    out dx,al
    cmp si,endmagic
    jb .magic
    mov dx,0x501
    mov al,4
    out dx,al
    inc dx
    mov al,bl
    out dx,al
    cli
    hlt
magic db '86Box',1,5
endmagic:
os_text db 'OS handoff output',13,10,0
times 510-($-$$) db 0
dw 0xAA55
""")
    code=legacy.assemble('native-retry-rom',f"""bits 16
org 0
db 55h,0AAh,4
jmp init
init:
    xor ax,ax
    mov ds,ax
    mov word [0x600],1
    mov word [0x602],0
    mov byte [0x604],0
    mov word [0x64],chain
    mov word [0x66],cs
    mov word [0x70],tick
    mov word [0x72],cs
    retf
chain:
    xor ax,ax
    mov ds,ax
    inc word [0x602]
    jmp 0xF000:{legacy.rtc.symbol('int19')}
tick:
    pushad
    push ds
    push es
    push fs
    xor ax,ax
    mov ds,ax
    cmp byte [0x604],12
    jae .done
    mov ax,0xB800
    mov es,ax
    mov di,14*160             ; First failed order follows the summary.
    cmp byte [0x604],6
    jb .find
    mov di,16*160             ; A failed fresh retry visibly appends another pair.
.find:
    mov bx,di
    mov si,prompt
.match:
    mov al,[cs:si]
    test al,al
    jz .visible
    cmp al,[es:bx]
    jne .next
    add bx,2
    inc si
    jmp .match
.next:
    add di,2
    cmp di,4000
    jb .find
    jmp .done
.visible:
    cmp byte [0x49E],2
    jne .fail
    mov ax,[0x41A]
    cmp ax,[0x41C]
    jne .fail
    mov ax,1
    cmp byte [0x604],6
    jb .chain_count
    inc ax
.chain_count:
    cmp [0x602],ax
    jne .fail
    mov ax,14*160
    cmp byte [0x604],6
    jb .prompt_row
    add ax,2*160
.prompt_row:
    cmp di,ax
    jne .fail
    cmp byte [es:37*2],'b'
    jne .fail
    cmp byte [es:3*2],'C'
    jne .fail
    cmp byte [es:di-160],'N'  ; Failure result is directly above the retry prompt.
    jne .fail
    cmp word [es:12*160],0x0720 ; Blank row below the table.
    jne .fail
    inc byte [0x604]
    cmp byte [0x604],6
    je .stimulus              ; First fresh retry still has unsigned media.
    cmp byte [0x604],12
    jb .done
    call capture
    jc .fail
    ; Correct the disposable medium through its existing installed owner.
    ; The BIOS has already exhausted its entire selected order and waited.
    push cs
    pop es
    mov bx,sector
    mov ax,0x0301
    mov cx,1
    mov dx,0x80
    int 0x13
    jc .fail
    ; D2 delivers one fresh scan to the real IRQ1/INT16 consumer.
.stimulus:
    mov cx,0xFFFF
.ibf:
    in al,0x64
    test al,2
    jz .inject
    loop .ibf
    jmp .fail
.inject:
    mov al,0xD2
    out 0x64,al
    mov cx,0xFFFF
.ibf2:
    in al,0x64
    test al,2
    jz .key
    loop .ibf2
    jmp .fail
.key:
    mov al,0x1E
    out 0x60,al
.done:
    pop fs
    pop es
    pop ds
    popad
    iret
.fail:
    mov dx,0x80
    mov si,magic
.trigger:
    cs lodsb
    out dx,al
    cmp si,endmagic
    jb .trigger
    mov dx,0x501
    mov al,4
    out dx,al
    inc dx
    mov al,0x69
    out dx,al
    cli
    hlt
capture:
    mov dx,0x80
    mov si,magic
    mov cx,7
.trigger:
    cs lodsb
    out dx,al
    loop .trigger
    mov dx,0x501
    mov al,1
    out dx,al
    inc dx
    mov al,1
    out dx,al
    mov di,0xA00
    mov cx,12
.header:
    in al,dx
    mov [di],al
    inc di
    loop .header
    mov word [0x800],16
    mov word [0x802],1
    mov word [0x804],0xA00
    mov word [0x806],0
    mov dword [0x808],63
    mov dword [0x80C],0
    mov si,0x800
    mov ax,0x4300
    mov dl,0x80
    int 0x13
    jc .return
    mov word [0x804],0
    mov word [0x806],0x1000
    mov dword [0x808],64
    mov ax,[0xA00]
    shr ax,3
    mov [0x802],ax
    xor bp,bp
.tile:
    mov dx,0x501
    mov al,2
    out dx,al
    inc dx
    mov ax,[0xA00]
    call .word
    mov ax,16
    call .word
    mov ax,[0xA08]
    call .word
    mov ax,bp
    add ax,[0xA0A]
    call .word
    mov ax,0x1000
    mov es,ax
    xor di,di
    mov cx,[0xA00]
    shl cx,6
    cld
    rep insb
    mov si,0x800
    mov ax,0x4300
    mov dl,0x80
    int 0x13
    jc .return
    movzx eax,word [0x802]
    add [0x808],eax
    add bp,16
    cmp bp,[0xA02]
    jb .tile
    clc
.return:
    ret
.word:
    out dx,al
    mov al,ah
    out dx,al
    ret
prompt db 'Press any key to retry',0
magic db '86Box',1,5
endmagic:
sector:
incbin '{(BUILD/'legacy-fixtures/native-retry-sector.bin').as_posix()}'
times 2048-($-$$) db 0
""")
    image=bytearray(code);image[-1]=-sum(image[:-1])&255
    scratch=(BUILD/'tmp').resolve();scratch.mkdir(exist_ok=True)
    vm=Path(tempfile.mkdtemp(prefix='legacy-native-retry-',dir=scratch))
    disk=vm/'hdd.img'
    with disk.open('xb') as out:out.truncate(64*1024*1024)
    roms=matrix.config(vm,disk,0,0,vm/'none-a',vm/'none-b')
    cfg=(vm/'86box.cfg').read_text().replace('hdc_1 = ide_isa','hdc_1 = ide_isa\nscsicard_1 = aha154xb')
    cfg+='\n[Adaptec AHA-154xB #1]\nbase = 0330\nbios_rev = v3_20\nbios_addr = C8000\n'
    (vm/'86box.cfg').write_text(cfg)
    provider=roms/'scsi/adaptec/aha1540b320_330.bin'
    original=provider.read_bytes()
    exe=shutil.which('86Box.exe') or str(Path(os.environ['LOCALAPPDATA'])/'Microsoft/WinGet/Packages/86Box.86Box_Microsoft.Winget.Source_8wekyb3d8bbwe/86Box.exe')
    print('START synthetic external native retry stimulus: '+str(vm),flush=True)
    provider.write_bytes(bytes(image)+bytes(16384-len(image)))
    try:
        result=matrix.run_hidden([exe,'-P',str(vm),'-R',str(roms),'-N'],timeout=timeout)
    finally:provider.write_bytes(original)
    assert provider.read_bytes()==original
    assert result.returncode==0x68,(result.returncode,vm)
    with disk.open('rb') as inp:
        inp.seek(63*512);width,height=struct.unpack('<HH',inp.read(4))
        assert width in (640,720) and height==400,(width,height)
        inp.seek(64*512);pixels=inp.read(width*height*4)
    capture=BUILD/'legacy-native-retry.png'
    # Same dependency-free BGRX encoder as the existing native Setup capture.
    rows=bytearray()
    for row in range(height):
        rows.append(0)
        for col in range(width):
            offset=(row*width+col)*4
            rows.extend(pixels[offset:offset+3][::-1])
    def chunk(kind,data):
        return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data))
    capture.write_bytes(b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',width,height,8,2,0,0,0))+
                        chunk(b'IDAT',zlib.compress(rows))+chunk(b'IEND',b''))
    print('Actual retained-VGA retry capture: '+str(capture),flush=True)
    print('PASS synthetic native ROM stimulus -> stable full-order prompt/twelve timer waits/failed fresh retry/media correction/fresh IRQ1/installed19/reset/signedBOOT, one ROM init',flush=True)
    return vm


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case',choices=('scsi','scsi-shadow','mixed','pxe','pxe-failure','retry'),action='append')
    parser.add_argument('--timeout',type=int,default=180)
    parser.add_argument('--observe',action='store_true',help='Bounded summary publication observation, not a boot proof')
    args=parser.parse_args()
    for name in args.case or ('scsi','mixed','pxe','pxe-failure'):
        if name.startswith('pxe'):network(name=='pxe-failure',args.timeout)
        elif name=='retry':retry(args.timeout)
        elif name=='scsi-shadow':scsi(False,args.timeout,args.observe,shadow=True)
        else:scsi(name=='mixed',args.timeout,args.observe)
