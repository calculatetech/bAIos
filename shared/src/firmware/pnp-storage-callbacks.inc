; Real POST bridges to existing storage owners. Public PM services keep their
; existing selector-safe cores and never call these private real-mode entries.
pnp_nv_read_callback:
    call settings_nv6_read
    retf
pnp_rtc_read_callback:
    call rtc_read
    retf
pnp_nv_index_callback:
    call settings_nv6_index
    retf
pnp_nv_byte_callback:
    push ax
    call rtc_write
    pop ax
    call settings_verify_byte_core
    retf
pnp_nv_checksum_callback:
    call update_cmos_checksum
    retf

; The public decoder's work buffers are caller-stack relative. Keep the live
; EBDA selector intact while using that same decoder from real-mode POST.
pnp_node_callback:
    push fs
    push ss
    pop fs
    call pnp_load_work
    call pnp_build_node
    pop fs
    retf
pnp_ports_apply_callback:
    call ports_apply
    retf
pnp_uart_base_callback:
    call ports_uart_base
    retf
pnp_parallel_base_callback:
    mov ax,[cs:ports_parallel+bx]
    retf
pnp_serial_initialize_callback:
    call serial_initialize
    retf

%ifdef BOARD_PRIVATE_POST_CLOCK
%include "firmware/pnp-post-clock-callbacks.inc"
%endif

%macro pnp_post_callback 2
%1:
    call %2
    retf
%endmacro
pnp_post_callback pnp_post_led_callback,keyboard_led_tick
%ifdef BOARD_PRIVATE_POST_CLOCK
pnp_post_callback pnp_post_cmos_callback,update_cmos_checksum
%endif
pnp_post_callback pnp_post_keyboard_callback,post_keyboard_wait
pnp_post_callback pnp_post_gate_callback,setup_post_gate
pnp_post_callback pnp_post_entering_callback,post_entering_setup
pnp_post_callback pnp_post_setup_callback,setup_main
pnp_post_callback pnp_post_ui_callback,post_ui_begin
%unmacro pnp_post_callback 2

%include "firmware/post-ui-resident.inc"
