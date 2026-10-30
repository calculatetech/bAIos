%include "pc/cpu.inc"
%include "hardware/chipset.inc"
%include "hardware/memory.inc"
%include "hardware/cache.inc"
%include "hardware/pci.inc"
%include "hardware/sio-core.inc"
%include "hardware/post-core.inc"
%include "hardware/ata-core.inc"
%ifdef EMULATOR_SETUP_SAVE_FIELDS
%include "../tests/core-setup-board.inc"
%endif

interrupt_ok:
    push bp
    mov bp,sp
    and word [ss:bp+6],0xFFFE
    pop bp
    iret
board_keyboard_handoff:
    ; Late AUX/ROM owners must return the same keyboard policy as startup.
    ; Keep queued keys: dispatch pending bytes instead of kbc_drain.
    pushf
    cli
    pushad
    push ds
    mov cx,32
.pending:
    mov al,0xAD
    call kbc_command
    jc .failed
    call kbc_wait_input_clear
    jc .failed
    in al,KBC_STATUS
    test al,1
    jz .policy
    test al,0x20
    jnz .aux
    int 0x09
    jmp .next
.aux:
    int 0x74
.next:
    loop .pending
    jmp .failed
.policy:
    mov al,0x20
    call kbc_command
    jc .failed
    call kbc_read_data
    jc .failed
    or al,CFG_PLATFORM_KBC_RUNTIME_SET_BITS
    and al,~CFG_PLATFORM_KBC_RUNTIME_CLEAR_BITS
    or al,0x10                ; Hold the keyboard clock through readback.
    mov bl,al                 ; Retain unrelated bits, including AUX IRQ.
    mov al,0x60
    call kbc_command
    jc .failed
    mov al,bl
    call kbc_write_data
    jc .failed
    call kbc_wait_input_clear
    jc .failed
    mov al,0x20
    call kbc_command
    jc .failed
    call kbc_read_data
    jc .failed
    cmp al,bl
    jne .failed
    mov al,0xAE
    call kbc_command
    jc .failed
    call kbc_wait_input_clear
    jc .failed
    in al,0x21
    and al,0xFD               ; Restore IRQ1 without changing other owners.
    out 0x21,al
    pop ds
    popad
    popf
    ret
.failed:
    pop ds
    popad
    popf
    mov al,0xE6               ; Policy handoff or controller readback failed.
    jmp keyboard_halt
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
    board_video_blank 1
    xor ax,ax
    mov ds,ax
    mov word [0x472],0x1234
    in al,0x61
    and al,0xFC
    out 0x61,al
    wbinvd
    ; HIMEM can leave A20 closed; restore reset-vector addressing before RESET.
    in al,0x92
    and al,0xFE
    or al,2
    out 0x92,al
    mov al,0xFE
    call kbc_command
    jc .failed
.wait:
    hlt
    jmp .wait
.failed:
    mov al,0xEE
    jmp keyboard_halt
controlled_defaults_restart:
    cli
    board_video_blank 1
    wbinvd
    mov al,0xFE
    call kbc_command
    jmp hard_halt

core_verify_initialization:
    ; Validate this port's real mapped state, not donor VLSI registers.
    call load_bios_state
    cmp dword [fs:S_EXTENDED_KIB32],1024
    jb .bad
    clc
    ret

.bad:
    mov bl,0x7F
    stc
    ret

%ifdef EMULATOR_RAM_SKIP_TEST
%include "../tests/core-ram.inc"
%endif
%ifdef EMULATOR_CLOCK_NO_ERRORS
%include "../tests/core-clock-watch.inc"
%endif
%ifdef EMULATOR_DOS_WARM_STATE
%include "../tests/core-warm-state.inc"
%endif

%ifdef EMULATOR_TEST
report_memory:
    pushad
    push fs
    call load_bios_state
    mov si,umc_ram_report
    call print_string
    mov al,[fs:HW_HB52]
    call memory_hex_byte
    mov al,'/'
    call memory_character
    mov al,[fs:HW_HB53]
    call memory_hex_byte
    mov si,umc_ram_total
    call print_string
    mov eax,[fs:S_EXTENDED_KIB32]
    add eax,1024
    call memory_decimal32
    mov si,umc_ram_end
    call print_string
    pop fs
    popad
    ret
memory_decimal32:
    xor edx,edx
    mov ebx,10
    div ebx
    test eax,eax
    jz .digit
    push edx
    call memory_decimal32
    pop edx
.digit:
    mov al,dl
    add al,'0'
    jmp memory_character
umc_ram_report db 'UMC HB52/HB53=',0
umc_ram_total db ' RAM=',0
umc_ram_end db ' KiB',13,10,0
%include "../tests/firmware/memory-report.inc"
%endif
