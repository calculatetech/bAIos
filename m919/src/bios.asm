bits 16
%include "configuration.inc"
%include "hardware/board-definition.inc"
section smm_extension start=0 vstart=0
%include "hardware/smm.inc"
%include "pc/state.inc"
%include "firmware/pnp-module.inc"
times 0x10000-($-$$) db 0xFF
section core start=0x10000 vstart=0
%define BOARD_DEFINITION "hardware/board-definition.inc"
%include "firmware/bios.asm"
