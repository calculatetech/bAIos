; Private real-mode POST composition. It is never a public PM entry point.
align 16,db 0xFF
pnp_module_start:
    db 'BAIPNP2',0
    dw pnp_module_end-pnp_module_start
    dw pnp_module_entry-pnp_module_start
pnp_module_entry:
    call bx
    retf

%ifdef PNP_EXTERNAL_JOURNAL
%define PNP_ALLOCATE pnp_module_allocate
%endif
%define PNP_STATE_LOAD pnp_module_state
%include "firmware/pnp-isa.inc"
%include "firmware/pnp-resources.inc"
%include "pc/pnp-post-state.inc"
%ifndef PNP_EXTERNAL_JOURNAL
%include "firmware/pnp-post.inc"
%endif
%include "firmware/pnp-ledger.inc"
%include "firmware/pnp-census.inc"
%include "firmware/pnp-select.inc"
%include "firmware/pnp-program.inc"
%define PNP_NODE_LOAD pnp_module_node
%include "firmware/pnp-map.inc"
pnp_module_node:
    call CFG_ROM_CODE_SEGMENT:pnp_node_callback
    ret
%undef PNP_NODE_LOAD
%include "firmware/pnp-allocation.inc"
%include "firmware/pnp-rom-resources.inc"
%include "firmware/pnp-rom.inc"
%include "firmware/pnp-pack.inc"
%include "firmware/pnp-peripheral-post.inc"
%ifdef PB430_PORT
%include "hardware/pnp-video.inc"
%include "firmware/pnp-post-clock.inc"
%endif
%ifdef M919_BOARD_DEFINITION
%include "firmware/pnp-pci-rom.inc"
%endif
%ifdef PNP_EXTERNAL_JOURNAL
pnp_module_allocate:
    call CFG_ROM_CODE_SEGMENT:pnp_allocate_callback
    ret
%endif
pnp_module_state:
    call CFG_ROM_CODE_SEGMENT:pnp_state_callback
    ret
    align 2,db 0x90
pnp_module_end:
%undef PNP_STATE_LOAD
%undef PNP_ALLOCATE
