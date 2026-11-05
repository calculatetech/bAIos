; Existing POST clock/defaults transaction, behind the qualified PB module.
%define load_bios_state pnp_clock_load_bios_state
%define post_message_cursor pnp_clock_post_message_cursor
%define print_string pnp_clock_print_string
%define post_error_tone pnp_clock_post_error_tone
%define post_notice_wait pnp_clock_post_notice_wait
%define rtc_read pnp_clock_rtc_read
%define setup_defaults pnp_clock_setup_defaults
%define settings_save pnp_clock_settings_save
%define settings_load pnp_clock_settings_load
%define controlled_defaults_restart pnp_clock_restart
pnp_post_clock_alert:
%include "firmware/post-clock-alert.inc"
%undef load_bios_state
%undef post_message_cursor
%undef print_string
%undef post_error_tone
%undef post_notice_wait
%undef rtc_read
%undef setup_defaults
%undef settings_save
%undef settings_load
%undef controlled_defaults_restart
pnp_clock_load_bios_state:
    call CFG_ROM_CODE_SEGMENT:pnp_clock_load_bios_state_callback
    ret
pnp_clock_post_message_cursor:
    call CFG_ROM_CODE_SEGMENT:pnp_clock_post_message_cursor_callback
    ret
pnp_clock_print_string:
    call CFG_ROM_CODE_SEGMENT:pnp_clock_print_string_callback
    ret
pnp_clock_post_error_tone:
    call CFG_ROM_CODE_SEGMENT:pnp_clock_post_error_tone_callback
    ret
pnp_clock_post_notice_wait:
    call CFG_ROM_CODE_SEGMENT:pnp_clock_post_notice_wait_callback
    ret
pnp_clock_rtc_read:
    call CFG_ROM_CODE_SEGMENT:pnp_clock_rtc_read_callback
    ret
pnp_clock_setup_defaults:
    call CFG_ROM_CODE_SEGMENT:pnp_clock_setup_defaults_callback
    ret
pnp_clock_settings_save:
    call CFG_ROM_CODE_SEGMENT:pnp_clock_settings_save_callback
    ret
pnp_clock_settings_load:
    call CFG_ROM_CODE_SEGMENT:pnp_clock_settings_load_callback
    ret
pnp_clock_restart:
    jmp CFG_ROM_CODE_SEGMENT:controlled_defaults_restart
