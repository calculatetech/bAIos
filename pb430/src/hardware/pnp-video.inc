; Retain the exact existing ACC/VGA staging transaction in the POST module.
%define board_video_prepare pnp_board_video_prepare
%define acc_read pnp_module_acc_read
%define acc_write pnp_module_acc_write
%macro pnp_video_post 1
    push ax
    mov al,%1
    out POST_PORT,al
    pop ax
%endmacro
%macro pnp_video_failed 1
    call CFG_ROM_CODE_SEGMENT:pnp_video_failed_callback
%endmacro
%define post_code pnp_video_post
%define pb_stage pnp_video_failed
pnp_board_video_prepare:
%include "hardware/video-prepare.inc"
%define pnp_rom_enter pnp_initialize_image
pnp_initialize_video:
%include "hardware/video-init.inc"
%undef pnp_rom_enter
%undef board_video_prepare
%undef acc_read
%undef acc_write
%undef post_code
%undef pb_stage
%unmacro pnp_video_post 1
%unmacro pnp_video_failed 1
pnp_module_acc_read:
    call CFG_ROM_CODE_SEGMENT:pnp_acc_read_callback
    ret
pnp_module_acc_write:
    call CFG_ROM_CODE_SEGMENT:pnp_acc_write_callback
    ret
