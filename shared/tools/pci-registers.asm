bits 16
org 0x100
%include "configuration.inc"

start:
    push cs
    pop ds
    push cs
    pop es
    cld
    mov ax,0xB101
    int 0x1A
    jc unavailable
    test ah,ah
    jnz unavailable
    cmp edx,0x20494350
    jne unavailable
    xor di,di
    mov si,registers
read_register:
    mov bx,CFG_PLATFORM_HOST_PCI_DEVICE << 3
    mov ax,0xB108
    int 0x1A
    jc read_failed
    test ah,ah
    jnz read_failed
    mov [si],cl
    inc si
    inc di
    cmp di,256
    jb read_register
    mov dx,header
    mov cx,header_end-header
    call stdout
    jc output_failed
    xor bp,bp
    mov si,registers
row:
    mov di,line
    mov ax,bp
    call hex_byte
    mov ax,0x203A
    stosw
    mov cx,16
column:
    lodsb
    call hex_byte
    mov al,' '
    stosb
    loop column
    mov ax,0x0A0D
    stosw
    mov dx,line
    mov cx,54
    call stdout
    jc output_failed
    add bp,16
    cmp bp,256
    jb row
    mov ax,0x4C00
    int 0x21

unavailable:
    mov dx,no_pci
    mov cx,no_pci_end-no_pci
    jmp error
read_failed:
    mov dx,ax
    mov ax,di
    mov di,read_error_offset
    call hex_byte
    mov al,dh
    mov di,read_error_status
    call hex_byte
    mov dx,read_error
    mov cx,read_error_end-read_error
error:
    call stdout
    mov ax,0x4C02
    int 0x21
output_failed:
    mov ax,0x4C01
    int 0x21

stdout:
    push bx
    mov bx,1
    mov ah,0x40
    int 0x21
    pop bx
    jc .done
    cmp ax,cx
    je .done
    stc
.done:
    ret

hex_byte:
    push ax
    mov ah,al
    shr al,4
    call .digit
    mov al,ah
    and al,15
    call .digit
    pop ax
    ret
.digit:
    cmp al,9
    jbe .number
    add al,7
.number:
    add al,'0'
    stosb
    ret

header db CFG_PLATFORM_HOST_BRIDGE,' host PCI configuration (read only)',13,10
header_end:
no_pci db 'PCI BIOS unavailable.',13,10
no_pci_end:
read_error db 'PCI read failed at '
read_error_offset db '00',' status '
read_error_status db '00',13,10
read_error_end:
registers times 256 db 0
line times 54 db 0
