
; CMOS10 holds logical drive types; C/U_TYPES retain physical connector order.
; Loading fallback never writes CMOS.
settings_load:
    pushad
    push fs
    call load_bios_state
    mov dword [fs:C_TYPES], (0x01010100 | FLOPPY_DEFAULT_TYPES)
    mov byte [fs:C_SLAVE], 1
    mov dword [fs:C_BASE_VALID], 0x02000100
    mov byte [fs:C_BOOT], DEFAULT_BOOT_FIRST
    mov word [fs:C_BOOT_SECOND], DEFAULT_BOOT_REST
    mov byte [fs:C_BOOT_FOURTH], 0
    mov byte [fs:C_VALID], 0
    mov byte [fs:C_THEME], 0
    mov byte [fs:U_THEME_ACTIVE], 0
    xor bp, bp
    mov byte [fs:C_CLOCK24], 0
    mov byte [fs:C_POST_DELAY],1
%ifdef BOARD_PCI_VIDEO_ORDER
    mov byte [fs:C_VIDEO_ORDER],1
%endif
    mov al, 0x10
    call rtc_read
    mov dl, al
    call settings_types_valid
    jc .record
    test dl, dl
    jz .record
    mov [fs:C_TYPES], dl
.record:
    mov al, 0x38
    call rtc_read
    cmp al, 'B'
    jne .done
    mov bl, al
    mov al, 0x39
    call rtc_read
    cmp al, '8'
    jne .done
    add bl, al
    mov al, 0x3A
    call rtc_read
    cmp al,1
    jb .done
    cmp al,6
    ja .done
.schema:
    mov ch, al
    xor bh, bh              ; Legacy records have no fourth target.
    add bl, al
    mov al, dl
    call settings_types_valid
    jc .done
    add bl, dl
    mov al, 0x3B
    call rtc_read
    mov dh, al
    add bl, al
    mov al, 0x3C
    call rtc_read
    add bl, al              ; Checksum covers the packed byte, before decoding.
    cmp ch, 4
    jb .first_boot
    cmp ch, 5
    jae .schema5_theme
    test al, 0xC0
    jnz .done
    movzx bp, al
    shr bp, 2
    cmp bp, THEME_COUNT
    jae .done
    and al, 3
    jmp .first_boot
.schema5_theme:
    test al, 0x80
    jnz .done
    movzx bp, al
    shr bp, 3
    cmp bp, THEME_COUNT
    jae .done
    and al, 7
.first_boot:
    cmp al, 2
    jbe .boot_valid
    cmp ch, 4
    jb .done
    cmp al, 3
    je .boot_valid
    cmp ch, 5
    jb .done
    cmp al, 4
    ja .done
.boot_valid:
    mov cl, al
    mov al, 0x3D
    call rtc_read
    add bl, al
    cmp ch, 2
    jae .schema2
    test bl, bl
    jnz .done
    cmp dh, 1
    ja .done
    mov [fs:C_HDD], dh
    mov al, 0x3E
    call rtc_read
    cmp al, 0xA5
    jne .legacy_slave
    mov byte [fs:C_SEEK], 0
.legacy_slave:
    mov al, 0x3F
    call rtc_read
    cmp al, 0xA5
    jne .legacy_boot
    mov byte [fs:C_SLAVE], 0
.legacy_boot:
    mov byte [fs:C_BOOT], 1
    mov word [fs:C_BOOT_SECOND], 2
    test cl, cl
    jz .publish
    mov byte [fs:C_BOOT], 2
    mov byte [fs:C_BOOT_SECOND], 1
    cmp cl, 1
    je .publish
    mov byte [fs:C_BOOT_SECOND], 0
    jmp .publish
.schema2:
    cmp ch, 3
    jae .policy_flags
    test dh, 0x80
    jnz .done
.policy_flags:
    mov al, dh
    and al, 0x18
    cmp al, 0x18
    je .done
    mov al, 0x3E
    call rtc_read
    add bl, al
    cmp ch, 5
    jb .second_plain
    test al, 0xC0
    jnz .done
    mov ah, al
    shr ah, 3
    cmp ah, 4
    ja .done
    mov bh, ah
    and al, 7
.second_plain:
    cmp al, 4
    ja .done
    cmp ch, 5
    jae .second_valid
    cmp al, 3
    ja .done
    cmp ch, 4
    je .second_valid
    cmp al, 2
    ja .done
.second_valid:
    movzx si, al
    mov al, 0x3F
    call rtc_read
    add bl,al              ; Include all stored schema6 bits in the checksum.
    cmp ch,6
    jb .third_plain
    movzx di,al
    shr di,3
%ifdef BOARD_PCI_VIDEO_ORDER
    cmp di,6
    ja .done
    mov ah,al
    and ah,0x18
    cmp ah,0x18
    je .done
%else
    cmp di,2
    ja .done
%endif
    shl di,8
    or bp,di               ; Retain new fields until the entire base validates.
    and al,7
.third_plain:
    cmp al, 4
    ja .done
    cmp ch, 5
    jae .third_valid
    cmp al, 3
    ja .done
    cmp ch, 4
    je .third_valid
    cmp al, 2
    ja .done
.third_valid:
    movzx di, al
    test bl, bl
    jnz .done
    test cl, cl
    jz .second_duplicate
    mov ax, si
    cmp al, cl
    je .done
    mov ax, di
    cmp al, cl
    je .done
.second_duplicate:
    test si, si
    jz .fourth_duplicate
    cmp si, di
    je .done
.fourth_duplicate:
    test bh, bh
    jz .flags
    cmp bh, cl
    je .done
    mov ax, si
    cmp bh, al
    je .done
    mov ax, di
    cmp bh, al
    je .done
.flags:
    mov [fs:C_BOOT_FOURTH], bh
    mov al, dh
    shr al, 7
    mov [fs:C_CLOCK24], al
    mov [fs:C_BOOT], cl
    mov ax, si
    mov [fs:C_BOOT_SECOND], al
    mov ax, di
    mov [fs:C_BOOT_THIRD], al
    mov al, dh
    and al, 1
    mov [fs:C_NUMLOCK], al
    mov al, dh
    shr al, 1
    and al, 1
    mov [fs:C_SEEK], al
    mov al, dh
    shr al, 2
    and al, 1
    mov [fs:C_SWAP], al
    mov al, dh
    shr al, 3
    and al, 3
    mov [fs:C_HALT], al
    mov al, dh
    shr al, 5
    not al
    and al, 1
    mov [fs:C_HDD], al
    mov al, dh
    shr al, 6
    not al
    and al, 1
    mov [fs:C_SLAVE], al
.publish:
    mov ax, bp
    mov [fs:C_THEME], al
    cmp ch,6
    jne .old_delay
    mov [fs:C_POST_DELAY],ah
    and byte [fs:C_POST_DELAY],3
%ifdef BOARD_PCI_VIDEO_ORDER
    shr ah,2
    mov [fs:C_VIDEO_ORDER],ah
%endif
.old_delay:
    mov [fs:C_TYPES], dl
    mov byte [fs:C_BASE_VALID], 1
    mov byte [fs:C_VALID], 1
.done:
    cmp byte [fs:C_SWAP], 0
    je .physical_types
    ror byte [fs:C_TYPES], 4
.physical_types:
    call ide_settings_load
    call ports_settings_load
    call chipset_settings_load
%ifdef BOARD_PNP_SUPPORT
    mov di,C_PNP
    call pnp_defaults
    call settings_nv6_present
    jne .pnp_done
    call settings_nv6_pnp_load
    jc .pnp_bad
    mov si,C_PNP
    call pnp_settings_valid
    jnc .pnp_done
.pnp_bad:
    mov di,C_PNP
    call pnp_defaults
    mov byte [fs:C_VALID],0
.pnp_done:
%endif
    pop fs
    popad
    ret

settings_types_valid:
    push ax
    mov ah, al
    and al, 15
    shr ah, 4
    cmp al, 5
    ja .bad
    cmp ah, 5
    ja .bad
    pop ax
    clc
    ret
.bad:
    pop ax
    stc
    ret

settings_save:
    pushf
    cli
    pushad
    push fs
    call load_bios_state
    sub sp,74
    mov di,sp
    call settings_nv6_build_all
    jc .done
    add di,66
    call settings_base_pack
    movzx edi,sp
    mov ebp,1
    call settings_commit32
.done:
    jc .bad
    lea sp,[di]             ; EDI is restored by the commit core.
    add sp,74
    pop fs
    popad
    popf
    clc
    ret
.bad:
    lea sp,[di]
    add sp,74
    pop fs
    popad
    popf
    stc
    ret

; SS:DI=8-byte canonical base (CMOS10,39..3F);38 is the fixed 'B'.
; Both live and draft snapshots use the same encoder and field order.
settings_base_pack:
    pushad
    mov si,settings_base_draft_fields
    jmp settings_base_encode
settings_base_active_pack:
    pushad
    mov si,settings_base_active_fields
settings_base_encode:
    call settings_base_value
    xor al,1
    shl al,1
    mov dl,al
    call settings_base_value
    xor al,1
    or dl,al
    shl dl,2
    call settings_base_value
    or dl,al
    shl dl,1
    call settings_base_value
    or dl,al
    shl dl,1
    call settings_base_value
    or dl,al
    shl dl,1
    call settings_base_value
    or dl,al
    call settings_base_value
    shl al,7
    or dl,al
    mov [ss:di+3],dl
    call settings_base_value
    test dl,4
    jz .types
    ror al,4
.types:
    mov [ss:di],al
    mov word [ss:di+1],0x0638
    call settings_base_value
    shl al,3
    mov dh,al
    call settings_base_value
    or al,dh
    mov [ss:di+4],al
    call settings_base_value
    shl al,3
    mov dh,al
    call settings_base_value
    or al,dh
    mov [ss:di+6],al
    call settings_base_value
    mov dl,al
    call settings_base_value
    shl al,3
    or dl,al
%ifdef BOARD_PCI_VIDEO_ORDER
    call settings_base_value
    shl al,5
    or dl,al
%endif
    mov [ss:di+7],dl
    mov al,'B'
    mov cx,8
.sum:
    cmp cx,3
    je .next
    add al,[ss:di]
.next:
    inc di
    loop .sum
    neg al
    mov [ss:di-3],al
    popad
    ret
settings_base_value:
    mov bx,[cs:si]
    add si,2
    mov al,[fs:bx]
    ret
%ifndef PRESARIO_SHARED_OWNER
%include "firmware/settings-base-fields.inc"
%endif

; ZF reports equality. A persisted byte must not fail on one transient read.
settings_verify_byte:
    mov [fs:U_SAVE_TRACE], al
    mov [fs:U_SAVE_TRACE + 1], ah
    call settings_verify_byte_core
    mov [fs:U_SAVE_TRACE + 2], al
    ret

; EBP selects the existing Setup trace facade or a selector-safe core.
settings_verify_buffer_byte:
    test ebp,ebp
    jnz settings_verify_byte
settings_verify_byte_core:
    push bx
    mov bl,al
    call rtc_read
    cmp al,ah
    je .done
    mov al,bl
    call kbc_delay_2ms
    call rtc_read
    cmp al,ah
.done:
    pop bx
    ret

post_success_tone:
    call load_bios_state
    cmp byte [fs:C_ERROR], 0
    jne .done
    push si
    mov si, post_happy_notes
    call post_tone
    pop si
.done:
    ret

post_error_tone:
    push si
    mov si, post_sad_notes
    call post_tone
    pop si
    ret

; PIT2 only. IRQ0 measures time; IRQ1 remains available during every note.
post_tone:
    pushad
    push ds
    xor ax, ax
    mov ds, ax
.note:
    cs lodsw
    test ax, ax
    jz .off
    push ax
    mov al, 0xB6
    out 0x43, al
    pop ax
    out 0x42, al
    mov al, ah
    out 0x42, al
    cs lodsb
    movzx cx, al
    in al, 0x61
    or al, 3
    out 0x61, al
    mov bp, [0x046C]
.wait:
    sti
    hlt
    mov ax, [0x046C]
    sub ax, bp
    cmp ax, cx
    jb .wait
    jmp .note
.off:
    in al, 0x61
    and al, 0xFC
    out 0x61, al
    pop ds
    popad
    ret

post_happy_notes: dw 2281
    db 2
    dw 1810
    db 2
    dw 1522
    db 2
    dw 0
post_sad_notes: dw 2712
    db 2
    dw 3419
    db 2
    dw 4571
    db 3
    dw 0

; OEM F000:2783: 250 kb/s, seek48 then8, step back to physical TRK0.
; Configured40-track drives stop at39 instead of probing beyond their travel.
post_floppy_seek:
    pushad
    push ds
    push fs
    call load_bios_state
    cmp byte [fs:C_PORTS + P_FLOPPY], 0
    je .done
    cmp byte [fs:C_SEEK], 1
    jne .done
    xor ax, ax
    mov ds, ax
    mov byte [fs:F_BUSY], 1
    mov byte [fs:0x176], 0 ; Per-drive failures; stage/status pairs at178h.
    mov byte [fs:F_CAL], 0
    xor si, si
.drive:
    cmp byte [fs:F_TYPES + si], 0
    je .next
    mov ax, si
    add al, 0x62
    out POST_PORT, al
    mov ax, si
    mov [fs:F_DRIVE], al
    mov byte [fs:F_HEAD], 0
    mov byte [fs:F_CYL], 0
    mov byte [fs:F_FUNC], 0
    mov byte [fs:F_STATUS], 0
    call fdc_prepare
    jc .error
    mov bl, 0x10
    call post_track_zero
    jc .error
    mov byte [fs:F_RATE], 2 ; OEM2825/2786: 250 kb/s gives the POST step rate.
    call fdc_specify
    jc .error
    mov al, 48
    cmp byte [fs:F_TRACKS], 40
    jne .outward
    mov al, 39
.outward:
    mov [fs:F_CYL], al
    call fdc_seek
    jc .error
    xor bl, bl
    call post_track_zero
    jc .error
    mov byte [fs:F_CYL], 8
.inward:
    cmp byte [fs:S_SETUP_REQUEST], 1
    je .finish
    call fdc_seek
    jc .error
    cmp byte [fs:F_CYL], 0
    je .at_zero
    xor bl, bl
    call post_track_zero
    jc .error
    dec byte [fs:F_CYL]
    jmp .inward
.at_zero:
    mov bl, 0x10
    call post_track_zero
    jc .error
    mov ax, si
    add al, 0x64
    out POST_PORT, al
    jmp .next
.error:
    or byte [fs:C_ERROR], 2
    mov cx, si
    mov al, 1
    shl al, cl
    or [fs:0x176], al
    not al
    and [fs:F_CAL], al      ; Failed physical motion is not a calibrated drive.
    cmp byte [fs:P_PHASE], 0
    je .seek_error_text
    pushad
    call post_message_cursor
    popad
.seek_error_text:
    push si
    mov si, u_seek_error_a
    cmp byte [fs:F_DRIVE], 0
    je .print
    mov si, u_seek_error_b
.print:
    call print_string
    pop si
    mov ax, si
    add al, 0xEC
    out POST_PORT, al
.next:
    cmp byte [fs:F_TYPES + si], 0
    je .advance
    mov bx, si
    shl bx, 1
    mov al, [fs:F_STAGE]
    mov ah, [fs:F_STATUS]
    mov [fs:0x178 + bx], ax
.advance:
    cmp byte [fs:S_SETUP_REQUEST], 1
    je .finish
    inc si
    cmp si, 2
    jb .drive
.finish:
    mov dx, FDC_DOR
    mov al, 0x0C
    out dx, al
    mov word [0x043F], 0
    mov byte [fs:F_BUSY], 0
    cmp byte [fs:0x176], 0
    je .done
    call post_error_notice
.done:
    pop fs
    pop ds
    popad
    ret

post_track_zero:
    mov byte [fs:F_STAGE], 4
    mov al, 4
    call fdc_write
    jc .done
    call fdc_unit_head
    call fdc_write
    jc .done
    call fdc_read
    jc .done
    and al, 0x10
    cmp al, bl
    jne .bad
    clc
.done:
    ret
.bad:
    mov byte [fs:F_STATUS], 0x40
    stc
    ret

setup_draft_defaults:
    mov byte [fs:U_THEME], 0
    mov byte [fs:U_CLOCK24], 0
    mov byte [fs:U_POST_DELAY],1
%ifdef BOARD_PCI_VIDEO_ORDER
    mov byte [fs:U_VIDEO_ORDER],1
%endif
    mov dword [fs:U_TYPES], (0x01010100 | FLOPPY_DEFAULT_TYPES)
    mov byte [fs:U_SLAVE], 1
    mov byte [fs:U_NUMLOCK], 1
    mov byte [fs:U_SWAP], 0
    mov byte [fs:U_HALT], 2
    mov byte [fs:U_BOOT], DEFAULT_BOOT_FIRST
    mov word [fs:U_BOOT_SECOND], DEFAULT_BOOT_REST
    mov byte [fs:U_BOOT_FOURTH], 0
    ret

; Confirmed defaults action shared by both Setup entry paths.
setup_defaults:
    call setup_draft_defaults
    mov di, U_IDE
    call ide_defaults
    mov di, U_PORTS
    call ports_defaults
    mov di, U_CHIP
    call chipset_defaults
%ifdef BOARD_PNP_SUPPORT
    mov di,U_PNP
    call pnp_defaults
%endif
    ret

post_numlock_apply:
%ifdef BOARD_PNP_SUPPORT
    push bx
    mov bx,pnp_post_numlock
    call pnp_post_invoke
    pop bx
    ret
%else
%include "firmware/post-numlock.inc"
%endif

post_keyboard_presence:
    pushad
    push ds
    call load_bios_state
    xor ax, ax
    mov ds, ax
    cmp byte [0x0400 + KB_ABSENT], 0
    je .done
    or byte [fs:C_ERROR], 8
    mov si, u_keyboard_absent
    call print_string
    cmp byte [fs:C_HALT], 0
    jne .done
    call post_error_notice
.done:
    pop ds
    popad
    ret


post_error_notice:
    cmp byte [fs:C_HALT], 1
    je .done
    mov ax, [0x041C]
    mov [0x041A], ax
    mov si, u_post_continue
    call print_string
    call post_error_tone
    call post_notice_wait
.done:
    ret

; Called after VGA and keyboard arming. Getters retain RTC validation ownership.
post_clock_alert:
%ifdef BOARD_PRIVATE_POST_CLOCK
    push bx
    mov bx,pnp_post_clock_alert
    call pnp_post_invoke
    pop bx
    ret
%else
%include "firmware/post-clock-alert.inc"
%endif

; Shared fresh-key gate. Caller has resolved FS and supplies DS=0.
post_notice_wait:
.wait_key:
    call post_keyboard_wait
    cmp byte [fs:S_SETUP_REQUEST], 1
    je .done
    mov ah, 1
    int 0x16
    jnz .key
    sti
    hlt
    jmp .wait_key
.key:
    xor ah, ah
    int 0x16                 ; Consume the notice key, not later setup input.
.done:
    ret

; Consume only requests received during hardware detection. Close before tone.
setup_post_gate:
    pushad
    push ds
    call load_bios_state
    xor ax, ax
    mov ds, ax
    call post_keyboard_wait
    cli
    mov byte [0x0400 + KB_POST_STATE], 2
    sti
    cmp byte [fs:S_SETUP_REQUEST], 1
    je .open
    jmp .done
.open:
    call post_entering_setup
    call setup_main
    cmp byte [fs:P_PHASE], 0
    je .restored
    call post_ui_begin
.restored:
    mov byte [0x0400 + KB_POST_STATE], 2
.done:
    pop ds
    popad
    ret

%ifdef BOARD_PNP_SUPPORT
setup_main:
    post_ui_facade setup_main
setup_video_mode:
    post_ui_facade setup_video_mode
%else
%include "firmware/setup-loop.inc"
%endif

post_summary_base_memory:
    pushad
    push ds
    push es
    xor ax,ax
    mov ds,ax
    movzx eax,word [0x0413]
    push word 0xB800
    pop es
    call setup_number
    pop es
    pop ds
    popad
    ret

; Read-only snapshot of active settings. Setup entry is already closed.
%ifdef BOARD_PNP_SUPPORT
post_debug_summary:
    post_ui_facade post_debug_summary
%else
%include "firmware/post-summary.inc"
%endif

%ifdef BOARD_PNP_SUPPORT
post_header:
    post_ui_facade post_header
%else
%include "firmware/post-header.inc"
%endif

post_processor_name:
    call board_cpu_detect_name
    test si,si
    jnz .done
    mov ax, [fs:S_CPU_SIGNATURE]
    mov si, u_summary_unknown
    mov bx, ax
    and bx, 0x0F00
    cmp bx, 0x0500
    je .pentium
    cmp bx, 0x0400
    jne .done
    shr ax, 4
    and ax, 15
    mov bx, ax
    shl bx, 1
    mov si, [cs:u_summary_cpu_models+bx]
.done:
    ret
.pentium:
    mov si, u_summary_pentium
    and ax, 0x3FF0             ; Intel type1/family5/model3, either P24T stepping.
    cmp ax, 0x1530
    jne .done
    mov si, u_summary_p24t
    ret
u_summary_cpu_models dw u_summary_dx,u_summary_dx,u_summary_sx,u_summary_dx2
    dw u_summary_sl,u_summary_sx2,u_summary_486,u_summary_dx2
    dw u_summary_dx4,u_summary_dx4,u_summary_486,u_summary_486
    dw u_summary_486,u_summary_486,u_summary_486,u_summary_486
u_summary_486 db '486',0
u_summary_unknown db 'Unknown',0
u_summary_dx db '486DX',0
u_summary_sx db '486SX',0
u_summary_dx2 db '486DX2',0
u_summary_sx2 db '486SX2',0
u_summary_sl db '486SL',0
u_summary_dx4 db '486DX4',0
u_summary_pentium db 'Pentium',0
u_summary_p24t db 'Pentium P24T',0
u_summary_processor db 'Processor',0
u_summary_fpu db 'FPU',0
u_summary_banks db 'Memory Banks',0
u_summary_interleaved db ', Interleaved',0
u_summary_recovery db 'RAM recovered',0
u_summary_mb db ' MB',0
u_summary_pio db ' PIO',0

setup_hex8:
    push ax
    push bx
    mov bl, al
    shr al, 4
    call .digit
    mov al, bl
    and al, 15
    call .digit
    pop bx
    pop ax
    ret
.digit:
    cmp al, 10
    sbb al, 0x69
    das
    mov ah, 7
    push ax
    call setup_color
    stosw
    pop ax
    ret

; EAX=value, CL=hex digit count1..8, BH=logical color, ES:DI=position.
; Like setup_text, preserve caller registers and destination position.
setup_hex_number:
    pushad
    movzx edx, cl
    mov ebp, eax
    mov cl, 8
    sub cl, dl
    shl cl, 2
    shl ebp, cl
    mov ecx, edx
.digit:
    rol ebp, 4
    mov eax, ebp
    and al, 15
    cmp al, 10
    jb .decimal
    add al, 'A'-10
    jmp .write
.decimal:
    add al, '0'
.write:
    mov ah, bh
    call setup_color
    stosw
    loop .digit
    popad
    ret

%ifdef BOARD_PNP_SUPPORT
setup_restore_text:
    post_ui_facade setup_restore_text
setup_change:
    post_ui_facade setup_change
setup_enum_store:
    post_ui_facade setup_enum_store
setup_boot_parameters:
    post_ui_facade setup_boot_parameters
setup_boot_choice_valid:
    post_ui_facade setup_boot_choice_valid
setup_ide_controller_parameters:
    post_ui_facade setup_ide_controller_parameters
%ifdef BOARD_IDE_SECONDARY_DISABLE_POLICY
setup_ide_controller_store:
    post_ui_facade setup_ide_controller_store
%endif
setup_choices:
    post_ui_facade setup_choices
%else
%include "firmware/setup-actions.inc"
%endif

; AH logical attribute, AL glyph, DI byte offset. Only AH changes; flags retained.
; CS lookup works for shared consumers whose DS points at the BDA.
setup_color:
    pushf
    cmp byte [fs:U_THEME_ACTIVE], 1
    jne .done
    push bx
    push dx
    mov dl, al
    xor bx, bx
    ; Selected field labels discard the highlight background before mapping.
    cmp ah, 0x0F
    jne .find
    cmp byte [fs:U_THEME], 0
    je .restore
    mov ah, 0x07
.find:
    cmp ah, [cs:setup_color_keys + bx]
    je .role
    inc bx
    cmp bl, 10
    jb .find
    jmp .restore
.role:
    cmp di, 24 * 160
    jb .header
    mov bl, 12
    jmp .lookup
.header:
    cmp di, 2 * 160
    jae .border
    cmp ah, 0x1F
    jne .detail
    mov bl, 10
    jmp .lookup
.detail:
    cmp ah, 0x1B
    jne .lookup
    mov bl, 11
    jmp .lookup
.border:
    cmp ah, 0x0B
    jne .lookup
    cmp dl, 0xB3
    jb .lookup
    cmp dl, 0xDA
    ja .lookup
    mov bl, 13
.lookup:
    movzx dx, byte [fs:U_THEME]
    cmp dx, THEME_COUNT
    jb .bounded_theme
    xor dx, dx
.bounded_theme:
    imul dx, 14
    add bx, dx
    mov ah, [cs:setup_colors + bx]
.restore:
    pop dx
    pop bx
.done:
    popf
    ret
setup_color_keys db 0x07,0x08,0x0B,0x0C,0x0E,0x1F,0x17,0x70,0x1B,0x1E
; Body, locked, accent, error, warning, selected, popup, cursor, panel accent,
; panel text, header title, header detail, footer, border.
setup_colors:
    db 0x07,0x08,0x0B,0x0C,0x0E,0x1F,0x17,0x70,0x1B,0x1F,0x1F,0x1B,0x0B,0x0B ; Current
    db 0x1F,0x18,0x1E,0x1C,0x1E,0xE1,0x1F,0xE1,0x1E,0x1F,0x1F,0x1F,0x1F,0x1F ; Award Blue
    db 0x70,0x78,0x71,0x74,0x74,0x1F,0x70,0x1F,0x71,0x70,0x30,0x31,0x30,0x70 ; Award Gray
    db 0x1F,0x18,0x1F,0x1C,0x1E,0x5F,0x1F,0x5F,0x1F,0x1F,0x1F,0x1F,0x1F,0x1D ; AMI Purple
    db 0x1F,0x18,0x1B,0x1C,0x1E,0x30,0x1F,0x30,0x1B,0x1F,0x1B,0x1B,0x1B,0x1B ; AMI Teal
    db 0x57,0x58,0x5F,0x5C,0x5E,0x70,0x67,0x70,0x6F,0x67,0x2F,0x2F,0x20,0x2A ; AMI Classic
    db 0x0E,0x08,0x0E,0x0E,0x0E,0xE0,0x0E,0xE0,0x0E,0x0E,0x0E,0x0E,0x0E,0x0E ; Monochrome Amber
    db 0x0F,0x08,0x0F,0x0F,0x0F,0x70,0x0F,0x70,0x0F,0x0F,0x0F,0x0F,0x0F,0x0F ; Black and White
    db 0x0E,0x08,0x0E,0x0C,0x0F,0x30,0x1E,0x30,0x1E,0x1E,0x1E,0x1E,0x0E,0x0E ; High Contrast
THEME_COUNT equ ($ - setup_colors) / 14

; Hide main-loop function hints while a modal owner consumes the keys.
%ifdef BOARD_PNP_SUPPORT
setup_modal_footer:
    post_ui_facade setup_modal_footer
%else
%include "firmware/setup-modal.inc"
%endif

setup_text:
    push ax
    push si
    push di
    push bx
    push cx
    push dx
    mov ax, ds
    mov dx, cs
    cmp ax, dx
    jne .next
    cmp byte [si], 1
    jne .next
    inc si
    mov dl, bh
    mov cx, 32
.encoded:
    lodsb
    test al, al
    jz .done
    call .token
    jmp .encoded
.next:
    lodsb
    test al, al
    jz .done
    mov ah, bh
    push ax
    call setup_color
    stosw
    pop ax
    jmp .next
.done:
    pop dx
    pop cx
    pop bx
    pop di
    pop si
    pop ax
    ret
.token:
    cmp al, 128
    jb .glyph
    jcxz .return
    dec cx
    xor ah, ah
    sub al, 128
    shl ax, 1
    mov bx, ax
    push bx
    mov al, [cs:ui_text_pairs + bx]
    call .token
    pop bx
    mov al, [cs:ui_text_pairs + bx + 1]
    call .token
    inc cx
.return:
    ret
.glyph:
    mov ah, dl
    call setup_color
    stosw
    ret
ui_text_pairs:
    db UI_TEXT_PAIRS
times -(($-ui_text_pairs)!=256) db 0 ; Assembly-time bound also permits NASM-E.

setup_value:
    push ax
    push si
    push di
.next:
    mov al, [fs:si]
    inc si
    test al, al
    jz .done
    mov ah, bh
    push ax
    call setup_color
    stosw
    pop ax
    jmp .next
.done:
    pop di
    pop si
    pop ax
    ret

setup_number:
    pushad
    xor cx, cx
    mov ebx, 10
.digit:
    xor edx, edx
    div ebx
    push dx
    inc cx
    test eax, eax
    jnz .digit
.write:
    pop ax
    add al, '0'
    mov ah, 7
    push ax
    call setup_color
    stosw
    pop ax
    loop .write
    popad
    ret

%ifdef BOARD_PNP_SUPPORT
setup_draw:
    post_ui_facade setup_draw
%else
%include "firmware/setup-draw.inc"
%endif

%ifdef BOARD_PNP_SUPPORT
setup_selection_bar:
    post_ui_facade setup_selection_bar
setup_choice_highlight:
    post_ui_facade setup_choice_highlight
setup_field_highlight:
    post_ui_facade setup_field_highlight
%else
%include "firmware/setup-fields.inc"
%endif

u_clock_rows db 5,6,7
u_drive_rows db 5,6
%assign ide_row 8
%rep BOARD_ATA_DEVICE_COUNT
    db ide_row
%assign ide_row ide_row+1
%endrep
    db BOARD_ATA_DEVICE_COUNT+9,BOARD_ATA_DEVICE_COUNT+10,BOARD_ATA_DEVICE_COUNT+11
u_boot_rows db 5,6,7,8,9,10,11
%ifdef BOARD_FAST_BOOT_SETTING
    db 12,13
%else
    db 12
%endif
%ifdef BOARD_PCI_VIDEO_ORDER
    db 14
%endif
u_boot_pointers dw U_BOOT,U_BOOT_SECOND,U_BOOT_THIRD,U_BOOT_FOURTH,U_SEEK,U_NUMLOCK,U_HALT
%ifdef BOARD_FAST_BOOT_SETTING
    dw U_CHIP+(BOARD_FAST_BOOT_SETTING-C_CHIP)
%endif
POST_DELAY_FIELD equ ($-u_boot_pointers)/2
    dw U_POST_DELAY
%ifdef BOARD_PCI_VIDEO_ORDER
VIDEO_ORDER_FIELD equ ($-u_boot_pointers)/2
    dw U_VIDEO_ORDER
%endif
BOOT_FIELD_COUNT equ ($-u_boot_pointers)/2
u_boot_labels dw u_boot_order,u_boot_second,u_boot_third,u_boot_fourth,u_seek,u_numlock,u_halt
%ifdef BOARD_FAST_BOOT_SETTING
    dw u_fast_boot
%endif
    dw u_post_delay
%ifdef BOARD_PCI_VIDEO_ORDER
    dw u_video_order
%endif
u_ide_rows db 5,6,7,8,9,10,11,14,15,16
%ifdef BOARD_IDE_32BIT_POLICY
    db 17
%endif
%ifdef BOARD_ATA_PIO_POLICY
    db 18
%endif
u_exit_rows db 5,6

%ifdef BOARD_PNP_SUPPORT
setup_submenu_arrow:
    post_ui_facade setup_submenu_arrow
setup_field_color:
    post_ui_facade setup_field_color
setup_field_available:
    post_ui_facade setup_field_available
setup_help:
    post_ui_facade setup_help
%else
%include "firmware/setup-fields-edit.inc"
%endif

%ifdef BOARD_PNP_SUPPORT
setup_pair:
    post_ui_facade setup_pair
setup_clock:
    post_ui_facade setup_clock
setup_format_time:
    post_ui_facade setup_format_time
setup_edit_begin:
    post_ui_facade setup_edit_begin
setup_parse_pair:
    post_ui_facade setup_parse_pair
setup_edit_apply:
    post_ui_facade setup_edit_apply
setup_confirm:
    post_ui_facade setup_confirm
%else
%include "firmware/setup-clock-edit.inc"
%endif

u_title:
    ui_string 'bAIos Setup', u_title
u_summary db 'bAIos',0
u_cpu_unknown db 'CPU family/model/speed: Unknown',0
u_fpu db 'Numeric processor',0
u_detected db 'Detected',0
u_capacity_unknown db 'Capacity: Unknown',0
u_rom_disks db 'Option ROM disks',0
u_effective db '(effective)',0
u_warnings db 'POST warnings:',0
u_clock_warning db 'Clock',0
u_floppy_warning db 'Floppy',0
u_settings_warning db 'Settings',0
u_keyboard_warning db 'Keyboard',0
u_rom_warning db 'ROM',0
u_active db 'ACTIVE SETTINGS',0
u_saved db 'CMOS settings',0
u_saved_values dw u_fallback,u_valid
u_fallback db 'Defaults',0
u_valid db 'Valid',0
u_l1 db 'CPU L1 cache',0
u_l2 db 'L2 cache',0
u_l2_missing db 'Not detected',0
u_ram_recovered db 'RAM test failed; chipset defaults loaded.',0
u_clock_unset db 'WARNING: CMOS date/time not set.',13,10,0
u_clock_save_error db 'Clock defaults failed. Entering Setup.',13,10,0
u_cmos_invalid db 'WARNING: CMOS settings invalid.',13,10,0
u_cmos_clock_invalid db 'WARNING: CMOS settings invalid; date/time not set.',13,10,0
u_cmos_recover db 'Enter/D: Load defaults and continue.  Delete: Setup.',13,10,0
u_platform db BOARD_DISPLAY_NAME,0
u_build db 'ROM build:',0
u_menu db 'SETUP MENU',0
u_standard:
    ui_string 'Standard Setup', u_standard
u_drives db 'Drives',0
u_boot db 'Boot',0
u_exit:
    ui_string 'Exit Setup', u_exit
u_standard_title:
    ui_string 'bAIos Setup > Standard Setup', u_standard_title
u_drives_title:
    ui_string 'bAIos Setup > Drives', u_drives_title
u_boot_title:
    ui_string 'bAIos Setup > Boot', u_boot_title
u_exit_title:
    ui_string 'bAIos Setup > Exit Setup', u_exit_title
u_footer:
    ui_string 'F1 Help   F4/F5 Theme   F9 Defaults   F10 Save', u_footer
u_edit_footer:
    ui_string 'F1 Help   F4/F5 Theme', u_edit_footer
u_time_footer:
    ui_string 'A/P AM/PM   F1 Help   F4/F5 Theme', u_time_footer
u_version:
    ui_string 'Version:', u_version
u_clock_format:
    ui_string 'Time Format', u_clock_format
u_clock_formats dw u_clock12,u_clock24
u_clock12 db '12 Hour',0
u_clock24 db '24 Hour',0
u_choices db 'SELECT VALUE',0
u_choices_keys:
    ui_string 'Arrows Select   Enter Apply   Esc Cancel', u_choices_keys
u_date:
    ui_string 'System Date', u_date
u_time:
    ui_string 'System Time', u_time
u_total:
    ui_string 'Total Memory', u_total
u_base db 'Base Memory',0
u_extended db 'Extended Memory',0
u_mb db 'MB',0
u_kb db 'KB',0
u_slash db '/',0
u_invalid db 'Invalid date or time.',0
u_drive_a db 'Floppy Drive A',0
u_drive_b db 'Floppy Drive B',0
u_hdd_policy:
    ui_string 'Primary IDE Master', u_hdd_policy
u_slave_policy:
    ui_string 'Primary IDE Slave', u_slave_policy
u_geometry db 'BIOS C / H / S',0
u_absent db 'Not detected',0
u_boot_order:
    ui_string 'First Boot Device', u_boot_order
u_boot_second:
    ui_string 'Second Boot Device', u_boot_second
u_boot_third:
    ui_string 'Third Boot Device', u_boot_third
u_boot_fourth:
    ui_string 'Fourth Boot Device', u_boot_fourth
u_numlock:
    ui_string 'Boot Num Lock', u_numlock
u_swap:
    ui_string 'Swap Floppy Drives', u_swap
u_halt:
    ui_string 'Halt On', u_halt
u_keyboard_absent db 'WARNING: Keyboard not detected.',13,10,0
u_seek:
    ui_string 'Floppy Seek', u_seek
u_save:
    ui_string 'Save and Exit', u_save
u_discard:
    ui_string 'Discard and Exit', u_discard
u_save_error db 'CMOS verification failed. Settings not applied.',0
u_save_trace:
    ui_string 'CMOS reg/expected/read:', u_save_trace
u_save_confirm:
    ui_string 'Save and restart? Enter/Y = Yes   Esc/N = Cancel', u_save_confirm
u_discard_confirm:
    ui_string 'Discard settings? Enter/Y = Yes   Esc/N = Cancel', u_discard_confirm
u_defaults_confirm:
    ui_string 'Load defaults? Enter/Y = Yes   Esc/N = Cancel', u_defaults_confirm
u_seek_error_a db 'Floppy A seek error.',13,10,0
u_seek_error_b db 'Floppy B seek error.',13,10,0
u_post_continue db 'Press any key to continue or Delete for Setup.',13,10,0
u_help_topics:
    dw u_standard,u_help_standard1,u_help_standard2
    dw u_date,u_help_date1,u_help_date2
    dw u_time,u_help_time1,u_help_time2
    dw u_drives,u_help_drives1,u_help_drives2
    dw u_boot,u_help_boot1,u_help_boot2
    dw u_exit,u_help_exit1,u_help_exit2
    dw u_drive_a,u_help_floppy1,u_help_floppy2
    dw u_drive_b,u_help_floppy1,u_help_floppy2
    dw u_hdd_policy,u_help_hdd1,u_help_hdd2
    dw u_boot_order,u_help_boot1,u_help_boot2
    dw u_seek,u_help_seek1,u_help_seek2
    dw u_save,u_help_save1,u_help_save2
    dw u_discard,u_help_discard1,u_help_discard2
    dw u_slave_policy,u_help_hdd1,u_help_hdd2
    dw u_ide_enabled,u_help_ide_enabled1,u_help_ide_enabled2
    dw u_ide_type,u_help_ide_type1,u_help_ide_type2
    dw u_ide_cyl,u_help_ide_cyl1,u_help_ide_cyl2
    dw u_ide_heads,u_help_ide_heads1,u_help_ide_heads2
    dw u_ide_sectors,u_help_ide_sectors1,u_help_ide_sectors2
    dw u_ide_precomp,u_help_ide_precomp1,u_help_ide_precomp2
    dw u_ide_landing,u_help_ide_landing1,u_help_ide_landing2
    dw u_ide_translation,u_help_ide_translation1,u_help_ide_translation2
    dw u_ide_block,u_help_ide_block1,u_help_ide_block2
    dw u_ide_edd,u_help_ide_edd1,u_help_ide_edd2
    dw u_ide_controller,u_help_ide_controller1,u_help_ide_controller2
    dw u_devices,u_help_devices1,u_help_devices2
    dw u_uart_a,u_help_uart1,u_help_uart2
    dw u_uart_b,u_help_uart1,u_help_uart2
    dw u_uart_pair,u_help_pair1,u_help_pair2
    dw u_parallel,u_help_parallel1,u_help_parallel2
    dw u_parallel_mode,u_help_mode1,u_help_mode2
    dw u_fdc,u_help_fdc1,u_help_fdc2
%ifdef BOARD_MOUSE_HELP1
    dw u_mouse,BOARD_MOUSE_HELP1,BOARD_MOUSE_HELP2
%else
    dw u_mouse,u_help_mouse1,u_help_mouse2
%endif
    dw u_isa,u_help_isa1,u_help_isa2
    dw u_numlock,u_help_num1,u_help_num2
    dw u_swap,u_help_swap1,u_help_swap2
    dw u_halt,u_help_halt1,u_help_halt2
    dw u_clock_format,u_help_format1,u_help_format2
    dw u_time,u_help_time24,u_help_time2
%ifdef BOARD_IDE_32BIT_POLICY
IDE_DWORD_HELP_TOPIC equ ($-u_help_topics)/6
    dw u_ide_dword,u_help_ide_dword1,u_help_ide_dword2
%endif
%ifdef BOARD_ATA_PIO_POLICY
IDE_PIO_HELP_TOPIC equ ($-u_help_topics)/6
    dw u_ide_pio,u_help_ide_pio1,u_help_ide_pio2
%endif
POST_DELAY_HELP_TOPIC equ ($-u_help_topics)/6
    dw u_post_delay,u_help_post_delay1,u_help_post_delay2
%ifdef BOARD_PCI_VIDEO_ORDER
VIDEO_ORDER_HELP_TOPIC equ ($-u_help_topics)/6
    dw u_video_order,u_help_video_order1,u_help_video_order2
%endif
%ifdef BOARD_FAST_BOOT_SETTING
FAST_BOOT_HELP_TOPIC equ ($-u_help_topics)/6
    dw u_fast_boot,u_help_fast1,u_help_fast2
u_fast_boot:
    ui_string 'Fast Boot', u_fast_boot
u_help_fast1:
    ui_string 'Skip the startup RAM test above 1 MB.', u_help_fast1
u_help_fast2:
    ui_string 'Off runs the full test and is the default.', u_help_fast2
%endif
%ifdef BOARD_IDE_32BIT_POLICY
u_ide_dword db '32-bit ATA Transfers',0
u_help_ide_dword1:
    ui_string 'Uses 32-bit data transfers on supported IDE.', u_help_ide_dword1
u_help_ide_dword2:
    ui_string 'Disabled uses the compatible 16-bit default.', u_help_ide_dword2
%endif
%ifdef BOARD_ATA_PIO_POLICY
u_ide_pio db 'PIO Mode Limit',0
u_help_ide_pio1:
    ui_string 'Limits IDE speed. Auto selects a supported mode.', u_help_ide_pio1
u_help_ide_pio2:
    ui_string 'Faster modes need the actual 33 MHz timing clock.', u_help_ide_pio2
u_ide_pio_values dw u_auto,u_ide_pio0,u_ide_pio1,u_ide_pio2,u_ide_pio3,u_ide_pio4
u_ide_pio_choices dw u_ide_pio0,u_ide_pio1,u_ide_pio2,u_ide_pio3,u_ide_pio4,u_auto
u_ide_pio0 db '0',0
u_ide_pio1 db '1',0
u_ide_pio2 db '2',0
u_ide_pio3 db '3',0
u_ide_pio4 db '4',0
ide_ui_pio_value:
    mov cl,[fs:U_IDE_DEVICE]
    shl cl,1
    mov al,[fs:U_CHIP+(BOARD_ATA_PIO_POLICY-C_CHIP)]
    shr al,cl
    and al,3
    shr cl,1
    mov ah,[fs:U_CHIP+(BOARD_ATA_PIO_POLICY_HIGH-C_CHIP)]
    shr ah,cl
    and ah,1
    shl ah,2
    or al,ah
    ret
%endif
u_help_standard1:
    ui_string 'System date, time, and detected memory.', u_help_standard1
u_help_standard2:
    ui_string 'Select a clock field to edit it.', u_help_standard2
u_help_date1:
    ui_string 'Calendar date: 1980-2099.', u_help_date1
u_help_date2:
    ui_string 'MM/DD/YYYY. Enter applies the date.', u_help_date2
u_help_time1:
    ui_string '12-hour clock. Press A for AM or P for PM.', u_help_time1
u_help_time2:
    ui_string 'Enter applies the time; Esc cancels the edit.', u_help_time2
u_help_time24:
    ui_string '24-hour clock: 00:00:00 to 23:59:59.', u_help_time24
u_help_format1:
    ui_string 'Choose a 12-hour or 24-hour clock display.', u_help_format1
u_help_format2:
    ui_string 'This changes how the time appears in Setup.', u_help_format2
u_help_drives1:
    ui_string 'Choose the installed drives and their settings.', u_help_drives1
u_help_drives2:
    ui_string 'Enter opens all choices. Arrows change values.', u_help_drives2
u_help_exit1:
    ui_string 'Save settings and restart, or discard edits.', u_help_exit1
u_help_exit2:
    ui_string 'Confirmed clock changes are retained.', u_help_exit2
u_help_floppy1:
    ui_string 'Select the installed drive type, or None.', u_help_floppy1
u_help_floppy2:
    ui_string 'The type sets drive capacity, not disk capacity.', u_help_floppy2
u_help_hdd1:
    ui_string 'Auto detects hard disks and CD drives at startup.', u_help_hdd1
u_help_hdd2:
    ui_string 'Disabled stops the BIOS from using this drive.', u_help_hdd2
u_help_boot1:
    ui_string 'Choose which device to try at each boot step.', u_help_boot1
u_help_boot2:
    ui_string 'Other tries boot support on expansion cards.', u_help_boot2
u_help_seek1:
    ui_string 'Check drives during POST. Default Enabled.', u_help_seek1
u_help_seek2:
    ui_string 'No disk is needed. Halt On sets error behavior.', u_help_seek2
u_help_save1:
    ui_string 'Save your settings and restart the computer.', u_help_save1
u_help_save2:
    ui_string 'The BIOS checks that your settings were saved.', u_help_save2
u_help_discard1:
    ui_string 'Return without saving your setting changes.', u_help_discard1
u_help_discard2:
    ui_string 'Confirmed clock changes are retained.', u_help_discard2
u_hdd_values dw u_disabled,u_auto
%ifndef BOARD_PNP_SETUP_LATE
%include "firmware/setup-post-options.inc"
%endif
%ifdef PB430_PORT
%include "firmware/setup-post-delay-values.inc"
%endif
u_boot_values dw u_disabled,u_boot_floppy,u_boot_hdd,u_boot_cd,u_boot_other
u_boot_other db 'Other',0
u_boot_floppy db 'Floppy',0
u_boot_hdd db 'Hard Disk',0
u_boot_cd db 'CD-ROM',0
u_halt_values dw u_halt_all,u_halt_none,u_halt_keyboard
u_halt_all db 'All Errors',0
u_halt_none db 'No Errors',0
u_halt_keyboard db 'All Except Keyboard',0
u_help_num1:
    ui_string 'Choose whether Num Lock starts enabled.', u_help_num1
u_help_num2:
    ui_string 'The keypad and keyboard lamp use this value.', u_help_num2
u_help_swap1:
    ui_string 'Swap the names of floppy drives A and B.', u_help_swap1
u_help_swap2:
    ui_string 'Set each drive type for its original connector.', u_help_swap2
u_help_halt1:
    ui_string 'Choose which errors pause startup.', u_help_halt1
u_help_halt2:
    ui_string 'Serious hardware faults always stop startup.', u_help_halt2
u_seek_values dw u_off,u_on
u_off:
u_disabled db 'Disabled',0
u_auto db 'Auto',0
u_a_first db 'A, then HDD',0
u_hdd_first db 'HDD, then A',0
u_hdd_only db 'HDD only',0
u_on db 'Enabled',0
u_floppies dw u_none,u_360,u_1200,u_720,u_1440,u_2880
u_none db 'Not installed',0
u_360 db '360 KB, 5.25 in',0
u_1200 db '1.2 MB, 5.25 in',0
u_720 db '720 KB, 3.5 in',0
u_1440 db '1.44 MB, 3.5 in',0
u_2880 db '2.88 MB, 3.5 in',0

; SI/BX resolve the current physical position's draft, never active state.
%ifdef BOARD_PNP_SUPPORT
ide_ui_record:
    post_ui_facade ide_ui_record
ide_ui_enable_pointer:
    post_ui_facade ide_ui_enable_pointer
ide_ui_enable_index:
    post_ui_facade ide_ui_enable_index
ide_ui_type_value:
    post_ui_facade ide_ui_type_value
ide_ui_parameters:
    post_ui_facade ide_ui_parameters
ide_ui_store:
    post_ui_facade ide_ui_store
ide_ui_select:
    post_ui_facade ide_ui_select
ide_ui_change:
    post_ui_facade ide_ui_change
ide_ui_set_type:
    post_ui_facade ide_ui_set_type
ide_ui_draw:
    post_ui_facade ide_ui_draw
setup_colored_number:
    post_ui_facade setup_colored_number
ide_ui_type_text:
    post_ui_facade ide_ui_type_text
ide_ui_types:
    post_ui_facade ide_ui_types
ide_ui_number:
    post_ui_facade ide_ui_number
%ifdef BOARD_PNP_SUPPORT
pnp_ui_number:
    post_ui_facade pnp_ui_number
%endif
setup_number_editor:
    post_ui_facade setup_number_editor
%else
%include "firmware/setup-ide-ui.inc"
%endif

u_ide_labels dw u_ide_enabled,u_ide_type,u_ide_cyl,u_ide_heads,u_ide_sectors
    dw u_ide_precomp,u_ide_landing,u_ide_translation,u_ide_block,u_ide_edd
%ifdef BOARD_IDE_32BIT_POLICY
    dw u_ide_dword
%endif
%ifdef BOARD_ATA_PIO_POLICY
    dw u_ide_pio
%endif
IDE_FIELD_COUNT equ ($-u_ide_labels)/2
u_ide_number_offsets dw IDE_CYLINDERS,IDE_HEADS,IDE_SECTORS,IDE_PRECOMP,IDE_LANDING
u_ide_number_max dw 65535,16,63,65535,65535,65535
%ifdef BOARD_PNP_SUPPORT
    dw 65535
%endif
u_ide_translation_values dw u_auto,u_ide_normal,u_ide_large,u_ide_lba
u_ide_translation_choices dw u_auto,u_ide_large,u_ide_lba,u_ide_normal
ide_translation_to_display db 0,3,1,2
ide_translation_from_display db 0,2,3,1
u_ide_block_values dw u_auto,u_off,u_ide_block2,u_ide_block4,u_ide_block8
    dw u_ide_block16,u_ide_block32,u_ide_block64,u_ide_block128
u_ide_block_choices dw u_ide_block2,u_ide_block4,u_ide_block8,u_ide_block16
    dw u_ide_block32,u_ide_block64,u_ide_block128,u_auto,u_off
u_ide_edd_values dw u_on,u_off
%ifdef BOARD_IDE_SECONDARY_DISABLE_POLICY
u_ide_controller_choices dw u_ide_both_channels,u_off,u_ide_primary_only
u_ide_both_channels db 'Both Channels',0
u_ide_primary_only db 'Primary Only',0
%endif
%if BOARD_ATA_DEVICE_COUNT = 4
u_ide_controller:
    ui_string 'Onboard IDE Controller', u_ide_controller
%else
u_ide_controller:
    ui_string 'Primary IDE Controller', u_ide_controller
%endif
u_ide_disk_group db 'DISK CONFIGURATION',0
u_ide_transfer_group db 'TRANSFER OPTIONS',0
u_ide_enabled:
    ui_string 'Device', u_ide_enabled
u_ide_type:
    ui_string 'Disk Type', u_ide_type
u_ide_none db 'None',0
u_ide_translation:
    ui_string 'Translation', u_ide_translation
u_ide_block:
    ui_string 'Block Mode', u_ide_block
u_ide_cyl:
    ui_string 'Cylinders', u_ide_cyl
u_ide_heads db 'Heads',0
u_ide_sectors:
    ui_string 'Sectors per Track', u_ide_sectors
u_ide_precomp:
    ui_string 'Write Precompensation', u_ide_precomp
u_ide_landing:
    ui_string 'Landing Zone', u_ide_landing
u_ide_edd:
    ui_string 'INT13 Extensions', u_ide_edd
u_ide_user db 'User (48)',0
u_ide_type_prefix db 'Type ',0
u_ide_type_menu db 'PHOENIX DISK TYPE',0
u_ide_type_columns:
    ui_string 'Type            Cyls    Heads   Sectors', u_ide_type_columns
u_ide_reserved db 'Reserved',0
u_ide_page_keys db 'PgUp/PgDn Page',0
u_ide_number_prompt:
    ui_string 'Enter value', u_ide_number_prompt
u_ide_invalid db 'Invalid value.',0
u_ide_normal db 'Normal',0
u_ide_large db 'Large',0
u_ide_lba db 'LBA',0
u_ide_block2 db '2 sectors',0
u_ide_block4 db '4 sectors',0
u_ide_block8 db '8 sectors',0
u_ide_block16 db '16 sectors',0
u_ide_block32 db '32 sectors',0
u_ide_block64 db '64 sectors',0
u_ide_block128 db '128 sectors',0
u_help_ide_enabled1:
    ui_string 'Disabled stops the BIOS from using this drive.', u_help_ide_enabled1
u_help_ide_enabled2:
    ui_string 'Other drives keep their own settings.', u_help_ide_enabled2
u_help_ide_type1:
    ui_string 'Auto detects. None leaves it to an expansion card.', u_help_ide_type1
u_help_ide_type2:
    ui_string 'Choose User to enter the drive details yourself.', u_help_ide_type2
u_help_ide_translation1:
    ui_string 'Choose how the BIOS addresses this hard disk.', u_help_ide_translation1
u_help_ide_translation2:
    ui_string 'Keep the mode used when the disk was formatted.', u_help_ide_translation2
u_help_ide_block1:
    ui_string 'Transfer several disk sectors together.', u_help_ide_block1
u_help_ide_block2:
    ui_string 'Auto selects a size supported by the drive.', u_help_ide_block2
u_help_ide_cyl1:
    ui_string 'For User type, enter the cylinder count: 1-65535.', u_help_ide_cyl1
u_help_ide_cyl2:
    ui_string 'Use the value printed on the drive or its manual.', u_help_ide_cyl2
u_help_ide_heads1:
    ui_string 'For User type, enter the head count: 1-16.', u_help_ide_heads1
u_help_ide_heads2:
    ui_string 'Use the value printed on the drive or its manual.', u_help_ide_heads2
u_help_ide_sectors1:
    ui_string 'For User type, enter sectors per track: 1-63.', u_help_ide_sectors1
u_help_ide_sectors2:
    ui_string 'Use the value printed on the drive or its manual.', u_help_ide_sectors2
u_help_ide_precomp1:
    ui_string 'An older drive setting. 65535 means None.', u_help_ide_precomp1
u_help_ide_precomp2:
    ui_string 'IDE drives manage this themselves.', u_help_ide_precomp2
u_help_ide_landing1:
    ui_string 'An older head parking setting: 0-65535.', u_help_ide_landing1
u_help_ide_landing2:
    ui_string 'IDE drives park their heads themselves.', u_help_ide_landing2
u_help_ide_edd1:
    ui_string 'Enable extended BIOS support for larger disks.', u_help_ide_edd1
u_help_ide_edd2:
    ui_string 'Disable only for software that needs older access.', u_help_ide_edd2
%ifdef BOARD_IDE_SECONDARY_DISABLE_POLICY
u_help_ide_controller1:
    ui_string 'Both Channels enables both motherboard IDE ports.', u_help_ide_controller1
u_help_ide_controller2:
    ui_string 'Primary Only disables the secondary IDE port.', u_help_ide_controller2
%else
u_help_ide_controller1:
    ui_string 'Enable the motherboard hard disk controller.', u_help_ide_controller1
u_help_ide_controller2:
    ui_string 'Disabled turns off its hard disk and CD drives.', u_help_ide_controller2
%endif

%ifdef BOARD_PNP_SUPPORT
ports_ui_parameters:
    post_ui_facade ports_ui_parameters
ports_ui_choice_valid:
    post_ui_facade ports_ui_choice_valid
ports_ui_choices:
    post_ui_facade ports_ui_choices
ports_ui_change:
    post_ui_facade ports_ui_change
ports_ui_draw:
    post_ui_facade ports_ui_draw
%else
%include "firmware/setup-ports-ui.inc"
%endif

u_devices:
    ui_string 'Devices', u_devices
u_devices_title:
    ui_string 'bAIos Setup > Devices', u_devices_title
u_uart_a db 'Serial Port A',0
u_uart_b db 'Serial Port B',0
u_uart_pair db 'COM3 / COM4 Addresses',0
u_parallel db 'Parallel Port',0
u_parallel_mode db 'Parallel Port Mode',0
u_fdc:
    ui_string 'Floppy Controller', u_fdc
u_mouse db 'PS/2 Mouse',0
u_isa db 'ISA Serial Discovery',0
u_ports_rows db BOARD_PORTS_ROWS
%ifdef BOARD_PORTS_SETUP_LABELS
u_ports_labels dw BOARD_PORTS_SETUP_LABELS
%else
u_ports_labels dw u_uart_a,u_uart_b,u_uart_pair,u_parallel,u_parallel_mode,u_fdc,u_mouse,u_isa
%endif
u_ports_values dw BOARD_PORTS_VALUES
u_uart_values dw u_disabled,u_com1,u_com2,u_com3,u_com4
u_pair_values dw u_pair0,u_pair1,u_pair2,u_pair3
u_parallel_values dw u_disabled,u_lpt0,u_lpt1,u_lpt2
u_mode_values dw BOARD_PORTS_MODES
u_com1 db '3F8h / COM1 / IRQ4',0
u_com2 db '2F8h / COM2 / IRQ3',0
u_com3 db '3E8h / COM3 / IRQ4',0
u_com4 db '2E8h / COM4 / IRQ3',0
u_pair0 db '338h COM3 / 238h COM4',0
u_pair1 db '3E8h COM3 / 2E8h COM4',0
u_pair2 db '2E8h COM3 / 2E0h COM4',0
u_pair3 db '220h COM3 / 228h COM4',0
u_lpt0 db '3BCh / LPT3',0
u_lpt1 db '378h / LPT1',0
u_lpt2 db '278h / LPT2',0
u_printer db 'Printer',0
u_bidirectional db 'PS/2 Bidirectional',0
u_help_devices1:
    ui_string 'Configure onboard ports and devices.', u_help_devices1
u_help_devices2:
    ui_string 'Save applies settings after restart.', u_help_devices2
u_help_uart1:
    ui_string 'Choose a COM port number for this serial port.', u_help_uart1
u_help_uart2:
    ui_string 'Disabled turns off the onboard serial port.', u_help_uart2
u_help_pair1:
    ui_string 'Choose the address pair for COM3 and COM4.', u_help_pair1
u_help_pair2:
    ui_string 'Match the addresses required by your software.', u_help_pair2
u_help_parallel1:
    ui_string 'Choose the printer port address or Disabled.', u_help_parallel1
u_help_parallel2:
    ui_string 'Printer ports on expansion cards are also found.', u_help_parallel2
u_help_mode1 db BOARD_PORTS_MODE_HELP,0
u_help_mode2:
    ui_string 'Available when the parallel port is enabled.', u_help_mode2
u_help_fdc1:
    ui_string 'Enable or disable both motherboard floppy drives.', u_help_fdc1
u_help_fdc2:
    ui_string 'Saved drive types remain available when enabled.', u_help_fdc2
u_help_mouse1:
    ui_string 'Enable or disable the PS/2 mouse port.', u_help_mouse1
u_help_mouse2:
    ui_string 'Keyboard operation remains enabled.', u_help_mouse2
u_help_isa1:
    ui_string 'Find serial ports on ISA expansion cards.', u_help_isa1
u_help_isa2:
    ui_string 'Set each card with its jumpers or setup program.', u_help_isa2
ports_summary:
    pushad
    push ds
    ui_text 6, 40, u_summary_com, 0x0B
    mov di, 6*160+(58+BOARD_POST_SUMMARY_SHIFT)*2
    xor ax, ax
    mov ds, ax
    mov si, 0x400
    mov cx, 4
    call .bases
    push cs
    pop ds
    ui_text 7, 40, u_summary_lpt, 0x0B
    mov di, 7*160+(58+BOARD_POST_SUMMARY_SHIFT)*2
    xor ax, ax
    mov ds, ax
    mov si, 0x408
    mov cx, 3
    call .bases
    pop ds
    popad
    ret
.bases:
    lodsw
    test ax, ax
    jz .next
    push ax
    mov al, ah
    call setup_hex8
    pop ax
    call setup_hex8
    mov ax, 0x0720
    push ax
    call setup_color
    stosw
    pop ax
 .next:
    loop .bases
    ret
u_summary_com db 'COM Ports',0
u_summary_lpt db 'LPT Ports',0

%include BOARD_PORTS_SETUP_STRINGS

u_ide_policy_labels:
%if BOARD_ATA_DEVICE_COUNT = 4
    dw u_hdd_policy,u_slave_policy,u_ide_policy3,u_ide_policy4
u_ide_policy3 db 'Secondary IDE Master',0
u_ide_policy4 db 'Secondary IDE Slave',0
%else
    dw u_hdd_policy,u_slave_policy
%endif

%ifdef BOARD_PNP_SUPPORT
%macro pnp_ui_navigation 0
; The shared Setup draft owns every reservation. No probing or allocation here.
pnp_ui_count:
    post_ui_facade pnp_ui_count
pnp_ui_select:
    post_ui_facade pnp_ui_select
pnp_ui_choices:
    post_ui_facade pnp_ui_choices
pnp_counts db 6,11,8,4,12
%endmacro
%ifndef BOARD_PNP_NAVIGATION_LATE
pnp_ui_navigation
%endif
pnp_sidebar_up db 0,0,1,2,6,3,5
pnp_sidebar_down db 1,2,3,5,4,6,4
pnp_sidebar_rows db 5,6,7,8,11,9,10
%ifndef BOARD_PNP_SETUP_LATE
%ifdef PRESARIO_SHARED_OWNER
%strcat PNP_SHARED_SOURCE PRESARIO_SOURCE_DIRECTORY,"../../shared/src/firmware/setup-pnp.inc"
%include PNP_SHARED_SOURCE
%else
%include "firmware/setup-pnp.inc"
%endif
%endif
%endif
%ifndef BOARD_PNP_SUPPORT
setup_sidebar_up db 0,0,1,2,5,3
setup_sidebar_down db 1,2,3,5,4,4
setup_sidebar_rows db 5,6,7,8,10,9
%endif
