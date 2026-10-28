bits 16
cpu 386
org 0x100

start:
    push cs
    pop ds
    push cs
    pop es
    cld
    smsw ax
    test al,1
    jnz protected_mode
    mov eax,cr0
    mov [saved_cr0],eax
    pushf
    cli
    in al,0xF2
    mov [saved_index],al
    in al,0x78
    mov [jumpers],al
    in al,0x92
    mov [system_control],al
    mov si,registers
    mov cx,register_count
.read:
    lodsb
%ifdef ACC_CMOS
    out 0x70,al
    in al,0x84
    in al,0x71
%else
    out 0xF2,al
    out 0xED,al
    in al,0xF3
    out 0xED,al
%endif
    mov [si],al
    inc si
    loop .read
%ifdef ACC_CMOS
    xor al,al
    out 0x70,al
%else
    mov al,[saved_index]
    out 0xF2,al
    out 0xED,al
%endif
    popf

    mov edx,[saved_cr0]
    mov di,cr0_text
    mov cx,4
.cr0:
    rol edx,8
    mov al,dl
    call hex_byte
    loop .cr0
    mov al,[jumpers]
    mov di,jumper_text
    call hex_byte
    mov al,[system_control]
    mov di,system_text
    call hex_byte
    mov si,registers
    mov di,dump_text
    mov cx,register_count
    xor bx,bx
.format:
    lodsb
    call hex_byte
    mov al,'='
    stosb
    lodsb
    call hex_byte
    mov al,' '
    stosb
    inc bx
    test bl,7
    jnz .next
    mov ax,0x0A0D
    stosw
.next:
    loop .format
    mov ax,0x0A0D
    stosw
    mov dx,output
    mov cx,output_end-output
    call stdout
    jc output_failed
    mov ax,0x4C00
    int 0x21

protected_mode:
    mov dx,mode_error
    mov cx,mode_error_end-mode_error
    call stdout
    jc output_failed
    mov ax,0x4C02
    int 0x21
output_failed:
    mov ax,0x4C01
    int 0x21

; Keep DOS output and its redirection outside the indexed-read critical section.
stdout:
    mov bx,1
    mov ah,0x40
    int 0x21
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

saved_cr0 dd 0
saved_index db 0
jumpers db 0
system_control db 0
; Reference BIOS registers plus the requested related-chip timing registers.
registers:
%ifdef ACC_CMOS
%rep 2
%assign index 0x10
%rep 0x70
    db index,0
%assign index index+1
%endrep
%endrep
%else
%assign index 0
%rep 0x14
    db index,0
%assign index index+1
%endrep
    db 0x14,0, 0x16,0, 0x18,0, 0x19,0
    db 0x1A,0, 0x1B,0, 0x1C,0, 0x1D,0, 0x1E,0, 0x25,0, 0x26,0, 0x37,0
%endif
register_count equ ($-registers)/2

%ifdef ACC_CMOS
output db 'PB430 CMOS snapshot - two reads of 10-7F; no data writes',13,10
%else
output db 'ACC chipset snapshot - PB430 only; no configuration writes',13,10
%endif
    db 'CR0='
cr0_text db '00000000  P78='
jumper_text db '00  P92='
system_text db '00',13,10
dump_text times register_count*6+(register_count/8)*2+2 db 0
output_end:
%ifdef ACC_CMOS
mode_error db 'Boot plain DOS without EMM386 or Windows, then run ACCCMOS.',13,10
%else
mode_error db 'Boot plain DOS without EMM386 or Windows, then run ACCDUMP.',13,10
%endif
mode_error_end:
