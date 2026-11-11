bits 16
%define BOARD_PNP_SETUP_LATE 1
%define BOARD_PNP_NAVIGATION_LATE 1
%define BOARD_PNP_NV6_LATE 1
org 0

%define BIOS_VERSION '0.10.2'
%define BIOS_RELEASE_DATE '10/31/2026'
%substr BIOS_DATE_PREFIX BIOS_RELEASE_DATE 1,6
%substr BIOS_DATE_YEAR BIOS_RELEASE_DATE 9,2

%ifndef BOARD_DEFINITION
%define BOARD_DEFINITION "boards/presario800.inc"
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

%include "shared-owner.inc"
presario_shared "setup/ui-text-pairs.inc"
presario_shared "setup/ui-text.inc"
presario_shared "firmware/cache-lifecycle.inc"
presario_shared "pc/cache-test.inc"

presario_shared "pc/processor.inc"
presario_shared "pc/state.inc"
presario_shared "pc/ram-test-state.inc"

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

startup:
    cli
    post_code_early 0x10
    cld
    jmp 0xF000:.normalized
.normalized:
    xor ax, ax
    mov ds, ax
    mov es, ax

    ; OEM CCA2-CCB4/CD01-CD16: a CPU-only reset can be a service return,
    ; not a boot. Consume CMOS shutdown before touching RAM/chipset/stack.
    ; The 8042 SYS bit excludes stale battery-backed requests on power-on.
    ; Keep EDX intact: NSSI's reset-based CPU identification needs it.
    in al, KBC_STATUS
    mov bh, al
    mov al, 0x8F
    out 0x70, al
    in al, 0x84
    in al, 0x71
    mov bl, al
    xor al, al
    out 0x71, al
    test bh, 0x04
    jz .normal_reset
    cmp bl, 0x05
    je .resume_eoi
    cmp bl, 0x0A
    jne .normal_reset
    jmp .resume
.resume_eoi:
    mov al, 0x20
    out 0x20, al
.resume:
    ; OEM CC52 clears reset-default CD/NW before any shutdown continuation.
    ; CPU identification resets must not leave the caller's L1 disabled.
    mov eax, cr0
    and eax, 0x9FFFFFFF
    mov cr0, eax
    mov ax, 0x0040
    mov ds, ax
    jmp far [0x0067]
.normal_reset:
    movzx ebp, dx             ; Carry signature above the 16-bit warm marker.
    shl ebp, 16
    xor ax, ax

    ; The chipset must be usable before the first stack access.
    out CHIPSET_CONFIG_ON, al
    ; Write back both cache levels before discarding the old RAM map.
    wbinvd
    mov al, EXTERNAL_CACHE_REG
    out CHIPSET_INDEX, al
    xor al, al
    out CHIPSET_DATA, al
    ; CPU-only reset retains shadow RAM. Fetch from ROM before changing any
    ; bank map, as the software warm path does. Shutdown resumes bypass this.
    mov al, SYSTEM_SHADOW_REG
    out CHIPSET_INDEX, al
    xor al, al
    out CHIPSET_DATA, al
    wbinvd
    ; Read the warm marker while a retained interleave map still owns it.
    xor bp, bp
    test bh, 0x04
    jz .cold_classified
    cmp word [0x0472], 0x1234
    jne .cold_classified
    inc bp
.cold_classified:
    ; Mask retained DMA before either mapping transition on normal reset.
    xor al, al
    out DMA1_MASTER_CLEAR, al
    out DMA2_MASTER_CLEAR, al
    mov dx, CHIPSET_INDEX
    mov al, RAMTMG_REG
    out dx, al
    inc dx
    mov al, RAMTMG_VALUE
    out dx, al
    dec dx
    ; Remove interleave before changing any bank geometry.
    mov al, RAMSET_REG
    out dx, al
    inc dx
    mov al, RAMSET_VALUE
    out dx, al
    dec dx
    mov al, RAMCFG0_REG
    out dx, al
    inc dx
    mov al, RAMCFG0_VALUE
    out dx, al
    dec dx
    mov al, RAMCFG1_REG
    out dx, al
    inc dx
    mov al, RAMCFG1_VALUE
    out dx, al
    dec dx
    mov al, NTBREF_REG
    out dx, al
    inc dx
    mov al, NTBREF_VALUE
    out dx, al
    dec dx
    mov al, ROMSET_REG
    out dx, al
    inc dx
    mov al, ROMSET_VALUE
    out dx, al
    out CHIPSET_CONFIG_OFF, al

    post_code_early 0x20

    ; Test RAM without a call, push, or RAM-backed stack.
    mov di, 0x0600
    mov cx, 128
    mov ax, 0x55AA
.ram_write_a:
    stosw
    not ax
    loop .ram_write_a
    mov di, 0x0600
    mov cx, 128
    mov ax, 0x55AA
.ram_check_a:
    scasw
    jne .ram_failed
    not ax
    loop .ram_check_a
    xor si, si                   ; Reset-vector entry must detect RAM again.
    jmp .classify_reset

.controlled_restart:
    cli
    cld
    wbinvd
    mov eax, cr0
    or eax, 0x60000000
    mov cr0, eax
    wbinvd
    out CHIPSET_CONFIG_ON, al
    mov al, EXTERNAL_CACHE_REG
    out CHIPSET_INDEX, al
    xor al, al
    out CHIPSET_DATA, al
    mov al, MISCSET_REG
    out CHIPSET_INDEX, al
    in al, CHIPSET_DATA
    and al, ~PRIMARY_CACHE_EN
    out CHIPSET_DATA, al
    ; Fetch ROM and remove all retained shadow mappings before remapping RAM.
    mov al, SYSTEM_SHADOW_REG
    out CHIPSET_INDEX, al
    xor al, al
    out CHIPSET_DATA, al
    wbinvd
    mov bl, VGA_SHADOW_REG
.clear_shadow:
    mov al, bl
    out CHIPSET_INDEX, al
    xor al, al
    out CHIPSET_DATA, al
    inc bl
    cmp bl, SYSTEM_SHADOW_REG
    jb .clear_shadow
    out DMA1_MASTER_CLEAR, al
    out DMA2_MASTER_CLEAR, al
    mov al, RAMTMG_REG
    out CHIPSET_INDEX, al
    mov al, RAMTMG_VALUE
    out CHIPSET_DATA, al
    mov al, NTBREF_REG
    out CHIPSET_INDEX, al
    in al, CHIPSET_DATA
    and al, 0x10              ; TURBO is read-only.
    out CHIPSET_DATA, al
    mov al, CLKCTL_REG
    out CHIPSET_INDEX, al
    mov al, CLKCTL_VALUE
    out CHIPSET_DATA, al
    mov al, ROMSET_REG
    out CHIPSET_INDEX, al
    mov al, ROMSET_VALUE
    out CHIPSET_DATA, al
    mov al, 0x24
    out CHIPSET_INDEX, al
    in al, CHIPSET_DATA
    mov ah, al
    mov al, 0xB7
    out 0x70, al
    mov cx, 0xFFFF
.strap_settle:
    loop .strap_settle
    in al, 0x71
    and al, 0x40
    and ah, ~0x4C
    or al, ah
    or al, 0x08
    out CHIPSET_DATA, al
    mov al, RAMSET_REG
    out CHIPSET_INDEX, al
    mov al, RAMSET_VALUE       ; Sequential map; retain detected bank geometry.
    out CHIPSET_DATA, al
    out CHIPSET_CONFIG_OFF, al
    xor ax, ax
    mov ds, ax
    mov es, ax
    xor bp, bp                ; Never read the old BDA after the map change.
    mov si, 2                 ; Retained geometry, current controlled retry.
    jmp .classify_reset

.warm_start:
    ; OEM E05B -> 92BC -> 003E is a warm re-entry, not a CPU reset.
    ; The caller released the keyboard and removed ROM shadows. RAM setup
    ; is retained; discard the old interrupt frame when the stack is rebuilt.
    cli
    cld
    post_code_early 0x94
    xor ax, ax
    mov ds, ax
    mov es, ax
%ifdef EMULATOR_WARM_RESET_TEST
    ; Observe reset-entry flushing before POST clears the BDA/controller.
    mov ax, [0x041A]
    cmp ax, [0x041C]
    jne .flush_failed
    in al, KBC_STATUS
    test al, 1
    jz .flush_verified
.flush_failed:
    mov al, 0x6F
    call emulator_exit
    jmp hard_halt
.flush_verified:
%endif
    mov ax, [0x040E]
    mov es, ax
    movzx ebp, word [es:S_CPU_SIGNATURE]
    shl ebp, 16
    xor ax, ax
    mov es, ax
    mov si, 1                    ; Only software warm entry retains RAM setup.
.classify_reset:
    ; A warm entry can retain enabled parity checking before the IVT exists.
    in al, 0x61
    or al, 0x0C
    out 0x61, al
    ; Keep POST and shadow setup uncached on both cold and software-warm
    ; entry. Flush before disabling so a warm caller's dirty data survives.
    wbinvd
    mov eax, cr0
    or eax, 0x60000000
    mov cr0, eax
    wbinvd

    ; OEM 0204 -> 860A also disables the chipset's primary-cache control
    ; before RAM/shadow setup. CR0 alone leaves warm-boot CEN set.
    out CHIPSET_CONFIG_ON, al
    mov al, MISCSET_REG
    out CHIPSET_INDEX, al
    in al, CHIPSET_DATA
    and al, ~PRIMARY_CACHE_EN
    out CHIPSET_DATA, al
    mov al, EXTERNAL_CACHE_REG
    out CHIPSET_INDEX, al
    xor al, al
    out CHIPSET_DATA, al
    ; Retained ISA windows must not intercept RAM discovery or POST scratch.
    mov al, 0x21
    out CHIPSET_INDEX, al
    xor al, al
    out CHIPSET_DATA, al
    mov al, 0x23
    out CHIPSET_INDEX, al
    xor al, al
    out CHIPSET_DATA, al
    out CHIPSET_CONFIG_OFF, al

    ; CPU-reset entry captured this before removing retained interleave.
    ; Software warm entry still uses the retained map here.
    cmp si, 1
    jne .warm_marker_captured
    xor bp, bp
    in al, KBC_STATUS
    test al, 0x04
    jz .warm_marker_captured
    cmp word [0x0472], 0x1234
    jne .warm_marker_captured
    inc bp
.warm_marker_captured:
    test bp, bp
    jz .reset_classified
    post_code_early 0x11
.reset_classified:
%ifdef EMULATOR_WARM_RESET_TEST
    ; Seed visible output so omission of the production blank is observable.
    ; Select the color status port in the opaque VGA test fixture first.
    mov dx, 0x03CC
    in al, dx
    or al, 1
    mov dx, 0x03C2
    out dx, al
    mov dx, 0x03DA
    in al, dx
    mov dx, 0x03C0
    mov al, 0x20
    out dx, al
    in al, dx
    test al, 0x20
    jnz .blank_seeded
    or bp, 0x8000
.blank_seeded:
%endif
    ; OEM F000:0179-0192 blanks video before the long POST operations.
    ; Reset both attribute flip-flops, then clear Palette Address Source.
    mov al, 1
    mov dx, 0x03B8
    out dx, al
    mov dx, 0x03D8
    out dx, al
    mov dx, 0x03BA
    in al, dx
    mov dx, 0x03DA
    in al, dx
    mov dx, 0x03C0
    xor al, al
    out dx, al
    post_code_early 0x30
    mov di, 0x0600
    mov cx, 128
    xor ax, ax
    rep stosw

    mov ss, ax
    mov sp, 0x7000
%ifdef EMULATOR_WARM_RESET_TEST
    ; Observe the production blank before IVT clearing or shadow work.
    test bp, 0x8000
    jz .blank_seed_passed
    mov al, 0x5C
    call emulator_exit
    jmp hard_halt
.blank_seed_passed:
    mov dx, 0x03C0
    in al, dx
    test al, 0x20
    jz .blank_test_passed
.blank_test_failed:
    mov al, 0x5A
    call emulator_exit
    jmp hard_halt
.blank_test_passed:
    ; Both cold and software-warm POST must disable caching before shadows.
    mov eax, cr0
    and eax, 0x60000000
    cmp eax, 0x60000000
    je .post_cache_disabled
    mov al, 0x6E
    call emulator_exit
    jmp hard_halt
.post_cache_disabled:
    out CHIPSET_CONFIG_ON, al
    mov al, MISCSET_REG
    out CHIPSET_INDEX, al
    in al, CHIPSET_DATA
    test al, PRIMARY_CACHE_EN
    jnz .post_cache_failed
    out CHIPSET_CONFIG_OFF, al
    xor ax, ax
    jmp .post_cache_verified
.post_cache_failed:
    mov al, 0x6E
    call emulator_exit
    jmp hard_halt
.post_cache_verified:
%endif

    cache_phase early
    call init_memory
    mov ax, STATE_SEG
    mov es, ax
    mov dx, [es:S_EXTENDED_KIB]
    call chipset_memory_prepare
    call memory_interleave_options
    call chipset_interleave_policy
    ; The helper frame has returned. Change the map from ROM, then rebuild
    ; low RAM without reading any old stack, workspace, or EBDA byte.
    out CHIPSET_CONFIG_ON, al
    mov al, RAMSET_REG
    out CHIPSET_INDEX, al
    mov al, cl
    out CHIPSET_DATA, al
    out CHIPSET_CONFIG_OFF, al
    shr al, 5
    add al, 0x18               ; Mode 0..6: POST 18h..1Eh.
    out POST_PORT, al
.memory_map_ready:
    ; Check only firmware-owned RAM before building state; the bulk RAM
    ; test runs with visible progress after retained VGA initialization.
    ; No active frame survives this destructive pass.
    jmp chipset_ram_test
.ram_test_done:
    ; Clear the IVT, BDA, boot workspace, and identify buffer.
    xor ax, ax
    mov es, ax
    mov di, 0
    mov cx, 0x0500 / 2
    rep stosw
    mov di, STATE_BASE
    mov cx, (0x0A00 - STATE_BASE) / 2
    rep stosw

    ; Reserve the final conventional-memory KiB as an EBDA for BIOS state.
    mov ax, STATE_SEG
    mov es, ax
    xor di, di
    xor ax, ax
    mov cx, 1024 / 2
    rep stosw
    mov byte [es:0], 1
    mov [es:S_EXTENDED_KIB], dx
    mov [es:S_INSTALLED_KIB], dx
    mov eax, ebp
    shr eax, 16
    mov [es:S_CPU_SIGNATURE], ax
    mov ax, bp
    mov [es:S_WARM_BOOT], al
%ifdef EMULATOR_WARM_RESET_TEST
    sidt [0x0600]              ; Capture after the early RAM owner's scratch use.
    mov bx, [0x0600]
    mov [es:S_RESET_IDT_LIMIT], bx
%endif
    xor ax, ax
    mov es, ax

    call shadow_system_bios
    ; Relocate the embedded lower ROM as the working MR BIOS does.
    xor ax, ax
    out CHIPSET_CONFIG_ON, al
    mov dx, CHIPSET_INDEX
    mov al, ROMSET_REG
    out dx, al
    inc dx
    mov al, VGA_ROMSET_VALUE
    out dx, al
    wbinvd
    dec dx

    ; Follow the OEM 32 KiB VGA shadow sequence exactly.
    mov al, VGA_SHADOW_REG
    out dx, al
    inc dx
    mov al, VGA_SHADOW_CLEAR
    out dx, al
    wbinvd
    push ds
    push es
    mov ax, VGA_SEGMENT
    mov es, ax
    xor di, di
    xor ax, ax
    mov cx, VGA_ROM_WORDS
    rep stosw

    mov dx, CHIPSET_INDEX
    mov al, VGA_SHADOW_REG
    out dx, al
    inc dx
    mov al, VGA_SHADOW_FILL
    out dx, al
    wbinvd
    mov ax, VGA_SEGMENT
    mov ds, ax
    call validate_vga_image
    jc .vga_mapping_failed
    xor si, si
    xor di, di
    mov cx, VGA_ROM_WORDS
    rep movsw
    mov dx, CHIPSET_INDEX
    mov al, VGA_SHADOW_REG
    out dx, al
    inc dx
    mov al, VGA_SHADOW_RUN
    out dx, al
    wbinvd
    call validate_vga_image
    jc .vga_shadow_failed
    out CHIPSET_CONFIG_OFF, al
    pop es
    pop ds

    post_code 0x40

    ; Start with harmless handlers, then install the services we own.
    mov di, 0
    mov cx, 256
    mov ax, default_iret
    mov dx, 0xF000
.vector_loop:
    stosw
    mov [es:di], dx
    add di, 2
    loop .vector_loop
    set_vector 0x08, int08
    set_vector 0x02, chipset_nmi
    set_vector 0x09, int09
    set_vector 0x0E, int0e
    set_vector 0x10, default_iret
    set_vector 0x11, int11
    set_vector 0x12, int12
    set_vector 0x13, int13
    set_vector 0x15, int15
    set_vector 0x16, int16
    set_vector 0x18, int18
    set_vector 0x19, int19
    set_vector 0x1A, int1a
    set_vector 0x1E, floppy_dpt_1440
    set_vector 0x70, int70
    set_vector 0x74, int74
    set_vector 0x75, int75
    set_vector 0x76, int76
    mov word [es:0x0108], VGA_INT10_ENTRY + 1
    mov word [es:0x010A], VGA_SEGMENT

    ; Minimal BIOS Data Area required by the retained VGA firmware.
    mov word [0x0410], 0x0020
    mov word [0x040E], STATE_SEG
    mov word [0x0413], 639
    mov byte [0x0449], 3
    mov word [0x044A], 80
    mov word [0x044C], 0x1000
    mov word [0x0463], 0x03D4
    mov byte [0x0484], 24
    mov word [0x0485], 16
    mov word [0x041A], KB_BUFFER_START
    mov word [0x041C], KB_BUFFER_START
    mov word [0x0480], KB_BUFFER_START
    mov word [0x0482], KB_BUFFER_END
    mov byte [0x0400 + KB_EXT_FLAGS], 0x10 ; MF-II keyboard services.

    call publish_memory_cmos

    call init_pic_pit
    call init_rtc
    call init_superio
    call init_at_prerequisites
    post_code 0x50
    call pnp_early

    ; This retained component owns the Cirrus video initialization and INT 10h.
    mov ax,0xFFFF
    mov dx,VGA_SEGMENT
    mov cl,2
    call pnp_rom_enter
    xor ax, ax
    mov es, ax
    ; Keep the public entry installed by the VGA ROM (including its STI).
    cmp word [es:0x0042], VGA_SEGMENT
    jne video_failed

    post_code 0x60

    mov ax, 0x0003
    int 0x10

%ifdef VGA_BIOS_141
    ; Cirrus monitor policy: retain the default resolutions and use
    ; non-interlaced 60 Hz for 1024x768 instead of the ROM's 87 Hz default.
    pushad
    push ds
    push es
    mov ax, 0x1203
    mov bx, 0x10A4
    xor cx, cx
    xor dx, dx
    int 0x10
    pop es
    pop ds
    popad
%endif

    ; Video is available for failure diagnostics, not a keyboard prerequisite.
    call post_ui_begin
    mov al,1
    call post_status
    call init_keyboard
    post_code 0x48
    call arm_keyboard_runtime
    jc keyboard_runtime_failed
    mov byte [0x0400 + KB_POST_STATE], 1
    sti
    ; Do not display interactive POST while initialization discards scans.
    call load_bios_state
    mov byte [fs:P_PHASE], 0
    mov byte [fs:P_ROM_COUNT], 0 ; Add-in ROMs only; VGA has its own line.
    call post_ui_begin
%ifdef EMULATOR_SETUP_INVALID_NOTICE
    call setup_test_alert_begin
%endif
%ifdef EMULATOR_SETUP_POWERLOSS
    xor ax, ax
    mov fs, ax                ; POST notice must resolve its own state segment.
%endif
.post_settings:
    call settings_load
    call post_numlock_apply
    call post_keyboard_presence
%ifdef EMULATOR_BOOT_SETTINGS_RECOVERY
    call boot_settings_alert_begin
%endif
    call chipset_apply
    call publish_memory_cmos
    call chipset_post_recovery_notice
    mov byte [fs:P_PHASE], 1
    call post_ui_cache
    call post_early_setup
    mov al,2
    call post_status
    call chipset_visible_ram_test
    mov byte [fs:P_PHASE], 2
    call post_early_setup
    call post_clock_alert
%ifdef EMULATOR_SETUP_POWERLOSS
    call load_bios_state
    call setup_test_begin     ; Notice Delete enters Setup at the next early gate.
%endif
    call post_early_setup
    call load_bios_state
    mov al,3
    call post_status
    cache_phase after_ram
    mov al,4
    call post_status
    call init_peripherals
    mov al,5
    call post_status
    call pnp_configure_isa
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
    call init_mouse
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
    call post_success_tone
    mov byte [fs:P_PHASE], 5
    call post_ui_cache
    call post_ui_roms
    mov al,8
    call post_status
    call option_rom_discovery
%ifdef EMULATOR_CHIPSET_POST_UI
    call post_ui_capture
%endif
    call pnp_publish_finish
    call presario_post_complete
%ifdef EMULATOR_SETUP_TEST
    call setup_test_end
%endif
%ifdef EMULATOR_BOOT_POLICY_TEST
    call boot_policy_ready
%endif
    mov byte [0x0400 + KB_POST_STATE], 0
    sti
    int 0x19

.vga_mapping_failed:
    pop es
    pop ds
    mov dx, POST_PORT
    mov al, 0xE5
    out dx, al
    jmp hard_halt

.vga_shadow_failed:
    pop es
    pop ds
    mov dx, POST_PORT
    mov al, 0xE6
    out dx, al
    jmp hard_halt

.ram_failed:
    mov dx, POST_PORT
    mov al, 0xE1
    out dx, al
    jmp hard_halt

; OEM F000:8516/8574-8589: select fast clock and clear non-turbo waits.
; OEM 8659 cacheability table, 85CE primary enable, and CC52/86A1 CR0 setup.
; Probe the optional OEM 128 KiB cache card before enabling the CPU cache.
enable_cpu_full_speed:
    push eax
    push cx
    out CHIPSET_CONFIG_ON, al
    out FAST_CPU_PORT, al
    mov al, NTBREF_REG
    out CHIPSET_INDEX, al
    in al, CHIPSET_DATA
    and al, 0x1F                ; Preserve refresh controls and read-only TURBO.
    out CHIPSET_DATA, al

    mov cl, CACHE_REGION_FIRST
.device_regions:
    mov al, cl
    out CHIPSET_INDEX, al
    mov al, 0x55                ; A0000-EFFFF must not cache VGA/device accesses.
    out CHIPSET_DATA, al
    inc cl
    cmp cl, CACHE_REGION_ROM
    jb .device_regions
    mov al, CACHE_REGION_ROM
    out CHIPSET_INDEX, al
    mov al, 0xAA                ; OEM cacheable, write-protected system shadow.
    out CHIPSET_DATA, al
    out CHIPSET_CONFIG_OFF, al
    call init_external_cache
    out CHIPSET_CONFIG_ON, al
    mov al, MISCSET_REG
    out CHIPSET_INDEX, al
    in al, CHIPSET_DATA
    or al, PRIMARY_CACHE_EN
    out CHIPSET_DATA, al
    out CHIPSET_CONFIG_OFF, al
    wbinvd
    mov eax, cr0
    and eax, 0x9FFFFFFF         ; Clear CD/NW, preserving the other CPU controls.
    mov cr0, eax
    pop cx
    pop eax
    ret

; OEM F000:88AA-8C69: direct SRAM test, then normal-mode fill/eviction.
; OEM bank detection, extended with a capacity alias test for32KiB..1MiB cards.
; No stack access while direct mode redirects RAM. Failure leaves L2 disabled.
; Returns ZF=passed; otherwise CF=SRAM failure, CF clear=no presence response.
init_external_cache:
    pushad
    push ds
    push es
    sub sp, 6
    mov di, sp
    sgdt [ss:di]
    in al, 0x92
    push ax
    and al, 0xFE
    or al, 2
    out 0x92, al
    mov al, 0x80
    out 0x70, al
    mov ebp, cr0
    wbinvd
    out CHIPSET_CONFIG_ON, al
    ; Detect SRAM at the tested OEM timings, independent of user tuning.
    ; Save controls before direct mode redirects RAM; restore only after it ends.
    mov al, RAMTMG_REG
    out CHIPSET_INDEX, al
    in al, CHIPSET_DATA
    mov ah, al
    mov al, RAMTMG_REG
    push ax
    mov al, CACHE_PROBE_RAMTMG
    out CHIPSET_DATA, al
    mov al, MISCSET_REG
    out CHIPSET_INDEX, al
    in al, CHIPSET_DATA
    mov ah, al
    mov al, MISCSET_REG
    push ax
    mov al, ah
    and al, 0x40               ; Preserve the read-only tag input.
    ; Direct SRAM must be read on the bus, without P24T L1 line fills.
    ; WBINVD below clears old L1 lines; CEN stays off until normal L2 mode.
    or al, EXTERNAL_SEGMENT_EN
    out CHIPSET_DATA, al
    mov al, 0x24
    out CHIPSET_INDEX, al
    in al, CHIPSET_DATA
    mov ah, al
    mov al, 0x24
    push ax
    mov al, ah
    and al, ~0x08              ; OEM direct probe has no added cache-read wait.
    out CHIPSET_DATA, al
    mov al, CACHE_REGION_ROM
    out CHIPSET_INDEX, al
    mov al, 0x55                ; Fetch ROM/shadow, never direct SRAM.
    out CHIPSET_DATA, al
    wbinvd                     ; Drain saved control words before direct-mode INVD.
    mov eax, ebp
    and eax, 0x9FFFFFFF
    mov cr0, eax                ; CEN is off: direct scratch cannot enter L1.
    mov al, EXTERNAL_CACHE_REG
    out CHIPSET_INDEX, al
    mov al, EXTERNAL_CACHE_DIRECT
    out CHIPSET_DATA, al
    post_code_early 0x12         ; Direct SRAM presence check.
.presence:
    ; Use free POST scratch instead of overwriting live IVT entries 0..3.
    mov ax, 0x1000
    mov es, ax
    mov dword [es:0], 0xAA55AA55
    mov dword [es:4], 0x55AA55AA
    mov dword [es:8], 0xFF00FF00
    mov dword [es:12], 0x00FF00FF
    invd                       ; Presence reads must reach SRAM, not an L1 copy.
    cmp dword [es:0], 0xAA55AA55
    jne .absent
    cmp dword [es:4], 0x55AA55AA
    jne .single_bank
    cmp dword [es:8], 0xFF00FF00
    jne .absent
    cmp dword [es:12], 0x00FF00FF
    jne .absent
    jmp .banks_ready
.single_bank:
    ; OEM8996/8A09: bank A must respond before falling back from bank B.
    cmp dword [es:8], 0xFF00FF00
    jne .absent
    mov al, EXTERNAL_CACHE_REG
    out CHIPSET_INDEX, al
    in al, CHIPSET_DATA
    test al, 0x80
    jz .absent                  ; A failed single-bank response is not a fallback.
    and al, 0x7F
    out CHIPSET_DATA, al
    jmp .presence
.banks_ready:
    post_code_early 0x13         ; SRAM capacity/independence/data test.
    lgdt [cs:move_gdtr]
    mov eax, cr0
    or al, 1
    mov cr0, eax
    jmp 0x08:.protected
.protected:
    mov ax, 0x10
    mov ds, ax
    mov es, ax
    mov al, EXTERNAL_CACHE_REG
    out CHIPSET_INDEX, al
    in al, CHIPSET_DATA
    and al, 0xB0               ; Preserve bank/tag/valid controls, not direct mode.
    movzx esi, al
    mov ebx, 0x8000
    mov ecx, 1                 ; CSIZE1..6:32KiB..1MiB.
.capacity:
    a32 mov dword [0x100000], 0xAA55AA55
    mov dword [ebx+0x100000], 0x55AA55AA
    invd
    a32 cmp dword [0x100000], 0xAA55AA55
    je .larger
    a32 cmp dword [0x100000], 0x55AA55AA
    jne .bad_sram
    cmp dword [ebx+0x100000], 0x55AA55AA
    jne .bad_sram
    or esi, ecx
    add ebx, 0x100000          ; Exclusive end of detected SRAM capacity.
    jmp .data_test
.larger:
    cmp dword [ebx+0x100000], 0x55AA55AA
    jne .bad_sram
    shl ebx, 1
    inc ecx
    cmp ecx, 7
    jb .capacity
    jmp .bad_sram              ; No alias within1MiB: do not invent a size.
.data_test:
    cache_address_patterns .bad_sram,0x100000,ebx,invd
.data_done:
    mov al, EXTERNAL_CACHE_REG
    out CHIPSET_INDEX, al
    mov eax, esi
    out CHIPSET_DATA, al
    mov al, MISCSET_REG
    out CHIPSET_INDEX, al
    in al, CHIPSET_DATA
    or al, PRIMARY_CACHE_EN
    out CHIPSET_DATA, al
    ; OEM 8C03-8C42 seeds one cache capacity and reads two capacities to
    ; replace the initial tags and drain dirty lines. Scratch is free at POST.
    mov edi, 0x100000
    mov eax, 0x5A5A5A5A
    mov ecx, ebx
    sub ecx, 0x100000
    shr ecx, 2                 ; One detected capacity in dwords.
    a32 rep stosd
    invd                       ; Only disposable scratch was cached so far.
    mov edi, 0x100000
    mov ecx, ebx
    sub ecx, 0x100000
    shr ecx, 1                 ; Twice the detected capacity in dwords.
.fill_tags:
    mov eax, [edi]
    add edi, 4
    a32 loop .fill_tags
    wbinvd
    post_code_early 0x15         ; L2 initialized in normal cache mode.
    mov esi, 0x15
    jmp .leave_protected
.bad_sram:
    mov esi, 0x14
    post_code_early 0x14         ; SRAM test failed; disable L2.
    mov al, EXTERNAL_CACHE_REG
    out CHIPSET_INDEX, al
    xor al, al
    out CHIPSET_DATA, al
.leave_protected:
    mov ax, 0x18
    mov ds, ax
    mov es, ax
    mov eax, cr0
    and al, 0xFE
    mov cr0, eax
    jmp 0xF000:.real
.absent:
    mov esi, 0x16
    post_code_early 0x16         ; Card absent/unresponsive; disable L2.
    mov al, EXTERNAL_CACHE_REG
    out CHIPSET_INDEX, al
    xor al, al
    out CHIPSET_DATA, al
.real:
    wbinvd
    mov eax, ebp
    mov cr0, eax
    pop ax                     ; Restore XCTL, cache phasing and RAM timing.
    out CHIPSET_INDEX, al
    mov al, ah
    out CHIPSET_DATA, al
    pop ax
    out CHIPSET_INDEX, al
    mov al, ah
    and al, ~PRIMARY_CACHE_EN
    or al, EXTERNAL_SEGMENT_EN
    out CHIPSET_DATA, al
    pop ax
    out CHIPSET_INDEX, al
    mov al, ah
    out CHIPSET_DATA, al
    mov al, CACHE_REGION_ROM
    out CHIPSET_INDEX, al
    mov al, 0xAA
    out CHIPSET_DATA, al
    out CHIPSET_CONFIG_OFF, al
    pop ax
    and al, 0xFE
    out 0x92, al
    mov di, sp
    o32 lgdt [ss:di]
    add sp, 6
    pop es
    pop ds
    cmp esi, 0x15               ; POPAD restores registers without changing result flags.
    popad
    ret

; OEM 3972-3998 detects the x87, publishes equipment bit 1, and unmasks
; IRQ13/cascade. Normalize inherited warm-boot controls for our legacy
; IRQ13 contract: no EM/TS traps or native #MF, without changing cache state.
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
    mov dx, POST_PORT
    mov al, 0xE2
    out dx, al
    jmp hard_halt

; OEM F000:8753-87B1: stage the complete F000 ROM at 1000:0000,
; execute there while enabling shadow RAM, copy and compare, then protect.
; The temporary 64 KiB is conventional RAM and is free again on return.
; Late comparison failures discard the old RAM frame. Early failures jump
; directly to startup.controlled_restart with the register-held identity.
controlled_defaults_restart:
    ; Late RAM failures still have a valid identity in the retained EBDA.
    xor ax, ax
    mov ds, ax
    mov ax, [0x040E]
    mov es, ax
    movzx ebp, word [es:S_CPU_SIGNATURE]
    shl ebp, 16
    jmp 0xF000:startup.controlled_restart

shadow_system_bios:
    push ds
    push es
    post_code 0x28
    out CHIPSET_CONFIG_ON, al
    mov ax, 0xF000
    mov ds, ax
    xor si, si
    mov ax, 0x1000
    mov es, ax
    xor di, di
    mov cx, 0x8000
    rep movsw
    jmp 0x1000:.staged
.staged:
%ifdef EMULATOR_WARM_RESET_TEST
    mov ax, cs
    cmp ax, 0x1000
    jne .test_failed
%endif
    mov al, SYSTEM_SHADOW_REG
    out CHIPSET_INDEX, al
    mov al, 0xFF
    out CHIPSET_DATA, al
    wbinvd
    mov ax, 0x1000
    mov ds, ax
    xor si, si
    mov ax, 0xF000
    mov es, ax
    xor di, di
    mov cx, 0x8000
    rep movsw
    xor si, si
    xor di, di
    mov cx, 0x8000
    repe cmpsw
    jne .failed
%ifdef EMULATOR_WARM_RESET_TEST
    ; Complete 64 KiB comparison must exhaust CX and wrap both offsets.
    test cx, cx
    jnz .test_failed
    test si, si
    jnz .test_failed
    test di, di
    jnz .test_failed
%endif
    mov al, SYSTEM_SHADOW_REG
    out CHIPSET_INDEX, al
    mov al, 0xAA
    out CHIPSET_DATA, al
    wbinvd
    jmp 0xF000:.shadowed
.shadowed:
%ifdef EMULATOR_WARM_RESET_TEST
    mov ax, cs
    cmp ax, 0xF000
    jne .test_failed
    mov bx, [cs:startup]
    mov ax, bx
    not ax
    mov [cs:startup], ax
    cmp [cs:startup], bx
    jne .test_failed
%endif
    out CHIPSET_CONFIG_OFF, al
    pop es
    pop ds
    ret
.failed:
    post_code_early 0xE0
    ; CS is the staging segment. Do not enter potentially damaged F000 RAM.
    cli
.halt:
    hlt
    jmp .halt
%ifdef EMULATOR_WARM_RESET_TEST
.test_failed:
    mov al, 0x5B
    call emulator_exit
    jmp .halt
%endif

validate_vga_image:
    cmp word [0], 0xAA55
    jne .failed
    cmp byte [2], 0x40
    jne .failed
    cmp word [3], VGA_INIT_JUMP_WORD
    jne .failed
    ; OEM F000:2F45-2F55: sum header-size * 512 bytes modulo 256.
    ; Like the OEM, this loop now executes from the protected system shadow.
    xor bx, bx
    xor si, si
    xor cx, cx
    mov ch, [2]
    shl cx, 1
.checksum:
    lodsb
    add bl, al
    loop .checksum
    test bl, bl
    jnz .failed
    clc
    ret
.failed:
    stc
    ret

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

presario_shared "pc/pic-pit.inc"

init_at_prerequisites:
    ; OEM cold-start table 8659, pair 8673: enable the VL82C114 PS/2 mode
    ; before any controller transactions. AT mode has no AUX interface.
    out CHIPSET_CONFIG_ON, al
    ; OEM table8659 and 86C1: establish the ISA/DMA bus baseline on cold
    ; and warm POST. CPU turbo alone does not program the ISA divider.
    mov al, CLKCTL_REG
    out CHIPSET_INDEX, al
    mov al, CLKCTL_VALUE
    out CHIPSET_DATA, al
    mov al, DMACTL_REG
    out CHIPSET_INDEX, al
    mov al, DMACTL_VALUE
    out CHIPSET_DATA, al
    mov al, BUSCTL_REG
    out CHIPSET_INDEX, al
    mov al, BUSCTL_VALUE
    out CHIPSET_DATA, al
    mov al, KBC_PLATFORM_REG
    out CHIPSET_INDEX, al
    mov al, KBC_PLATFORM_VALUE
    out CHIPSET_DATA, al
    out CHIPSET_CONFIG_OFF, al
    ; Both working references establish this AT glue before resetting the
    ; physical keyboard.  The target MR BIOS uses the same first four writes
    ; immediately before its controller self-test.
    post_code 0xB0
    xor al, al
    out DMA1_MASTER_CLEAR, al
    out DMA2_MASTER_CLEAR, al
    post_code 0xB1
    mov dx, FDC_DOR
    out dx, al
    mov al, 0x0C
    out SYSTEM_PORT_B, al
    mov al, 0x54
    out PIT_COMMAND, al
    mov al, 0x12
    out PIT_CHANNEL1, al
    post_code 0xB9
    ret

init_superio:
    mov dx, SUPERIO_INDEX
    mov al, 0x55
    out dx, al
    out dx, al
    xor al, al
    out dx, al
    inc dx
    mov al, 0x3F
    out dx, al
    dec dx
    mov al, 0xAA
    out dx, al
    ret

presario_shared "pc/keyboard-controller.inc"

presario_shared "pc/text.inc"

default_iret:
    iret

presario_shared "pc/ata-irq.inc"

; Standard AT numeric-error acknowledgment and application INT02 chain.
; VL82C481 F0 clears IRQ13 and asserts IGNNE while FERR is active.
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

presario_shared "pc/timer.inc"

presario_shared "pc/keyboard-irq.inc"

warm_reset:
    cli
    in al, 0x61
    and al, 0xFC
    out 0x61, al             ; A reset during a POST note must stop it now.
    mov word [0x0072], 0x1234
    post_code 0x90
%ifdef EMULATOR_EMM_RESET_TEST
    ; A reboot alone can hide an EMM386 fault/reset fallback. Require the
    ; keyboard intercept to have returned to real mode before touching CR0.
    smsw ax
    test ax, 1
    jz .real_mode
    mov al, 0x68
    call emulator_exit
    jmp hard_halt
.real_mode:
%endif
%ifdef EMULATOR_WARM_RESET_TEST
    ; Leave a second scan pending while the reset-triggering IRQ1 owns IF.
    mov al, 0xD2
    call kbc_command
    jc .failed
    mov al, 0x1E
    call kbc_write_data
    jc .failed
    call kbc_wait_output_full
    jc .failed
%endif
    ; Discard pre-reset input in both queues. Inhibit the keyboard while
    ; draining; release it below so POST input remains available.
    mov al, 0xAD
    call kbc_command
    jc .failed
    call kbc_wait_input_clear_mr
    jc .failed
    call kbc_drain
    jc .failed
    mov word [KB_HEAD], KB_BUFFER_START
    mov word [KB_TAIL], KB_BUFFER_START
    ; OEM C450/EB13 releases the keyboard before EA81 sets the warm flag.
    mov al, 0xAE
    call kbc_command
    jc .failed
    call kbc_wait_input_clear_mr
    jc .failed
    ; OEM 92BC/8651/86FB: unlock chipset, remove system and VGA shadows,
    ; invalidate the CPU cache, then enter warm POST with RAM configured.
    out CHIPSET_CONFIG_ON, al
    mov al, SYSTEM_SHADOW_REG
    out CHIPSET_INDEX, al
    xor al, al
    out CHIPSET_DATA, al
    mov al, VGA_SHADOW_REG
    out CHIPSET_INDEX, al
    xor al, al
    out CHIPSET_DATA, al
    wbinvd
    out CHIPSET_CONFIG_OFF, al
    post_code 0x91
    jmp 0xF000:startup.warm_start
.failed:
    mov al, 0xEE
    jmp keyboard_halt

presario_shared "pc/keyboard-bios.inc"

%ifdef KEYBOARD_DIAGNOSTIC
%include "keyboard-diagnostic.inc"
%endif


presario_shared "pc/keyboard-tables.inc"

presario_shared "firmware/system-services.inc"

presario_shared "firmware/extended-memory.inc"

%include "rtc.inc"

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
presario_shared "firmware/disk-dispatch.inc"

presario_shared "firmware/disk-request.inc"

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
    push ecx
    push fs
    call load_bios_state     ; FS may select the secondary disk record.
    movzx ecx,byte [fs:0]
    shl ecx,10
    xor ebx, ebx
    mov bx, fs
    pop fs
    shl ebx, 4
    cmp edx, ebx
    jbe .good
    add ebx,ecx
    cmp eax, ebx
    jb .bad
.good:
    pop ecx
    pop ebx
    clc
    ret
.bad:
    pop ecx
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

presario_shared "firmware/edd-parameters.inc"

presario_shared "pc/primary-ata.inc"

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
    call ide_pio_begin
    jc .done
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
    mov dx, ATA_DRIVE
    mov al, 0xA0
    or al, [fs:S_ATA_DEVICE]
    out dx, al
    call ata_delay
    mov dx, ATA_STATUS
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
    mov dx, ATA_COMMAND
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
    mov dx, ATA_CONTROL
    mov al, 0x0A
    out dx, al
    post_code 0x76
    mov cx, 25
.packet_settle:
    call kbc_delay_2ms
    loop .packet_settle
    mov dx, ATA_ERROR        ; Write side is Features, not the Error register.
    xor al, al
    out dx, al
    post_code 0x77
    mov dx, ATA_COMMAND
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
    mov dx, ATA_COMMAND
    mov al, 8
    out dx, al
    call ata_delay
    post_code 0x7A
    mov cx, 15000
    mov dx, ATA_CONTROL
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
    mov dx, ATA_CONTROL
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
    mov dx, ATA_DATA
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
    mov dx, ATA_CONTROL
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
    call ide_pio_identify
    jmp .snapshot
.identify_failed:
    post_code 0x7F
    cmp byte [fs:S_ATAPI], 1
    jne .clear_packet
    mov dx, ATA_CONTROL
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
    mov dx, ATA_STATUS
    call ata_read_status
    mov [fs:S_IDENTIFY_TRACE + 1], al
    mov dx, ATA_ERROR
    in al, dx
    mov [fs:S_IDENTIFY_TRACE + 2], al
    inc dx
    in al, dx
    mov [fs:S_IDENTIFY_TRACE + 3], al
    mov dx, ATA_LBA1
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
    mov dx, ATA_LBA1
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

presario_shared "firmware/disk-parameter-table.inc"

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
    call ide_pio_guard
    jc .return
    mov dx, ATA_DRIVE
    mov al, 0xA0
    or al, [fs:S_ATA_DEVICE]
    out dx, al
    call ata_delay
    jmp ata_wait_ready
.return:
    ret

ata_no_data_command:
    mov dx, ATA_COMMAND
    out dx, al
    jmp ata_wait_complete

presario_shared "pc/chs-geometry.inc"

presario_shared "pc/ata-reset.inc"


presario_shared "firmware/ata-transfer.inc"

presario_shared "pc/ata-status.inc"

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
    mov dx, ATA_CONTROL
    mov cx, 4
.again:
    in al, dx
    loop .again
    pop dx
    pop cx
    ret

%include "boot.inc"

presario_shared "firmware/boot-terminal.inc"

%ifdef EMULATOR_TEST
verify_initialization:
    push ax
    push cx
    push dx
    push di
    push es

    mov bl, 0x70
    xor al, al
    out CHIPSET_CONFIG_ON, al
    mov dx, CHIPSET_INDEX
    mov al, RAMTMG_REG
    out dx, al
    inc dx
    in al, dx
    cmp al, [fs:C_CHIP]       ; POST has applied the selected timing policy.
    jne .failed
    dec dx
    mov al, RAMCFG0_REG
    out dx, al
    inc dx
    in al, dx
    cmp al, RAMCFG0_VALUE
    je .bank0_valid
    cmp al, RAMCFG0_DOUBLE
    jne .failed
.bank0_valid:
    dec dx
    mov al, RAMCFG1_REG
    out dx, al
    inc dx
    in al, dx
    cmp al, RAMCFG1_VALUE
    jne .failed
    dec dx
    mov al, RAMSET_REG
    out dx, al
    inc dx
    in al, dx
    cmp al, RAMSET_VALUE
    jne .failed
    dec dx
    mov al, NTBREF_REG
    out dx, al
    inc dx
    in al, dx
    ; Before the final speed setup, warm POST may retain non-turbo waits.
    ; Check refresh here; the boot guest checks the final speed state.
    and al, 0x0F
    cmp al, NTBREF_VALUE
    jne .failed
    dec dx
    mov al, ROMSET_REG
    out dx, al
    inc dx
    in al, dx
    cmp al, VGA_ROMSET_VALUE
    jne .failed
    dec dx
    mov al, VGA_SHADOW_REG
    out dx, al
    inc dx
    in al, dx
    cmp al, VGA_SHADOW_RUN
    jne .failed
    mov al, SYSTEM_SHADOW_REG
    out CHIPSET_INDEX, al
    in al, CHIPSET_DATA
    cmp al, 0xAA
    jne .failed
    out CHIPSET_CONFIG_OFF, al

    mov bl, 0x71
    in al, 0x21
    cmp al, 0xFC
    jne .failed
    mov bl, 0x72
    in al, 0xA1
    cmp al, 0xFF
    jne .failed
    mov bl, 0x73
    mov al, 0xE2
    out 0x43, al
    in al, 0x40
    and al, 0x3F
    cmp al, 0x36
    jne .failed

    mov bl, 0x74
    mov dx, SUPERIO_INDEX
    mov al, 0x55
    out dx, al
    out dx, al
    xor al, al
    out dx, al
    inc dx
    in al, dx
    mov ah, 0x27
    cmp byte [fs:C_PORTS+P_FLOPPY], 0
    je .fdc_policy_verified
    or ah, 0x18
.fdc_policy_verified:
    cmp al, ah
    pushf
    dec dx
    mov al, 0xAA
    out dx, al
    popf
    jne .failed

    mov bl, 0x75
    xor ax, ax
    mov es, ax
    cmp word [es:0x0040], VGA_INT10_ENTRY
    jne .failed
    cmp word [es:0x0042], VGA_SEGMENT
    jne .failed
    mov bl, 0x76
    mov ax, 0xB800
    mov es, ax
    xor di, di
    mov cx, 2000
.find_banner:
    cmp byte [es:di], 'b'
    jne .next_cell
    cmp byte [es:di + 2], 'A'
    jne .next_cell
    cmp byte [es:di + 4], 'I'
    jne .next_cell
    cmp byte [es:di + 6], 'o'
    jne .next_cell
    cmp byte [es:di + 8], 's'
    je .passed
.next_cell:
    add di, 2
    loop .find_banner
.failed:
    stc
    jmp .done
.passed:
    clc
.done:
    pop es
    pop di
    pop dx
    pop cx
    pop ax
    ret

%endif
%ifdef EMULATOR_TEST
%define EMULATOR_EXIT_REQUIRED
%endif
%ifdef EMULATOR_POST_SUMMARY_TEST
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

%include "floppy.inc"
%include "mouse.inc"
%include "memory.inc"
%include "ide.inc"
presario_shared "firmware/ide-pio.inc"
%include "peripherals.inc"
%include "setup.inc"
presario_shared "firmware/pnp-interface.inc"
presario_shared "firmware/pnp-entry.inc"
presario_shared "firmware/pnp-storage-callbacks.inc"
presario_shared "firmware/pnp-post.inc"
%include "hardware/pnp-module.inc"
%include "post.inc"
%include "chipset.inc"
%include "apm.inc"
%include "cdboot.inc"
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

%include "identity.inc"

; Test observers use resident headroom before the fixed compatibility entries.
%ifdef EMULATOR_PAUSE_ONLY
%include "../tests/post-pause-test.inc"
%endif
%ifdef EMULATOR_PORTS_TEST
%include "../tests/ports-test.inc"
%endif
%ifdef EMULATOR_CHIPSET_TEST
%include "../tests/chipset-test.inc"
%endif
%ifdef EMULATOR_SETUP_TEST
%include "../tests/setup-test.inc"
%endif
%ifdef EMULATOR_BOOT_POLICY_TEST
%include "../tests/boot-policy-test.inc"
%endif
%ifdef EMULATOR_BOOT_SETTINGS_RECOVERY
%include "../tests/boot-policy-test.inc"
%endif
%ifdef EMULATOR_POST_SUMMARY_TEST
%include "../tests/summary-test.inc"
%else
%ifdef EMULATOR_TEST
%include "../tests/summary-test.inc"
%endif
%endif

; The retained VGA installer writes this fixed Compaq INT 42h vector.
rom_code_end:
times 0xF065 - ($ - $$) db 0xFF
int42_compat:
    cmp ah, 0x1D
    jae .unsupported
    jmp VGA_SEGMENT:VGA_INT10_ENTRY
.unsupported:
    iret

presario_shared "firmware/settings-nv6.inc"
presario_shared "firmware/setup-pnp.inc"

; The guarded name catalogue uses free ROM after the retained INT42 shim.
presario_shared "pc/cpu.inc"
presario_shared "pc/smm.inc"
board_cpu_detect_name:
    jmp cpu_detect_sl_name

board_cpu_sl_query:
    call cpu_detect_sl
    mov dx,0                 ; CPU evidence does not qualify board SL functions.
    ret

board_smm_prepare:
    call board_cpu_sl_query
    jmp smm_install

presario_shared "pc/ata-identify.inc"
presario_cpu_end:



times 0xFFF0 - ($ - $$) db 0xFF
reset_vector:
    jmp 0xF000:startup
; Standard BIOS date at F000:FFF5, also used by the OEM ROM and NSSI.
bios_date      db BIOS_DATE_PREFIX, BIOS_DATE_YEAR
times 0xFFFE - ($ - $$) db 0xFF
db 0xFC                       ; AT model, matching INT15/C0.
db 0

; Newly owned private POST bank; the builder packs it into lower-ROM C000h.
section post_payload start=0x10000 vstart=0
%define PNP_EXTERNAL_JOURNAL
presario_shared "firmware/pnp-module.inc"
%undef PNP_EXTERNAL_JOURNAL
; The shared packer serializes this complete raw tail into the owned bank.
