%ifdef PB430_VGA60
%include "hardware/vga-compat.inc"
%endif
%include "firmware/setup-pnp.inc"
%include "firmware/pnp-boot-route.inc"
; CPU helpers use late space to preserve the fixed F065 VGA entry.
%ifndef BOARD_LATE_CDBOOT
%include "hardware/cpu.inc"
%endif
%ifdef BOARD_ATA_PIO_LATE
%include "pc/ata-reset.inc"
%include "firmware/ide-pio.inc"
%endif
%include "hardware/cache-test.inc"
pb430_isa_ui
pb430_isa_choices
pb430_rom_extensions_end:
