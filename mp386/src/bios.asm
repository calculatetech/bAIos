bits 16
%include "configuration.inc"
section core start=0 vstart=0
%define BOARD_DEFINITION "hardware/board-definition.inc"
%include "firmware/bios.asm"
