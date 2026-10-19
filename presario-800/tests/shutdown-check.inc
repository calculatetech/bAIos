; Code0A software entry proves full EDX preservation. Code05 uses a real
; 8042 CPU reset, like NSSI CID_Check_M1. Neither may initialize POST RAM.
shutdown_check_begin:
    pushf
    cli
    pushad
    push ds
    push es
    mov [cs:shutdown_sp], sp
    mov [cs:shutdown_ss], ss
    in al, 0x21
    mov [cs:shutdown_pic], al
    in al, 0xA1
    mov [cs:shutdown_pic + 1], al
    mov eax, cr0
    mov [cs:shutdown_cr0], eax
    mov eax, [0x0467]
    mov [cs:shutdown_old_vector], eax
    mov ax, [0x0500]
    mov [cs:shutdown_old_word], ax
    mov word [0x0500], 0xA55A
    mov byte [cs:shutdown_phase], 0
    mov bl, 0x0A
shutdown_request:
    ; Snapshot the retained RAM, timing, bus, shadow and cache registers.
    out 0xFB, al
    xor si, si
    mov cx, 0x19
.snapshot:
    mov ax, si
    inc ax
    out 0xEC, al
    in al, 0xED
    mov [cs:shutdown_chipset+si], al
    inc si
    loop .snapshot
    out 0xF9, al
    ; Both entry types must restore L1, not just reset-default hardware05.
    wbinvd
    mov eax, cr0
    or eax, 0x60000000
    mov cr0, eax
    mov word [0x0467], shutdown_return
    mov word [0x0469], cs
    mov al, 0x8F
    out 0x70, al
    in al, 0x84
    mov al, bl
    out 0x71, al
    mov edx, 0x12345678
    cmp byte [cs:shutdown_phase], 0
    jne shutdown_hardware
    jmp 0xF000:0xFFF0
shutdown_hardware:
    mov cx, 0xFFFF
.wait:
    in al, 0x64
    test al, 2
    jz .ready
    loop .wait
    mov al, 0x57
    jmp fail
.ready:
    wbinvd
    mov al, 0xFE
    out 0x64, al
.halt:
    hlt
    jmp .halt
shutdown_return:
    cli
    mov ax, [cs:shutdown_ss]
    mov ss, ax
    mov sp, [cs:shutdown_sp]
    xor ax, ax
    mov ds, ax
    mov es, ax
    cmp byte [cs:shutdown_phase], 0
    jne .signature
    cmp edx, 0x12345678
    jne .bad
    jmp .state
.signature:
    ; The test machine is an Intel i486DX (family4); stepping may vary.
    and edx, 0xFFFFFF00
    cmp edx, 0x00000400
    jne .bad
.state:
    out 0xFB, al
    xor si, si
    mov cx, 0x19
.retained:
    mov ax, si
    inc ax
    out 0xEC, al
    in al, 0xED
    cmp al, [cs:shutdown_chipset+si]
    jne .bad
    inc si
    loop .retained
    out 0xF9, al
    ; Check before restoring caller CR0: that restoration hid disabled L1.
    mov eax, cr0
    test eax, 0x60000000
    jnz .bad
    mov eax, [cs:shutdown_cr0]
    mov cr0, eax
    ; A reset caller restores its interrupt environment (NSSI saves21h).
    mov al, [cs:shutdown_pic]
    out 0x21, al
    mov al, [cs:shutdown_pic + 1]
    out 0xA1, al
    mov al, 0x8F
    out 0x70, al
    in al, 0x84
    in al, 0x71
    test al, al
    jnz .bad
    cmp word [0x0500], 0xA55A
    jne .bad
    cmp byte [cs:shutdown_phase], 0
    jne .done
    inc byte [cs:shutdown_phase]
    mov bl, 0x05
    jmp shutdown_request
.bad:
    mov al, 0x57
    jmp fail
.done:
    mov eax, [cs:shutdown_old_vector]
    mov [0x0467], eax
    mov ax, [cs:shutdown_old_word]
    mov [0x0500], ax
    xor al, al
    out 0x70, al
    pop es
    pop ds
    popad
    popf
    jmp shutdown_check_done
shutdown_sp: dw 0
shutdown_ss: dw 0
shutdown_cr0: dd 0
shutdown_old_vector: dd 0
shutdown_old_word: dw 0
shutdown_phase: db 0
shutdown_pic: dw 0
shutdown_chipset: times 0x19 db 0
shutdown_check_done:
