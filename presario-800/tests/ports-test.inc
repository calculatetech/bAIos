; External keyboard stimuli and terminal observations over real startup/Save.
%define PT_STEP 0x0630
%define PT_WAIT 0x0631
%define PT_CHECK 0x0632
%define PT_CAPTURE 0x0633
%include "../tests/setup-test.inc"
ports_test_begin:
    cmp byte [fs:C_PORTS], 3
    je .done
%ifdef EMULATOR_PORTS_COLD
    jmp ports_test_fail
%endif
    mov dword [PT_STEP], 0
    set_vector 0x1C, ports_test_tick
.done:
    ret

ports_test_observe:
    cmp byte [fs:C_PORTS], 3
    je ports_test_verify
    ret

ports_test_tick:
    pushad
    push ds
    push es
    xor ax, ax
    mov ds, ax
    mov es, ax
    cmp byte [PT_CAPTURE], 1
    je .done
    inc byte [PT_WAIT]
    cmp byte [PT_WAIT], 200
    jae ports_test_fail
    movzx bx, byte [PT_STEP]
    cmp bx, 2
    jb .send
    cmp byte [0x484], 49
    jne .done
    cmp word [0x485], 8
    jne .done
    mov ax, 0xB800
    mov es, ax
    cmp word [es:(0 * 80 + 34) * 2], 0x1F62
    jne .done
    cmp bx, 6
    jne .send
%ifdef EMULATOR_PORTS_SCREEN
    ; Navigation has reached Devices. Capture the retained VGA surface once.
    call setup_test_snapshot
    mov byte [PT_CAPTURE], 1
%endif
.send:
    mov al, [cs:ports_test_keys+bx]
    test al, al
    jz .done
    inc byte [PT_STEP]
    push ax
    mov al, 0xD2
    call kbc_command
    pop ax
    jc ports_test_fail
    call kbc_write_data
    jc ports_test_fail
.done:
    pop es
    pop ds
    popad
    iret

ports_test_verify:
    cli
    mov byte [PT_CHECK], 0x40
    cmp dword [fs:C_PORTS], 0x03010003
    jne ports_test_fail
    cmp dword [fs:C_PORTS+4], 0x01000001
    jne ports_test_fail
    mov byte [PT_CHECK], 0x41
    cmp word [0x400], 0x3E8
    jne ports_test_fail
    mov byte [PT_CHECK], 0x48
    cmp word [0x402], 0
    jne ports_test_fail
    mov byte [PT_CHECK], 0x49
    cmp dword [0x404], 0
    jne ports_test_fail
    cmp word [0x408], 0x278
    jne ports_test_fail
    mov byte [PT_CHECK], 0x4A
    cmp word [0x40E], STATE_SEG
    jne ports_test_fail
    mov byte [PT_CHECK], 0x4B
    test word [0x410], 0xC5
    jnz ports_test_fail
    mov byte [PT_CHECK], 0x42
    mov dx, 0x3F0
    mov al, 0x55
    out dx, al
    out dx, al
    mov al, 1
    out dx, al
    inc dx
    in al, dx
    and al, 0x7F
    cmp al, 0x37
    jne ports_test_fail
    dec dx
    mov al, 2
    out dx, al
    inc dx
    in al, dx
    cmp al, 0x0E
    jne ports_test_fail
    dec dx
    mov al, 0xAA
    out dx, al
    xor dx, dx
    mov byte [PT_CHECK], 0x43
    mov ax, 0x00E3
    int 0x14
    test ah, 0x80
    jnz ports_test_fail
    mov ax, 0x0501
    mov bx, 0x1B
    int 0x14
    mov ax, 0x0500
    int 0x14
    cmp bl, 0x1B
    jne ports_test_fail
    mov byte [PT_CHECK], 0x44
    mov dx, 0x3E8
    mov al, 0x4D
    out dx, al                ; Opaque UART loopback supplies a received byte.
    xor dx, dx
    mov cx, 100
.loopback:
    mov ah, 3
    int 0x14
    test ah, 1
    jnz .loopback_ready
    call kbc_delay_2ms
    loop .loopback
    jmp ports_test_fail
.loopback_ready:
    mov ax, 0x0501
    xor bx, bx
    int 0x14
    mov ax, 0x025A
    mov byte [PT_CHECK], 0x45
    mov dx, 3
    int 0x17
    cmp ax, 0x015A
    jne ports_test_fail
    mov byte [PT_CHECK], 0x46
    mov ax, 0xC205
    mov bh, 3
    int 0x15
    jnc ports_test_fail
    cmp ah, 3
    jne ports_test_fail
    mov byte [PT_CHECK], 0x47
    mov ax, 0
    xor dx, dx
    int 0x13
    jnc ports_test_fail
    cmp ah, 1
    jne ports_test_fail
    mov al, 0x67
    call emulator_exit
    jmp hard_halt

ports_test_fail:
    mov al, [PT_CHECK]
    test al, al
    jnz .exit
    mov al, 0x50
    add al, [PT_STEP]
.exit:
    call emulator_exit
    jmp hard_halt

ports_test_keys:
    db 0xE0,0x53,0x50,0x50,0x50,28
    db 0x4D,0x4D,0x50,0x4D,0x50,0x4D,0x50,0x4D
    db 15,0x48,0x48,28,0x50,0x50,0x50,0x50,0x50,0x4D,0x44,28,0

; Export the external VGA capture from mainline, before Save clears RAM.
ports_test_capture_drain:
    pushad
    push ds
    xor ax, ax
    mov ds, ax
    cmp byte [PT_CAPTURE], 1
    jne .done
    call setup_test_dump
    mov byte [PT_CAPTURE], 2
%ifdef EMULATOR_PORTS_SCREEN
    mov al, 0x67
    call emulator_exit
    jmp hard_halt
%endif
.done:
    pop ds
    popad
    ret
