; INT13 must preserve non-output registers, including their upper halves.
; Speedsys keeps counters in ECX across BIOS disk calls. All writes here
; target only the disposable guest's existing A5 bulk-test sector.
    pushad
    push fs
    push gs
    ; DOS generic drive IOCTLs may call floppy parameters with IF cleared.
    xor dx, dx
    mov ax, 0x0800
    cli
    int 0x13
    pushf
    pop ax
    test ax, 0x0200
    jz .disk_register_failed
    xor ax, ax
    mov es, ax
    mov byte [disk_register_index], 0
.disk_register_next:
    mov eax, BULK_LBA
    mov cx, 1
    mov bx, BOOT_WORK_BUFFER
    xor dx, dx
    call set_dap
    mov word [edd_parameters], 26
    movzx di, byte [disk_register_index]
    cmp di, 8
    jne .disk_register_size
    mov dword [dap + 12], 1    ; Rejected 64-bit LBA must also retain registers.
.disk_register_size:
    cmp di, 10
    jne .disk_register_function
    mov word [edd_parameters], 25
.disk_register_function:
    mov ah, [cs:disk_register_functions + di]
    mov esi, 0x13570000 + dap
    cmp ah, 0x48
    jne .disk_register_pointer
    mov si, edd_parameters
.disk_register_pointer:
    mov [disk_register_si], esi
    mov ebx, 0xC7C70000 + BOOT_WORK_BUFFER
    mov ecx, 0xA5A50000 + BULK_LBA + 1
    mov edx, 0xB6B60080
    mov edi, 0xD8D81234
    mov ebp, 0xE9E92345
    mov [disk_register_bx], ebx
    mov [disk_register_cx], ecx
    mov [disk_register_dx], edx
    cmp ah, 0x08
    jne .disk_register_type
    mov word [disk_register_cx], 0xFEFF ; OEM maximum1022/255/63; full geometry1024.
    mov word [disk_register_dx], 0xFE01
.disk_register_type:
    cmp ah, 0x15
    jne .disk_register_extensions
    mov word [disk_register_cx], DISK_SECTORS >> 16
    mov word [disk_register_dx], DISK_SECTORS & 0xFFFF
.disk_register_extensions:
    cmp byte [disk_register_index], 13
    jne .disk_register_count
    mov bx, 0x55AA
    mov word [disk_register_bx], 0xAA55
    mov word [disk_register_cx], 1
.disk_register_count:
    mov al, 0x01               ; One sector for legacy read/write.
    cmp ah, 0x43
    jne .disk_register_options
    xor al, al                ; Extended write without verify.
.disk_register_options:
    push ax
    mov eax, 0x12340000
    pop ax
    cli                        ; Both disk dispatchers must restore OEM IF=1.
    int 0x13
    mov [disk_register_status], ah
    pushf
    pop word [disk_register_flags]
    test word [disk_register_flags], 0x0200
    jz .disk_register_failed
    shr eax, 16
    cmp ax, 0x1234
    jne .disk_register_failed
    cmp ebx, [disk_register_bx]
    jne .disk_register_failed
    cmp ecx, [disk_register_cx]
    jne .disk_register_failed
    cmp edx, [disk_register_dx]
    jne .disk_register_failed
    cmp esi, [disk_register_si]
    jne .disk_register_failed
    cmp edi, 0xD8D81234
    jne .disk_register_failed
    cmp ebp, 0xE9E92345
    jne .disk_register_failed
    movzx di, byte [disk_register_index]
    mov al, [cs:disk_register_errors + di]
    cmp al, [disk_register_status]
    jne .disk_register_failed
    cmp di, 12                ; AH15/41 return a nonzero AH on success.
    je .disk_register_clear_carry
    cmp di, 13
    jne .disk_register_carry
.disk_register_clear_carry:
    xor al, al
.disk_register_carry:
    neg al
    sbb al, al
    and al, 1
    mov dl, [disk_register_flags]
    and dl, 1
    cmp al, dl
    jne .disk_register_failed
    inc byte [disk_register_index]
    cmp byte [disk_register_index], disk_register_end - disk_register_functions
    jb .disk_register_next
    pop gs
    pop fs
    popad
    jmp disk_register_done
.disk_register_failed:
    mov al, 0x58
    jmp fail
disk_register_functions: db 0x42, 0x44, 0x47, 0x48, 0x00, 0x02, 0x03, 0x43, 0x42, 0x99, 0x48, 0x08, 0x15, 0x41, 0x41
    db 0x01, 0x04, 0x09, 0x0C, 0x0D, 0x10, 0x11, 0x14
disk_register_end:
disk_register_errors: db 0, 0, 0, 0, 0, 0, 0, 0, 4, 1, 4, 0, 3, 0x11, 1
    db 1, 0, 0, 0, 0, 0, 0, 0
disk_register_index: db 0
disk_register_si: dd 0
disk_register_status: db 0
disk_register_flags: dw 0
disk_register_bx: dd 0
disk_register_cx: dd 0
disk_register_dx: dd 0
disk_register_done:
