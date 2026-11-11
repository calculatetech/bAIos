int12:
    push ds
    mov ax, 0x40
    mov ds, ax
    mov ax, [0x13]
    pop ds
    iret

int15:
    push bp
    mov bp, sp
    cmp ah, 0x53
    je apm_int15
    cmp ah, 0xC2
    je mouse_int15
    cmp ah, 0xC0
    je .configuration
    cmp ah, 0xC1
    je .extended_data_area
%ifdef EMULATOR_TEST
    cmp ah, 0xEF
    je .test_control
%endif
    cmp ah, 0x88
    je .memory
    cmp ah, 0x87
    je .move_memory
    cmp ax, 0x448E
    je .oem_ok
    mov ah, 0x86
    or word [ss:bp + 6], 1
    pop bp
    iret
.configuration:
    push cs
    pop es
    mov bx, system_configuration
    xor ax, ax
    jmp .oem_ok
.extended_data_area:
    ; Windows EBIOS uses C1 to protect this page in 386 Enhanced mode.
    ; Read the current pointer: a DOS memory manager may relocate the EBDA.
    push fs
    call load_bios_state
    push fs
    pop es
    pop fs
    jmp .oem_ok
.move_memory:
    call move_extended_memory
    jc .move_failed
    xor ah, ah
    jmp .oem_ok
.move_failed:
    mov ah, 2
    or word [ss:bp + 6], 1
    pop bp
    iret
.memory:
    push fs
    call load_bios_state
    mov ax, [fs:S_EXTENDED_KIB]
    pop fs
.oem_ok:
    and word [ss:bp + 6], 0xFFFE
    pop bp
    iret
%ifdef EMULATOR_TEST
.test_control:
    push ds
    push ax
    xor ax, ax
    mov ds, ax
    mov ax, [0x040E]
    mov ds, ax
    pop ax
    cmp al, 1
    je .test_missing
    cmp al, 2
    je .test_present
    cmp al, 3
    je .test_after_read
    mov [S_TEST_ATA], al
    test al, al
    jnz .test_done
    mov byte [S_TEST_AFTER_STATUS], 0
    mov byte [S_TEST_AFTER_COUNT], 0
    mov byte [S_TEST_PHASE], 0
    jmp .test_done
.test_missing:
    mov byte [S_PRESENT], 0
    jmp .test_done
.test_present:
    mov byte [S_PRESENT], 1
    jmp .test_done
.test_after_read:
    mov [S_TEST_AFTER_STATUS], bl
    mov [S_TEST_AFTER_COUNT], bh
    mov byte [S_TEST_ATA], 0
.test_done:
    pop ds
    xor ah, ah
    and word [ss:bp + 6], 0xFFFE
    pop bp
    iret
%endif

; AT block move: ES:SI points to the caller's descriptor table, CX words.
; OEM F000:F3EC-F5C3 uses a protected-mode copy and a direct 486 return.
; Use a private flat descriptor instead of modifying the caller's table.
; Interrupts remain masked; no stack access occurs in protected mode.
