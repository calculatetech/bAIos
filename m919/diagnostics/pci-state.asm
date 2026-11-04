; Plain DOS comparison through PCI BIOS byte reads. No direct I/O or VGA access.
bits 16
org 0x100
%include "configuration.inc"
start:
    cld
    push cs
    pop ds
    smsw ax
    test al,1
    jnz protected_dos
    mov ax,0xB101
    int 0x1A
    jc unavailable
    test ah,ah
    jnz unavailable
    cmp edx,0x20494350
    jne unavailable
    ; Snapshot activity and IDE state before DOS output can change either.
    call capture_extra
    mov si,title
    call puts
    mov word [bdf],CFG_PLATFORM_HOST_PCI_DEVICE << 3
    call heading
    xor bp,bp
    mov cx,0x64
    call dump_range
    mov word [bdf],CFG_PLATFORM_ISA_PCI_DEVICE << 3
    call heading
    xor bp,bp
    mov cx,0x58
    call dump_range
    mov bp,0xA4
    mov cx,1
    call dump_range
    mov si,vga_title
    call puts
    mov ax,0xB103
    mov ecx,0x030000
    xor si,si
    int 0x1A
    jc no_vga
    test ah,ah
    jnz no_vga
    mov [bdf],bx
    call heading
    xor bp,bp
    mov cx,0x40
    call dump_range
done:
    mov word [bdf],CFG_PLATFORM_ISA_PCI_DEVICE << 3
    call heading
    mov si,extra_title
    call puts
    test byte [extra_valid],1
    jz .no_ibc
    mov si,ibc_indices
    mov di,ibc_values
    mov cx,ibc_count
    call print_extra
    jmp .ide
.no_ibc:
    mov si,wrong_ibc
    call puts
.ide:
    mov word [bdf],(CFG_PLATFORM_ISA_PCI_DEVICE << 3) | 1
    call heading
    mov si,extra_title
    call puts
    mov eax,[ide_identity]
    call hex32
    mov si,newline
    call puts
    test byte [extra_valid],2
    jz .no_ide
    mov si,ide_indices
    mov di,ide_values
    mov cx,ide_count
    call print_extra
    jmp .complete
.no_ide:
    mov si,wrong_ide
    call puts
.complete:
    mov si,complete
    call puts
    mov ax,0x4C00
    int 0x21
no_vga:
    mov si,no_vga_message
    call puts
    jmp done
protected_dos:
    mov si,real_message
    jmp error
unavailable:
    mov si,no_pci
    jmp error
read_failed:
    call heading
    mov si,read_error
    call puts
    mov ax,bp
    call hex8
    mov si,status_message
    call puts
    mov al,[status]
    call hex8
    mov si,newline
error:
    call puts
    mov ax,0x4C02
    int 0x21
capture_extra:
    mov word [bdf],CFG_PLATFORM_ISA_PCI_DEVICE << 3
    mov di,ibc_identity
    call capture_identity
    cmp dword [ibc_identity],0x886A1060
    jne .ide
    mov si,ibc_indices
    mov di,ibc_values
    mov cx,ibc_count
    call capture_indices
    or byte [extra_valid],1
.ide:
    mov word [bdf],(CFG_PLATFORM_ISA_PCI_DEVICE << 3) | 1
    mov di,ide_identity
    call capture_identity
    cmp dword [ide_identity],0x673A1060
    jne .done
    mov si,ide_indices
    mov di,ide_values
    mov cx,ide_count
    call capture_indices
    or byte [extra_valid],2
.done:
    ret
capture_identity:
    xor bp,bp
    mov cx,4
.byte:
    call read_byte
    jc read_failed
    mov al,[value]
    mov [di],al
    inc di
    inc bp
    loop .byte
    ret
capture_indices:
    lodsb
    movzx bp,al
    call read_byte
    jc read_failed
    mov al,[value]
    mov [di],al
    inc di
    loop capture_indices
    ret
print_extra:
    mov bp,8
.byte:
    lodsb
    call hex8
    mov al,'='
    call character
    mov al,[di]
    inc di
    call hex8
    mov al,' '
    call character
    dec bp
    jnz .next
    push si
    mov si,newline
    call puts
    pop si
    mov bp,8
.next:
    loop .byte
    cmp bp,8
    je .done
    mov si,newline
    call puts
.done:
    ret
heading:
    mov si,pci_title
    call puts
    mov ax,[bdf]
    mov al,ah
    call hex8
    mov al,':'
    call character
    mov ax,[bdf]
    shr al,3
    call hex8
    mov al,'.'
    call character
    mov al,[bdf]
    and al,7
    call hex_nibble
    mov si,newline
    call puts
    ret
dump_range:
.row:
    mov ax,bp
    call hex8
    mov al,':'
    call character
    mov al,' '
    call character
    ; Publish the current row before invoking firmware, even on redirected output.
    call flush
    mov di,16
.byte:
    call read_byte
    jc read_failed
    mov al,[value]
    call hex8
    mov al,' '
    call character
    inc bp
    dec di
    loop .more
    jmp .end
.more:
    test di,di
    jnz .byte
.end:
    mov si,newline
    call puts
    test cx,cx
    jnz .row
    ret
read_byte:
    pushad
    mov bx,[bdf]
    mov di,bp
    mov ax,0xB108
    int 0x1A
    mov [status],ah
    jc .failed
    test ah,ah
    jnz .failed
    mov [value],cl
    popad
    clc
    ret
.failed:
    popad
    stc
    ret
hex32:
    pushad
    mov cx,8
.digit:
    rol eax,4
    push eax
    call hex_nibble
    pop eax
    loop .digit
    popad
    ret
hex8:
    push ax
    shr al,4
    call hex_nibble
    pop ax
    push ax
    and al,15
    call hex_nibble
    pop ax
    ret
hex_nibble:
    push ax
    and al,15
    add al,'0'
    cmp al,'9'
    jbe .print
    add al,7
.print:
    call character
    pop ax
    ret
character:
    pushad
    mov bx,[used]
    mov [output+bx],al
    inc bx
    mov [used],bx
    cmp al,10
    je .flush
    cmp bx,128
    jb .done
.flush:
    call flush
.done:
    popad
    ret
puts:
    pushad
.next:
    lodsb
    test al,al
    jz .done
    call character
    jmp .next
.done:
    popad
    ret
flush:
    pushad
    mov cx,[used]
    jcxz .done
    mov word [used],0
    mov dx,output
    mov bx,1
    mov ah,0x40
    int 0x21
    jc output_error
    cmp ax,cx
    jne output_error
.done:
    popad
    ret
output_error:
    mov ax,0x4C01
    int 0x21
title db 'PCISTATE 3 - PCI BIOS byte reads; PM/IDE startup snapshot',13,10,0
pci_title db 'PCI ',0
vga_title db 'VGA lookup',13,10,0
complete db 'Complete.',13,10,0
no_vga_message db 'VGA lookup unavailable; bridge capture retained.',13,10,0
real_message db 'Run in plain DOS without EMM386 or another protected manager.',13,10,0
no_pci db 'PCI BIOS unavailable.',13,10,0
read_error db 'PCI read failed at ',0
status_message db ' status ',0
newline db 13,10,0
extra_title db 'Startup snapshot (offset=value): ',13,10,0
wrong_ibc db 'UM8886BF ID not matched; extra bridge reads skipped.',13,10,0
wrong_ide db 'UM8886BF IDE ID not matched; private IDE reads skipped.',13,10,0
; Only documented/source-observed control windows; no ATA ports or gap sweep.
ibc_indices db 0x70,0x71,0x72,0x73,0x74,0x76,0x80,0x81,0x82,0x83
            db 0x90,0x91,0x92,0x93,0xA0,0xA2,0xA3,0xA4,0xA7,0xA8
ibc_count equ $-ibc_indices
ide_indices db 4,5,6,7,8,9,10,11,12,13,14,15,0x3C
%assign index 0x40
%rep 0x1A
    db index
%assign index index+1
%endrep
ide_count equ $-ide_indices
extra_valid db 0
ibc_identity dd 0
ide_identity dd 0
ibc_values times ibc_count db 0
ide_values times ide_count db 0
bdf dw 0
status db 0
value db 0
used dw 0
output times 128 db 0
