%include "pc/cpu.inc"
%include "pc/smm.inc"
board_cpu_detect_name:
    jmp cpu_detect_sl_name

board_cpu_sl_query:
    call cpu_detect_sl
    mov dx,0                 ; No qualified SL support for the 386 board/adapter.
    ret

board_smm_prepare:
    call board_cpu_sl_query
    jmp smm_install

%include "hardware/mitsubishi-init.inc"
%include "hardware/memory-init.inc"
%include "hardware/cache.inc"
%include "hardware/shadow.inc"
%include "pc/linear-ram.inc"
%include "hardware/io.inc"
%include "hardware/video.inc"
%include "hardware/post-core.inc"
%include "hardware/ata-core.inc"

core_verify_initialization:
    call load_bios_state
    cmp word [0x413],632
    jne .bad
    clc
    ret
.bad:
    mov bl,0xE1
    stc
    ret
