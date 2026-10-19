; build-speedsys-probe.py inserts unchanged application routines at their
; original offsets. This DOS probe writes VGA memory only, not disk sectors.
bits 16
org 0x100
start:
    smsw ax
    test al, 1
    mov al, 0x7C
    jnz fail                   ; Run from clean DOS, not EMM386/V86.
    mov ax, cs
    add ax, 0x1420
    cmp ax, [2]                ; DOS-owned allocation covers private scratch.
    mov al, 0x7D
    ja fail
    in al, 0x61
    mov [saved_port61], al
    mov ax, cs
    add ax, 0x1000
    mov es, ax
    mov ds, ax
    xor di, di
    xor ax, ax
    mov cx, 0x2000
    cld
    rep stosw
    mov ax, cs
    add ax, 0x1400
    mov [0x19], ax             ; Original VBE buffer is ES:0000.
    cmp byte [cs:0x80], 0
    je .plain
    o32 sgdt [cs:saved_gdtr]
    mov byte [cs:unreal], 1
    call 0xA3BB                ; Any argument: original unreal-mode/A20 setup.
    mov al, 0x7E
    jc fail
.plain:
    xor ax, ax
    mov es, ax
    cli
    mov eax, [es:0x20]
    mov [cs:0xA303], eax
    mov word [es:0x20], 0xA340
    mov [es:0x22], cs
    mov byte [cs:installed], 1
    sti
    call 0x5F41                ; Exact VBE mode/fill/timer sequence.
    cmp byte [0x3594], 0
    mov al, 0x7B
    je fail
    mov ax, 3
    int 0x10
    mov ax, 0x12
    int 0x10
    call check_irq_registers
    push word .verified
    pusha
    push gs
    mov ax, 8
    mov bx, 8
    mov cx, 623
    mov dx, 463
    mov bp, 11
    call 0xA640                ; Exact rectangle, including GC word writes.
    jmp check_direct_planar.verify
.verified:
    mov al, 0x67

fail:
    mov [cs:result], al
    cli
    cmp byte [cs:installed], 0
    je .restored
    xor ax, ax
    mov es, ax
    mov eax, [cs:0xA303]
    mov [es:0x20], eax
    mov al, [cs:saved_port61]
    out 0x61, al
.restored:
    cmp byte [cs:unreal], 0
    je .gdtr_restored
    o32 lgdt [cs:saved_gdtr]
.gdtr_restored:
    sti
    mov ax, 3
    int 0x10
    push cs
    pop ds
    mov al, [result]
    mov ah, al
    shr al, 4
    call hex
    mov [digits], al
    mov al, ah
    and al, 15
    call hex
    mov [digits + 1], al
    mov dx, message
    mov ah, 9
    int 0x21
%ifdef EMULATOR_TEST
    mov dx, 0x80
    mov al, '8'
    out dx, al
    mov al, '6'
    out dx, al
    mov al, 'B'
    out dx, al
    mov al, 'o'
    out dx, al
    mov al, 'x'
    out dx, al
    mov al, 1
    out dx, al
    mov al, 5
    out dx, al
    mov dx, 0x501
    mov al, 4
    out dx, al
    inc dx
    mov al, [result]
    out dx, al
%endif
    mov al, [result]
    mov ah, 0x4C
    int 0x21
hex:
    add al, '0'
    cmp al, '9'
    jbe .done
    add al, 7
.done:
    ret
message: db 'SPEEDRAW result: '
digits: db '00 (67=PASS, 7A=planar data, 7B=no VBE mode)',13,10,'$'
installed: db 0
saved_port61: db 0
result: db 0
unreal: db 0
saved_gdtr: times 6 db 0
irq_poll_limit: dd 0
irq_rounds: db 0

; The real application leaves full-width counters live across timer IRQs.
; No BIOS calls in the wait; compare all seven GPRs after actual ticks.
check_irq_registers:
    pushad
    mov byte [cs:irq_rounds], 4
.round:
    cli
    mov word [cs:0xA350], 0
    mov dword [cs:irq_poll_limit], 0x400000
    mov eax, 0x12345678
    mov ebx, 0x23456789
    mov ecx, 0x3456789A
    mov edx, 0x456789AB
    mov esi, 0x56789ABC
    mov edi, 0x6789ABCD
    mov ebp, 0x789ABCDE
    sti
.wait:
    cmp word [cs:0xA350], 0
    jne .check
    dec dword [cs:irq_poll_limit]
    jnz .wait
    mov al, 0x7F
    jmp fail
.check:
    cmp eax, 0x12345678
    jne .eax_bad
    cmp ebx, 0x23456789
    jne .ebx_bad
    cmp ecx, 0x3456789A
    jne .ecx_bad
    cmp edx, 0x456789AB
    jne .edx_bad
    cmp esi, 0x56789ABC
    jne .esi_bad
    cmp edi, 0x6789ABCD
    jne .edi_bad
    cmp ebp, 0x789ABCDE
    jne .ebp_bad
    dec byte [cs:irq_rounds]
    jnz .round
    popad
    ret
.eax_bad:
    mov al, 0x60
    jmp fail
.ebx_bad:
    mov al, 0x61
    jmp fail
.ecx_bad:
    mov al, 0x62
    jmp fail
.edx_bad:
    mov al, 0x63
    jmp fail
.esi_bad:
    mov al, 0x64
    jmp fail
.edi_bad:
    mov al, 0x65
    jmp fail
.ebp_bad:
    mov al, 0x66
    jmp fail
%include "planar-check.inc"
times 0xA7A2 - ($ - $$ + 0x100) db 0
