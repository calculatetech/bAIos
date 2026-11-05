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
