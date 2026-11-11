; The existing POST initializer/probes share the already owned private lifetime.
; Public INT14/17 services, serial_initialize, selectors and tables stay F000.
%define ports_apply pnp_module_ports_apply
%define load_bios_state pnp_module_state
%define ports_uart_base pnp_module_uart_base
%define serial_initialize pnp_module_serial_initialize
%define PNP_PRIVATE_PERIPHERALS
%macro pnp_set_vector 2
    mov word [es:(%1)*4],%2
    mov word [es:(%1)*4+2],0xF000
%endmacro
%define set_vector pnp_set_vector
pnp_init_peripherals:
%include "firmware/peripheral-post.inc"
%undef ports_apply
%undef load_bios_state
%undef ports_uart_base
%undef serial_initialize
%undef PNP_PRIVATE_PERIPHERALS
%undef set_vector
%unmacro pnp_set_vector 2
pnp_module_ports_apply:
    call CFG_ROM_CODE_SEGMENT:pnp_ports_apply_callback
    ret
pnp_module_uart_base:
    call CFG_ROM_CODE_SEGMENT:pnp_uart_base_callback
    ret
pnp_module_parallel_base:
    call CFG_ROM_CODE_SEGMENT:pnp_parallel_base_callback
    ret
pnp_module_serial_initialize:
    call CFG_ROM_CODE_SEGMENT:pnp_serial_initialize_callback
    ret

%define load_bios_state pnp_module_state
%define keyboard_led_tick pnp_post_led_tick
pnp_post_numlock:
%include "firmware/post-numlock.inc"
%undef keyboard_led_tick
%ifdef BOARD_PRIVATE_POST_CLOCK
%define update_cmos_checksum pnp_post_cmos_checksum
pnp_publish_memory_cmos:
%include "firmware/post-memory-cmos.inc"
%undef update_cmos_checksum
%endif
%define post_keyboard_wait pnp_post_keyboard_wait
%define setup_post_gate pnp_post_setup_gate
%define post_wait_2ms pnp_delay_2ms
pnp_post_summary_pause:
%include "firmware/post-pause.inc"
%define post_entering_setup pnp_post_entering
%define setup_main pnp_post_setup_main
%define post_ui_begin pnp_post_ui_begin
pnp_post_early_setup:
%include "firmware/post-early-setup.inc"
%undef post_entering_setup
%undef setup_main
%undef post_ui_begin
%undef post_keyboard_wait
%undef setup_post_gate
%undef post_wait_2ms
%undef load_bios_state
%macro pnp_post_service 2
%1:
    call CFG_ROM_CODE_SEGMENT:%2
    ret
%endmacro
pnp_post_service pnp_post_led_tick,pnp_post_led_callback
%ifdef BOARD_PRIVATE_POST_CLOCK
pnp_post_service pnp_post_cmos_checksum,pnp_post_cmos_callback
%endif
pnp_post_service pnp_post_keyboard_wait,pnp_post_keyboard_callback
pnp_post_service pnp_post_setup_gate,pnp_post_gate_callback
pnp_post_service pnp_post_entering,pnp_post_entering_callback
pnp_post_service pnp_post_setup_main,pnp_post_setup_callback
pnp_post_service pnp_post_ui_begin,pnp_post_ui_callback
%unmacro pnp_post_service 2
