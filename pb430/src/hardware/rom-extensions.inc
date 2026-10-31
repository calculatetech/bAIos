%ifdef PB430_VGA60
%include "hardware/vga-compat.inc"
%endif
%ifdef BOARD_ATA_PIO_LATE
%include "pc/ata-reset.inc"
%include "firmware/ide-pio.inc"
%endif
%include "hardware/cache-test.inc"
pb430_isa_ui
pb430_isa_choices
pb430_rom_extensions_end:
