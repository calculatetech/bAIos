; Read-only snapshot for the current M919 runtime layout. No ATA commands.
; P0=host allowed, P2=controller. Revisions are informational.
; I=IDE ID, V=IDE/sibling revisions, B=BDF, U=enabled/usable.
; X=blocked channel mask; position R/L/E=request/limit/effective, S=current status.
bits 16
org 0x100
%define BOARD_ATA_DEVICE_COUNT 4
%include "pc/state.inc"
%ifndef STATE_KIB
%error "Pass the configured runtime size"
%endif
; Private M919 offsets are checked against board-definition.inc by the runner.
%define HW_IDE_BDF 0x1034
%define HW_IDE_USABLE 0x1039
start:
    mov ax,cs
    mov ds,ax
    mov es,ax
    mov ss,ax
    mov sp,stack_top
    cld
    smsw ax
    test al,1
    jnz protected_dos
    xor ax,ax
    mov es,ax
    mov ax,[es:0x40E]
    cmp ax,0x8000
    jb invalid_state
    cmp ax,0xA000-STATE_KIB*64
    ja invalid_state
    mov es,ax
    cmp byte [es:0],STATE_KIB
    jne invalid_state
    pushfd
    cli
    mov al,[es:C_IDE]
    mov [enabled],al
    mov al,[es:HW_IDE_USABLE]
    mov [usable],al
    mov ax,[es:HW_IDE_BDF]
    mov [bdf],ax
    mov al,[es:S_PIO_BLOCKED]
    mov [blocked],al
    xor bx,bx
    mov di,records
    mov cx,4
.record:
    mov al,[es:bx+S_PRESENT]
    mov [di],al
    mov al,[es:bx+S_ATAPI]
    mov [di+1],al
    mov al,[es:bx+S_PIO_REQUEST]
    mov [di+2],al
    mov al,[es:bx+S_PIO_LIMIT]
    mov [di+3],al
    mov al,[es:bx+S_PIO_MODE]
    mov [di+4],al
    mov al,[es:bx+S_STATUS]
    mov [di+5],al
    add di,6
    add bx,512
    loop .record
    cmp word [bdf],0xFFFF
    je .pci_done
    mov dx,0xCF8
    in eax,dx
    mov [saved_cf8],eax
    movzx ebx,word [bdf]
    shl ebx,8
    or ebx,0x80000000
    mov eax,ebx
    call pci_read
    mov [identity],eax
    mov eax,ebx
    or al,8
    call pci_read
    mov [ide_revision],al
    mov eax,ebx
    and ax,0xF8FF
    or al,8
    call pci_read
    mov [sibling_revision],al
    mov dx,0xCF8
    mov eax,[saved_cf8]
    out dx,eax
.pci_done:
    popfd
    mov al,'2'
    cmp byte [enabled],1
    jne .gate
    cmp byte [usable],1
    jne .gate
    mov bx,[bdf]
    and bl,7
    cmp bl,1
    jne .gate
    cmp dword [identity],0x673A1060
    jne .gate
    mov al,'0'
.gate:
    push ax
    mov al,'P'
    call putc
    pop ax
    call putc
    mov si,id_label
    call puts
    mov eax,[identity]
    mov cx,8
    call hex32
    mov si,revision_label
    call puts
    mov al,[ide_revision]
    call hex8
    mov al,'/'
    call putc
    mov al,[sibling_revision]
    call hex8
    mov si,bdf_label
    call puts
    mov eax,0
    mov ax,[bdf]
    shl eax,16
    mov cx,4
    call hex32
    mov si,usable_label
    call puts
    mov al,[enabled]
    call nibble
    mov al,[usable]
    call nibble
    mov si,blocked_label
    call puts
    mov al,[blocked]
    call nibble
    xor bx,bx
    mov si,records
.device:
    cmp byte [si],1
    je .present
    cmp byte [si+1],1
    jne .next
.present:
    mov al,' '
    call putc
    mov al,bl
    call nibble
    mov al,'R'
    call putc
    mov al,[si+2]
    call nibble
    mov al,'L'
    call putc
    mov al,[si+3]
    call nibble
    mov al,'E'
    call putc
    mov al,[si+4]
    call nibble
    mov al,'S'
    call putc
    mov al,[si+5]
    call hex8
    mov al,'D'
    cmp byte [si+1],1
    jne .type
    mov al,'C'
.type:
    call putc
.next:
    add si,6
    inc bl
    cmp bl,4
    jb .device
    mov si,newline
    jmp finish
protected_dos:
    mov si,protected_text
    jmp finish
invalid_state:
    mov si,state_text
finish:
    call puts
    mov ax,0x4C00
    int 0x21
pci_read:
    mov dx,0xCF8
    out dx,eax
    mov dx,0xCFC
    in eax,dx
    ret
hex32:
    rol eax,4
    push eax
    call nibble
    pop eax
    loop hex32
    ret
hex8:
    push ax
    shr al,4
    call nibble
    pop ax
    jmp nibble
nibble:
    and al,15
    add al,'0'
    cmp al,'9'
    jbe putc
    add al,7
putc:
    push ax
    push dx
    mov dl,al
    mov ah,2
    int 0x21
    pop dx
    pop ax
    ret
puts:
    lodsb
    test al,al
    jz .done
    call putc
    jmp puts
.done:
    ret
id_label db ' I',0
revision_label db ' V',0
bdf_label db ' B',0
usable_label db ' U',0
blocked_label db ' X',0
newline db 13,10,0
protected_text db 'N0 plain DOS required',13,10,0
state_text db 'N1 invalid bAIos state',13,10,0
enabled db 0
usable db 0
blocked db 0
bdf dw 0xFFFF
identity dd 0xFFFFFFFF
ide_revision db 0xFF
sibling_revision db 0xFF
saved_cf8 dd 0
records times 24 db 0
times 256 db 0
stack_top:
