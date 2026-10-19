bits 16
%include "configuration.inc"
section padding start=0
times 0x10000 db 0xFF
section core start=0x10000 vstart=0
%define BOARD_DEFINITION "hardware/board-definition.inc"
%include "firmware/bios.asm"
