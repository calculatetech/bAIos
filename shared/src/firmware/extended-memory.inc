move_extended_memory:
    pushad
    push ds
    push es
    sub sp, 6
    mov di, sp
    sgdt [ss:di]
    smsw ax
    test al, 1
    jnz .invalid
    cmp cx, 0x8000
    ja .invalid
    cmp si, 0xFFD0
    ja .invalid
    mov bx, si
    mov esi, [es:bx + 0x12]
    and esi, 0x00FFFFFF
    movzx eax, byte [es:bx + 0x17]
    shl eax, 24
    or esi, eax
    mov edi, [es:bx + 0x1A]
    and edi, 0x00FFFFFF
    movzx eax, byte [es:bx + 0x1F]
    shl eax, 24
    or edi, eax
    movzx ecx, cx
    mov eax, ecx
    shl eax, 1
    add eax, esi
    jc .invalid
    mov eax, ecx
    shl eax, 1
    add eax, edi
    jc .invalid
    ; Temporarily enable fast A20 and restore its exact prior gate state.
    board_a20_read
    mov dl, al
    and al, 0xFE
    or al, 2
    board_a20_write
    mov al, 0x80
    out 0x70, al
    lgdt [cs:move_gdtr]
    mov ebx, cr0
    mov eax, ebx
    or al, 1
    mov cr0, eax
    jmp 0x08:.protected
.protected:
    mov ax, 0x10
    mov ds, ax
    mov es, ax
    cld
    a32 rep movsw
    ; Restore real-mode data limits before leaving protected mode.
    mov ax, 0x18
    mov ds, ax
    mov es, ax
    mov cr0, ebx
    jmp 0xF000:.real
.real:
    mov di, sp
    o32 lgdt [ss:di]
    mov al, dl
    and al, 0xFE
    board_a20_write
    xor al, al
    out 0x70, al
    clc
    jmp .return
.invalid:
    stc
.return:
    mov di, sp
    lea sp, [di + 6]
    pop es
    pop ds
    popad
    ret

align 8
move_gdt:
    dq 0
    dw 0xFFFF, 0x0000
    db 0x0F, 0x9B, 0x00, 0x00 ; 16-bit BIOS code, accessed bit already set.
    dw 0xFFFF, 0x0000
    db 0x00, 0x93, 0x8F, 0x00 ; Flat 4 GiB data.
    dw 0xFFFF, 0x0000
    db 0x00, 0x93, 0x00, 0x00 ; Real-mode 64 KiB data limits.
move_gdtr:
    dw $ - move_gdt - 1
    dd 0xF0000 + move_gdt

