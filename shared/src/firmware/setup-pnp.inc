%ifdef BOARD_PNP_NAVIGATION_LATE
pnp_ui_navigation
%endif
pnp_ui_parameters:
    post_ui_facade pnp_ui_parameters
pnp_ui_bit:
    post_ui_facade pnp_ui_bit
pnp_ui_commit:
    post_ui_facade pnp_ui_commit
pnp_ui_change:
    post_ui_facade pnp_ui_change
pnp_ui_draw:
    post_ui_facade pnp_ui_draw
pnp_ui_help:
    post_ui_facade pnp_ui_help
pnp_title:
    ui_string 'bAIos Setup > Plug and Play', pnp_title
pnp_menu:
    ui_string 'Plug and Play', pnp_menu
pnp_open db 'Open',0
pnp_main_labels dw pnp_irqs,pnp_dmas,pnp_windows,pnp_memory,pnp_config,pnp_clear
pnp_irq_numbers db 3,4,5,6,7,9,10,11,12,14,15
pnp_irqs:
    ui_string 'IRQ Reservations', pnp_irqs
pnp_dmas:
    ui_string 'DMA Reservations', pnp_dmas
pnp_windows:
    ui_string 'Reserved I/O Ports', pnp_windows
pnp_memory:
    ui_string 'Upper Memory', pnp_memory
pnp_config:
    ui_string 'Configuration', pnp_config
pnp_clear:
    ui_string 'Clear ESCD', pnp_clear
pnp_io_labels dw pnp_io1,pnp_len1,pnp_io2,pnp_len2
pnp_io1:
    ui_string 'Range 1 Start', pnp_io1
pnp_len1:
    ui_string 'Range 1 Port Count', pnp_len1
pnp_io2:
    ui_string 'Range 2 Start', pnp_io2
pnp_len2:
    ui_string 'Range 2 Port Count', pnp_len2
pnp_policy_values dw pnp_bios,pnp_os
pnp_bios:
    ui_string 'BIOS', pnp_bios
pnp_os:
    ui_string 'Operating System', pnp_os
pnp_clear_values dw pnp_keep,pnp_request
pnp_keep db 'Keep',0
pnp_request db 'Request',0
pnp_reservation_values dw pnp_available,pnp_reserved
pnp_available:
    ui_string 'Available', pnp_available
pnp_reserved db 'Reserved',0
pnp_irq_prefix db 'IRQ ',0
pnp_dma_prefix db 'DMA ',0
pnp_memory_suffix db '000h (16 KiB)',0
pnp_help1:
    ui_string 'Reserve resources for manual cards.', pnp_help1
pnp_help2:
    ui_string 'Example: Start 220h, decimal Count 16.', pnp_help2
pnp_help3:
    ui_string 'Count 0 disables the range.', pnp_help3
%ifdef BOARD_PNP_SETUP_LATE
%include "firmware/setup-post-options.inc"
%endif

%ifdef BOARD_PNP_SETUP_LATE
%include "firmware/pnp-post-display.inc"
%endif
