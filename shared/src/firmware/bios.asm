bits 16

%define BIOS_VERSION CFG_IDENTITY_VERSION
%define BIOS_RELEASE_DATE CFG_IDENTITY_RELEASE_DATE
%substr BIOS_DATE_PREFIX BIOS_RELEASE_DATE 1,6
%substr BIOS_DATE_YEAR BIOS_RELEASE_DATE 9,2

%ifndef BOARD_DEFINITION
%error "Select a board definition before composing the firmware core"
%endif
%include BOARD_DEFINITION
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
    call load_bios_state
    call init_peripherals
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
%ifdef BOARD_RAM_POLICY_BEFORE_TEST
    post_code 0x7F
    call BOARD_RAM_CACHE_FINISH
%else
    call chipset_late_cache
%ifdef BOARD_LATE_MEMORY_POLICY
    call BOARD_LATE_MEMORY_POLICY
%endif
%endif
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
    call post_debug_summary
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

; OEM F000:B343: DOS ATAPI drivers chain hard-disk IRQ14 here.
; A bare IRET leaves the slave PIC and cascade in service and blocks devices.
int76:
    push ax
    push ds
    mov ax, 0x0040
    mov ds, ax
    mov byte [0x008E], 0xFF
    mov al, 0x66               ; Specific slave IRQ6 (system IRQ14) EOI.
    out 0xA0, al
    mov al, 0x62               ; Specific master cascade EOI.
    out 0x20, al
    xor ax, ax
    mov ds, ax
    mov ax, 0x9100             ; OEM device-completion notification hook.
    int 0x15
    pop ds
    pop ax
    iret

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

int12:
    push ds
    mov ax, 0x40
    mov ds, ax
    mov ax, [0x13]
    pop ds
    iret

int15:
    push bp
    mov bp, sp
    cmp ah, 0x53
    je apm_int15
    cmp ah, 0xC2
    je mouse_int15
    cmp ah, 0xC0
    je .configuration
    cmp ah, 0xC1
    je .extended_data_area
%ifdef EMULATOR_TEST
    cmp ah, 0xEF
    je .test_control
%endif
    cmp ah, 0x88
    je .memory
    cmp ah, 0x87
    je .move_memory
    cmp ax, 0x448E
    je .oem_ok
    mov ah, 0x86
    or word [ss:bp + 6], 1
    pop bp
    iret
.configuration:
    push cs
    pop es
    mov bx, system_configuration
    xor ax, ax
    jmp .oem_ok
.extended_data_area:
    ; Windows EBIOS uses C1 to protect this page in 386 Enhanced mode.
    ; Read the current pointer: a DOS memory manager may relocate the EBDA.
    push fs
    call load_bios_state
    push fs
    pop es
    pop fs
    jmp .oem_ok
.move_memory:
    call move_extended_memory
    jc .move_failed
    xor ah, ah
    jmp .oem_ok
.move_failed:
    mov ah, 2
    or word [ss:bp + 6], 1
    pop bp
    iret
.memory:
    push fs
    call load_bios_state
    mov ax, [fs:S_EXTENDED_KIB]
    pop fs
.oem_ok:
    and word [ss:bp + 6], 0xFFFE
    pop bp
    iret
%ifdef EMULATOR_TEST
.test_control:
    push ds
    push ax
    xor ax, ax
    mov ds, ax
    mov ax, [0x040E]
    mov ds, ax
    pop ax
    cmp al, 1
    je .test_missing
    cmp al, 2
    je .test_present
    cmp al, 3
    je .test_after_read
    mov [S_TEST_ATA], al
    test al, al
    jnz .test_done
    mov byte [S_TEST_AFTER_STATUS], 0
    mov byte [S_TEST_AFTER_COUNT], 0
    mov byte [S_TEST_PHASE], 0
    jmp .test_done
.test_missing:
    mov byte [S_PRESENT], 0
    jmp .test_done
.test_present:
    mov byte [S_PRESENT], 1
    jmp .test_done
.test_after_read:
    mov [S_TEST_AFTER_STATUS], bl
    mov [S_TEST_AFTER_COUNT], bh
    mov byte [S_TEST_ATA], 0
.test_done:
    pop ds
    xor ah, ah
    and word [ss:bp + 6], 0xFFFE
    pop bp
    iret
%endif

; AT block move: ES:SI points to the caller's descriptor table, CX words.
; OEM F000:F3EC-F5C3 uses a protected-mode copy and a direct 486 return.
; Use a private flat descriptor instead of modifying the caller's table.
; Interrupts remain masked; no stack access occurs in protected mode.
move_extended_memory:
    pushad
    push ds
    push es
    sub sp, 6
    mov di, sp
    sgdt [ss:di]
    smsw ax
    test al, 1
    jnz .invalid
    cmp cx, 0x8000
    ja .invalid
    cmp si, 0xFFD0
    ja .invalid
    mov bx, si
    mov esi, [es:bx + 0x12]
    and esi, 0x00FFFFFF
    movzx eax, byte [es:bx + 0x17]
    shl eax, 24
    or esi, eax
    mov edi, [es:bx + 0x1A]
    and edi, 0x00FFFFFF
    movzx eax, byte [es:bx + 0x1F]
    shl eax, 24
    or edi, eax
    movzx ecx, cx
    mov eax, ecx
    shl eax, 1
    add eax, esi
    jc .invalid
    mov eax, ecx
    shl eax, 1
    add eax, edi
    jc .invalid
    ; Temporarily enable fast A20 and restore its exact prior gate state.
    in al, 0x92
    mov dl, al
    and al, 0xFE
    or al, 2
    out 0x92, al
    mov al, 0x80
    out 0x70, al
    lgdt [cs:move_gdtr]
    mov ebx, cr0
    mov eax, ebx
    or al, 1
    mov cr0, eax
    jmp 0x08:.protected
.protected:
    mov ax, 0x10
    mov ds, ax
    mov es, ax
    cld
    a32 rep movsw
    ; Restore real-mode data limits before leaving protected mode.
    mov ax, 0x18
    mov ds, ax
    mov es, ax
    mov cr0, ebx
    jmp 0xF000:.real
.real:
    mov di, sp
    o32 lgdt [ss:di]
    mov al, dl
    and al, 0xFE
    out 0x92, al
    xor al, al
    out 0x70, al
    clc
    jmp .return
.invalid:
    stc
.return:
    mov di, sp
    lea sp, [di + 6]
    pop es
    pop ds
    popad
    ret

align 8
move_gdt:
    dq 0
    dw 0xFFFF, 0x0000
    db 0x0F, 0x9B, 0x00, 0x00 ; 16-bit BIOS code, accessed bit already set.
    dw 0xFFFF, 0x0000
    db 0x00, 0x93, 0x8F, 0x00 ; Flat 4 GiB data.
    dw 0xFFFF, 0x0000
    db 0x00, 0x93, 0x00, 0x00 ; Real-mode 64 KiB data limits.
move_gdtr:
    dw $ - move_gdt - 1
    dd 0xF0000 + move_gdt

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
    call disk_refresh_vector
    mov word [fs:S_BLOCK_SIZE], 512
    cmp dl, 0x80
    je .first_drive
    cmp dl, 0x81
    jne .invalid_drive
    cmp byte [fs:S_PRESENT], 1
    jne .invalid_drive
    cmp byte [fs:0x200 + S_PRESENT], 1
    jne .invalid_drive
    jmp .slave_drive
.first_drive:
    cmp byte [fs:S_PRESENT], 1
    je .drive_ok
    cmp byte [fs:0x200 + S_PRESENT], 1
    jne .drive_ok           ; Retain absent80h status/capability behavior.
.slave_drive:
    push ax
    mov ax, fs
    add ax, 0x20
    mov fs, ax
    pop ax
    mov word [fs:S_BLOCK_SIZE], 512
    jmp .drive_ok
.invalid_drive:
    call .clear_dap_if_packet
    jmp .bad_command
.drive_ok:
    cmp ah, 0x01
    je .status
    cmp ah, 0x00
    je .reset
    cmp ah, 0x0D
    je .reset
    cmp ah, 0x04
    je .known_function
    cmp ah, 0x05
    je .known_function
    cmp ah, 0x09
    je .known_function
    cmp ah, 0x0A
    je .known_function
    cmp ah, 0x0B
    je .known_function
    cmp ah, 0x0C
    je .known_function
    cmp ah, 0x10
    je .known_function
    cmp ah, 0x11
    je .known_function
    cmp ah, 0x14
    je .known_function
    cmp ah, 0x02
    je .known_function
    cmp ah, 0x03
    je .known_function
    cmp ah, 0x08
    je .known_function
    cmp ah, 0x15
    je .known_function
    cmp ah, 0x41
    je .known_function
    cmp ah, 0x42
    je .known_function
    cmp ah, 0x43
    je .known_function
    cmp ah, 0x44
    je .known_function
    cmp ah, 0x47
    je .known_function
    cmp ah, 0x48
    jne .bad_command
.known_function:
    cmp byte [fs:S_PRESENT], 1
    je .present
    call .clear_dap_if_packet
    jmp .timeout
.present:
    cmp ah, 0x41
    jb .extensions_allowed
    cmp byte [fs:S_IDE + IDE_EDD_OFF], 1
    je .bad_command
.extensions_allowed:
    cmp ah, 0x04
    je .legacy_verify
    cmp ah, 0x05
    je .legacy_format
    cmp ah, 0x09
    je .initialize_parameters
    cmp ah, 0x0A
    je .legacy_read_long
    cmp ah, 0x0B
    je .legacy_write_long
    cmp ah, 0x0C
    je .legacy_seek
    cmp ah, 0x10
    je .ready
    cmp ah, 0x11
    je .recalibrate
    cmp ah, 0x14
    je .diagnostic
    cmp ah, 0x02
    je .legacy_read
    cmp ah, 0x03
    je .legacy_write
    cmp ah, 0x08
    je .geometry
    cmp ah, 0x15
    je .type
    cmp ah, 0x41
    je .extensions
    cmp ah, 0x42
    je .extended_read
    cmp ah, 0x43
    je .extended_write
    cmp ah, 0x44
    je .extended_verify
    cmp ah, 0x47
    je .extended_seek
    cmp ah, 0x48
    je .parameters
    jmp .bad_command

.status:
    mov ah, [fs:S_STATUS]
    mov al, ah
    test ah, ah
    jnz .return_error
    jmp .success

.reset:
    cmp byte [fs:S_PRESENT], 1
    jne .timeout
    call ata_reset
    jc .return_error
    xor ah, ah
    jmp .success

.ready:
    call ata_select_ready
    jc .return_error
    xor ah, ah
    jmp .success

.initialize_parameters:
    ; Program native ATA geometry, never the translated BIOS geometry.
    call ata_select_ready
    jc .return_error
    mov al, [fs:S_NATIVE_HEADS]
    test al, al
    jz .bad_address
    cmp al, 16
    ja .bad_address
    dec al
    or al, 0xA0
    or al, [fs:S_ATA_DEVICE]
    ata_port ATA_DRIVE
    out dx, al
    mov al, [fs:S_NATIVE_SECTORS]
    ata_port ATA_COUNT
    out dx, al
    mov al, 0x91
    jmp .controller_command
.recalibrate:
    call ata_select_ready
    jc .return_error
    mov al, 0x10
    jmp .controller_command
.diagnostic:
    call ata_select_ready
    jc .return_error
    mov al, 0x90
    call ata_no_data_command
    jc .return_error
    ata_port ATA_DATA + 1
    in al, dx
    cmp al, 1
    jne .controller_error
    xor ah, ah
    jmp .success
.controller_command:
    call ata_no_data_command
    jc .return_error
    xor ah, ah
    jmp .success
.controller_error:
    mov byte [fs:S_STATUS], ERR_CONTROLLER
    jmp .return_error

.legacy_seek:
    ; AH0C specifies a cylinder/head; AL, sector bits and ES:BX are not data.
    and cl, 0xC0
    or cl, 1
    call chs_to_lba
    jc .return_error
    cmp eax, [fs:S_CAPACITY]
    jae .bad_address
    mov [fs:S_LBA], eax
    mov byte [fs:S_COMMAND], CMD_SEEK
    mov byte [fs:S_COUNT], 1
    mov byte [fs:S_DONE], 0
    call ata_transfer
    jc .return_error
    xor ah, ah
    jmp .success

.legacy_format:
    test al, al
    jz .bad_address
    push ax
    call get_chs_geometry
    mov dl, ah
    pop ax
    cmp al, dl
    ja .bad_address
    ; ATA FORMAT TRACK consumes one 512-byte interleave descriptor block.
    ; Device ABRT is a real controller error, never a fabricated success.
    mov al, 1
    and cl, 0xC0
    or cl, 1
    mov byte [fs:S_COMMAND], CMD_FORMAT
    jmp .legacy
.legacy_verify:
    mov byte [fs:S_COMMAND], CMD_VERIFY
    jmp .legacy
.legacy_read_long:
    mov word [fs:S_BLOCK_SIZE], 516
    mov byte [fs:S_COMMAND], CMD_READ_LONG
    jmp .legacy
.legacy_write_long:
    mov word [fs:S_BLOCK_SIZE], 516
    mov byte [fs:S_COMMAND], CMD_WRITE_LONG
    jmp .legacy
.legacy_read:
    mov byte [fs:S_COMMAND], CMD_READ
    jmp .legacy
.legacy_write:
    mov byte [fs:S_COMMAND], CMD_WRITE
.legacy:
    call prepare_chs
    jc .legacy_chs_error
    call ata_transfer
    jc .legacy_io_error
    mov al, [fs:S_DONE]
    cmp byte [fs:S_COMMAND], CMD_READ
    jne .legacy_success
    push ax
    call get_chs_geometry
    shr al, 4
    or al, 0xA0
    out POST_PORT, al
    pop ax
.legacy_success:
    xor ah, ah
    jmp .success
.legacy_chs_error:
    cmp byte [fs:S_COMMAND], CMD_READ
    jne .return_error_al
    post_code 0xB2
    jmp .return_error_al
.legacy_io_error:
    cmp byte [fs:S_COMMAND], CMD_READ
    jne .return_error_al
    post_code 0xB3
    jmp .return_error_al

.geometry:
    call publish_disk_table
    call get_chs_geometry
    movzx ecx, al
    movzx edx, ah
    imul ecx, edx
    push ax
    mov eax, [fs:S_CAPACITY]
    xor edx, edx
    div ecx
    test eax, eax
    jnz .geometry_present
    pop ax
    jmp .bad_address
.geometry_present:
    dec eax
    cmp eax, 1023
    jbe .geometry_cylinder
    mov eax, 1023
.geometry_cylinder:
    ; OEM B0DA/B0DB reports count minus two: last cylinder number plus
    ; one reserved cylinder. WDCTRL compares this with the fixed table.
    ; A one-cylinder disk must still report cylinder zero.
    test eax, eax
    jz .geometry_encoded
    dec eax
.geometry_encoded:
    mov ch, al
    mov dl, ah
    and dl, 3
    shl dl, 6
    pop ax
    mov cl, ah
    or cl, dl
    mov dh, al
    dec dh
    push es
    xor dx, dx
    mov es, dx
    mov dl, [es:0x0475]
    pop es
    mov dh, al
    dec dh
    xor ah, ah
    jmp .cx_dx_result

.type:
    mov eax, [fs:S_CAPACITY]
    mov dx, ax
    shr eax, 16
    mov cx, ax
    mov ah, 3
.cx_dx_result:
    mov [ss:bp - 8], cx
    mov [ss:bp - 12], dx
    jmp .success

.extensions:
    cmp bx, 0x55AA
    jne .bad_command
    mov bx, 0xAA55
    mov ah, 0x11
    mov cx, 1
    mov [ss:bp - 16], bx
    mov [ss:bp - 8], cx
    jmp .success

.extended_read:
    mov byte [fs:S_COMMAND], CMD_READ
    jmp .extended_transfer
.extended_write:
    test al, al
    jz .write_option_ok
    mov word [ds:si + 2], 0
    jmp .bad_command
.write_option_ok:
    mov byte [fs:S_COMMAND], CMD_WRITE
    jmp .extended_transfer
.extended_verify:
    mov byte [fs:S_COMMAND], CMD_VERIFY
.extended_transfer:
    call prepare_dap
    jc .return_error_dap
    call ata_transfer
    push ax
    mov al, [fs:S_DONE]
    mov [ds:si + 2], al
    mov byte [ds:si + 3], 0
    pop ax
    jc .return_error
    xor ah, ah
    jmp .success

.extended_seek:
    mov byte [fs:S_COMMAND], 0
    call prepare_dap
    jc .return_error_dap
    mov word [ds:si + 2], 0
    xor ah, ah
    jmp .success

.parameters:
    call fill_edd_parameters
    jc .return_error
    xor ah, ah
    jmp .success

.bad_address:
    mov byte [fs:S_STATUS], ERR_BAD_ADDRESS
    jmp .return_error
.bad_command:
    mov byte [fs:S_STATUS], ERR_BAD_COMMAND
    jmp .return_error
.timeout:
    mov byte [fs:S_STATUS], ERR_TIMEOUT
.return_error:
    mov ah, [fs:S_STATUS]
    or word [ss:bp + 6], 1
    jmp .return
.return_error_al:
    mov al, [fs:S_DONE]
    jmp .return_error
.return_error_dap:
    mov word [ds:si + 2], 0
    jmp .return_error
.success:
    mov byte [fs:S_STATUS], 0
    and word [ss:bp + 6], 0xFFFE
.return:
    push ax
    push ds
    xor ax, ax
    mov ds, ax
    mov al, [fs:S_STATUS]
    mov [0x0474], al
    pop ds
    pop ax
    ; OEM AE4A: DOS drive services can enter with IF=0 and require IF=1 back.
    or word [ss:bp + 6], 0x0200
    mov [ss:bp - 4], ax
    pop fs
    popad
    pop bp
    iret

.clear_dap_if_packet:
    cmp ah, 0x42
    je .clear_packet_count
    cmp ah, 0x43
    je .clear_packet_count
    cmp ah, 0x44
    je .clear_packet_count
    cmp ah, 0x47
    jne .packet_done
.clear_packet_count:
    mov word [ds:si + 2], 0
.packet_done:
    ret

prepare_chs:
    push cx
    push dx
    push bx
    mov [fs:S_COUNT], al
    mov byte [fs:S_DONE], 0
    test al, al
    jz .bad
    cmp al, 128                ; Legacy CHS permits a full 64 KiB transfer.
    ja .bad
    call chs_to_lba
    jc .bad
    mov [fs:S_LBA], eax
    pop bx
    mov [fs:S_BUFFER_OFF], bx
    mov [fs:S_BUFFER_SEG], es
    call validate_request
    pop dx
    pop cx
    ret
.bad:
    mov byte [fs:S_STATUS], ERR_BAD_ADDRESS
    stc
    pop bx
    pop dx
    pop cx
    ret

; Translate one CHS address without any data-buffer or sector-count dependency.
chs_to_lba:
    push bx
    push edx
    call get_chs_geometry
    mov bx, ax
    mov al, cl
    and al, 0x3F
    jz .bad
    cmp al, bh
    ja .bad
    cmp dh, bl
    jae .bad
    movzx eax, ch
    push dx
    movzx edx, cl
    and edx, 0xC0
    shl edx, 2
    or eax, edx
    pop dx
    push dx
    movzx edx, bl
    imul eax, edx
    pop dx
    movzx edx, dh
    add eax, edx
    movzx edx, bh
    imul eax, edx
    movzx edx, cl
    and edx, 0x3F
    dec edx
    add eax, edx
    pop edx
    pop bx
    clc
    ret
.bad:
    mov byte [fs:S_STATUS], ERR_BAD_ADDRESS
    stc
    pop edx
    pop bx
    ret

prepare_dap:
    cmp byte [ds:si], 0x10
    jne .bad
    cmp byte [ds:si + 1], 0
    jne .bad
    mov ax, [ds:si + 2]
    test ax, ax
    jz .bad
    cmp ax, 127
    ja .bad
    mov [fs:S_COUNT], al
    mov byte [fs:S_DONE], 0
    mov ax, [ds:si + 4]
    mov [fs:S_BUFFER_OFF], ax
    mov ax, [ds:si + 6]
    mov [fs:S_BUFFER_SEG], ax
    mov eax, [ds:si + 8]
    mov [fs:S_LBA], eax
    cmp dword [ds:si + 12], 0
    jne .bad
    call validate_request
    ret
.bad:
    mov byte [fs:S_STATUS], ERR_BAD_ADDRESS
    stc
    ret

; EMM386 relocates the EBDA and updates 0040:000E. Never cache its segment
; across BIOS calls. OEM handlers also load the BDA pointer (e.g. F000:9CCC).
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
    push fs
    call load_bios_state     ; FS may select the secondary disk record.
    xor ebx, ebx
    mov bx, fs
    pop fs
    shl ebx, 4
    cmp edx, ebx
    jbe .good
    add ebx, CFG_PLATFORM_STATE_KIB*1024
    cmp eax, ebx
    jb .bad
.good:
    pop ebx
    clc
    ret
.bad:
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

fill_edd_parameters:
    cmp word [ds:si], 26
    jb .bad
    movzx eax, si
    add eax, 26
    cmp eax, 0x10000
    ja .bad
    xor eax, eax
    mov ax, ds
    shl eax, 4
    movzx edx, si
    add eax, edx
    mov edx, eax
    add edx, 26
    call check_disk_buffer
    jc .bad
.buffer_safe:
    mov word [ds:si], 26
    mov word [ds:si + 2], 2
    call get_chs_geometry
    push ax
    movzx ecx, al
    movzx edx, ah
    imul ecx, edx
    mov eax, [fs:S_CAPACITY]
    xor edx, edx
    div ecx
    mov [ds:si + 4], eax
    pop ax
    movzx ecx, al
    mov [ds:si + 8], ecx
    movzx ecx, ah
    mov [ds:si + 12], ecx
    mov eax, [fs:S_CAPACITY]
    mov [ds:si + 16], eax
    mov dword [ds:si + 20], 0
    mov word [ds:si + 24], 512
    clc
    ret
.bad:
    mov byte [fs:S_STATUS], ERR_BAD_ADDRESS
    stc
    ret

ata_report_device:
    post_code 0x83
    call print_string
    cmp byte [fs:S_CONTROLLER], 0
    je .disabled
    cmp byte [fs:C_HDD], 1
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
    mov word [fs:S_GEOMETRY], 0
    cmp byte [fs:S_CONTROLLER], 0
    je .done
    cmp byte [fs:C_HDD], 1
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

; POST identification can wait for a cold ATAPI drive without a CPU-speed limit.
; Runtime ATA transfer waits retain their existing fast owner.
ata_identify_wait_drq:
    mov cx, 15000
    ata_port ATA_STATUS
    cmp byte [fs:S_IDENTIFY_TRACE], 3
    je .poll
    ata_port ATA_CONTROL     ; Packet polling must not acknowledge INTRQ.
.poll:
    call ata_read_status
    test al, 0x80
    jnz .next
    test al, 0x21
    jnz .controller
    test al, 8
    jnz .ok
.next:
    call kbc_delay_2ms
    loop .poll
    mov byte [fs:S_STATUS], ERR_TIMEOUT
    stc
    ret
.controller:
    mov byte [fs:S_STATUS], ERR_CONTROLLER
    stc
    ret
.ok:
    clc
    ret

; Publish the detected drive, not a code pointer masquerading as its table.
; Reload the far pointer after EMM386 relocates the EBDA.
disk_refresh_vector:
    push ax
    push es
    push fs
    call load_bios_state
    xor ax, ax
    mov es, ax
    mov byte [es:0x0475], 0
    mov dword [es:0x0104], 0
    mov dword [es:0x0118], 0
    cmp byte [fs:S_PRESENT], 1
    jne .slave
    inc byte [es:0x0475]
    mov word [es:0x0104], S_FDPT
    mov [es:0x0106], fs
.slave:
    cmp byte [fs:0x200 + S_PRESENT], 1
    jne .done
    mov ax, fs
    add ax, 0x20
    cmp byte [es:0x0475], 0
    jne .second
    mov word [es:0x0104], S_FDPT
    mov [es:0x0106], ax
    jmp .count
.second:
    mov word [es:0x0118], S_FDPT
    mov [es:0x011A], ax
.count:
    inc byte [es:0x0475]
.done:
    pop fs
    pop es
    pop ax
    ret

publish_disk_table:
    pushad
    push es
    call disk_refresh_vector
    mov ax, fs
    mov es, ax
    mov di, S_FDPT
    xor ax, ax
    mov cx, 8
    cld
    rep stosw
    cmp byte [fs:S_PRESENT], 1
    jne .done
    call get_chs_geometry
    mov [fs:S_FDPT+2], al
    mov [fs:S_FDPT+14], ah
    mov byte [fs:S_FDPT+7], 4
    mov word [fs:S_FDPT+5], 0xFFFF
    cmp byte [fs:S_IDE + IDE_TYPE], 0
    je .default_metadata
    mov ax, [fs:S_IDE + IDE_PRECOMP]
    mov [fs:S_FDPT+5], ax
.default_metadata:
    call get_chs_geometry
    cmp al, 8
    jbe .control
    mov byte [fs:S_FDPT+8], 8
.control:
    movzx ecx, al
    movzx edx, ah
    imul ecx, edx
    mov eax, [fs:S_CAPACITY]
    xor edx, edx
    div ecx
    cmp eax, 1024
    jbe .cylinders
    mov eax, 1024
.cylinders:
    mov [fs:S_FDPT], ax
    mov [fs:S_FDPT+12], ax
    cmp byte [fs:S_IDE + IDE_TYPE], 0
    je .done
    mov ax, [fs:S_IDE + IDE_LANDING]
    mov [fs:S_FDPT+12], ax
.done:
    pop es
    popad
    ret

; Publish the logical80h/81h disks, excluding packet devices.
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
    jne .type
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
    ata_port ATA_DRIVE
    mov al, 0xA0
    or al, [fs:S_ATA_DEVICE]
    out dx, al
    call ata_delay
    jmp ata_wait_ready

ata_no_data_command:
    ata_port ATA_COMMAND
    out dx, al
    call ata_delay
    jmp ata_wait_complete

get_chs_geometry:
    mov ax, [fs:S_GEOMETRY]
    test ax, ax
    jnz .return
    mov ax, 0x3F20
    cmp dword [fs:S_CAPACITY], 0x001F8000
    jbe .capacity_done
    mov al, 64
    cmp dword [fs:S_CAPACITY], 0x003F0000
    jbe .capacity_done
    mov al, 128
    cmp dword [fs:S_CAPACITY], 0x007E0000
    jbe .capacity_done
    mov al, 255
.capacity_done:
    ; The boot-sector BPB belongs only to the first logical disk.
    call hardware_bpb_owner
    jc .return
.bpb:
    push ds
    push ax
    xor ax, ax
    mov ds, ax
    pop ax
    cmp byte [0x7C00], 0xEB
    je .check_bpb
    cmp byte [0x7C00], 0xE9
    jne .done
.check_bpb:
    cmp word [0x7C0B], 512
    jne .done
    cmp word [0x7C0E], 0
    je .done
    cmp word [0x7C18], 0
    je .done
    cmp word [0x7C18], 63
    ja .done
    cmp word [0x7C1A], 0
    je .done
    cmp word [0x7C1A], 255
    ja .done
    cmp word [0x7DFE], 0xAA55
    jne .done
    mov ah, [0x7C18]
    mov al, [0x7C1A]
.done:
    pop ds
.return:
    ret

ata_reset:
    push dx
    call ata_reset_bus
    call ata_select_ready
    jc .done
    ; SRST affects both positions. Restore each configured CHS disk before
    ; returning to the original selected record and subsequent transfers.
    push fs
    call load_bios_state
    call .geometry
    jc .geometry_error
    mov ax, fs
    add ax, 0x20
    mov fs, ax
    call .geometry
    jc .geometry_error
    pop fs
    call ata_select_ready
.done:
    pop dx
    ret
.geometry_error:
    mov al, [fs:S_STATUS]
    pop fs
    mov [fs:S_STATUS], al
    stc
    jmp .done
.geometry:
    cmp byte [fs:S_PRESENT], 1
    je ide_initialize_geometry
    clc
    ret

ata_reset_bus:
    push cx
    push dx
    ata_port ATA_CONTROL
    mov al, 4
    out dx, al
    mov cx, 16
.hold_srst:
    call ata_delay
    loop .hold_srst
    xor al, al
    out dx, al
    mov cx, 5000
.settle:
    call ata_delay
    loop .settle
    pop dx
    pop cx
    ret

ata_transfer:
    cmp byte [fs:S_COUNT], 1
    jbe .single
    cmp byte [fs:S_COMMAND], CMD_READ
    je .multiple
    cmp byte [fs:S_COMMAND], CMD_WRITE
    jne .single
.multiple:
    call ide_negotiate_multiple
    cmp byte [fs:S_MULTIPLE], 2
    jae ide_multiple_transfer
.single:
    push ds
    push es
    push si
    push di
    push bx
    push cx
    push dx
    cld
    mov ax, [fs:S_BUFFER_SEG]
    mov es, ax
    mov bx, [fs:S_BUFFER_OFF]
.sector:
    call ata_select_ready
    jc .error
    call ide_program_address
    ata_port ATA_COUNT
    mov al, 1
    cmp byte [fs:S_COMMAND], CMD_FORMAT
    jne .count_ready
    push ax
    call get_chs_geometry
    mov dl, ah
    pop ax
    mov al, dl
    ata_port ATA_COUNT
.count_ready:
    out dx, al
    ata_port ATA_COMMAND
    mov al, [fs:S_COMMAND]
    out dx, al
    cmp al, CMD_VERIFY
    je .verify
    cmp al, CMD_SEEK
    je .verify
    call ata_wait_drq
    jc .error
    ata_port ATA_DATA
    mov cx, 256
    cmp byte [fs:S_COMMAND], CMD_READ
    je .read
    cmp byte [fs:S_COMMAND], CMD_READ_LONG
    jne .write
.read:
    mov di, bx
    pushf
    cli
    rep insw
    cmp byte [fs:S_COMMAND], CMD_READ_LONG
    jne .read_data_done
    mov cx, 4                 ; OEM A343/A34C: data words, then ECC bytes.
    rep insb
.read_data_done:
    popf
    call ata_delay              ; Allow the device to update BSY/DRQ after data.
%ifdef EMULATOR_TEST
    call ata_test_after_read
%endif
    call ata_wait_complete
    jc .error
    jmp .sector_done
.write:
    push ds
    mov ax, es
    mov ds, ax
    mov si, bx
    pushf
    cli
    rep outsw
    cmp byte [fs:S_COMMAND], CMD_WRITE_LONG
    jne .write_data_done
    mov cx, 4                 ; OEM A318/A325: ECC uses byte-sized port I/O.
    rep outsb
.write_data_done:
    popf
    pop ds
    call ata_wait_complete
    jc .error
    jmp .sector_done
.verify:
    call ata_wait_complete
    jc .error
.sector_done:
    add bx, [fs:S_BLOCK_SIZE]
    inc dword [fs:S_LBA]
    inc byte [fs:S_DONE]
    mov al, [fs:S_DONE]
    cmp al, [fs:S_COUNT]
    jb .sector
    clc
    jmp .finish
.error:
    stc
.finish:
    pop dx
    pop cx
    pop bx
    pop di
    pop si
    pop es
    pop ds
    ret

ata_wait_ready:
    mov ecx, 0x00100000
    ata_port ATA_STATUS
.loop:
    call ata_read_status
    test al, 0x80
    jnz .next
    test al, 0x40
    jnz .ok
.next:
    dec ecx
    jnz .loop
    mov byte [fs:S_STATUS], ERR_TIMEOUT
    stc
    ret
.ok:
    clc
    ret

ata_wait_complete:
    mov ecx, 0x00100000
    ata_port ATA_STATUS
.loop:
    call ata_read_status
    test al, 0x80
    jnz .next
    test al, 0x21
    jnz .controller
    clc
    ret
.next:
    dec ecx
    jnz .loop
    mov byte [fs:S_STATUS], ERR_TIMEOUT
    stc
    ret
.controller:
    mov byte [fs:S_STATUS], ERR_CONTROLLER
    stc
    ret

ata_wait_drq:
    mov ecx, 0x00100000
    ata_port ATA_STATUS
.loop:
    call ata_read_status
    test al, 0x80
    jnz .next
    test al, 0x21
    jnz .controller
    test al, 0x08
    jnz .ok
.next:
    dec ecx
    jnz .loop
    mov byte [fs:S_STATUS], ERR_TIMEOUT
    stc
    ret
.controller:
    mov byte [fs:S_STATUS], ERR_CONTROLLER
    stc
    ret
.ok:
    clc
    ret

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

halt_forever:
    cli
    xor dx, dx
    mov ds, dx
    call load_bios_state
    mov byte [0x0400 + KB_POST_STATE], 2
%ifdef EMULATOR_TEST
%ifndef EMULATOR_BOOT_POLICY_TEST
    call verify_terminal_diagnostic
    jnc .diagnostic_ok
    mov al, 0x77
    call emulator_exit
.diagnostic_ok:
    push ax
    xor ax, ax
    mov es, ax
    mov word [es:0x046C], 0
    mov word [es:0x046E], 0
%endif
%endif
.halt:
    call post_keyboard_wait
.idle:
    sti
    hlt
    cli
%ifdef EMULATOR_TEST
%ifndef EMULATOR_BOOT_POLICY_TEST
%ifndef EMULATOR_PORTS_TEST
    cmp word [es:0x046C], 0
    jne .timer_woke_halt
    mov al, 0x78
    call emulator_exit
.timer_woke_halt:
    pop ax
    call emulator_exit
%endif
%endif
%endif
    jmp .halt

hard_halt:
    cli
.halt:
    hlt
    jmp .halt

%ifdef EMULATOR_TEST
verify_terminal_diagnostic:
    push ax
    push cx
    push dx
    push si
    push di
    push es
    mov dl, al
    cmp dl, 0x63
    jne .boot_error
    mov si, msg_no_disk
    jmp .scan
.boot_error:
    mov si, msg_boot_error
.scan:
    mov ax, 0xB800
    mov es, ax
    xor di, di
    mov cx, 2000
.next_cell:
    push cx
    push si
    push di
.compare:
    cs lodsb
    cmp al, 32
    jb .found
    cmp al, [es:di]
    jne .not_here
    add di, 2
    jmp .compare
.not_here:
    pop di
    pop si
    pop cx
    add di, 2
    loop .next_cell
    stc
    jmp .done
.found:
    add sp, 6
    clc
.done:
    pop es
    pop di
    pop si
    pop dx
    pop cx
    pop ax
    ret

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
%include "firmware/post.inc"
%include "hardware/chipset-core.inc"
%include "firmware/apm.inc"
%include "firmware/cdboot.inc"
%ifdef EMULATOR_PORTS_TEST
%include BOARD_PORTS_TEST
%endif
%ifdef EMULATOR_CHIPSET_TEST
%include BOARD_CHIPSET_TEST
%endif
%ifdef EMULATOR_SETUP_TEST
%ifndef BOARD_ROM_COMPAT_SOURCE
%include "../tests/firmware/setup-test.inc"
%endif
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
rom_code_end:
%ifdef BOARD_ROM_COMPAT_SOURCE
%include BOARD_ROM_COMPAT_SOURCE
; Keep emulator-only Setup observers out of the fixed VGA entry's address range.
%ifdef EMULATOR_SETUP_TEST
%include "../tests/firmware/setup-test.inc"
%endif
%endif
times CFG_ROM_CHECKSUM_OFFSET-0x10000-($-$$) db 0xFF
checksum_byte: db 0
reset_vector:
    jmp CFG_ROM_CODE_SEGMENT:startup
bios_date db BIOS_DATE_PREFIX,BIOS_DATE_YEAR
    db 0,CFG_ROM_MODEL_BYTE,0
