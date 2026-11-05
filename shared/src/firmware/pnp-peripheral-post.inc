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
