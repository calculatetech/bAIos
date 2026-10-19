; Live 80x25 POST presentation. State is transient and follows the EBDA.
post_ui_begin:
    pushad
    push ds
    push es
    call load_bios_state
    call setup_restore_text
    push cs
    pop ds
    mov ax, 0xB800
    mov es, ax
    xor di, di
    mov ax, 0x0720
    mov cx, 2000
    cld
    rep stosw
    call post_header
    ui_text 2, 3, u_summary_processor, 0x0B
    call post_processor_name
    mov di, 2*160+24*2
    mov bh, 7
    call setup_text
    cmp byte [fs:P_PHASE], 0
    je .keys
    call post_ui_cache
    cmp byte [fs:P_RAM_FLAGS], 0
    je .drives
    ui_text 5, 3, u_post_ram, 0x0B
    ui_text 5, 30, u_kb, 7
    memory_installed_kib eax
    add eax, 1024
    mov di, 5*160+24*2
    call post_count
    call post_ram_status
    cmp byte [fs:P_PHASE], 2
    jb .drives
    call post_ui_banks
.drives:
    cmp byte [fs:P_PHASE], 3
    jb .keys
    call post_ui_floppy
    cmp byte [fs:P_PHASE], 4
    jb .keys
    call post_ui_disks
    cmp byte [fs:P_PHASE], 5
    jb .keys
    call post_ui_roms
.keys:
    ui_text 24, 3, u_post_keys, 8
    call post_message_cursor
    pop es
    pop ds
    popad
    ret

post_ui_floppy:
    pushad
    push ds
    push es
    push cs
    pop ds
    mov ax, 0xB800
    mov es, ax
    ui_text 8, 3, u_drive_a, 0x0B
    ui_text 9, 3, u_drive_b, 0x0B
    mov di, 8*160+24*2
    call post_clear_value
    mov al, [fs:F_TYPES]
    call post_debug_summary.floppy
    mov di, 9*160+24*2
    call post_clear_value
    mov al, [fs:F_TYPES+1]
    call post_debug_summary.floppy
    pop es
    pop ds
    popad
    ret

post_ui_disks:
    pushad
    push ds
    push es
    push fs
    push cs
    pop ds
    mov ax, 0xB800
    mov es, ax
    call post_device_label
    mov di,11*160+3*2
    mov bh,0x0B
    call setup_text
    mov bp, 11*160
    call .device
    mov ax, fs
    add ax, 0x20
    mov fs, ax
    call post_device_label
    mov di,12*160+3*2
    mov bh,0x0B
    call setup_text
    mov bp, 12*160
    call .device
    pop fs
    pop es
    pop ds
    popad
    ret
.device:
    mov di, bp
    add di, 24*2
    push di
    mov ax, 0x0720
    mov cx, 55
    rep stosw
    pop di
    mov si, u_disabled
    cmp byte [fs:S_CONTROLLER], 0
    je .disabled
    cmp byte [fs:C_HDD], 1
    je .detected
.disabled:
    mov bh, 7
    jmp setup_text
.detected:
    mov si, u_absent
    cmp byte [fs:S_PRESENT], 1
    je .model
    cmp byte [fs:S_ATAPI], 1
    jne .disabled
.model:
    mov si, S_MODEL
    mov cx, 40
.character:
    mov al, [fs:si]
    inc si
    test al, al
    jz .done
    mov ah, 7
    stosw
    loop .character
.done:
    ret

; Publish the current IDE position as soon as its existing probe returns.
post_ui_disk:
    pushad
    push ds
    push es
    push fs
    call load_bios_state
    cmp byte [fs:P_PHASE], 0
    pop fs
    je .done
    push cs
    pop ds
    mov ax, 0xB800
    mov es, ax
    mov bp, 11*160
    mov ax,fs
    cmp ax,STATE_SEG
    jne .slave
    call post_device_label
    mov di,11*160+3*2
    mov bh,0x0B
    call setup_text
    jmp .result
.slave:
    mov bp, 12*160
    call post_device_label
    mov di,12*160+3*2
    mov bh,0x0B
    call setup_text
.result:
    call post_ui_disks.device
.done:
    pop es
    pop ds
    popad
    ret

post_ram_start:
    mov byte [fs:P_RAM_FLAGS], 1
    pushad
    push ds
    push es
    push cs
    pop ds
    mov ax, 0xB800
    mov es, ax
    ui_text 5, 3, u_post_ram, 0x0B
    ui_text 5, 30, u_kb, 7
    xor eax, eax
    mov di, 5*160+24*2
    call post_count
    call post_ram_status
    pop es
    pop ds
    popad
    ret

post_ram_finish:
    mov al, 4
    cmp byte [fs:S_SETUP_REQUEST], 1
    je .skip
    test byte [fs:P_RAM_FLAGS], 2
    jz .set
.skip:
    mov al, 2
.set:
    mov [fs:P_RAM_FLAGS], al
    pushad
    push ds
    push es
    push cs
    pop ds
    mov ax, 0xB800
    mov es, ax
%ifdef BOARD_FAST_BOOT_SETTING
    cmp byte [fs:BOARD_FAST_BOOT_SETTING], 1
    jne .status
    memory_installed_kib eax
    add eax, 1024
    mov di, 5*160+24*2
    call post_count
.status:
%endif
    call post_ram_status
    call post_ui_banks
    pop es
    pop ds
    popad
    ret

; Called only once the visible RAM owner has returned or during its redraw.
post_ui_banks:
    ui_text 6, 3, u_summary_banks, 0x0B
    mov di, 6*160+24*2
    jmp post_memory_banks

post_ui_roms:
    pushad
    push ds
    push es
    push cs
    pop ds
    mov ax, 0xB800
    mov es, ax
    ui_text 15, 3, u_post_vga, 0x0B
    mov dx, 0xC000
    mov bx, 0x0800
    call post_rom_state
    mov di, 15*160+24*2
    call post_rom_state_text
    ui_text 16, 3, u_post_system, 0x0B
    mov dx, 0xF000
    mov bx, 0x1000
    call post_rom_state
    mov di, 16*160+24*2
    call post_rom_state_text
    ui_text 17, 3, u_post_roms, 0x0B
    ui_text 17, 24, u_absent, 7
    pop es
    pop ds
    popad
    ret

post_ram_status:
    mov di, 5*160+34*2
    call post_clear_value
    mov si, u_post_blank
    test byte [fs:P_RAM_FLAGS], 2
    jz .passed
    mov si, u_post_skipped
    jmp .text
.passed:
    test byte [fs:P_RAM_FLAGS], 4
    jz .text
    mov si, u_post_passed
.text:
    mov bh, 7
    jmp setup_text

post_clear_value:
    push ax
    push cx
    push di
    mov ax, 0x0720
    mov cx, 19
    rep stosw
    pop di
    pop cx
    pop ax
    ret

; Left-aligned decimal count; clear the field when replacing a longer value.
post_count:
    pushad
    push eax
    push di
    mov cx, MEMORY_COUNT_DIGITS
    mov ax, 0x0720
    rep stosw
    pop di
    pop eax
    call setup_number
    popad
    ret

post_entering_setup:
    pushad
    push ds
    push es
    push cs
    pop ds
    mov ax, 0xB800
    mov es, ax
    mov di, 22*160
    mov ax, 0x0720
    mov cx, 80
    rep stosw
    ui_text 22, 3, u_post_entering, 0x0F
    pop es
    pop ds
    popad
    ret

post_early_setup:
    pushf
    pushad
    push ds
    push es
    push fs
    call load_bios_state
    mov cx, 32
.poll:
    sti
    nop
    call post_keyboard_wait
    in al, KBC_STATUS
    and al, 0x21
    cmp al, 1
    jne .request
    loop .poll
.request:
    cmp byte [fs:S_SETUP_REQUEST], 1
    jne .done
    call post_entering_setup
    call setup_main
    xor ax, ax
    mov ds, ax
    mov byte [0x0400+KB_POST_STATE], 1
    call post_ui_begin
.done:
    pop fs
    pop es
    pop ds
    popad
    popf
    ret

post_message_cursor:
    pushf
    pushad
    push es
    mov ax, 0xB800
    mov es, ax
    mov di, 22*160
    mov ax, 0x0720
    mov cx, 160
    cld
    rep stosw               ; A new notice replaces only the two message rows.
    mov dx, 0x1603
    xor bx, bx
    mov ah, 2
    int 0x10
    pop es
    popad
    popf
    ret

; DX is a validated add-in ROM segment. Emit every record; scroll this group.
post_ui_rom:
    pushad
    push ds
    push es
    mov ds, dx
    movzx bx, byte [2]
    shl bx, 5
    push cs
    pop ds
    call post_rom_state
    push ax
    mov ax, 0xB800
    mov es, ax
    movzx ax, byte [fs:P_ROM_COUNT]
    cmp ax, 4
    jb .row
    push ds
    push es
    pop ds
    mov si, 19*160
    mov di, 18*160
    mov cx, 3*80
    cld
    rep movsw
    mov ax, 0x0720
    mov cx, 80
    rep stosw
    pop ds
    mov ax, 3
.row:
    add ax, 18
    imul ax, 160
    mov di, ax
    add di, 3*2
    mov al, dh
    call setup_hex8
    mov al, dl
    call setup_hex8
    mov ax, 0x0768
    stosw
    add di, 16 ; State at column16, after the address and spacing.
    pop ax
    call post_rom_state_text
    inc byte [fs:P_ROM_COUNT]
    mov di, 17*160+24*2
    call post_clear_value
    movzx eax, byte [fs:P_ROM_COUNT]
    call setup_number
    ui_text 17, 28, u_post_detected, 7
    pop es
    pop ds
    popad
    ret

; DX=start segment, BX=extent in paragraphs. AL=any state, AH=all state:
; bit0 shadowed, bit1 cache eligible, bit2 uncertain primary policy.
; Read configuration only. Sample every2KiB, including the final short block.
post_rom_state_text:
    push ax
    mov si, u_post_unshadowed
    test al, 1
    jz .shadow
    mov si, u_post_partial_shadow
    test ah, 1
    jz .shadow
    mov si, u_post_shadowed
.shadow:
    mov bh, 7
    call .advance
    mov si, u_post_separator
    call .advance
    pop ax
    mov si, u_post_unknown_cache
    test al, 4
    jnz .cache
    mov si, u_post_uncached
    test al, 2
    jz .cache
    mov si, u_post_partial_cache
    test ah, 2
    jz .cache
    mov si, u_post_cached
.cache:
    jmp setup_text
.advance:
    call setup_text
    push ax
    push si
.length:
    lodsb
    test al, al
    jz .done
    add di, 2
    jmp .length
.done:
    pop si
    pop ax
    ret

%ifdef EMULATOR_CHIPSET_POST_UI
post_ui_capture:
%ifdef EMULATOR_CHIPSET_PREVIEW
.hold:
    sti
    hlt
    jmp .hold
%else
    mov dx, 0x03DA
    mov cx, 2
.low:
    in al, dx
    test al, 8
    jnz .low
.high:
    in al, dx
    test al, 8
    jz .high
    loop .low
    call setup_test_snapshot
    call setup_test_dump
    mov al, 0x67
    call emulator_exit
    jmp hard_halt
%endif
%endif

u_post_l1 db 'L1 Cache',0
u_post_enabled db 'Enabled',0
u_post_ram db 'RAM Test',0
u_post_blank db 0
u_post_skipped db 'Skipped',0
u_post_passed db 'Passed',0
u_post_master db 'Primary IDE Master',0
u_post_slave db 'Primary IDE Slave',0
u_post_roms db 'Option ROMs',0
u_post_vga db 'VGA BIOS',0
u_post_system db 'System BIOS',0
u_post_detected db 'detected',0
u_post_shadowed db 'Shadowed',0
u_post_unshadowed db 'Not shadowed',0
u_post_partial_shadow db 'Partly shadowed',0
u_post_separator db ', ',0
u_post_cached db 'Cached',0
u_post_uncached db 'Not cached',0
u_post_partial_cache db 'Partly cached',0
u_post_unknown_cache db 'Cache status unknown',0
u_post_cache_on db 'Enabled,',0
u_post_entering db 'Entering setup...',0
u_post_keys db 'Del: Setup    Esc: Skip RAM test',0
