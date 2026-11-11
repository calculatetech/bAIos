; Existing resident service bridges for the private POST clock transaction.
pnp_clock_load_bios_state_callback:
    call load_bios_state
    retf
pnp_clock_post_message_cursor_callback:
    call post_message_cursor
    retf
pnp_clock_print_string_callback:
    call print_string
    retf
pnp_clock_post_error_tone_callback:
    call post_error_tone
    retf
pnp_clock_post_notice_wait_callback:
    call post_notice_wait
    retf
pnp_clock_rtc_read_callback:
    call rtc_read
    retf
pnp_clock_setup_defaults_callback:
    call setup_defaults
    retf
pnp_clock_settings_save_callback:
    call settings_save
    retf
pnp_clock_settings_load_callback:
    call settings_load
    retf
