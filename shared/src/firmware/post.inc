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
post_entering_setup:
    post_ui_facade post_entering_setup
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
