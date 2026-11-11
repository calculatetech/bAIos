; Live 80x25 POST presentation. State is transient and follows the EBDA.
%ifdef BOARD_PNP_SUPPORT
post_ui_begin:
    post_ui_facade post_ui_begin
post_ui_floppy:
    post_ui_facade post_ui_floppy
post_ui_disks:
    post_ui_facade post_ui_disks
post_ui_disk:
    post_ui_facade post_ui_disk
post_ram_start:
    post_ui_facade post_ram_start
post_ram_finish:
    post_ui_facade post_ram_finish
post_ui_banks:
    post_ui_facade post_ui_banks
post_ui_roms:
    post_ui_facade post_ui_roms
post_ram_status:
    post_ui_facade post_ram_status
post_clear_value:
    post_ui_facade post_clear_value
post_count:
    post_ui_facade post_count
%else
%include "firmware/post-screen.inc"
%endif

post_early_setup:
%ifdef BOARD_PNP_SUPPORT
    push bx
    mov bx,pnp_post_early_setup
    call pnp_post_invoke
    pop bx
    ret
%else
%include "firmware/post-early-setup.inc"
%endif


%ifdef BOARD_PNP_SUPPORT
post_message_cursor:
    post_ui_facade post_message_cursor
post_ui_rom:
    post_ui_facade post_ui_rom
post_rom_state_text:
    post_ui_facade post_rom_state_text
%ifdef EMULATOR_CHIPSET_POST_UI
post_ui_capture:
    post_ui_facade post_ui_capture
%endif
%else
%include "firmware/post-screen-detail.inc"
%endif

; Keep the current operation visible while its existing owner waits.
; IRQ1 can call this without reentering BIOS video or the private UI module.
post_entering_setup:
    pushf
    pushad
    push ds
    push es
    push cs
    pop ds
    mov ax,0xB800
    mov es,ax
    mov di,24*160
    mov ax,0x0F20
    mov cx,40                 ; Keep the feature indicators on the right.
    cld
    rep stosw
    mov di,24*160+3*2
    mov si,u_post_entering
.character:
    lodsb
    test al,al
    jz .done
    mov ah,0x0F
    stosw
    jmp .character
.done:
    pop es
    pop ds
    popad
    popf
    ret

post_features:
    pushf
    pushad
    push ds
    push es
    push cs
    pop ds
    mov ax,0xB800
    mov es,ax
    mov di,24*160+(79-(u_post_features_end-u_post_features-1))*2
    mov si,u_post_features
    mov bh,8
    cld
    call setup_text
    pop es
    pop ds
    popad
    popf
    ret

post_status:
    pushf
    pushad
    push ds
    push es
    push fs
    push gs
    cmp al,13
    ja .done
    movzx bx,al
    shl bx,1
    mov si,[cs:post_status_labels+bx]
    push cs
    pop ds
    ; Publication can release the private UI; notices must remain resident.
    mov ax,0xB800
    mov es,ax
    mov di,22*160
    mov ax,0x0720
    mov cx,160
    cld
    rep stosw
    mov di,22*160+3*2
    mov bh,7
    call setup_text
.done:
    pop gs
    pop fs
    pop es
    pop ds
    popad
    popf
    ret
post_status_labels:
    dw u_post_blank,u_post_keyboard,u_post_memory_check,u_post_cache_check
    dw u_post_ports,u_post_pnp,u_post_floppy_check,u_post_ide_check,u_post_rom_check
    dw u_post_summary_wait
    dw u_post_escd_rebuild,u_post_escd_update,u_post_escd_done,u_post_escd_retry
u_post_keyboard db 'Checking keyboard...',0
u_post_memory_check db 'Checking memory...',0
u_post_cache_check db 'Checking cache...',0
u_post_ports db 'Detecting ports...',0
u_post_pnp db 'Configuring Plug and Play devices...',0
u_post_floppy_check db 'Detecting floppy drives...',0
u_post_ide_check db 'Detecting IDE drives...',0
u_post_rom_check db 'Initializing option ROMs...',0
u_post_summary_wait db 'POST complete. Waiting before summary...',0
u_post_escd_rebuild db 'Rebuilding ESCD...',0
u_post_escd_update db 'Updating ESCD...',0
u_post_escd_done db 'ESCD rebuilt.',0
u_post_escd_retry db 'ESCD update failed; will retry.',0
u_post_features:
%ifdef BOARD_PNP_SUPPORT
    db 'PnP ', '0'+(BIOS_PNP_SPEC_VERSION >> 4),'.','0'+(BIOS_PNP_SPEC_VERSION & 15)
    db '  '
%endif
    db 'APM ', '0'+(BIOS_APM_SPEC_VERSION >> 8),'.','0'+(BIOS_APM_SPEC_VERSION & 255),0
u_post_features_end:
    ; A future ACPI indicator can join the same right-aligned list.
u_post_memory db 'Memory',0
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

post_summary_pause:
    push ax
    mov al,9
    call post_status
    pop ax
%ifdef BOARD_PNP_SUPPORT
    push bx
    mov bx,pnp_post_summary_pause
    call pnp_post_invoke
    pop bx
    ret
%else
%include "firmware/post-pause.inc"
%endif
%ifndef BOARD_PNP_SUPPORT
post_wait_2ms:
    push ax
    push bx
    push cx
    push dx
    mov dx,4773                ; Mode3 falls twice per1.193182MHz input clock.
    jmp kbc_delay_count         ; Reuse the exact established PIT wait loop.
%endif
