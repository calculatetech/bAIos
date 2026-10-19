; Legacy ISA ROM initialization and non-returning bootstrap continuation.
; Unused first-record gap3D..50, before chipset60; never floppy80/mouseB0.
%define R_SCANNED 0x3D
%define R_NEXT    0x3E
%define R_ENTRY   0x40               ; offset,segment
%define R_SS      0x44
%define R_SP      0x46
%define B_CURSOR  0x48               ; Next saved selection,0..4.
%define B_ACTIVE  0x49
%define B_DRIVE   0x4A
%define B_ROM19   0x4C               ; Installed option-ROM bootstrap chain.

option_rom_discovery:
    pushf
    pushad
    push ds
    push es
    push fs
    push gs
    cld
    call load_bios_state
    cmp byte [fs:R_SCANNED], 1
    je .return
    mov byte [fs:R_SCANNED], 1
    ; ROMs capture this continuation while initializing. The public INT19
    ; router is installed after discovery, so Other owns their boot priority.
    xor ax, ax
    mov es, ax
    mov word [es:0x64], boot_rom_fallback
    mov word [es:0x66], 0xF000
%ifdef BOARD_OPTION_ROM_INIT
    call BOARD_OPTION_ROM_INIT
%endif
%ifdef BOARD_OPTION_ROM_FIRST_SEG
    mov dx, BOARD_OPTION_ROM_FIRST_SEG
%else
    mov dx, 0xC800
%endif
    ; Video was validated and initialized before discovery. Skip its full
    ; declared extent, preserving the selected floor and2KiB probe policy.
    mov ax, 0xC000
    mov ds, ax
    movzx ax, byte [2]
    shl ax, 5                      ; 512-byte units to paragraphs.
    add ax, 0xC07F
    and ax, 0xFF80
    cmp dx, ax
    jae .scan
    mov dx, ax
.scan:
%ifdef BOARD_OPTION_ROM_SKIP
    call BOARD_OPTION_ROM_SKIP
%endif
    cmp dx, 0xE000
    jae .done
    mov ds, dx
    cmp word [0], 0xAA55
    jne .next
    movzx ax, byte [2]
    test ax, ax
    jz .bad
    mov bp, ax
    shl ax, 5                      ; 512-byte units to paragraphs.
    add ax, dx
    jc .bad
    cmp ax, 0xE000
    ja .bad
    mov di, ax
    xor bx, bx
.sum_unit:
    xor si, si
    mov cx, 512
.sum_byte:
    lodsb
    add bl, al
    loop .sum_byte
    mov ax, ds
    add ax, 32
    mov ds, ax
    dec bp
    jnz .sum_unit
    test bl, bl
    jnz .bad
    add di, 0x7F                   ; Skip every covered2KiB probe position.
    and di, 0xFF80
    mov [fs:R_NEXT], di
    mov word [fs:R_ENTRY], 3
    mov [fs:R_ENTRY+2], dx
    call post_ui_rom
    pushf
    pushad
    push ds
    push es
    push fs
    push gs
    mov [fs:R_SS], ss
    mov [fs:R_SP], sp
    mov ds, dx
    xor ax, ax
    mov es, ax                     ; ES:DI is not a PnP installation pointer.
    xor di, di
    cld
    sti
    call far [fs:R_ENTRY]
    ; A returning legacy image can leave arbitrary segments/IF/DF/stack.
    ; Resolve the current EBDA inline before touching its saved BIOS frame.
    cli
    xor ax, ax
    mov fs, ax
    mov fs, [fs:0x040E]
    mov ss, [fs:R_SS]
    mov sp, [fs:R_SP]
    pop gs
    pop fs
    pop es
    pop ds
    popad
    popf
    cld
    call load_bios_state
    mov dx, [fs:R_NEXT]
    jmp .scan
.bad:
    xor ax, ax
    mov ds, ax
    or byte [fs:C_ERROR], 0x10
    cmp byte [fs:P_PHASE], 0
    je .error_text
    pushad
    call post_message_cursor
    popad
.error_text:
    mov si, msg_rom_invalid
    call print_string
    call post_error_notice
    call load_bios_state
    cld
.next:
    add dx, 0x80
    jmp .scan
.done:
    xor ax, ax
    mov ds, ax
    mov eax, [0x64]
    cmp eax, (0xF000 << 16) + (boot_rom_fallback - $$)
    jne .save_boot_chain
    xor eax, eax
.save_boot_chain:
    mov [fs:B_ROM19], eax
    mov dword [0x64], (0xF000 << 16) + (int19 - $$)
.return:
    pop gs
    pop fs
    pop es
    pop ds
    popad
    popf
    ret

; INT18/19 and retry deliberately abandon the caller's failed stack.
; Reuse POST's bounded0:7000 stack and the current relocatable EBDA owner.
%macro boot_context 0
    cli
    cld
    xor ax, ax
    mov ds, ax
    mov es, ax
    mov gs, ax
    mov ss, ax
    mov esp, 0x7000
    mov fs, ax
    mov fs, [fs:0x040E]
%endmacro

boot_rom_fallback:
    boot_context
    cmp byte [fs:B_ACTIVE], 0xA5
    jne int19
    jmp boot_candidate

int19:
    boot_context
%ifdef BOARD_LATE_POST_TRACE
    post_code 0x5F
%endif
%ifdef BOARD_BOOT_HANDOFF
    call BOARD_BOOT_HANDOFF
%endif
    call cd_boot_clear
    mov byte [fs:B_CURSOR], 0
    mov byte [fs:B_ACTIVE], 0xA5
    mov byte [0x0400+KB_POST_STATE], 2
    ; Use installed INT13 reset owners for corrected removable media.
    xor dx, dx
    xor ax, ax
    sti
    int 0x13
    boot_context
    cmp byte [0x0475], 0
    je boot_candidate
    mov dx, 0x80
    xor ax, ax
    sti
    int 0x13
    boot_context
    jmp boot_candidate

int18:
    boot_context
    cmp byte [fs:B_ACTIVE], 0xA5
    je boot_candidate
    mov byte [fs:B_CURSOR], 0        ; A card chained into BIOS before our order.
    mov byte [fs:B_ACTIVE], 0xA5

boot_candidate:
    boot_context
    call cd_boot_clear
    movzx bx, byte [fs:B_CURSOR]
    cmp bx, 4
    jae boot_retry
    inc byte [fs:B_CURSOR]          ; Persist before a provider/sector takes control.
    mov al, [fs:C_BOOT]
    test bx, bx
    jz .selected
    mov al, [fs:C_BOOT_SECOND]
    cmp bx, 1
    je .selected
    mov al, [fs:C_BOOT_THIRD]
    cmp bx, 2
    je .selected
    mov al, [fs:C_BOOT_FOURTH]
.selected:
    test al, al
    jz boot_candidate
    cmp al, 4
    je .other
    cmp al, 3
    jne .ordinary
    sti
    call cd_boot
    jmp boot_candidate
.other:
    cmp dword [fs:B_ROM19], 0
    je boot_candidate
    sti
    pushf
    call far [fs:B_ROM19]
    jmp boot_candidate
.ordinary:
    xor dx, dx
    cmp al, 1
    jne .hdd
    cmp byte [fs:C_PORTS+P_FLOPPY], 0
    je boot_candidate
    cmp byte [fs:F_TYPES], 0
    jz boot_candidate
    jmp .read
.hdd:
    cmp byte [0x0475], 0            ; Published by native ATA or a ROM provider.
    je boot_candidate
    mov dx, 0x80
.read:
    mov [fs:B_DRIVE], dx
    mov word [es:0x7DFE], 0         ; Failed reads cannot reuse a signed old buffer.
    mov bx, 0x7C00
    mov ax, 0x0201
    mov cx, 1
    sti
    int 0x13
    setc bl
    boot_context
    test bl, bl
    jnz boot_candidate
    cmp word [es:0x7DFE], 0xAA55
    jne boot_candidate
    mov dx, [fs:B_DRIVE]
    mov byte [0x0400+KB_POST_STATE], 0
    sti
    jmp 0:0x7C00

boot_retry:
    boot_context
    mov byte [0x0400+KB_POST_STATE], 2
    ; Drain bounded pending controller scans through the existing IRQ owner,
    ; then discard the old BIOS queue. Pause/release still owns its own state.
    mov cx, 32
.flush:
    sti                         ; Let a latched IRQ1 consume its own stale scan.
    nop
    cli
    call keyboard_poll
    loop .flush
    mov ax, [0x041C]
    mov [0x041A], ax
    mov si, msg_boot_unavailable
    call print_string
    mov si, msg_boot_retry
    call print_string
    post_code 0xE4
%ifdef EMULATOR_BOOT_RETRY_EXIT
%ifdef BOARD_BOOT_RETRY_TEST_SOURCE
    call core_boot_retry_observe
%else
    mov al, EMULATOR_BOOT_RETRY_EXIT
    call emulator_exit          ; Test-only observation of the new retry terminal.
%endif
%endif
.wait:
    call post_keyboard_wait
    mov ah, 1
    int 0x16
    jnz .key
    sti
    hlt
    cli
    jmp .wait
.key:
    xor ah, ah
    int 0x16                       ; One fresh key belongs only to retry.
    boot_context
    mov word [fs:B_CURSOR], 0       ; Fresh chain may enter BIOS18 before BIOS19.
    mov byte [0x0400+KB_POST_STATE], 2
    sti
    int 0x19                       ; Restart the installed legacy chain, not POST.
    jmp boot_retry                 ; A returning chain remains bounded too.

msg_rom_invalid db 'Expansion ROM invalid; skipped.',13,10,0
msg_boot_unavailable db 'No boot device available',13,10,0
msg_boot_retry db 'Press any key to retry',13,10,0
%ifdef EMULATOR_BOOT_RETRY_EXIT
%ifdef BOARD_BOOT_RETRY_TEST_SOURCE
%include BOARD_BOOT_RETRY_TEST_SOURCE
%endif
%endif
