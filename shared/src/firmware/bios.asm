bits 16

%define BIOS_VERSION CFG_IDENTITY_VERSION
%define BIOS_RELEASE_DATE CFG_IDENTITY_RELEASE_DATE
%substr BIOS_DATE_PREFIX BIOS_RELEASE_DATE 1,6
%substr BIOS_DATE_YEAR BIOS_RELEASE_DATE 9,2

%ifndef BOARD_DEFINITION
%error "Select a board definition before composing the firmware core"
%endif
%include BOARD_DEFINITION
%include "pc/firmware-versions.inc"
%include "setup/ui-text.inc"
%include "firmware/cache-lifecycle.inc"
%include "pc/processor.inc"
%ifdef EMULATOR_WARM_RESET_TEST
%define EMULATOR_PAUSE_ONLY
%endif

%ifdef EMULATOR_SETUP_INVALID_DATE
%define EMULATOR_SETUP_INVALID_NOTICE
%endif
%ifdef EMULATOR_SETUP_BAD_CMOS
%define EMULATOR_SETUP_INVALID_NOTICE
%endif
%ifdef EMULATOR_SETUP_POWERLOSS
%define EMULATOR_SETUP_INVALID_NOTICE
%endif

%include "pc/state.inc"
%include "pc/ram-test-state.inc"

%macro set_vector 2
    mov word [es:(%1) * 4], %2
    mov word [es:(%1) * 4 + 2], 0xF000
%endmacro

%macro post_code_early 1
    mov al, %1
    out POST_PORT, al
%endmacro

%macro post_code 1
    push ax
    post_code_early %1
    pop ax
%endmacro

%include "hardware/startup-core.inc"
.post_settings:
    call settings_load
%ifdef BOARD_LATE_POST_TRACE
    post_code 0xD0
%endif
    call post_numlock_apply
%ifdef BOARD_LATE_POST_TRACE
    post_code 0xD1
%endif
    call post_keyboard_presence
%ifdef BOARD_LATE_POST_TRACE
    post_code 0xD2
%endif
%ifdef EMULATOR_BOOT_SETTINGS_RECOVERY
    call boot_settings_alert_begin
%endif
    call chipset_apply
    call publish_memory_cmos
    call chipset_post_recovery_notice
    mov byte [fs:P_PHASE], 1
    call post_ui_cache
    call post_early_setup
%ifdef BOARD_RAM_POLICY_BEFORE_TEST
    call BOARD_RAM_TRIAL_BEGIN
    call BOARD_LATE_MEMORY_POLICY
    post_code 0x7B
%endif
%ifdef EMULATOR_RAM_SKIP_TEST
    call core_ram_test_begin
%endif
    mov al,2
    call post_status
    call chipset_visible_ram_test
%ifdef BOARD_RAM_POLICY_BEFORE_TEST
    post_code 0x7C
%endif
    mov byte [fs:P_PHASE], 2
    call post_early_setup
    call post_clock_alert
%ifdef EMULATOR_SETUP_POWERLOSS
    call load_bios_state
    call setup_test_begin     ; Notice Delete enters Setup at the next early gate.
%endif
    call post_early_setup
    mov al,3
    call post_status
    cache_phase after_ram
    call load_bios_state
    call post_ui_cache
    mov al,4
    call post_status
    call init_peripherals
%ifdef BOARD_PNP_SUPPORT
    mov al,5
    call post_status
%ifdef M919_BOARD_DEFINITION
    post_code 0x55
%endif
    call pnp_configure_isa
%ifdef M919_BOARD_DEFINITION
    post_code 0x56
%endif
%endif
%ifdef EMULATOR_SETUP_TEST
%ifndef EMULATOR_SETUP_POWERLOSS
    call setup_test_begin
%endif
%endif
%ifdef EMULATOR_PORTS_TEST
    call ports_test_begin
%endif
%ifdef EMULATOR_CHIPSET_TEST
%ifndef EMULATOR_CHIPSET_POST_RAM
    call chipset_test_begin
%endif
%endif
%ifdef EMULATOR_BOOT_POLICY_TEST
    call boot_policy_begin
%endif
%ifdef EMULATOR_TEST
%ifndef EMULATOR_CHIPSET_POST_UI
    call report_memory         ; Raw bank/interleave output belongs to diagnostics.
%endif
%endif
%ifdef KEYBOARD_DIAGNOSTIC
    call post_keyboard_diagnostic
%endif

%ifdef EMULATOR_TEST
%ifndef EMULATOR_CHIPSET_PREVIEW
    call verify_initialization
%ifdef EMULATOR_BOOT_STALE
    ; A failed read must not transfer to a previously signed buffer.
    mov word [0x7C00], 0x7AB0 ; mov al,7Ah
    mov byte [0x7C02], 0xEA
    mov word [0x7C03], emulator_exit
    mov word [0x7C05], 0xF000
    mov word [0x7DFE], 0xAA55
%endif
    jnc .initialization_verified
    mov al, bl
    call emulator_exit
.initialization_verified:
%endif
%endif

    mov al,6
    call post_status
    call init_floppy
    mov byte [fs:P_PHASE], 3
    call post_ui_floppy
    call post_early_setup
    call post_floppy_seek
    call post_early_setup
%ifdef FLOPPY_DIAGNOSTIC
    call floppy_diagnostics
%endif
%ifdef EMULATOR_PAUSE_ONLY
    call post_pause_test_begin
%endif
    call post_keyboard_wait
%ifdef EMULATOR_PAUSE_ONLY
    call post_pause_test_end
%endif
    post_code 0x70
    mov al,7
    call post_status
    call ata_detect_primary
    call post_keyboard_wait
    mov byte [fs:P_PHASE], 4
    call post_ui_disks
    call post_early_setup
    cmp byte [0x0475], 0
    je .common_post
    post_code 0x80
%ifdef EMULATOR_BOOT_POST_STATUS
    mov byte [fs:S_TEST_AFTER_STATUS], EMULATOR_BOOT_POST_STATUS
    mov byte [fs:S_TEST_AFTER_COUNT], 1
%endif
.common_post:
%ifdef EMULATOR_CHIPSET_POST_RAM
    call setup_test_dump
    mov al, 0x67
    call emulator_exit
    jmp hard_halt
%endif
    ; Keyboard service is already armed. Do not discard current POST input.
%ifdef BOARD_MOUSE_INIT
    call BOARD_MOUSE_INIT
%else
    call init_mouse
%endif
%ifdef BOARD_MOUSE_HANDOFF
    call BOARD_MOUSE_HANDOFF
%endif
%ifdef EMULATOR_PORTS_TEST
    call ports_test_observe
%endif
    in al, 0x21
    and al, 0xF9
    out 0x21, al
    cli
    call init_fpu
    ; L2 remains off through the final Setup entry gate.
    post_code 0xCA
%ifdef EMULATOR_WARM_RESET_TEST
    call post_pause_test_begin
%endif
    call post_keyboard_wait
%ifdef EMULATOR_WARM_RESET_TEST
    call post_pause_test_end
    cli
%endif
    ; Recheck after detection: a clock read can fail after the initial notice.
    call load_bios_state
    test byte [fs:C_ERROR], 5
    jnz .clock_checked
    call post_clock_alert
.clock_checked:
    call setup_post_gate
    cache_phase finish
%ifdef BOARD_LATE_POST_TRACE
    post_code 0x56
%endif
    call post_success_tone
%ifdef BOARD_LATE_POST_TRACE
    post_code 0x57
%endif
    mov byte [fs:P_PHASE], 5
    call post_ui_cache
%ifdef BOARD_LATE_POST_TRACE
    post_code 0x58
%endif
    call post_ui_roms
%ifdef BOARD_LATE_POST_TRACE
    post_code 0x59
%endif
    mov al,8
    call post_status
    call option_rom_discovery
%ifdef BOARD_LATE_POST_TRACE
    post_code 0x5A
%endif
%ifdef EMULATOR_CHIPSET_POST_UI
    call post_ui_capture
%endif
%ifdef BOARD_LATE_POST_TRACE
    post_code 0x5B
%endif
%ifdef BOARD_PNP_SUPPORT
    call pnp_publish_finish
%else
    call post_debug_summary
%endif
%ifdef BOARD_LATE_POST_TRACE
    post_code 0x5C
%endif
    post_code 0xFF
%ifdef EMULATOR_DOS_WARM_STATE
    call core_warm_post_state
%endif
    call rtc_sync_ticks
%ifdef BOARD_RAM_TRIAL_FINISH
    call BOARD_RAM_TRIAL_FINISH
%endif
%ifdef BOARD_LATE_POST_TRACE
    post_code 0x5D
%endif
%ifdef EMULATOR_SETUP_TEST
    call setup_test_end
%endif
%ifdef EMULATOR_BOOT_POLICY_TEST
    call boot_policy_ready
%endif
    mov byte [0x0400 + KB_POST_STATE], 0
    sti
%ifdef BOARD_LATE_POST_TRACE
    post_code 0x5E
%endif
    int 0x19

%include "hardware/board-core.inc"
init_fpu:
    push eax
    push bp
    push ds
    xor ax, ax
    mov ds, ax
    and word [0x0410], 0xFFFD
    in al, 0xA1
    or al, 0x20
    out 0xA1, al
    mov eax, cr0
    and eax, 0xFFFFFFD1         ; MP/EM/TS/NE clear; OEM cold MP/EM/TS baseline.
    mov cr0, eax
    xor al, al
    out 0xF0, al               ; Clear the board's stale numeric-error latch.
    sub sp, 4
    mov bp, sp
    mov word [ss:bp], 0xFFFF
    mov word [ss:bp + 2], 0xFFFF
%ifdef BOARD_FPU_PROBE_ALLOWED
    call BOARD_FPU_PROBE_ALLOWED
    jc .done
%endif
    fninit
    fnstsw [ss:bp]
    fnstcw [ss:bp + 2]
    cmp word [ss:bp], 0
    jne .done
    mov ax, [ss:bp + 2]
    and ax, 0x103F
    cmp ax, 0x003F
    jne .done
    or word [0x0410], 2
    in al, 0xA1
    and al, 0xDF
    out 0xA1, al
    in al, 0x21
    and al, 0xFB
    out 0x21, al
.done:
%ifdef BOARD_FPU_CONFIGURE
    call BOARD_FPU_CONFIGURE
%endif
    add sp, 4
    pop ds
    pop bp
    pop eax
    ret

video_failed:
    post_code 0xE5
    jmp hard_halt
no_disk:
%ifdef EMULATOR_IDENTIFY_POST_STATUS
    cmp byte [fs:S_TEST_PHASE], 0xA5
    je .identify_post_seen
    mov al, 0x79
    call emulator_exit
.identify_post_seen:
%endif
    mov si, msg_no_disk
    call print_string
    mov dx, POST_PORT
    mov al, 0xE3
    out dx, al
    mov al, 0x63
    jmp halt_forever

keyboard_runtime_failed:
    mov al, 0xEF
    jmp keyboard_halt

%include "pc/pic-pit.inc"

%include "pc/keyboard-controller.inc"

%include "pc/text.inc"

default_iret:
    iret

%include "pc/ata-irq.inc"

; Standard AT numeric-error acknowledgment and application INT02 chain.
; The AT F0 latch clears external IRQ13/FERR state.
; Unlike OEM 9C59, this does not rewrite the saved x87 instruction opcode.
int75:
    push ax
    xor al, al
    out 0xF0, al
    mov al, 0x65               ; Specific slave IRQ5 (system IRQ13) EOI.
    out 0xA0, al
    mov al, 0x62               ; Specific master cascade EOI.
    out 0x20, al
    pop ax
    int 0x02
    iret

%include "pc/timer.inc"

%include "pc/keyboard-irq.inc"

%include "pc/keyboard-bios.inc"

%ifdef KEYBOARD_DIAGNOSTIC
%include "keyboard-diagnostic.inc"
%endif

%ifdef EMULATOR_PAUSE_ONLY
%include "../tests/firmware/post-pause-test.inc"
%endif

%include "pc/keyboard-tables.inc"

%include "firmware/system-services.inc"

%include "firmware/extended-memory.inc"

%include "firmware/rtc.inc"

int13:
    test dl, 0x80
    jz floppy_int13
    ; OEM F000:AE4F enables IRQs before HDD dispatch. INT entry cleared IF;
    ; polling with it clear starves timer, keyboard and sound for the request.
    ; The short PIO data blocks below retain their own interrupt exclusion.
    sti
    push bp
    mov bp, sp
    ; Preserve full caller registers across the 32-bit LBA helpers. Only
    ; publish documented outputs into this PUSHAD frame (AX by default).
    ; Speedsys keeps live loop counters in ECX across disk services.
    pushad
    push fs
    call load_bios_state
    mov word [fs:S_BLOCK_SIZE], 512
    call ata_select_bios_disk
    jnc .selected_drive
    cmp dl,0x80
    jne .invalid_drive
    ; Retain the established absent80h status/capability behavior.
.selected_drive:
    mov word [fs:S_BLOCK_SIZE],512
    jmp .drive_ok
%include "firmware/disk-dispatch.inc"

%include "firmware/disk-request.inc"

load_bios_state:
    push ax
    xor ax, ax
    mov fs, ax
    mov fs, [fs:0x040E]
    pop ax
    ret

; EAX=start, EDX=exclusive end. Protect only our current EBDA here.
; The caller owns the buffer mapping and A20: EMM386 can map UMB RAM into
; C8000-EFFFF, and HIMEM permits HMA buffers. OEM F000:A2FE/A343 likewise
; accepts the caller's segment:offset without a physical-memory-hole test.
; Both callers have already checked that the buffer does not wrap at 64 KiB.
check_disk_buffer:
    push ebx
%ifdef BOARD_PNP_SUPPORT
    push ecx
%endif
    push fs
    call load_bios_state     ; FS may select the secondary disk record.
%ifdef BOARD_PNP_SUPPORT
    movzx ecx,byte [fs:0]
    shl ecx,10
%endif
    xor ebx, ebx
    mov bx, fs
    pop fs
    shl ebx, 4
    cmp edx, ebx
    jbe .good
%ifdef BOARD_PNP_SUPPORT
    add ebx,ecx
%else
    add ebx, CFG_PLATFORM_STATE_KIB*1024
%endif
    cmp eax, ebx
    jb .bad
.good:
%ifdef BOARD_PNP_SUPPORT
    pop ecx
%endif
    pop ebx
    clc
    ret
.bad:
%ifdef BOARD_PNP_SUPPORT
    pop ecx
%endif
    pop ebx
    stc
    ret

validate_request:
    push edx
    cmp byte [fs:S_COMMAND], CMD_VERIFY
    je .state_safe
    cmp byte [fs:S_COMMAND], 0
    je .state_safe
    movzx eax, word [fs:S_BUFFER_OFF]
    movzx ecx, byte [fs:S_COUNT]
    movzx edx, word [fs:S_BLOCK_SIZE]
    imul ecx, edx
    add eax, ecx
    cmp eax, 0x10000
    ja .bad
    movzx eax, word [fs:S_BUFFER_SEG]
    shl eax, 4
    movzx edx, word [fs:S_BUFFER_OFF]
    add eax, edx
    mov edx, eax
    add edx, ecx
    call check_disk_buffer
    jc .bad
.state_safe:
    mov eax, [fs:S_LBA]
    movzx ecx, byte [fs:S_COUNT]
    add ecx, eax
    jc .bad
    cmp ecx, [fs:S_CAPACITY]
    ja .bad
    cmp eax, 0x10000000
    jae .bad
    pop edx
    clc
    ret
.bad:
    mov byte [fs:S_STATUS], ERR_BAD_ADDRESS
    pop edx
    stc
    ret

%include "firmware/edd-parameters.inc"

ata_report_device:
    post_code 0x83
    call print_string
    cmp byte [fs:S_CONTROLLER], 0
    je .disabled
%if BOARD_ATA_DEVICE_COUNT = 4
    cmp byte [fs:S_ENABLED],1
%else
    cmp byte [fs:C_HDD], 1
%endif
    jne .disabled
    mov si, msg_ata
    cmp byte [fs:S_PRESENT], 1
    je .model
    mov si, msg_atapi
    cmp byte [fs:S_ATAPI], 1
    je .model
    mov si, msg_ide_absent
    jmp print_string
.disabled:
    mov si, msg_ide_disabled
    jmp print_string
.model:
    call print_string
    mov bx, S_MODEL
.char:
    mov al, [fs:bx]
    inc bx
    test al, al
    jz .done
    mov ah, 0x0E
    push bx
    xor bx, bx
    int 0x10
    pop bx
    jmp .char
.done:
    mov si, msg_newline
    jmp print_string

ata_identify_selected:
    push es
    mov byte [fs:S_PRESENT], 0
    mov byte [fs:S_ATAPI], 0
    mov word [fs:S_PACKET_BYTES], 0
    mov byte [fs:S_MODEL], 0
    mov dword [fs:S_CAPACITY], 0
    mov word [fs:S_NATIVE_HEADS], 0
    mov byte [fs:S_STATUS], 0
    mov dword [fs:S_IDENTIFY_TRACE], 0
    mov word [fs:S_IDENTIFY_TRACE + 4], 0
    mov word [fs:S_MULTIPLE_MAX], 0
    mov byte [fs:S_CHS_ONLY], 0
%ifdef BOARD_ATA_PIO_MAX
%ifdef BOARD_ATA_PIO_ADAPTER
    mov byte [fs:S_PIO_MODE],0
    mov byte [fs:S_PIO_LIMIT],0
    call ide_pio_guard
%else
    call ide_pio_begin
%endif
    jc .done
%endif
    mov word [fs:S_GEOMETRY], 0
    cmp byte [fs:S_CONTROLLER], 0
    je .done
%if BOARD_ATA_DEVICE_COUNT = 4
    cmp byte [fs:S_ENABLED],1
%else
    cmp byte [fs:C_HDD], 1
%endif
    jne .done
    mov byte [fs:S_IDENTIFY_TRACE], 1
%ifdef EMULATOR_IDENTIFY_TIMEOUT
    mov byte [fs:S_TEST_ATA], 0x80
%endif
    post_code 0x71
    ata_port ATA_DRIVE
    mov al, 0xA0
    or al, [fs:S_ATA_DEVICE]
    out dx, al
    call ata_delay
    ata_port ATA_STATUS
    call ata_read_status
    cmp al, 0xFF
    je .snapshot
    ; ATAPI need not assert DRDY. Only wait for BSY before identification.
    mov byte [fs:S_IDENTIFY_TRACE], 2
    post_code 0x72
    mov cx, 15000           ; Up to30 seconds, measured by the existing PIT wait.
.not_busy:
    call ata_read_status
    test al, 0x80
    jz .identify
    call kbc_delay_2ms
    loop .not_busy
    mov byte [fs:S_STATUS], ERR_TIMEOUT
    jmp .snapshot
.identify:
    ; The reset signature identifies ATAPI before any task-file writes.
    post_code 0x73
    call ata_packet_signature
    jnc .packet_identify
    mov byte [fs:S_IDENTIFY_TRACE], 3
    post_code 0x74
    ata_port ATA_COMMAND
    mov al, 0xEC
    out dx, al
    call ata_delay
    call ata_read_status
    test al, al
    jz .snapshot
    cmp al, 0xFF
    je .snapshot
    call ata_identify_wait_drq
    jnc .data
    ; IDENTIFY DEVICE aborts on packet devices and returns14h/EBh signature.
    call ata_packet_signature
    jc .snapshot
.packet_identify:
    mov byte [fs:S_IDENTIFY_TRACE], 4
    mov di, 2               ; Initial IDENTIFY and one device-reset retry.
.packet_command:
    ; Linux ide-probe.c uses nIEN and Alternate Status for polled IDENTIFY.
    ; Keep the legacy Device Control bit3 set while suppressing device IRQs.
    post_code 0x75
    ata_port ATA_CONTROL
    mov al, 0x0A
    out dx, al
    post_code 0x76
    mov cx, 25
.packet_settle:
    call kbc_delay_2ms
    loop .packet_settle
    ata_port ATA_ERROR        ; Write side is Features, not the Error register.
    xor al, al
    out dx, al
    post_code 0x77
    ata_port ATA_COMMAND
    mov al, 0xA1
    out dx, al
    call ata_delay
    post_code 0x78
    call ata_identify_wait_drq
    jnc .packet_data
    cmp byte [fs:S_STATUS], ERR_TIMEOUT
    jne .packet_failed
    dec di
    jz .packet_failed
    ; Linux probe fallback; P5 BR0T E000:3E2A also uses DEVICE RESET (08h).
    ; Reset only this known packet device, never the already-detected disk.
    mov byte [fs:S_IDENTIFY_TRACE], 8
    post_code 0x79
    ata_port ATA_COMMAND
    mov al, 8
    out dx, al
    call ata_delay
    post_code 0x7A
    mov cx, 15000
    ata_port ATA_CONTROL
.packet_reset_wait:
    call ata_read_status
    test al, 0x80
    jz .packet_retry
    call kbc_delay_2ms
    loop .packet_reset_wait
    jmp .packet_failed
.packet_retry:
    mov byte [fs:S_IDENTIFY_TRACE], 9
    post_code 0x7B
    jmp .packet_command
.packet_failed:
    ata_port ATA_CONTROL
    xor al, al              ; Restore the established runtime IRQ policy.
    out dx, al
    jmp .snapshot
.packet_data:
    mov byte [fs:S_ATAPI], 1
.data:
    mov byte [fs:S_IDENTIFY_TRACE], 5
    post_code 0x7C
    xor ax, ax
    mov es, ax
    mov di, IDENTIFY_BUFFER
    ata_port ATA_DATA
    mov cx, 256
    ; AMI A1 transfer2B00 and Linux do_identify mask CPU interrupts here.
    ; Match the existing runtime PIO guard; retain the caller's IF and DF.
    pushf
    cli
    cld
    rep insw
    popf
%ifdef EMULATOR_IDENTIFY_POST_STATUS
    mov byte [fs:S_TEST_PHASE], 0xA5
    mov byte [fs:S_TEST_ATA], EMULATOR_IDENTIFY_POST_STATUS
%endif
    mov byte [fs:S_IDENTIFY_TRACE], 6
    post_code 0x7D
    call ata_wait_complete
    jc .identify_failed
    cmp byte [fs:S_ATAPI], 1
    jne .capacity
    ata_port ATA_CONTROL
    xor al, al
    out dx, al
    mov ax, [es:IDENTIFY_BUFFER]
    mov bx, ax
    and ax, 0xC000
    cmp ax, 0x8000
    jne .identify_failed
    mov ax, bx
    and ax, 3
    cmp ax, 1
    ja .model_start         ; Unknown packet size is display-only.
    shl al, 2
    add al, 12
    mov [fs:S_PACKET_BYTES], al
    shr bx, 8
    and bl, 0x1F
    cmp bl, 5
    sete byte [fs:S_PACKET_CD]
    jmp .model_start
.capacity:
    call ide_identify_capacity
    jc .snapshot
    jmp .model_start
.model_start:
    ; ATA strings store the first ASCII byte in the high half of each word.
    post_code 0x7E
    mov si, IDENTIFY_BUFFER + 54
    mov di, S_MODEL
    mov cx, 20
.model:
    mov ax, [es:si]
    xchg al, ah
    mov [fs:di], ax
    add si, 2
    add di, 2
    loop .model
    mov byte [fs:di], 0
    cmp byte [fs:S_ATAPI], 1
    je .identified
    mov byte [fs:S_PRESENT], 1
    call ide_configure_disk
    jc .snapshot
.identified:
    mov byte [fs:S_IDENTIFY_TRACE], 7
    mov byte [fs:S_STATUS], 0
%ifdef BOARD_ATA_PIO_MAX
    call ide_pio_identify
%endif
    jmp .snapshot
.identify_failed:
    post_code 0x7F
    cmp byte [fs:S_ATAPI], 1
    jne .clear_packet
    ata_port ATA_CONTROL
    xor al, al
    out dx, al
.clear_packet:
    mov byte [fs:S_ATAPI], 0
.snapshot:
    cmp byte [fs:S_PRESENT], 1
    je .snapshot_ports
    cmp byte [fs:S_ATAPI], 1
    je .snapshot_ports
    call ide_manual_fallback
.snapshot_ports:
    post_code 0x81
    ata_port ATA_STATUS
    call ata_read_status
    mov [fs:S_IDENTIFY_TRACE + 1], al
    ata_port ATA_ERROR
    in al, dx
    mov [fs:S_IDENTIFY_TRACE + 2], al
    inc dx
    in al, dx
    mov [fs:S_IDENTIFY_TRACE + 3], al
    ata_port ATA_LBA1
    in al, dx
    mov [fs:S_IDENTIFY_TRACE + 4], al
    inc dx
    in al, dx
    mov [fs:S_IDENTIFY_TRACE + 5], al
.done:
    post_code 0x82
    call publish_disk_table
    pop es
    ret

; CF clear only for the standard packet-device signature.
ata_packet_signature:
    ata_port ATA_LBA1
    in al, dx
    cmp al, 0x14
    jne .no
    inc dx
    in al, dx
    cmp al, 0xEB
    jne .no
    clc
    ret
.no:
    stc
    ret

; Publish the detected drive, not a code pointer masquerading as its table.
; Reload the far pointer after EMM386 relocates the EBDA.
; POST owns publication; option ROMs can reuse these vectors afterward.
 ; DL=BIOS disk number. Only present ATA records owe a BIOS number.
ata_select_bios_disk:
    push ax
    push bx
    push cx
    call load_bios_state
    mov bl,dl
    sub bl,0x80
    jc .missing
    mov cx,BOARD_ATA_DEVICE_COUNT
.position:
    cmp byte [fs:S_PRESENT],1
    jne .next
    test bl,bl
    jz .found
    dec bl
.next:
    mov ax,fs
    add ax,0x20
    mov fs,ax
    loop .position
.missing:
    call load_bios_state
    stc
    jmp .done
.found:
    clc
.done:
    pop cx
    pop bx
    pop ax
    ret

; A loaded BPB describes the actual boot disk, not every Auto disk.
ata_bpb_owner:
    push ax
    push dx
    push fs
    push es
    mov dx,fs
    call load_bios_state
    mov al,[fs:B_DRIVE]
    push dx
    mov dl,al
    call ata_select_bios_disk
    pop dx
    jc .done
    mov ax,fs
    cmp ax,dx
    jne .other
    clc
    jmp .done
.other:
    stc
.done:
    pop es
    pop fs
    pop dx
    pop ax
    ret

disk_refresh_vector:
    pushad
    push es
    push fs
    call load_bios_state
    xor ax,ax
    mov es,ax
    mov byte [es:0x0475],0
    mov dword [es:0x0104],0
    mov dword [es:0x0118],0
    mov cx,BOARD_ATA_DEVICE_COUNT
.position:
    cmp byte [fs:S_PRESENT],1
    jne .next
    mov di,0x0104
    cmp byte [es:0x0475],0
    je .pointer
    mov di,0x0118
    cmp byte [es:0x0475],1
    jne .count
.pointer:
    mov word [es:di],S_FDPT
    mov [es:di+2],fs
.count:
    inc byte [es:0x0475]
.next:
    mov ax,fs
    add ax,0x20
    mov fs,ax
    loop .position
    pop fs
    pop es
    popad
    ret

%include "firmware/disk-parameter-table.inc"

publish_disk_cmos:
    pushad
    push es
    push fs
    call disk_refresh_vector
    xor ax, ax
    mov es, ax
    mov ah, [es:0x0475]
    test ah, ah
    jz .type
    cmp ah, 2
    mov ah, 0xF0
    jb .type
    mov ah, 0xFF
.type:
    mov al, 0x12
    call rtc_write
    xor bp, bp
.drive:
    mov ax, [es:0x0106]
    test bp, bp
    jz .pointer
    mov ax, [es:0x011A]
.pointer:
    xor dx, dx
    test ax, ax
    jz .extended_type
    mov fs, ax
    mov dh, 47
.extended_type:
    mov ax, bp
    add al, 0x19
    mov ah, dh
    call rtc_write
    mov si, S_FDPT
    mov di, disk_cmos_offsets
    mov cx, 9
.byte:
    mov bx, [cs:di]
    xor bh, bh
    xor ah, ah
    test dh, dh
    jz .byte_write
    mov ah, [fs:si+bx]
.byte_write:
    mov al, 0x24
    sub al, cl              ; CMOS1B..23: cylinders through sectors/track.
    test bp, bp
    jz .write
    add al, 9
.write:
    call rtc_write
    inc di
    loop .byte
    inc bp
    cmp bp, 2
    jb .drive
    call update_cmos_checksum
    pop fs
    pop es
    popad
    ret
disk_cmos_offsets: db 0, 1, 2, 5, 6, 8, 12, 13, 14

ata_select_ready:
%ifdef BOARD_ATA_PIO_MAX
    call ide_pio_guard
    jc .return
%endif
    ata_port ATA_DRIVE
    mov al, 0xA0
    or al, [fs:S_ATA_DEVICE]
    out dx, al
    call ata_delay
    jmp ata_wait_ready
%ifdef BOARD_ATA_PIO_MAX
.return:
    ret
%endif

ata_no_data_command:
    ata_port ATA_COMMAND
    out dx, al
    jmp ata_wait_complete

%include "pc/chs-geometry.inc"

%ifndef BOARD_ATA_PIO_LATE
%include "pc/ata-reset.inc"
%endif


%include "firmware/ata-transfer.inc"

%include "pc/ata-status.inc"
%ifdef BOARD_ATA_PIO_MAX
%ifndef BOARD_ATA_PIO_LATE
%include "firmware/ide-pio.inc"
%endif
%endif

ata_read_status:
%ifdef EMULATOR_TEST
    cmp byte [fs:S_TEST_ATA], 0
    je .hardware
    mov al, [fs:S_TEST_ATA]
    ret
.hardware:
%endif
    in al, dx
    ret

%ifdef EMULATOR_TEST
ata_test_after_read:
    cmp byte [fs:S_TEST_AFTER_STATUS], 0
    je .done
    dec byte [fs:S_TEST_AFTER_COUNT]
    jnz .done
    mov al, [fs:S_TEST_AFTER_STATUS]
    mov [fs:S_TEST_ATA], al
    mov byte [fs:S_TEST_AFTER_STATUS], 0
    mov byte [fs:S_TEST_PHASE], 0xA6
.done:
    ret
%endif

ata_delay:
    push cx
    push dx
    ata_port ATA_CONTROL
    mov cx, 4
.again:
    in al, dx
    loop .again
    pop dx
    pop cx
    ret

%include "firmware/boot.inc"

%include "firmware/boot-terminal.inc"

%ifdef EMULATOR_TEST
verify_initialization:
    jmp core_verify_initialization

%endif
%ifdef EMULATOR_TEST
%define EMULATOR_EXIT_REQUIRED
%endif
%ifdef EMULATOR_POST_SUMMARY_TEST
%define EMULATOR_EXIT_REQUIRED
%endif
%ifdef EMULATOR_DOS_WARM_STATE
%define EMULATOR_EXIT_REQUIRED
%endif
%ifdef EMULATOR_EXIT_REQUIRED
emulator_exit:
    mov bl, al
    mov dx, POST_PORT
    mov al, '8'
    out dx, al
    mov al, '6'
    out dx, al
    mov al, 'B'
    out dx, al
    mov al, 'o'
    out dx, al
    mov al, 'x'
    out dx, al
    mov al, 0x01
    out dx, al
    mov al, 0x05
    out dx, al
    mov dx, 0x0501
    mov al, 4
    out dx, al
    inc dx
    mov al, bl
    out dx, al
    ret
%endif

%include "firmware/floppy.inc"
%include "hardware/floppy-core.inc"
%include "firmware/mouse.inc"
%ifdef BOARD_MOUSE_POLICY_SOURCE
%include BOARD_MOUSE_POLICY_SOURCE
%endif
%include "firmware/memory.inc"
%include "firmware/ide.inc"
%include "firmware/peripherals.inc"
%include "firmware/setup.inc"
%ifdef BOARD_PNP_SUPPORT
%include "firmware/pnp-interface.inc"
%include "firmware/pnp-entry.inc"
%include "firmware/pnp-storage-callbacks.inc"
%ifdef M919_BOARD_DEFINITION
%include "firmware/pnp-bridge.inc"
%elifdef PB430_PORT
%include "firmware/pnp-post.inc"
%include "hardware/pnp-module.inc"
%endif
%endif
%include "firmware/post.inc"
%include "hardware/chipset-core.inc"
%ifdef BOARD_APM_SOURCE
%include BOARD_APM_SOURCE
%else
%include "firmware/apm.inc"
%endif
%ifndef BOARD_LATE_CDBOOT
%include "firmware/cdboot.inc"
%endif
%ifdef EMULATOR_PORTS_TEST
%include BOARD_PORTS_TEST
%endif
%ifdef EMULATOR_CHIPSET_TEST
%include BOARD_CHIPSET_TEST
%endif
%ifdef EMULATOR_SETUP_TEST
; Diagnostic observers use resident headroom before fixed compatibility entries.
%include "../tests/firmware/setup-test.inc"
%endif
%ifdef EMULATOR_BOOT_POLICY_TEST
%include "../tests/firmware/boot-policy-test.inc"
%endif
%ifdef EMULATOR_BOOT_SETTINGS_RECOVERY
%include "../tests/firmware/boot-policy-test.inc"
%endif
%ifdef EMULATOR_POST_SUMMARY_TEST
%include "../tests/firmware/summary-test.inc"
%else
%ifdef EMULATOR_TEST
%include "../tests/firmware/summary-test.inc"
%endif
%endif

msg_ata         db 'ATA ',0
msg_atapi       db 'ATAPI ',0
msg_ide_absent  db 'Not detected',13,10,0
msg_ide_disabled db 'Disabled',13,10,0
msg_newline     db 13,10,0
msg_no_disk     db 'No primary ATA disk', 13, 10, 0
msg_boot_error  db 'No bootable disk', 13, 10, 0

; Speedsys 4.78's ROM scan (1348..139D) leaks DS=F000 and a stack word
; when no 198x/199x vendor string is found. This is a legacy scan token,
; not a build/copyright date. Keep the actual firmware identity unchanged.
legacy_rom_id   db 'Legacy ROM scan token: 1999, BAIOS', 0

%include "firmware/identity.inc"

; The board installs INT42 from the actual VGA provider's INT10 vector.
%ifdef BOARD_LATE_CDBOOT
%include BOARD_ROM_COMPAT_SOURCE
%include "firmware/cdboot.inc"
%endif
rom_code_end:
%ifndef BOARD_LATE_CDBOOT
%ifdef BOARD_ROM_COMPAT_SOURCE
%include BOARD_ROM_COMPAT_SOURCE
%endif
%endif
; Keep POST discovery helpers after any fixed VGA compatibility entry.
%include "pc/ata-identify.inc"
times CFG_ROM_CHECKSUM_OFFSET-((CFG_ROM_CODE_SEGMENT << 4)-CFG_ROM_BASE)-($-$$) db 0xFF
checksum_byte: db 0
reset_vector:
%ifdef BOARD_RESET_NEAR
    ; Preserve the CPU's high reset-CS alias until the board clears shadowing.
    db 0xE9
    dw (startup-($+2)) & 0xFFFF
    db 0x90,0x90
%else
    jmp CFG_ROM_CODE_SEGMENT:startup
%endif
bios_date db BIOS_DATE_PREFIX,BIOS_DATE_YEAR
    db 0,CFG_ROM_MODEL_BYTE,0
