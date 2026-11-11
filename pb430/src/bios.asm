bits 16
%include "configuration.inc"
section padding start=0
incbin "../reference/pb430-m27c1001.bin",0,0x8000
section post_payload start=0x8000 vstart=0
%include "hardware/board-definition.inc"
%include "pc/state.inc"
%define PNP_EXTERNAL_JOURNAL
%include "firmware/pnp-module.inc"
%undef PNP_EXTERNAL_JOURNAL
times 0x7FFF-($-$$) db 0xFF
db 0
section core start=0x10000 vstart=0
%define BOARD_DEFINITION "hardware/board-definition.inc"
%include "firmware/bios.asm"
