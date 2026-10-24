%include "pc/cpu.inc"
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
