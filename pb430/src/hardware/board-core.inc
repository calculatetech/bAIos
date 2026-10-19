%include "pc/cpu.inc"
%include "hardware/io.inc"
%include "hardware/memory.inc"
%include "hardware/shadow.inc"
%include "hardware/cache.inc"
%include "hardware/sio-core.inc"
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
controlled_defaults_restart:
    mov ax,0x008F ; OEM normal restart consumes stale service-resume state.
    call rtc_write
    wbinvd
    mov al,0xFE
    call kbc_command
    jc warm_reset.failed
    jmp hard_halt
board_a20_handoff:
    ; Both AT sources are ORed. Let HIMEM own the8042 gate after sizing.
    ; Keyboard init has enabled its output bit1; leave that gate enabled.
    push ax
    in al,0x92
    and al,0xFC               ; Release fast A20; never pulse the reset bit.
    out 0x92,al
    pop ax
    ret
warm_reset:
    cli
    push ax
    pb430_timing_restore
    pop ax
    call chipset_timing_trial_finish ; A deliberate restart retries the saved choice.
    call cache_reset_marker
    push ax
%ifdef PB430_CACHE_BURST_PROBE
    call chipset_burst_disable
%endif
    post_code 0x90
    mov ax,0x008F
    call rtc_write
    call cache_stock_controller_high ; OEM7EDC/7F0B forces the same C7/20 state.
    post_code 0x91
    ; Retain the stock timer through teardown and the early warm consumer.
    ; Normal startup replaces the vector after the retained-cache interval.
    push ds
    xor ax,ax
    mov ds,ax
    mov word [0x20],cache_stock_timer
    mov [0x22],cs
    pop ds
    call cache_stock_reset
.reset_pulse_prepare:
    ; OEM7EE2..7EF3: hold NMI and release shadows before the same reset pulse.
    cli
    mov al,0x80
    out 0x70,al
    mov al,2
    out CHIPSET_INDEX,al
    out 0xED,al
    in al,CHIPSET_DATA
    and al,0x98
    out CHIPSET_DATA,al
    out 0xED,al
.reset_pulse_ready:
    post_code 0x92
    in al,0x61
    and al,0xFC
    out 0x61,al
    mov al,0xAD
    call kbc_command
    jc .failed
    call kbc_drain
    jc .failed
    mov word [KB_HEAD],KB_BUFFER_START
    mov word [KB_TAIL],KB_BUFFER_START
    mov al,0xAE
    call kbc_command
    jc .failed
    pop ax
    mov [0x72],ax
    post_code 0x93
    mov al,0xFE
    call kbc_command
    jc .failed
    jmp hard_halt
.failed:
    mov al,0xEE
    jmp keyboard_halt

; Changed cache choices need cold tables; teardown still needs the active record.
cache_reset_marker:
    push fs
    push bx
    push cx
    push dx
    push si
    call load_bios_state
    mov dl,[fs:C_VALID]
    xor si,si
    mov cx,CHIP_SIZE/2
.save:
    push word [fs:C_CHIP+si]
    add si,2
    loop .save
    call chipset_settings_load
    mov ax,[fs:C_CHIP+1]
    mov cx,CHIP_SIZE/2
.restore:
    sub si,2
    pop word [fs:C_CHIP+si]
    loop .restore
    mov [fs:C_VALID],dl
    cmp ax,[fs:C_CHIP+1]
    mov ax,0
    jne .done
    mov ax,0x1234
.done:
    pop si
    pop dx
    pop cx
    pop bx
    pop fs
    ret
%ifdef EMULATOR_TEST
report_memory:
    ret
%endif

%ifdef EMULATOR_RAM_SETUP_BOOT
%include "../tests/core-setup-board.inc"
%endif

%ifdef EMULATOR_RAM_SKIP_TEST
%include "../tests/core-ram.inc"
%endif
