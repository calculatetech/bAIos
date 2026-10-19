bits 16
org 0x100

%ifndef XMS_TEST_KIB
%define XMS_TEST_KIB 2048
%endif

start:
%ifdef REQUIRE_UMB
    ; This variant must actually run in an EMM386 UMB, not fall back low.
    mov ax, ds
    cmp ax, 0xA000
    mov al, 0x6E
    jb exit
%endif
    ; Capture the actual driver startup messages, including failure text.
    mov dx, log_name
    xor cx, cx
    mov ah, 0x3C
    int 0x21
    jc .captured
    mov bx, ax
    mov ax, 0xB800
    mov fs, ax
    push ds
    pop es
    xor si, si
    mov di, screen
    mov bp, 25
.line:
    mov cx, 80
.cell:
    mov al, [fs:si]
    stosb
    add si, 2
    loop .cell
    mov al, 13
    stosb
    mov al, 10
    stosb
    dec bp
    jnz .line
    mov dx, screen
    mov cx, 25 * 82
    mov ah, 0x40
    int 0x21
    mov ah, 0x3E
    int 0x21
.captured:
    ; Conventional memory follows the BDA, including EMM's EBDA relocation.
    xor ax, ax
    mov fs, ax
    int 0x12
    cmp ax, [fs:0x0413]
    mov al, 0x68
    jne exit
%ifdef BIOS_INT15_OFFSET
    ; Bypass DOS's INT15 hook: the actual ROM must follow the moved EBDA.
%ifndef HIMEM_ONLY
    cmp word [fs:0x040E], 0x9FC0
    mov al, 0x69
    je exit
    pushf
    cli
    push gs
    mov ax, 0x9FC0
    mov gs, ax
    push word [gs:0xD0]
    mov word [gs:0xD0], 0xFFFF ; A fixed old-EBDA reader must now fail.
%endif
    mov ah, 0x88
    pushf
    call 0xF000:BIOS_INT15_OFFSET
%ifndef HIMEM_ONLY
    pushf
    pop dx
    pop word [gs:0xD0]        ; Restore borrowed bytes before IRQs or DOS calls.
    pop gs
    popf
    test dl, 1
    jz .memory_service_ok
    mov al, 0x68
    jmp exit
.memory_service_ok:
    clc
%endif
    mov bl, al
    mov al, 0x68
    jc exit
    mov al, bl
    cmp ax, EXPECTED_EXTENDED_KIB
    mov al, 0x68
    jne exit
    mov ax, fs
    test ax, ax
    mov al, 0x68
    jnz exit
%endif
%ifndef HIMEM_ONLY
    mov ax, [fs:0x040E]
    cmp ax, 0x9FC0
    mov al, 0x69
    je exit
    ; Parameter output in the guest's UMB must work after relocation.
    mov si, edd_parameters
    mov word [si], 26
    mov ah, 0x48
    mov dl, 0x80
    int 0x13
    mov al, 0x69
    jc exit
    cmp word [si + 24], 512
    jne exit
    cmp dword [si + 16], 0
    je exit
    ; The new EBDA remains excluded, even though its old address is free.
    push ds
    mov ax, [fs:0x040E]
    mov ds, ax
    mov si, 0x0100
    mov word [si], 26
    mov ah, 0x48
    mov dl, 0x80
    int 0x13
    pop ds
    mov al, 0x69
    jnc exit
    cmp ah, 4
    jne exit
%ifdef REQUIRE_UMB
    ; Only on the disposable card fixture: exercise every UMB data entry.
    ; Borrow the MBR disk-signature word, then restore all original bytes.
    push ds
    pop es
    mov bx, pattern
    mov ax, 0x0201
    mov cx, 1
    mov dx, 0x0080
    int 0x13
    mov bl, al
    mov al, 0x6F
    jc exit
    cmp bl, 1
    jne exit
    cmp word [pattern + 510], 0xAA55
    jne exit
    mov ax, ds
    mov [edd_dap + 6], ax
    call poison_sector
    mov word [edd_dap + 4], received
    mov ah, 0x42
    call umb_packet
    call compare_sector

    xor word [pattern + 440], 0xFFFF
    mov bx, pattern
    mov ax, 0x0301
    mov cx, 1
    mov dx, 0x0080
    int 0x13
    mov bl, al
    mov al, 0x6F
    jc exit
    cmp bl, 1
    jne exit
    call poison_sector
    mov ah, 0x42
    call umb_packet
    call compare_sector

    xor word [pattern + 440], 0xFFFF
    mov word [edd_dap + 4], pattern
    mov ah, 0x43
    call umb_packet
    call poison_sector
    mov bx, received
    mov ax, 0x0201
    mov cx, 1
    mov dx, 0x0080
    int 0x13
    mov bl, al
    mov al, 0x6F
    jc exit
    cmp bl, 1
    jne exit
    call compare_sector
    mov ah, 0x44
    call umb_packet
%endif
%endif
%ifdef CARD_READ_TEST
    ; CRCs come from the unmodified user backup, not another BIOS read.
    mov bp, file_checks
.file:
    mov dx, [bp]
    test dx, dx
    jz .files_done
    mov ax, 0x3D00
    int 0x21
    mov bx, ax
    mov al, 0x6A
    jc exit
    mov dword [file_crc], 0xFFFFFFFF
.read_file:
    mov dx, pattern
    mov cx, 8192
    mov ah, 0x3F
    int 0x21
    mov cx, ax
    mov al, 0x6B
    jc exit
    jcxz .file_end
    mov eax, [file_crc]
    mov si, pattern
.crc_byte:
    xor al, [si]
    inc si
    mov di, 8
.crc_bit:
    shr eax, 1
    jnc .crc_next
    xor eax, 0xEDB88320
.crc_next:
    dec di
    jnz .crc_bit
    loop .crc_byte
    mov [file_crc], eax
    jmp .read_file
.file_end:
    mov ah, 0x3E
    int 0x21
    mov al, 0x6C
    jc exit
    mov eax, [file_crc]
    not eax
    cmp eax, [bp + 2]
    mov al, 0x6D
    jne exit
    add bp, 6
    jmp .file
.files_done:
%endif
%ifdef HIMEM_ONLY
    ; Exercise the BIOS block move without EMM386 intercepting INT 15h.
    push ds
    pop es
    mov bp, 1
    call fill_pattern
    xor eax, eax
    mov ax, ds
    shl eax, 4
    add eax, pattern
    mov [descriptors + 0x12], ax
    shr eax, 16
    mov [descriptors + 0x14], al
    xor eax, eax
    mov ax, ds
    shl eax, 4
    add eax, received
    mov [descriptors + 0x1A], ax
    shr eax, 16
    mov [descriptors + 0x1C], al
    mov word [received + 34], 0xBEEF
    mov si, descriptors
    mov cx, 17
    mov ah, 0x87
    int 0x15
    mov al, 0x78
    jc exit
    test ah, ah
    jnz exit
    mov si, pattern
    mov di, received
    mov cx, 17
    repe cmpsw
    jne exit
    cmp word [received + 34], 0xBEEF
    jne exit
    mov si, descriptors
    mov cx, 0x8001
    mov ah, 0x87
    int 0x15
    mov al, 0x79
    jnc exit
    mov si, 0xFFE0
    mov cx, 1
    mov ah, 0x87
    int 0x15
    mov al, 0x7A
    jnc exit
%endif
    mov ax, 0x4300
    int 0x2F
    cmp al, 0x80
    mov al, 0x71
    jne exit
    mov ax, 0x4310
    int 0x2F
    mov [xms_entry], bx
    mov [xms_entry + 2], es
%ifndef HIMEM_ONLY
    smsw ax
    test al, 1                  ; EMM386 must have entered protected/V86 mode.
    mov al, 0x72
    jz exit
%endif
    mov ah, 9
    mov dx, XMS_TEST_KIB
    call far [xms_entry]
    cmp ax, 1
    mov al, 0x73
    jne exit
    mov [handle], dx
    mov [move_to_handle], dx
    mov [move_from_handle], dx
    mov ax, ds
    mov [move_to_source + 2], ax
    mov [move_from_dest + 2], ax
    push ds
    pop es
    mov bp, XMS_TEST_KIB / 8
.write_block:
    call fill_pattern
    mov si, move_to
    mov ah, 0x0B
    call far [xms_entry]
    cmp ax, 1
    mov al, 0x74
    jne exit
    add dword [move_to_offset], 8192
    dec bp
    jnz .write_block
    ; Read only after all writes, with a different pattern in each block.
    ; This catches aliasing between blocks, not just immediate readback.
    mov bp, XMS_TEST_KIB / 8
.read_block:
    call fill_pattern
    mov si, move_from
    mov ah, 0x0B
    call far [xms_entry]
    cmp ax, 1
    mov al, 0x75
    jne exit
    mov si, pattern
    mov di, received
    mov cx, 4096
    repe cmpsw
    mov al, 0x76
    jne exit
    add dword [move_from_offset], 8192
    dec bp
    jnz .read_block
    mov dx, [handle]
    mov ah, 0x0A
    call far [xms_entry]
    cmp ax, 1
    mov al, 0x77
    jne exit
    mov al, 0x67
exit:
    mov bl, al
    mov dx, 0x80
    mov si, signature
    mov cx, 7
.unlock:
    lodsb
    out dx, al
    loop .unlock
    mov dx, 0x501
    mov al, 4
    out dx, al
    inc dx
    mov al, bl
    out dx, al
    mov ax, 0x4C01
    int 0x21

%ifdef REQUIRE_UMB
umb_packet:
    mov word [edd_dap + 2], 1
    mov si, edd_dap
    xor al, al
    mov dl, 0x80
    int 0x13
    mov bl, al
    mov al, 0x6F
    jc exit
    test ah, ah
    jnz exit
    cmp bl, 1
    jne exit
    cmp word [edd_dap + 2], 1
    jne exit
    ret

poison_sector:
    mov di, received
    mov cx, 256
    xor ax, ax
    rep stosw
    ret

compare_sector:
    mov si, pattern
    mov di, received
    mov cx, 256
    repe cmpsw
    mov al, 0x6F
    jne exit
    ret
%endif

fill_pattern:
    mov di, pattern
    mov cx, 4096
    mov ax, bp
    xor ax, 0xA55A
.word:
    stosw
    inc ax
    loop .word
    ret

signature db '86Box', 1, 5
log_name db 'XMSBOOT.TXT', 0
xms_entry dd 0
handle dw 0
edd_parameters times 26 db 0
edd_dap:
    db 16, 0
    dw 1, received, 0
    dq 0
%ifdef CARD_READ_TEST
file_crc dd 0
file_checks:
    dw command_name
    dd 0x80E08363
    dw himem_name
    dd 0x40B3821F
    dw emm_name
    dd 0x223885BA
    dw ifshlp_name
    dd 0x14664E8C
    dw 0
command_name db 'C:\COMMAND.COM', 0
himem_name db 'C:\DOS\HIMEM.SYS', 0
emm_name db 'C:\DOS\EMM386.EXE', 0
ifshlp_name db 'C:\WINDOWS\IFSHLP.SYS', 0
%endif
descriptors:
    times 16 db 0
    dw 0xFFFF, 0
    db 0, 0x93, 0, 0
    dw 0xFFFF, 0
    db 0, 0x93, 0, 0
    times 16 db 0
move_to:
    dd 8192
    dw 0
move_to_source dw pattern, 0
move_to_handle dw 0
move_to_offset dd 0
move_from:
    dd 8192
move_from_handle dw 0
move_from_offset dd 0
    dw 0
move_from_dest dw received, 0
screen times 25 * 82 db 0
pattern times 8192 db 0
received times 8192 db 0
