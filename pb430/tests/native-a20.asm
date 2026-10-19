bits 16
org 0x7C00
%include "test-configuration.inc"
jmp short start
times 11-($-$$) db 0
dw 512
db 1
dw 1
times 24-($-$$) db 0
dw 63,16
dd 0
times 62-($-$$) db 0
start:
    mov ax,ss
    test ax,ax
    jnz bad
    cmp sp,0x7000
    jne bad
    xor ax,ax
    mov ds,ax
    cli
    in al,0x92
    test al,3
    jnz bad
    mov [fast_saved],al
    call read_output
    test al,2
    jz bad
    mov [output_saved],al
    mov word [0x800],0xA11A
    mov word [0x1800],0xD44D
    mov ax,0xFFFF
    mov es,ax
    mov word [es:0x810],0xB22B
    mov word [es:0x1810],0xC33C
    mov al,[output_saved]
    and al,0xFD
    call write_output
    cmp word [es:0x810],0xA11A ; FFFF:0810 physically wraps to000800.
    jne bad
    xor ax,ax
    mov es,ax
    mov si,move_table
    mov cx,1
    mov ax,0x8700
    int 0x15
    jc bad
    test ah,ah
    jnz bad
    in al,0x92
    cmp al,[fast_saved]
    jne bad
    mov ax,0xFFFF
    mov es,ax
    cmp word [es:0x1810],0xD44D ; Public move restores both-off wrapping.
    jne bad
    mov al,[output_saved]
    call write_output
    cmp word [es:0x810],0xB22B
    jne bad
    cmp word [es:0x1810],0xB22B ; AH87 read/copy used physical high RAM.
    jne bad
    cmp word [0x800],0xA11A
    jne bad
    cmp word [0x1800],0xD44D
    jne bad
    sti
    int 0x12
    cmp ax,632
    jne bad
    mov ah,0x88
    int 0x15
    jc bad
    cmp ax,TEST_RAM_KIB-1024
    jne bad
    ; Reuse the native terminal's complete text and original-font exports.
    mov si,dump_packet
    mov ax,0x4300
    mov dl,0x80
    int 0x13
    jc bad
    push ds
    mov ax,0x1130
    mov bh,6
    int 0x10
    pop ds
    mov [dump_packet+4],bp
    mov [dump_packet+6],es
    mov dword [dump_packet+8],9
    mov si,dump_packet
    mov ax,0x4300
    mov dl,0x80
    int 0x13
    jc bad
    mov al,0x60
    jmp terminal
read_output:
    call wait_input
    mov al,0xD0
    out 0x64,al
    mov cx,0xFFFF
.wait:
    in al,0x64
    test al,1
    jnz .ready
    loop .wait
    jmp bad
.ready:
    in al,0x60
    ret
write_output:
    push ax
    call wait_input
    mov al,0xD1
    out 0x64,al
    call wait_input
    pop ax
    out 0x60,al
    call wait_input
    ret
wait_input:
    mov cx,0xFFFF
.wait:
    in al,0x64
    test al,2
    jz .ready
    loop .wait
    jmp bad
.ready:
    ret
bad:
    mov al,0x62
    jmp terminal
fast_saved db 0
output_saved db 0
move_table:
    times 16 db 0
    dw 0xFFFF,0x0800
    db 0x10,0x93,0,0
    dw 0xFFFF,0x1800
    db 0x10,0x93,0,0
    times 16 db 0
dump_packet db 0x10,0
    dw 8,0,0xB800
    dq 1
%include "test-terminal.inc"
times 510-($-$$) db 0
dw 0xAA55
