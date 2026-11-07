post_ui_post_ui_begin:
    pushad
    push ds
    push es
    call post_ui_load_bios_state
    call post_ui_setup_restore_text
    post_ui_data_segment
    mov ax, 0xB800
    mov es, ax
    xor di, di
    mov ax, 0x0720
    mov cx, 2000
    cld
    rep stosw
    call post_ui_post_header
    ui_text 2, 3, u_summary_processor, 0x0B
    call post_ui_post_processor_name
    mov di, 2*160+24*2
    mov bh, 7
    call post_ui_setup_text
    cmp byte [fs:P_PHASE], 0
    je .keys
    call post_ui_post_ui_cache
    cmp byte [fs:P_RAM_FLAGS], 0
    je .drives
    ui_text BOARD_POST_RAM_ROW, 3, u_post_ram, 0x0B
    ui_text BOARD_POST_RAM_ROW, 30, u_kb, 7
    memory_installed_kib eax
    add eax, 1024
    mov di, BOARD_POST_RAM_ROW*160+24*2
    call post_ui_post_count
    call post_ui_post_ram_status
    cmp byte [fs:P_PHASE], 2
    jb .drives
    call post_ui_post_ui_banks
.drives:
    cmp byte [fs:P_PHASE], 3
    jb .keys
    call post_ui_post_ui_floppy
    cmp byte [fs:P_PHASE], 4
    jb .keys
    call post_ui_post_ui_disks
    cmp byte [fs:P_PHASE], 5
    jb .keys
    call post_ui_post_ui_roms
.keys:
    push ds
    push word 0x40
    pop ds
    cmp byte [KB_POST_STATE],1
    pop ds
    jne .no_keys
    ui_text 24, 3, u_post_keys, 8
.no_keys:
    call post_ui_post_message_cursor
    pop es
    pop ds
    popad
    ret

post_ui_post_ui_floppy:
    pushad
    push ds
    push es
    post_ui_data_segment
    mov ax, 0xB800
    mov es, ax
    ui_text 8, 3, u_drive_a, 0x0B
    ui_text 9, 3, u_drive_b, 0x0B
    mov di, 8*160+24*2
    call post_ui_post_clear_value
    mov al, [fs:F_TYPES]
    call post_ui_summary_floppy
    mov di, 9*160+24*2
    call post_ui_post_clear_value
    mov al, [fs:F_TYPES+1]
    call post_ui_summary_floppy
    pop es
    pop ds
    popad
    ret

post_ui_post_ui_disks:
    pushad
    push ds
    push es
    push fs
    post_ui_data_segment
    mov ax, 0xB800
    mov es, ax
    mov bp,11*160
    mov cx,BOARD_ATA_DEVICE_COUNT
.position:
    push cx
    call post_ui_post_device_label
    mov di,bp
    add di,3*2
    mov bh,0x0B
    call post_ui_setup_text
    call .device
    mov ax,fs
    add ax,0x20
    mov fs,ax
    add bp,160
    pop cx
    loop .position
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
%if BOARD_ATA_DEVICE_COUNT = 4
    cmp byte [fs:S_ENABLED],1
%else
    cmp byte [fs:C_HDD], 1
%endif
    je .detected
.disabled:
    mov bh, 7
    jmp post_ui_setup_text
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
post_ui_post_ui_disk:
    pushad
    push ds
    push es
    push fs
    call post_ui_load_bios_state
    cmp byte [fs:P_PHASE], 0
    pop fs
    je .done
    post_ui_data_segment
    mov ax, 0xB800
    mov es, ax
    push fs
    call post_ui_load_bios_state
    mov ax,fs
    pop fs
    mov dx,fs
    sub dx,ax
    shr dx,5
    imul bp,dx,160
    add bp,11*160
    call post_ui_post_device_label
    mov di,bp
    add di,3*2
    mov bh,0x0B
    call post_ui_setup_text
    call post_ui_disk_body
.done:
    pop es
    pop ds
    popad
    ret

post_ui_post_ram_start:
    mov byte [fs:P_RAM_FLAGS], 1
    pushad
    push ds
    push es
    post_ui_data_segment
    mov ax, 0xB800
    mov es, ax
    ui_text BOARD_POST_RAM_ROW, 3, u_post_ram, 0x0B
    ui_text BOARD_POST_RAM_ROW, 30, u_kb, 7
    xor eax, eax
    mov di, BOARD_POST_RAM_ROW*160+24*2
    call post_ui_post_count
    call post_ui_post_ram_status
    pop es
    pop ds
    popad
    ret

post_ui_post_ram_finish:
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
    post_ui_data_segment
    mov ax, 0xB800
    mov es, ax
%ifdef BOARD_FAST_BOOT_SETTING
    cmp byte [fs:BOARD_FAST_BOOT_SETTING], 1
    jne .status
    memory_installed_kib eax
    add eax, 1024
    mov di, BOARD_POST_RAM_ROW*160+24*2
    call post_ui_post_count
.status:
%endif
    call post_ui_post_ram_status
    call post_ui_post_ui_banks
    pop es
    pop ds
    popad
    ret

; Called only once the visible RAM owner has returned or during its redraw.
post_ui_post_ui_banks:
    ui_text BOARD_POST_RAM_ROW+1, 3, u_summary_banks, 0x0B
    mov di, (BOARD_POST_RAM_ROW+1)*160+24*2
    jmp post_ui_post_memory_banks

post_ui_post_ui_roms:
    pushad
    push ds
    push es
    post_ui_data_segment
    mov ax, 0xB800
    mov es, ax
    ui_text 15, 3, u_post_vga, 0x0B
    mov dx, 0xC000
    mov bx, 0x0800
    call post_ui_post_rom_state
    mov di, 15*160+24*2
    call post_ui_post_rom_state_text
    ui_text 16, 3, u_post_system, 0x0B
    mov dx, 0xF000
    mov bx, 0x1000
    call post_ui_post_rom_state
    mov di, 16*160+24*2
    call post_ui_post_rom_state_text
    ui_text 17, 3, u_post_roms, 0x0B
    ui_text 17, 24, u_absent, 7
    pop es
    pop ds
    popad
    ret

post_ui_post_ram_status:
    mov di, BOARD_POST_RAM_ROW*160+34*2
    call post_ui_post_clear_value
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
    jmp post_ui_setup_text

post_ui_post_clear_value:
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
post_ui_post_count:
    pushad
    push eax
    push di
    mov cx, MEMORY_COUNT_DIGITS
    mov ax, 0x0720
    rep stosw
    pop di
    pop eax
    call post_ui_setup_number
    popad
    ret

post_ui_post_entering_setup:
    pushad
    push ds
    push es
    post_ui_data_segment
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

