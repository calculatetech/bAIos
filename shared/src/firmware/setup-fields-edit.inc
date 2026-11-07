; Append the retained VGA font's right arrow after the complete value.
; A single internal space in Type/User labels must not end the scan.
post_ui_setup_submenu_arrow:
    pushad
    mov cx, UI_VALUE_WIDTH - 1
.scan:
    cmp byte [es:di], ' '
    jne .next
    cmp byte [es:di + 2], ' '
    je .arrow
.next:
    add di, 2
    loop .scan
    jmp .done
.arrow:
    mov al, 0x1A
    mov ah, bh
    push di
    add di, 2
    call post_ui_setup_color
    mov [es:di], ax
    pop di
.done:
    popad
    ret

post_ui_setup_field_color:
    mov bh, 7
    call post_ui_setup_field_available
    jnc .enabled
    mov bh, 8
    ret
.enabled:
    cmp byte [fs:U_FOCUS], 1
    jne .done
    cmp [fs:U_FIELD], cl
    jne .done
    mov bh, 0x1F
.done:
    ret

; CL=field. Carry means unavailable. Drawing and input share this rule.
post_ui_setup_field_available:
    pushad
    cmp byte [fs:U_PAGE], 5
    jne .ordinary_available
    call post_ui_chipset_ui_available
    jc .unavailable
    jmp .available
.ordinary_available:
    cmp byte [fs:U_PAGE], 3
    je .ports
    cmp byte [fs:U_PAGE], 1
    jne .available
    cmp byte [fs:U_IDE_DEVICE], BOARD_ATA_DEVICE_COUNT-1
    jbe .device
    cmp cl, 2
    jb .available
    cmp cl, BOARD_ATA_DEVICE_COUNT+1
    ja .available
%if BOARD_ATA_DEVICE_COUNT = 2
    cmp byte [fs:U_IDE], 0
    je .unavailable
%endif
    jmp .available
.device:
    cmp cl, 1                     ; None must still allow a new disk type.
    jbe .available
    call post_ui_ide_ui_enable_pointer
    cmp byte [fs:bx], 0
    je .unavailable
    cmp cl, 2
    jb .available
    cmp cl, 6
    ja .available
    call post_ui_ide_ui_record
    cmp byte [fs:bx + IDE_TYPE], 48
    jne .unavailable
    jmp .available
.ports:
    call post_ui_ports_ui_available
    jc .unavailable
    jmp .available
.available:
    popad
    clc
    ret
.unavailable:
    popad
    stc
    ret

; F1 follows the selected page or clock field, including a pending edit.
post_ui_setup_help:
    pushad
    call post_ui_setup_modal_footer
    cmp byte [fs:U_PAGE], 5
    jne .ordinary_help
    call post_ui_chipset_ui_help
    jmp .wait
.ordinary_help:
%ifdef BOARD_PNP_SUPPORT
    cmp byte [fs:U_PAGE],6
    jne .non_pnp_help
    call post_ui_pnp_ui_help
    jmp .wait
.non_pnp_help:
%endif
    mov di, 17 * 160 + 23 * 2
    mov dx, 6
    mov ax, 0x1E20
.clear:
    mov cx, 55
    push ax
    call post_ui_setup_color
    rep stosw
    pop ax
    add di, (80 - 55) * 2
    dec dx
    jnz .clear
%ifdef BOARD_PORTS_SETUP_HELP
    cmp byte [fs:U_PAGE],3
    jne .ordinary_port_help
    call post_ui_ui_board_ports_setup_help
    jmp .wait
.ordinary_port_help:
%endif
    movzx bx, byte [fs:U_PAGE]
    cmp bx, 3
    jne .old_help
    mov bx, 25
    cmp byte [fs:U_FOCUS], 0
    je .topic
    movzx bx, byte [fs:U_FIELD]
    add bx, 26
    jmp .topic
.old_help:
    cmp bx, 4
    jne .old_help_page
    mov bx, 3
.old_help_page:
    cmp bx, 1
    jne .normal_help
    cmp byte [fs:U_IDE_DEVICE], BOARD_ATA_DEVICE_COUNT-1
    ja .channel_help
%ifdef BOARD_IDE_32BIT_POLICY
    cmp byte [fs:U_FIELD],10
    jne .ordinary_ide_help
    mov bx,IDE_DWORD_HELP_TOPIC
    jmp .topic
.ordinary_ide_help:
%endif
%ifdef BOARD_ATA_PIO_POLICY
    cmp byte [fs:U_FIELD],11
    jne .ordinary_pio_help
    mov bx,IDE_PIO_HELP_TOPIC
    jmp .topic
.ordinary_pio_help:
%endif
    movzx bx, byte [fs:U_FIELD]
    add bx, 14
    jmp .topic
.channel_help:
    cmp byte [fs:U_FIELD], BOARD_ATA_DEVICE_COUNT+4
    jne .channel_existing
    mov bx, 35
    jmp .topic
.channel_existing:
    cmp byte [fs:U_FOCUS], 1
    jne .normal_help
    mov al,[fs:U_FIELD]
    sub al,2
    cmp al,BOARD_ATA_DEVICE_COUNT
    jae .channel_controls
    mov bx,8
    jmp .topic
.channel_controls:
    cmp byte [fs:U_FIELD], BOARD_ATA_DEVICE_COUNT+3
    jne .ide_help
    mov bx, 31             ; Existing Floppy Controller topic.
    jmp .topic
.ide_help:
    cmp byte [fs:U_FIELD], BOARD_ATA_DEVICE_COUNT+2
    jne .normal_help
    mov bx, 24
    jmp .topic
.normal_help:
    cmp byte [fs:U_FOCUS], 0
    je .page
    cmp bx, 1
    je .drive_field
    cmp bx, 2
    je .boot_field
    cmp bx, 3
    je .exit_field
    movzx bx, byte [fs:U_FIELD]
    cmp bx, 2
    jne .clock_time_help
    mov bx, 37
    jmp .topic
.clock_time_help:
    cmp bx, 1
    jne .clock_date_help
    cmp byte [fs:U_CLOCK24], 1
    jne .clock_date_help
    mov bx, 38
    jmp .topic
.clock_date_help:
    inc bx
    jmp .topic
.drive_field:
    mov bx, 6
    cmp byte [fs:U_FIELD], 3
    jne .field
    mov bx, 13
    jmp .topic
    jmp .field
.boot_field:
    cmp byte [fs:U_FIELD],POST_DELAY_FIELD
    jne .video_order_help
    mov bx,POST_DELAY_HELP_TOPIC
    jmp .topic
.video_order_help:
%ifdef BOARD_PCI_VIDEO_ORDER
    cmp byte [fs:U_FIELD],VIDEO_ORDER_FIELD
    jne .old_boot_help
    mov bx,VIDEO_ORDER_HELP_TOPIC
    jmp .topic
.old_boot_help:
%endif
%ifdef BOARD_FAST_BOOT_SETTING
    cmp byte [fs:U_FIELD], 7
    jne .ordinary_boot_help
    mov bx, FAST_BOOT_HELP_TOPIC
    jmp .topic
.ordinary_boot_help:
%endif
    mov bx, 9
    cmp byte [fs:U_FIELD], 4
    jb .topic
    mov bx, 10
    cmp byte [fs:U_FIELD], 4
    je .topic
    mov bx, 34
    cmp byte [fs:U_FIELD], 5
    je .topic
    mov bx, 36
    jmp .topic
.exit_field:
    mov bx, 11
.field:
    movzx ax, byte [fs:U_FIELD]
    add bx, ax
    jmp .topic
.page:
    test bx, bx
    jz .topic
    add bx, 2
.topic:
    imul bx, bx, 6
    mov si, [u_help_topics + bx]
    mov bp, bx
    cmp byte [fs:U_PAGE],1
    jne .boot_title
    cmp byte [fs:U_IDE_DEVICE],BOARD_ATA_DEVICE_COUNT-1
    jbe .help_title
    cmp byte [fs:U_FOCUS],1
    jne .help_title
    movzx ax,byte [fs:U_FIELD]
    sub ax,2
    cmp ax,BOARD_ATA_DEVICE_COUNT
    jae .help_title
    shl ax,1
    push bx
    mov bx,ax
    mov si,[u_ide_policy_labels+bx]
    pop bx
    jmp .help_title
.boot_title:
    cmp byte [fs:U_PAGE], 2
    jne .help_title
    cmp byte [fs:U_FOCUS], 1
    jne .help_title
    movzx ax, byte [fs:U_FIELD]
    cmp ax, 4
    jae .help_title
    shl ax, 1
    push bx
    mov bx, ax
    mov si, [u_boot_labels + bx]
    pop bx
.help_title:
    mov di, 18 * 160 + 25 * 2
    mov bh, 0x1E
    call post_ui_setup_text
    mov si, [ds:u_help_topics + bp + 2]
    mov di, 19 * 160 + 25 * 2
    call post_ui_setup_text
    mov si, [ds:u_help_topics + bp + 4]
    mov di, 20 * 160 + 25 * 2
    call post_ui_setup_text
.wait:
%ifdef EMULATOR_CHIPSET_TEST
    call post_ui_chipset_test_capture_drain
%endif
    call post_ui_setup_clock
    mov ah, 1
    int 0x16
    jnz .key
    sti
    hlt
    jmp .wait
.key:
    xor ah, ah
    int 0x16
    cmp al, 27
    je .done
    cmp ah, 0x3B
    jne .wait
.done:
    popad
    ret

