bits 16
org 0x7C00

%define DISK_SECTORS        0x01000000
%define LEGACY_LIMIT        0x00FB0400
%define CHS_TEST_LBA        0x00498AAC
%define PROTECTED_LBA       144 ; Outside guest sectors0..15 and bulk16..142.
%define COMPLETION_LBA      145
%define BULK_LBA            16
%define EDD_WRITE_LBA       13
%define EBDA_SEG            0x9FC0
%define BOOT_WORK_BUFFER    0x0500
%define BOOT_EDGE_BUFFER    0x9C00 ; Immediately after the full 8 KiB guest image.

%macro check_dap_rejection 4
    mov eax, 1
    mov cx, 1
    mov bx, BOOT_WORK_BUFFER
    xor dx, dx
    call set_dap
    mov si, dap
    mov ah, %1
    xor al, al
    mov dl, %2
    int 0x13
    mov al, %4
    jnc fail
    cmp ah, %3
    mov al, %4 + 1
    jne fail
    cmp word [dap + 2], 0
    mov al, %4 + 2
    jne fail
%endmacro

start:
    cli
    xor ax, ax
    mov ds, ax
    mov es, ax
    mov ss, ax
    mov sp, 0x7C00
    sti
    cld

    mov bx, 0x55AA
    mov ax, 0x4100
    mov dl, 0x80
    int 0x13
    mov al, 0x01
    jc fail
    cmp bx, 0xAA55
    mov al, 0x02
    jne fail
    test cx, 1
    mov al, 0x03
    jz fail
    cmp ah, 0x11
    mov al, 0x05
    jne fail

    mov si, stage_dap
    mov ax, 0x4200
    mov dl, 0x80
    int 0x13
    mov al, 0x04
    jc fail
    jmp 0x0000:stage2

stage_dap:
    db 0x10, 0
    dw 15
    dw stage2, 0
    dq 1

fail:
    out 0x80, al
    mov bl, al
    and bl, 0x7F                  ; 86Box clamps larger exit values to 7Fh.
    mov dx, 0x0080
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
    mov al, 0x01
    out dx, al
    mov al, 0x05
    out dx, al
    mov dx, 0x0501
    mov al, 4
    out dx, al
    inc dx
    mov al, bl
    out dx, al
    mov ah, 0x0E
    mov bx, 7
    mov al, 'F'
    int 0x10
.halt:
    cli
    hlt
    jmp .halt

times 510 - ($ - $$) db 0
dw 0xAA55

stage2:
%ifdef FAULT_TEST
    jmp fault_stage
%endif
    ; Check firmware memory reporting before HIMEM can hook INT 15h/88h.
%include "shutdown-check.inc"
%include "memory-check.inc"
%include "bus-check.inc"
%include "fpu-check.inc"
%include "disk-register-check.inc"
    ; SI8 benchmarks issue legacy 128-sector reads into a full 64 KiB buffer.
    mov ax, 0x8000
    mov es, ax
    xor bx, bx
    mov ax, 0x0280
    mov cx, BULK_LBA + 1
    mov dx, 0x0080
    int 0x13
    mov bl, al
    mov al, 0x59
    jc fail
    cmp bl, 128
    jne fail
    cmp word [es:0], 0xA5A5
    jne fail
    cmp word [es:0xFC00], 0xA5A5
    jne fail
    cmp word [es:0xFE00], 0
    jne fail
    xor ax, ax
    mov es, ax
    call check_vga
    call check_disk_interrupts
    ; HIMEM permits DOS to use HMA disk buffers. Test the legacy path first:
    ; a valid FFFF:0510 buffer must not return "sector not found" (AH=04h).
    mov ax, 0xFFFF
    mov es, ax
    mov bx, 0x0510
    mov ax, 0x0201
    mov cx, BULK_LBA + 1
    mov dx, 0x0080
    int 0x13
    mov al, 0x6B
    jc fail
    cmp word [es:0x0510], 0xA5A5
    mov al, 0x6C
    jne fail
    xor ax, ax
    mov es, ax
    ; The EBDA reserves the final 1 KiB of conventional memory.
    int 0x12
    cmp ax, 639
    mov al, 0xC6
    jne fail
    cmp word [0x040E], EBDA_SEG
    mov al, 0xC7
    jne fail
    cmp word [0x0413], 639
    mov al, 0xC8
    jne fail
    mov ax, EBDA_SEG
    mov es, ax
    cmp byte [es:0], 1
    mov al, 0xC9
    jne fail
    xor ax, ax
    mov es, ax
    ; EDD parameters must report the full explicit 8 GiB image.
    mov di, edd_parameters
    mov ax, 0xCCCC
    mov cx, 16
    rep stosw
    mov word [edd_parameters], 26
    mov si, edd_parameters
    mov ax, 0x4800
    mov dl, 0x80
    int 0x13
    mov al, 0x10
    jc fail
    cmp word [edd_parameters], 26
    mov al, 0x11
    jne fail
    cmp dword [edd_parameters + 16], DISK_SECTORS
    mov al, 0x12
    jne fail
    cmp dword [edd_parameters + 20], 0
    mov al, 0x13
    jne fail
    cmp word [edd_parameters + 2], 2
    mov al, 0x0A
    jne fail
    cmp dword [edd_parameters + 4], 1044
    mov al, 0x0B
    jne fail
    cmp dword [edd_parameters + 8], 255
    mov al, 0x0C
    jne fail
    cmp dword [edd_parameters + 12], 63
    mov al, 0x0D
    jne fail
    cmp word [edd_parameters + 24], 512
    mov al, 0x0E
    jne fail
    cmp word [edd_parameters + 26], 0xCCCC
    mov al, 0x0F
    jne fail

    ; Short and wrapping parameter buffers must be rejected.
    mov word [edd_parameters], 25
    mov si, edd_parameters
    mov ax, 0x4800
    mov dl, 0x80
    int 0x13
    mov al, 0x1A
    jnc fail
    cmp ah, 4
    jne fail
    mov word [0xFFF0], 26
    mov si, 0xFFF0
    mov ax, 0x4800
    mov dl, 0x80
    int 0x13
    mov al, 0x1B
    jnc fail
    cmp ah, 4
    jne fail

    ; Parameter output must not enter the reserved EBDA. HMA output is valid.
    push ds
    mov ax, 0x9FB0
    mov ds, ax
    mov word [0x00F0], 26
    mov si, 0x00F0
    mov ax, 0x4800
    mov dl, 0x80
    int 0x13
    pop ds
    mov al, 0xE0
    jnc fail
    cmp ah, 4
    mov al, 0xE1
    jne fail
    mov bx, 0x55AA
    mov ax, 0x4100
    mov dl, 0x80
    int 0x13
    mov al, 0xE2
    jc fail

    mov word [BOOT_WORK_BUFFER], 26
    mov si, BOOT_WORK_BUFFER
    mov ax, 0x4800
    mov dl, 0x80
    int 0x13
    mov al, 0xE3
    jc fail
    cmp dword [BOOT_WORK_BUFFER + 16], DISK_SECTORS
    mov al, 0xE4
    jne fail

    push ds
    mov ax, 0xFFFF
    mov ds, ax
    mov si, 0x101A
    mov word [si], 26
    mov ax, 0x4800
    mov dl, 0x80
    int 0x13
    pushf
    pop bx
    mov al, 0x6D
    cmp dword [si + 16], DISK_SECTORS
    jne fail
    pop ds
    push bx
    popf
    mov al, 0xE5
    jc fail
    test ah, ah
    mov al, 0xE6
    jne fail

    ; AH08 reports maximum1022/255/63 with the OEM reserved cylinder.
    mov ax, 0x0800
    mov dl, 0x80
    int 0x13
    mov al, 0x14
    jc fail
    cmp ch, 0xFE
    mov al, 0x15
    jne fail
    cmp cl, 0xFF
    mov al, 0x16
    jne fail
    cmp dh, 0xFE
    mov al, 0x17
    jne fail
    cmp dl, 1
    mov al, 0x1C
    jne fail

    ; A valid FAT BPB must override the capacity-derived geometry.
    mov byte [0x7C00], 0xEB
    mov word [0x7C0B], 512
    mov word [0x7C0E], 1
    mov word [0x7C18], 32
    mov word [0x7C1A], 128
    mov word [0x7DFE], 0xAA55
    mov ax, 0x0800
    mov dl, 0x80
    int 0x13
    mov al, 0xC0
    jc fail
    cmp cl, 0xE0
    mov al, 0xC1
    jne fail
    cmp dh, 127
    mov al, 0xC2
    jne fail
    mov byte [0x7C00], 0xFA

    mov ax, 0x1500
    mov dl, 0x80
    int 0x13
    mov al, 0x18
    jc fail
    cmp ah, 3
    mov al, 0x19
    jne fail
    cmp cx, 0x0100
    mov al, 0x1D
    jne fail
    test dx, dx
    mov al, 0x1E
    jnz fail

    ; Reset and EDD discovery rejection are separate entry-point checks.
    xor ax, ax
    mov dl, 0x80
    int 0x13
    mov al, 0x1F
    jc fail
    cmp dl, 0x80
    mov al, 0xD0
    jne fail
    mov bx, 0x1234
    mov ax, 0x4100
    int 0x13
    mov al, 0x40
    jnc fail
    cmp ah, 1
    jne fail
    mov ax, 0x9900
    mov dl, 0x80
    int 0x13
    mov al, 0x72
    jnc fail
    cmp ah, 1
    mov al, 0x73
    jne fail

    ; Read one sector beyond the maximum translated CHS range.
    mov eax, LEGACY_LIMIT
    mov cx, 1
    mov bx, BOOT_WORK_BUFFER
    xor dx, dx
    call set_dap
    std
    call edd_read
    cld
    mov al, 0x20
    jc fail
    cmp word [dap + 2], 1
    mov al, 0x41
    jne fail
    cmp dword [BOOT_WORK_BUFFER], 0x48474948       ; "HIGH"
    mov al, 0x21
    jne fail

    ; Read the final valid sector, then reject the first invalid sector.
    mov eax, DISK_SECTORS - 1
    mov cx, 1
    mov bx, BOOT_EDGE_BUFFER
    xor dx, dx
    call set_dap
    call edd_read
    mov al, 0x22
    jc fail
    cmp word [dap + 2], 1
    mov al, 0x42
    jne fail
    cmp dword [BOOT_EDGE_BUFFER], 0x5453414C       ; "LAST"
    mov al, 0x23
    jne fail
    mov eax, DISK_SECTORS
    mov cx, 1
    mov bx, BOOT_EDGE_BUFFER
    xor dx, dx
    call set_dap
    call edd_read
    mov al, 0x24
    jnc fail
    cmp ah, 4
    jne fail
    cmp word [dap + 2], 0
    jne fail

    ; Each malformed request starts from an otherwise valid packet.
    mov eax, 1
    mov cx, 1
    mov bx, BOOT_EDGE_BUFFER
    xor dx, dx
    call set_dap
    mov byte [dap], 0x0F
    call edd_read
    mov al, 0x25
    jnc fail
    cmp ah, 4
    jne fail
    cmp word [dap + 2], 0
    jne fail
    mov eax, 1
    mov cx, 1
    mov bx, BOOT_EDGE_BUFFER
    xor dx, dx
    call set_dap
    mov word [dap + 2], 0
    call edd_read
    mov al, 0x26
    jnc fail
    cmp ah, 4
    jne fail
    cmp word [dap + 2], 0
    jne fail
    mov eax, 1
    mov cx, 1
    mov bx, BOOT_EDGE_BUFFER
    xor dx, dx
    call set_dap
    mov dword [dap + 12], 1
    call edd_read
    mov al, 0x27
    jnc fail
    cmp ah, 4
    jne fail
    cmp word [dap + 2], 0
    jne fail
    mov eax, 1
    mov cx, 1
    mov bx, BOOT_EDGE_BUFFER
    xor dx, dx
    call set_dap
    mov dl, 0x81
    mov si, dap
    mov ax, 0x4200
    int 0x13
    mov al, 0x28
    jnc fail
    cmp ah, 1
    jne fail

    ; A request starting at the final sector must not cross the disk end.
    mov eax, DISK_SECTORS - 1
    mov cx, 2
    mov bx, BOOT_EDGE_BUFFER
    xor dx, dx
    call set_dap
    call edd_read
    mov al, 0x43
    jnc fail
    cmp ah, 4
    jne fail
    cmp word [dap + 2], 0
    jne fail

    ; Reject a wrapping buffer and a count of 128.
    mov eax, 1
    mov cx, 1
    mov bx, 0xFF00
    xor dx, dx
    call set_dap
    call edd_read
    mov al, 0x29
    jnc fail
    cmp ah, 4
    jne fail
    cmp word [dap + 2], 0
    jne fail
    mov eax, BULK_LBA
    mov cx, 128
    xor bx, bx
    mov dx, 0x1000
    call set_dap
    call edd_read
    mov al, 0x2A
    jnc fail
    cmp ah, 4
    jne fail
    cmp word [dap + 2], 0
    jne fail

    ; The EBDA is not a valid transfer buffer. The DOS boot workspace is.
    ; Exercise every read, write, and verify entry that shares validate_request.
    mov eax, BULK_LBA
    mov cx, 1
    xor bx, bx
    mov dx, EBDA_SEG
    call set_dap
    call edd_read
    mov al, 0xE0
    jnc fail
    cmp ah, 4
    jne fail
    cmp word [dap + 2], 0
    jne fail

    mov eax, BULK_LBA
    mov cx, 1
    mov bx, BOOT_WORK_BUFFER
    xor dx, dx
    call set_dap
    call edd_read
    mov al, 0xE1
    jc fail
    cmp word [dap + 2], 1
    jne fail
    cmp word [BOOT_WORK_BUFFER], 0xA5A5
    jne fail

    mov eax, BULK_LBA
    mov cx, 1
    xor bx, bx
    mov dx, EBDA_SEG
    call set_dap
    mov si, dap
    mov ax, 0x4300
    mov dl, 0x80
    int 0x13
    mov bl, al
    mov al, 0xE2
    jnc fail
    cmp ah, 4
    jne fail
    test bl, bl
    jne fail
    cmp word [dap + 2], 0
    jne fail
    call check_bulk_sentinel
    jc fail

    mov eax, BULK_LBA
    mov cx, 1
    mov bx, BOOT_WORK_BUFFER
    xor dx, dx
    call set_dap
    mov si, dap
    mov ax, 0x4300
    mov dl, 0x80
    int 0x13
    mov bl, al
    mov al, 0xE3
    jc fail
    cmp bl, 1
    jne fail
    cmp word [dap + 2], 1
    jne fail
    call check_bulk_sentinel
    jc fail

    mov eax, BULK_LBA
    mov cx, 1
    xor bx, bx
    mov dx, EBDA_SEG
    call set_dap
    mov si, dap
    mov ax, 0x4400
    mov dl, 0x80
    int 0x13
    mov bl, al
    mov al, 0xE4
    jc fail
    test ah, ah
    jne fail
    cmp bl, 1
    jne fail
    cmp word [dap + 2], 1
    jne fail

    mov eax, BULK_LBA
    mov cx, 1
    mov bx, BOOT_WORK_BUFFER
    xor dx, dx
    call set_dap
    mov si, dap
    mov ax, 0x4400
    mov dl, 0x80
    int 0x13
    mov bl, al
    mov al, 0xE5
    jc fail
    cmp bl, 1
    jne fail
    cmp word [dap + 2], 1
    jne fail

    ; HMA buffers are valid for EDD reads, writes and verify as well as CHS.
    mov ax, 0xFFFF
    mov es, ax
    mov di, 0x0510
    xor ax, ax
    mov cx, 256
    rep stosw
    mov eax, BULK_LBA
    mov cx, 1
    mov bx, 0x0510
    mov dx, 0xFFFF
    call set_dap
    call edd_read
    mov al, 0xEA
    jc fail
    test ah, ah
    jne fail
    cmp word [dap + 2], 1
    jne fail
    mov di, 0x0510
    mov ax, 0xA5A5
    mov cx, 256
    repe scasw
    mov al, 0x6A
    jne fail
    mov ax, 0xC3C3
    call fill_hma_sector

    mov eax, BULK_LBA
    mov cx, 1
    mov bx, 0x0510
    mov dx, 0xFFFF
    call set_dap
    mov si, dap
    mov ax, 0x4300
    mov dl, 0x80
    int 0x13
    mov bl, al
    mov al, 0xEE
    jc fail
    test ah, ah
    jne fail
    cmp bl, 1
    jne fail
    cmp word [dap + 2], 1
    jne fail
    mov bp, 0xC3C3
    call check_hma_write

    mov eax, BULK_LBA
    mov cx, 1
    mov bx, 0x0510
    mov dx, 0xFFFF
    call set_dap
    mov si, dap
    mov ax, 0x4400
    mov dl, 0x80
    int 0x13
    mov bl, al
    mov al, 0xEF
    jc fail
    test ah, ah
    jne fail
    cmp bl, 1
    jne fail
    cmp word [dap + 2], 1
    jne fail

    ; Seek has no transfer buffer, so the EBDA exclusion is irrelevant.
    mov eax, BULK_LBA
    mov cx, 1
    mov bx, BOOT_WORK_BUFFER
    xor dx, dx
    call set_dap
    mov byte [dap], 0x0F
    mov si, dap
    mov ax, 0x4700
    mov dl, 0x80
    int 0x13
    mov al, 0xF0
    jnc fail
    cmp ah, 4
    jne fail
    cmp word [dap + 2], 0
    jne fail

    mov eax, BULK_LBA
    mov cx, 1
    mov bx, 0xFF00
    xor dx, dx
    call set_dap
    mov si, dap
    mov ax, 0x4700
    mov dl, 0x80
    int 0x13
    mov al, 0xF1
    jc fail                   ; Seek ignores the unused transfer buffer.
    test ah, ah
    jne fail
    cmp word [dap + 2], 0
    jne fail

    mov eax, BULK_LBA
    mov cx, 1
    mov bx, 0x0500
    xor dx, dx
    call set_dap
    mov si, dap
    mov ax, 0x4700
    mov dl, 0x80
    int 0x13
    mov al, 0xEC
    jc fail
    cmp word [dap + 2], 0
    jne fail

    mov ax, EBDA_SEG
    mov es, ax
    xor bx, bx
    mov ax, 0x0201
    mov cx, 17
    xor dh, dh
    mov dl, 0x80
    int 0x13
    mov bl, al
    mov al, 0xE6
    jnc fail
    cmp ah, 4
    jne fail
    test bl, bl
    jne fail
    xor ax, ax
    mov es, ax

    mov ax, 0xFFFF
    mov es, ax
    mov bx, 0x0510
    mov ax, 0x0201
    mov cx, 17
    xor dh, dh
    mov dl, 0x80
    int 0x13
    mov bl, al
    mov al, 0xEB
    jc fail
    test ah, ah
    jne fail
    cmp bl, 1
    jne fail
    cmp cx, 17
    jne fail
    cmp dx, 0x0080
    jne fail
    xor ax, ax
    mov es, ax

    mov ax, 0xFFFF
    mov es, ax
    mov ax, 0x3C3C
    call fill_hma_sector
    mov bx, 0x0510
    mov ax, 0x0301
    mov cx, 17
    xor dh, dh
    mov dl, 0x80
    int 0x13
    mov bl, al
    mov al, 0xED
    jc fail
    test ah, ah
    jne fail
    cmp bl, 1
    jne fail
    cmp cx, 17
    jne fail
    cmp dx, 0x0080
    jne fail
    xor ax, ax
    mov es, ax
    mov bp, 0x3C3C
    call check_hma_write

    mov bx, BOOT_WORK_BUFFER
    mov ax, 0x0201
    mov cx, 17
    xor dh, dh
    mov dl, 0x80
    int 0x13
    mov bl, al
    mov al, 0xE7
    jc fail
    cmp bl, 1
    jne fail
    cmp word [BOOT_WORK_BUFFER], 0xA5A5
    jne fail

    mov ax, EBDA_SEG
    mov es, ax
    xor bx, bx
    mov ax, 0x0301
    mov cx, 17
    xor dh, dh
    mov dl, 0x80
    int 0x13
    mov bl, al
    mov al, 0xE8
    jnc fail
    cmp ah, 4
    jne fail
    test bl, bl
    jne fail
    xor ax, ax
    mov es, ax
    call check_bulk_sentinel
    jc fail

    mov bx, BOOT_WORK_BUFFER
    mov ax, 0x0301
    mov cx, 17
    xor dh, dh
    mov dl, 0x80
    int 0x13
    mov bl, al
    mov al, 0xE9
    jc fail
    cmp bl, 1
    jne fail
    call check_bulk_sentinel
    jc fail

    ; Accept 127 sectors and compare every word.
    mov eax, BULK_LBA
    mov cx, 127
    xor bx, bx
    mov dx, 0x1000
    call set_dap
    call edd_read
    mov al, 0x2B
    jc fail
    cmp word [dap + 2], 127
    mov al, 0x44
    jne fail
    mov ax, 0x1000
    mov es, ax
    xor di, di
    mov ax, 0xA5A5
    mov cx, 127 * 256
    repe scasw
    mov al, 0x2C
    jne fail
    xor ax, ax
    mov es, ax

    ; A one-sector transfer can end exactly at a segment boundary.
    ; Its nearest invalid neighbor must fail through both read/verify entries.
    mov bx, 0xFF00
    mov ax, 0x0201
    mov cx, BULK_LBA + 1
    mov dx, 0x0080
    int 0x13
    mov bl, al
    mov al, 0x6F
    jnc fail
    cmp ah, 4
    jne fail
    test bl, bl
    jne fail
    mov eax, BULK_LBA
    mov cx, 1
    mov bx, 0xFF00
    xor dx, dx
    call set_dap
    mov si, dap
    mov ax, 0x4400
    mov dl, 0x80
    int 0x13
    mov bl, al
    mov al, 0x6F
    jc fail                   ; Verify never transfers into ES:BX.
    test ah, ah
    jne fail
    cmp bl, 1
    jne fail
    cmp word [dap + 2], 1
    jne fail

    mov eax, 1
    mov cx, 1
    mov bx, 0xFE00
    xor dx, dx
    call set_dap
    call edd_read
    mov al, 0x2D
    jc fail

    ; CHS cylinder-high bits and nonzero head must map to the EDD LBA.
    xor ax, ax
    mov es, ax
    mov bx, 0xA000
    mov ax, 0x0201
    mov cx, 0x2C43
    mov dh, 2
    mov dl, 0x80
    int 0x13
    mov al, 0x30
    jc fail
    cmp cx, 0x2C43
    mov al, 0xD2
    jne fail
    cmp dx, 0x0280
    mov al, 0xD3
    jne fail
    cmp dword [0xA000], 0x53484343       ; "CCHS"
    mov al, 0x31
    jne fail
    mov eax, CHS_TEST_LBA
    mov cx, 1
    mov bx, 0xA200
    xor dx, dx
    call set_dap
    call edd_read
    mov al, 0x32
    jc fail
    mov eax, [0xA000]
    cmp eax, [0xA200]
    mov al, 0x33
    jne fail

    ; Sector zero is invalid in CHS form.
    mov bx, 0xA000
    mov ax, 0x0201
    mov cx, 0x2C40
    mov dh, 2
    mov dl, 0x80
    int 0x13
    mov bl, al
    mov al, 0x34
    jnc fail
    cmp ah, 4
    jne fail
    test bl, bl
    jne fail
    cmp cx, 0x2C40
    mov al, 0xD4
    jne fail
    cmp dx, 0x0280
    mov al, 0xD5
    jne fail

    ; Legacy write and readback through the shared ATA path.
    mov di, 0xA400
    mov ax, 0xBEEF
    mov cx, 256
    rep stosw
    mov bx, 0xA400
    mov ax, 0x0301
    mov cx, 0x2C44
    mov dh, 2
    mov dl, 0x80
    int 0x13
    mov al, 0x35
    jc fail
    cmp cx, 0x2C44
    mov al, 0xD6
    jne fail
    cmp dx, 0x0280
    mov al, 0xD7
    jne fail
    push cx
    mov di, 0xA400
    xor ax, ax
    mov cx, 256
    rep stosw
    pop cx
    mov bx, 0xA400
    mov ax, 0x0201
    int 0x13
    mov al, 0x36
    jc fail
    mov di, 0xA400
    mov ax, 0xBEEF
    mov cx, 256
    repe scasw
    mov al, 0x37
    jne fail

    ; A complete extended write must round-trip every word.
    mov di, 0xA600
    mov ax, 0xCAFE
    mov cx, 256
    rep stosw
    mov eax, EDD_WRITE_LBA
    mov cx, 1
    mov bx, 0xA600
    xor dx, dx
    call set_dap
    mov si, dap
    mov ax, 0x4300
    mov dl, 0x80
    int 0x13
    mov al, 0x45
    jc fail
    cmp word [dap + 2], 1
    mov al, 0x46
    jne fail
    mov eax, EDD_WRITE_LBA
    mov cx, 1
    mov bx, 0xA800
    xor dx, dx
    call set_dap
    call edd_read
    mov al, 0x47
    jc fail
    mov di, 0xA800
    mov ax, 0xCAFE
    mov cx, 256
    repe scasw
    mov al, 0x48
    jne fail

    ; Rejected extended and legacy writes must preserve a complete sector.
    mov di, 0xA600
    mov ax, 0xC3C3
    mov cx, 256
    rep stosw
    mov eax, PROTECTED_LBA
    mov cx, 1
    mov bx, 0xA600
    xor dx, dx
    call set_dap
    mov si, dap
    mov ax, 0x4302
    mov dl, 0x80
    int 0x13
    mov al, 0x38
    jnc fail
    cmp ah, 1
    jne fail
    cmp word [dap + 2], 0
    mov al, 0x77
    jne fail
    mov eax, PROTECTED_LBA
    mov cx, 1
    mov bx, 0xA800
    xor dx, dx
    call set_dap
    call edd_read
    mov al, 0x39
    jc fail
    mov di, 0xA800
    mov ax, 0x5A5A
    mov cx, 256
    repe scasw
    mov al, 0x3A
    jne fail

    mov di, 0xFE00
    mov ax, 0xC3C3
    mov cx, 256
    rep stosw
    mov eax, PROTECTED_LBA
    mov cx, 2
    mov bx, 0xFE00
    xor dx, dx
    call set_dap
    mov si, dap
    mov ax, 0x4300
    mov dl, 0x80
    int 0x13
    mov al, 0x74
    jnc fail
    cmp ah, 4
    jne fail
    cmp word [dap + 2], 0
    jne fail
    mov eax, PROTECTED_LBA
    mov cx, 1
    mov bx, 0xA800
    xor dx, dx
    call set_dap
    call edd_read
    mov al, 0x75
    jc fail
    mov di, 0xA800
    mov ax, 0x5A5A
    mov cx, 256
    repe scasw
    mov al, 0x76
    jne fail

    mov bx, 0xFE00
    mov ax, 0x0302
    mov cx, 0x000F
    xor dh, dh
    mov dl, 0x80
    int 0x13
    mov bl, al
    mov al, 0x49
    jnc fail
    cmp ah, 4
    jne fail
    test bl, bl
    jne fail
    cmp cx, 0x000F
    mov al, 0xD8
    jne fail
    cmp dx, 0x0080
    mov al, 0xD9
    jne fail
    mov eax, PROTECTED_LBA
    mov cx, 1
    mov bx, 0xA800
    xor dx, dx
    call set_dap
    call edd_read
    mov al, 0x4A
    jc fail
    mov di, 0xA800
    mov ax, 0x5A5A
    mov cx, 256
    repe scasw
    mov al, 0x4B
    jne fail

    ; Verify and seek must distinguish valid and invalid disk ranges.
    mov eax, DISK_SECTORS - 1
    mov cx, 1
    mov bx, BOOT_EDGE_BUFFER
    xor dx, dx
    call set_dap
    mov si, dap
    mov ax, 0x4400
    mov dl, 0x80
    int 0x13
    mov al, 0x3B
    jc fail
    cmp word [dap + 2], 1
    mov al, 0x4C
    jne fail
    mov word [dap + 2], 1
    mov ax, 0x4700
    int 0x13
    mov al, 0x3C
    jc fail
    cmp word [dap + 2], 0
    mov al, 0x4D
    jne fail

    mov eax, DISK_SECTORS - 1
    mov cx, 2
    mov bx, BOOT_EDGE_BUFFER
    xor dx, dx
    call set_dap
    mov si, dap
    mov ax, 0x4400
    mov dl, 0x80
    int 0x13
    mov al, 0x4E
    jnc fail
    cmp ah, 4
    jne fail
    cmp word [dap + 2], 0
    mov al, 0x4F
    jne fail
    mov eax, DISK_SECTORS
    mov cx, 1
    mov bx, BOOT_EDGE_BUFFER
    xor dx, dx
    call set_dap
    mov si, dap
    mov ax, 0x4700
    mov dl, 0x80
    int 0x13
    mov al, 0x50
    jnc fail
    cmp ah, 4
    jne fail
    cmp word [dap + 2], 0
    mov al, 0x51
    jne fail

    ; Early packet rejection must return a zero transfer count.
    check_dap_rejection 0x42, 0x81, 0x01, 0x80
    check_dap_rejection 0x43, 0x81, 0x01, 0x83
    check_dap_rejection 0x44, 0x81, 0x01, 0x86
    check_dap_rejection 0x47, 0x81, 0x01, 0x89
    mov word [dap + 2], 0xBEEF
    mov si, dap
    mov ax, 0x9900
    mov dl, 0x81
    int 0x13
    mov al, 0x8C
    jnc fail
    cmp ah, 1
    mov al, 0x8D
    jne fail
    cmp word [dap + 2], 0xBEEF
    mov al, 0x8E
    jne fail

    ; Write the completion marker only after every test has passed.
    mov di, 0xA800
    mov ax, 0
    mov cx, 256
    rep stosw
    mov dword [0xA800], 0x4F494142       ; "BAIO"
    mov dword [0xA804], 0x4B4F5F53       ; "S_OK"
    mov eax, COMPLETION_LBA
    mov cx, 1
    mov bx, 0xA800
    xor dx, dx
    call set_dap
    mov si, dap
    mov ax, 0x4300
    mov dl, 0x80
    int 0x13
    mov al, 0x3D
    jc fail

    mov al, 0x7F
    out 0x80, al
    mov ah, 0x0E
    mov bx, 7
    mov al, 'P'
    int 0x10
    jmp fail.halt

fault_stage:
    ; Exercise the real polling loops through the test-only ATA status seam.
    xor ax, ax
    mov dl, 0x80
    int 0x13
    mov al, 0x52
    jc fail

    ; A read is complete only after the device clears BSY without ERR or DF.
    mov bx, 0x0180
    call arm_after_read
    mov eax, 1
    mov cx, 1
    mov bx, BOOT_WORK_BUFFER
    xor dx, dx
    call set_dap
    call edd_read
    mov al, 0x90
    jnc fail
    cmp ah, 0x80
    mov al, 0x91
    jne fail
    cmp word [dap + 2], 0
    mov al, 0x92
    jne fail
    call recover_disk
    mov al, 0x93
    jc fail

    mov bx, 0x0121
    call arm_after_read
    mov eax, 1
    mov cx, 1
    mov bx, BOOT_WORK_BUFFER
    xor dx, dx
    call set_dap
    call edd_read
    mov al, 0x94
    jnc fail
    cmp ah, 0x20
    mov al, 0x95
    jne fail
    cmp word [dap + 2], 0
    mov al, 0x96
    jne fail
    call recover_disk
    mov al, 0x97
    jc fail

    mov bx, 0x0221
    call arm_after_read
    mov eax, 1
    mov cx, 2
    mov bx, BOOT_WORK_BUFFER
    xor dx, dx
    call set_dap
    call edd_read
    mov al, 0x98
    jnc fail
    cmp ah, 0x20
    mov al, 0x99
    jne fail
    cmp word [dap + 2], 1
    mov al, 0x9A
    jne fail
    call recover_disk
    mov al, 0x9B
    jc fail

    mov bx, 0x0180
    call arm_after_read
    mov bx, BOOT_WORK_BUFFER
    mov ax, 0x0201
    mov cx, 1
    xor dh, dh
    mov dl, 0x80
    int 0x13
    mov bl, al
    mov al, 0xB0
    jnc fail
    cmp ah, 0x80
    mov al, 0xB1
    jne fail
    test bl, bl
    mov al, 0xB2
    jne fail
    call recover_disk
    mov al, 0xB3
    jc fail

    mov bx, 0x0121
    call arm_after_read
    mov bx, BOOT_WORK_BUFFER
    mov ax, 0x0201
    mov cx, 1
    xor dh, dh
    mov dl, 0x80
    int 0x13
    mov bl, al
    mov al, 0xB4
    jnc fail
    cmp ah, 0x20
    mov al, 0xB5
    jne fail
    test bl, bl
    mov al, 0xB6
    jne fail
    call recover_disk
    mov al, 0xB7
    jc fail

    mov bx, 0x0221
    call arm_after_read
    mov bx, BOOT_WORK_BUFFER
    mov ax, 0x0202
    mov cx, 1
    xor dh, dh
    mov dl, 0x80
    int 0x13
    mov bl, al
    mov al, 0xB8
    jnc fail
    cmp ah, 0x20
    mov al, 0xB9
    jne fail
    cmp bl, 1
    mov al, 0xBA
    jne fail
    call recover_disk
    mov al, 0xBB
    jc fail

    call fault_on
    xor ax, ax
    mov dl, 0x80
    int 0x13
    mov al, 0x53
    jnc fail
    cmp ah, 0x80
    mov al, 0x54
    jne fail
    cmp dl, 0x80
    mov al, 0xDA
    jne fail
    call recover_disk
    mov al, 0x55
    jc fail

    call fault_on
    mov bx, BOOT_WORK_BUFFER
    mov ax, 0x0201
    mov cx, 1
    xor dh, dh
    mov dl, 0x80
    int 0x13
    mov al, 0x56
    jnc fail
    cmp ah, 0x80
    mov al, 0x57
    jne fail
    cmp cx, 1
    mov al, 0xCA
    jne fail
    cmp dx, 0x0080
    mov al, 0xCB
    jne fail
    call recover_disk
    mov al, 0x58
    jc fail

    call fault_on
    mov bx, BOOT_WORK_BUFFER
    mov ax, 0x0301
    mov cx, 1
    xor dh, dh
    mov dl, 0x80
    int 0x13
    mov al, 0x59
    jnc fail
    cmp ah, 0x80
    mov al, 0x5A
    jne fail
    cmp cx, 1
    mov al, 0xCC
    jne fail
    cmp dx, 0x0080
    mov al, 0xCD
    jne fail
    call recover_disk
    mov al, 0x5B
    jc fail

    mov eax, 1
    mov cx, 1
    mov bx, BOOT_WORK_BUFFER
    xor dx, dx
    call set_dap
    call fault_on
    call edd_read
    mov al, 0x5C
    jnc fail
    cmp ah, 0x80
    mov al, 0x5D
    jne fail
    cmp word [dap + 2], 0
    mov al, 0x5E
    jne fail
    call recover_disk
    mov al, 0x5F
    jc fail

    mov eax, EDD_WRITE_LBA
    mov cx, 1
    mov bx, BOOT_WORK_BUFFER
    xor dx, dx
    call set_dap
    call fault_on
    mov si, dap
    mov ax, 0x4300
    mov dl, 0x80
    int 0x13
    mov al, 0x61
    jnc fail
    cmp ah, 0x80
    mov al, 0x65
    jne fail
    cmp word [dap + 2], 0
    mov al, 0x66
    jne fail
    call recover_disk
    mov al, 0x67
    jc fail

    mov eax, 1
    mov cx, 1
    mov bx, BOOT_WORK_BUFFER
    xor dx, dx
    call set_dap
    call fault_on
    mov si, dap
    mov ax, 0x4400
    mov dl, 0x80
    int 0x13
    mov al, 0x68
    jnc fail
    cmp ah, 0x80
    mov al, 0x69
    jne fail
    cmp word [dap + 2], 0
    mov al, 0x6A
    jne fail
    call recover_disk
    mov al, 0x6B
    jc fail

    ; Pre-command ERR/DF is stale. Without DRDY, both entry paths time out.
    call controller_on
    xor ax, ax
    mov dl, 0x80
    int 0x13
    mov al, 0x7A
    jnc fail
    cmp ah, 0x80
    mov al, 0x7B
    jne fail
    call recover_disk
    mov al, 0x7C
    jc fail

    mov eax, 1
    mov cx, 1
    mov bx, BOOT_WORK_BUFFER
    xor dx, dx
    call set_dap
    call controller_on
    call edd_read
    mov al, 0x7D
    jnc fail
    cmp ah, 0x80
    mov al, 0x7E
    jne fail
    cmp word [dap + 2], 0
    mov al, 0x7F
    jne fail
    call recover_disk
    jc fail

    ; Missing-device dispatch must reject reset and transfer services.
    mov ax, 0xEF01
    int 0x15
    mov al, 0x6C
    jc fail
    mov ax, 0x9900
    mov dl, 0x80
    int 0x13
    mov al, 0x78
    jnc fail
    cmp ah, 1
    mov al, 0x79
    jne fail
    xor ax, ax
    mov dl, 0x80
    int 0x13
    mov al, 0x6D
    jnc fail
    cmp ah, 0x80
    mov al, 0x6E
    jne fail
    check_dap_rejection 0x42, 0x80, 0x80, 0xA0
    check_dap_rejection 0x43, 0x80, 0x80, 0xA3
    check_dap_rejection 0x44, 0x80, 0x80, 0xA6
    check_dap_rejection 0x47, 0x80, 0x80, 0xA9
    mov word [dap + 2], 0xBEEF
    mov si, dap
    mov ax, 0x9900
    mov dl, 0x80
    int 0x13
    mov al, 0xAC
    jnc fail
    cmp ah, 1
    mov al, 0xAD
    jne fail
    cmp word [dap + 2], 0xBEEF
    mov al, 0xAE
    jne fail
    mov ax, 0xEF02
    int 0x15
    mov al, 0x71
    jc fail

    mov al, 0x62
    jmp fail

fault_on:
    mov ax, 0xEFA1
    int 0x15
    ret

controller_on:
    mov ax, 0xEF21
    int 0x15
    ret

arm_after_read:
    mov ax, 0xEF03
    int 0x15
    ret

fault_off:
    mov ax, 0xEF00
    int 0x15
    ret

; INT clears IF even when the caller has interrupts enabled. Queue IRQ0
; with IF clear, then prove the HDD service accepts it before returning.
; Count only an interrupted BIOS CS, not a tick delivered after IRET.
%include "vga-check.inc"

check_disk_interrupts:
    cli
    push dword [0x1C * 4]
    mov word [0x1C * 4], .tick
    mov word [0x1C * 4 + 2], 0
    mov word [cs:disk_irq_ticks], 0
    mov ecx, 0x00100000
.pending:
    mov al, 0x0A
    out 0x20, al
    in al, 0x20
    test al, 1
    jnz .read
    dec ecx
    jnz .pending
    mov al, 0x6D
    jmp fail
.read:
    mov bx, BOOT_WORK_BUFFER
    mov ax, 0x0201
    mov cx, BULK_LBA + 1
    mov dx, 0x0080
    int 0x13
    mov al, 0x6D
    jc fail
    cmp word [cs:disk_irq_ticks], 0
    je fail
    pushf
    pop ax
    test ax, 0x0200
    mov al, 0x6D
    jz fail                    ; OEM returns with interrupts enabled.
    cli
    pop dword [0x1C * 4]
    sti
    ret
.tick:
    push bp
    mov bp, sp
    cmp word [ss:bp+52], 0xF000 ; int08's original interrupted CS.
    jne .outside_bios
    inc word [cs:disk_irq_ticks]
.outside_bios:
    pop bp
    iret
disk_irq_ticks: dw 0

recover_disk:
    call fault_off
    xor ax, ax
    mov dl, 0x80
    int 0x13
    ret

set_dap:
    mov byte [dap], 0x10
    mov byte [dap + 1], 0
    mov [dap + 2], cx
    mov [dap + 4], bx
    mov [dap + 6], dx
    mov [dap + 8], eax
    mov dword [dap + 12], 0
    ret

edd_read:
    mov si, dap
    mov ax, 0x4200
    mov dl, 0x80
    int 0x13
    ret

; These helpers belong only to the disposable synthetic-disk guest.
fill_hma_sector:
    push es
    mov dx, 0xFFFF
    mov es, dx
    mov di, 0x0510
    mov cx, 256
    rep stosw
    pop es
    ret

check_hma_write:
    ; Read through a distinct conventional buffer, then restore the sentinel.
    xor ax, ax
    mov es, ax
    mov di, BOOT_WORK_BUFFER
    mov cx, 256
    rep stosw
    mov eax, BULK_LBA
    mov cx, 1
    mov bx, BOOT_WORK_BUFFER
    xor dx, dx
    call set_dap
    call edd_read
    mov al, 0x6A
    jc fail
    mov di, BOOT_WORK_BUFFER
    mov ax, bp
    mov cx, 256
    repe scasw
    mov al, 0x6A
    jne fail
    mov di, BOOT_WORK_BUFFER
    mov ax, 0xA5A5
    mov cx, 256
    rep stosw
    mov word [dap + 2], 1
    mov si, dap
    mov ax, 0x4300
    mov dl, 0x80
    int 0x13
    mov al, 0x6A
    jc fail
    ret

check_bulk_sentinel:
    mov eax, BULK_LBA
    mov cx, 1
    mov bx, BOOT_WORK_BUFFER
    xor dx, dx
    call set_dap
    call edd_read
    jc .done
    push es
    xor ax, ax
    mov es, ax
    mov di, BOOT_WORK_BUFFER
    mov ax, 0xA5A5
    mov cx, 256
    repe scasw
    pop es
    je .ok
    stc
.done:
    ret
.ok:
    clc
    ret

align 4
dap:
    times 16 db 0
edd_parameters:
    times 32 db 0

times 16 * 512 - ($ - $$) db 0
