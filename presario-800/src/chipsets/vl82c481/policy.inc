%include "shared-owner.inc"
; VL82C481 controls. Datasheet pp18-24; board geometry/decode stays owned by POST.
; CMOS69=C2 schema (C1 read compatibility, D2 persistent recovery),6A=checksum,6B..7F/33..35=24-byte record.
; CMOS36: 5A=retry+notice,1A=retry acknowledged,DA=notice carried across POST.
; CMOS37=A0/E0 records the power-on HSPD strap for Auto and warm recovery.
; Stackless RTC settle for the failure path before RAM/stack is trustworthy.
%macro chipset_cmos_settle 0
    mov cx, 0xFFFF
%%wait:
    loop %%wait
%endmacro

chipset_defaults:
    pushad
    mov si, chipset_default
    mov cx, CHIP_SIZE
.byte:
    mov al, [cs:si]
    mov [fs:di], al
    inc si
    inc di
    loop .byte
    popad
    ret

chipset_valid:
    pushad
    xor bx, bx
.byte:
    mov al, [fs:si+bx]
    mov ah, [cs:chipset_masks+bx]
    not ah
    test al, ah
    jnz .bad
    inc bx
    cmp bx, CHIP_SIZE
    jb .byte
    mov al, [fs:si+9]
    and al, 0x30
    cmp al, 0x30
    jne .bad
    ; Each visible field is also a persisted selector's range authority.
    mov bp, chip_group_0
    mov dx, CHIP_FIELD_COUNT
.field:
    movzx bx, byte [cs:bp+2]
    mov cl, [cs:bp+3]
    mov al, [fs:si+bx]
    shr al, cl
    and al, [cs:bp+4]
    movzx ax, al
    cmp ax, [cs:bp+5]
    jae .bad
    add bp, CHIP_FIELD_SIZE
    dec dx
    jnz .field
    ; No reserved timing aliases in saved records.
    mov al, [fs:si]
    and al, 0xC0
    cmp al, 0xC0
    je .bad
    mov al, [fs:si+2]
    and al, 0x0C
    cmp al, 0x0C
    je .bad
    mov al, [fs:si+8]
    cmp al, 3
    je .bad
    mov al, [fs:si+10]
    and al, 3
    cmp al, 3
    je .bad
    ; Preset claims must match the selected coherent tuple.
    mov al, [fs:si+10]
    and al, 0xC0
    cmp al, 0x80
    je .tuple_ready
    cmp al, 0xC0
    jne .profile
    call chipset_fast_available
    jc .bad
.profile:
    call chipset_profile_value
    mov ah, [fs:si]
    and ah, 0x3F
    cmp al, ah
    jne .bad
.tuple_ready:
    ; A PMR must not replace conventional RAM, VGA ROM or the running BIOS.
    mov di, 17
.region:
    mov bx, si
    add bx, di
    movzx edx, byte [fs:bx+1]
    test dl, dl
    jz .next
    mov al, [fs:bx]
    call chipset_region_extent
    cmp eax, 0x100000
    jae .next
    cmp eax, 0xC8000
    jb .bad
    cmp ebx, 0xF0000
    ja .bad
    ; Shadowing and ISA remapping of the same window have two owners.
    cmp word [fs:si+21], 3
    jne .bad
.next:
    add di, 2
    cmp di, 21
    jb .region
    popad
    clc
    ret
.bad:
    popad
    stc
    ret

; AL=PMRA,DL=subregion mask. EAX=first selected byte,EBX=exclusive last.
chipset_region_extent:
    movzx eax, al
    and eax, 0x3F
    mov ecx, 0x10000
    test al, 0x20
    jz .small
    mov ecx, 0x100000
    test al, 0x10
    jz .large
    and eax, 15
    mov ecx, 0x800
    shl eax, 14
    add eax, 0xC0000
    jmp .selected
.large:
    and eax, 15
    shl eax, 23
    jmp .selected
.small:
    shl eax, 19
.selected:
    movzx edx, dl
    bsf ebx, edx
    imul ebx, ecx
    add eax, ebx
    ; Last selected bit can be separated from the first by disabled bits.
    bsr ebx, edx
    bsf edx, edx
    sub ebx, edx
    inc ebx
    imul ebx, ecx
    add ebx, eax
    ret

chipset_settings_load:
    pushad
    mov di, C_CHIP
    call chipset_defaults
    mov al, 0x69
    call rtc_read
    cmp al, 0xD2
    je .recovery
    cmp al, 0xC1
    je .record
    cmp al, 0xC2
    jne .done
.record:
    mov dl, al
    mov bl, al
    xor bp, bp
.byte:
    mov al, [cs:chipset_cmos+bp]
    call rtc_read
    mov [fs:C_CHIP+bp], al
    add bl, al
    inc bp
    cmp bp, CHIP_SIZE
    jb .byte
    mov al, 0x6A
    call rtc_read
    add bl, al
    jnz .bad
    cmp dl, 0xC1
    jne .validate
    ; Verify the legacy masks before adding metadata. Never write CMOS here.
    test byte [fs:C_CHIP+10], 0xF0
    jnz .bad
    test byte [fs:C_CHIP+23], 0xFE
    jnz .bad
    or byte [fs:C_CHIP+10], 0xA0 ; Manual, 70 ns.
    or byte [fs:C_CHIP+23], 2    ; Configured 33 MHz.
.validate:
    mov si, C_CHIP
    call chipset_valid
    jnc .done
.bad:
    mov di, C_CHIP
    call chipset_defaults
    mov byte [fs:C_VALID], 0
    jmp .done
.recovery:
    mov byte [fs:C_CHIP], 0xA6
    mov byte [fs:C_CHIP+10], 0x68 ; Compatibility, 70 ns, conservative XCTL.
.done:
    popad
    ret

; SI=record. Fast can match Normal's non-L2 2T CAS in the L2 table.
; Normal CAS00 is 1T without L2; the L2 table cannot represent it.
chipset_fast_available:
    push ax
    push bx
    call chipset_profile_index
    mov al, [cs:chipset_profiles+bx]
    and al, 3
    cmp al, 2
    pop bx
    pop ax
    jne .bad
    clc
    ret
.bad:
    stc
    ret

; SI=record. BX=Normal table index; metadata is range-checked.
chipset_profile_index:
    xor bx, bx
    test byte [fs:si+23], 2
    jz .speed
    mov bl, 2
.speed:
    mov al, [fs:si+10]
    and al, 0x30
    cmp al, 0x10             ; Unknown uses the 70 ns profile.
    je .done
    inc bx
.done:
    ret

; SI=record. Return selected low six RAMTMG bits; metadata is range-checked.
chipset_profile_value:
    push bx
    call chipset_profile_index
.mode:
    mov al, [fs:si+10]
    and al, 0xC0
    cmp al, 0x40
    jne .value
    add bx, 4
.value:
    mov al, [cs:chipset_profiles+bx]
    mov ah, [fs:si+10]
    and ah, 0xC0
    cmp ah, 0xC0
    jne .done
    dec al                  ; Normal non-L2 2T -> Fast L2 2T; write remains 1T.
.done:
    pop bx
    ret

; SI=record. Manual preserves raw timings; other modes retain cycle start.
chipset_profile_apply:
    push ax
    mov al, [fs:si+10]
    and al, 0xC0
    cmp al, 0x80
    je .done
    cmp al, 0xC0
    jne .apply
    call chipset_fast_available
    jnc .apply
    and byte [fs:si+10], 0x3F ; No L2 improvement available: select Normal.
.apply:
    call chipset_profile_value
    and byte [fs:si], 0xC0
    or [fs:si], al
.done:
    pop ax
    ret

chipset_settings_save:
    pushad
    xor dx, dx
    mov al, 0x69
    call rtc_read
    cmp al, 0xD2
    jne .validate
    mov dl, 0xD2            ; Interrupted/failed recovery saves keep Compatibility.
.validate:
    mov si, U_CHIP
    call chipset_valid
    jc .bad
    mov ax, 0x0069
    mov ah, dl
    call rtc_write
    mov bl, 0xC2
    xor bp, bp
.byte:
    mov al, [cs:chipset_cmos+bp]
    mov ah, [fs:U_CHIP+bp]
    add bl, ah
    call rtc_write
    inc bp
    cmp bp, CHIP_SIZE
    jb .byte
    neg bl
    mov al, 0x6A
    mov ah, bl
    call rtc_write
    mov al, 0x6A
    call settings_verify_byte
    jne .bad
    xor bp, bp
.verify:
    mov al, [cs:chipset_cmos+bp]
    mov ah, [fs:U_CHIP+bp]
    call settings_verify_byte
    jne .bad
    inc bp
    cmp bp, CHIP_SIZE
    jb .verify
    mov ax, 0xC269
    call rtc_write
    mov ax, 0xC269
    call settings_verify_byte
    jne .bad
    popad
    clc
    ret
.bad:
    mov ax, 0x0069
    mov ah, dl
    call rtc_write
    popad
    stc
    ret

; Before the interleave transition, use only disposable POST state.
; Reset the retry guard, but retain an actual defaults-restored notice.
chipset_memory_prepare:
    pushad
    push fs
    mov ax, STATE_SEG
    mov fs, ax
    ; Capture the strap before an override. KBC SYSTEM clears at power-on.
    in al, KBC_STATUS
    test al, 4
    jz .strap
    mov al, 0x37
    call rtc_read
    and al, 0xBF
    cmp al, 0xA0
    je .strap_ready
.strap:
    out CHIPSET_CONFIG_ON, al
    mov al, 0x24
    out CHIPSET_INDEX, al
    in al, CHIPSET_DATA
    and al, 0x40
    or al, 0xA0
    mov ah, al
    mov al, 0x37
    call rtc_write
    out CHIPSET_CONFIG_OFF, al
.strap_ready:
    cmp si, 2                 ; Internal restart preserves the current retry.
    je .load
    mov al, 0x36
    call rtc_read
    ram_test_startup_state
    call rtc_write
.load:
    call chipset_settings_load
    out CHIPSET_CONFIG_ON, al
    out FAST_CPU_PORT, al
    mov al, 6
    out CHIPSET_INDEX, al
    mov al, CLKCTL_VALUE
    out CHIPSET_DATA, al
    ; Test selected timings before building live firmware state.
    mov al, 1
    out CHIPSET_INDEX, al
    mov al, [fs:C_CHIP]
    out CHIPSET_DATA, al
    mov al, 5
    out CHIPSET_INDEX, al
    in al, CHIPSET_DATA
    and al, 0x10
    or al, [fs:C_CHIP+2]
    out CHIPSET_DATA, al
    mov al, 0x24
    out CHIPSET_INDEX, al
    in al, CHIPSET_DATA
    mov ah, [fs:C_CHIP+10]
    call chipset_xctl_policy

    out CHIPSET_DATA, al
    out CHIPSET_CONFIG_OFF, al
    pop fs
    popad
    ret

; AL=current XCTL,AH=policy. Auto restores the captured strap on warm boots.
chipset_xctl_policy:
    push bx
    mov bl, al
    mov bh, ah
    and bl, ~0x0C
    and ah, 0x0C
    or bl, ah
    and bh, 3
    test bh, bh
    jnz .override
    mov al, 0x37
    call rtc_read
    mov ah, al
    and ah, 0xBF
    cmp ah, 0xA0
    jne .done
    and bl, ~0x40
    and al, 0x40
    or bl, al
    jmp .done
.override:
    and bl, ~0x40
    cmp bh, 2
    jne .done
    or bl, 0x40
.done:
    mov al, bl
    pop bx
    ret

; AL=automatic interleave mode. Preserve all caller registers except AX/CX.
; Called after the selection helper returns and before any map is changed.
chipset_interleave_policy:
    push fs
    push bx
    mov bx, STATE_SEG
    mov fs, bx
    test byte [fs:C_CHIP+1], 0x80
    jnz .selected
    xor al, al
.selected:
    mov cl, al
    shl cl, 5
    mov al, [fs:C_CHIP+1]
    and al, 0x17
    or cl, al
    pop bx
    pop fs
    ret

; Quick destructive check of low64KiB and EBDA before firmware state exists.
; The bulk RAM test runs visibly after VGA initialization. No stack access
; while its storage is overwritten.
; DX=extended KiB,BP=warm marker; retain both across the test/map transition.
chipset_ram_test:
    movzx edx, dx
    in al, 0x92
    movzx eax, al
    shl eax, 24
    or edx, eax
    shr eax, 24
    and al, 0xFE
    or al, 2
    out 0x92, al
    mov esi, 0xA0000
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
    mov ecx, 0x55AA55AA
.pattern:
    xor edi, edi
.write:
    mov eax, edi
    xor eax, ecx
    mov [edi], eax
    add edi, 4
    cmp edi, 0x10000
    jne .write_limit
    mov edi, STATE_SEG << 4
.write_limit:
    cmp edi, esi
    jb .write
    xor edi, edi
.read:
    mov eax, edi
    xor eax, ecx
    cmp [edi], eax
    jne .failed
    add edi, 4
    cmp edi, 0x10000
    jne .read_limit
    mov edi, STATE_SEG << 4
.read_limit:
    cmp edi, esi
    jb .read
    not ecx
    cmp ecx, 0x55AA55AA
    jne .pattern
    xor edi, edi
    jmp .leave
.failed:
    mov edi, 1
.leave:
    mov ax, 0x18
    mov ds, ax
    mov es, ax
    mov cr0, ebx
    jmp 0xF000:.real
.real:
    xor ax, ax
    mov ds, ax
    mov es, ax
    mov eax, edx
    shr eax, 24
    and al, 0xFE
    out 0x92, al
    test edi, edi
    jz .passed
    ; The old stack/EBDA is untrusted. Restore the board baseline inline.
    mov al, 0xB6
    out 0x70, al
    chipset_cmos_settle
    in al, 0x71
    and al, 0xBF              ; Notice acknowledgement retains the retry guard.
    cmp al, 0x1A
    je .hard_failure
    mov al, 0xE9
    out 0x70, al
    chipset_cmos_settle
    mov al, 0xD2
    out 0x71, al           ; Persist Compatibility recovery, retaining devices.
    mov al, 0xB6
    out 0x70, al
    chipset_cmos_settle
    mov al, 0x5A
    out 0x71, al           ; Commit the notice before touching unstable RAM again.
    jmp 0xF000:startup.controlled_restart
.hard_failure:
    post_code_early 0xE7
    jmp hard_halt
.passed:
    jmp startup.ram_test_done

; After settings/peripherals load, and with L2 still off, apply saved policy.
chipset_apply:
    pushf
    cli
    pushad
    push fs
    push ds
    push es
    call load_bios_state
    wbinvd
    out CHIPSET_CONFIG_ON, al
    mov al, 0x19
    out CHIPSET_INDEX, al
    xor al, al
    out CHIPSET_DATA, al
    mov eax, cr0
    or eax, 0x60000000
    mov cr0, eax
    xor bp, bp
.register:
    mov al, [cs:chipset_registers+bp]
    out CHIPSET_INDEX, al
    in al, CHIPSET_DATA
    mov bl, [cs:chipset_apply_masks+bp]
    not bl
    and al, bl
    mov ah, [fs:C_CHIP+bp]
    mov bl, [cs:chipset_apply_masks+bp]
    and ah, bl
    or al, ah
    out CHIPSET_DATA, al
    inc bp
    cmp bp, 9
    jb .register
    mov al, 0x24
    out CHIPSET_INDEX, al
    in al, CHIPSET_DATA
    mov ah, [fs:C_CHIP+10]
    call chipset_xctl_policy

    out CHIPSET_DATA, al
    mov bp, 11
.cache_region:
    mov ax, bp
    add al, 8
    out CHIPSET_INDEX, al
    mov al, [fs:C_CHIP+bp]
    out CHIPSET_DATA, al
    inc bp
    cmp bp, 17
    jb .cache_region
    ; PMRs are programmed only with enables off; RAM reporting stops at the
    ; first mapped ISA hole because AH88 reports contiguous memory.
    mov ax, [fs:S_INSTALLED_KIB]
    test ax, ax
    jz .physical_count_ready
    mov [fs:S_EXTENDED_KIB], ax
.physical_count_ready:
    mov si, C_CHIP
    mov di, 17
.pmr:
    mov ax, di
    add al, 0x10
    out CHIPSET_INDEX, al
    xor al, al
    out CHIPSET_DATA, al
    mov ax, di
    add al, 0x0F
    out CHIPSET_INDEX, al
    mov bx, si
    add bx, di
    mov al, [fs:bx]
    out CHIPSET_DATA, al
    movzx edx, byte [fs:bx+1]
    test dl, dl
    jz .pmr_enable
    mov al, [fs:bx]
    call chipset_region_extent
    cmp eax, 0x100000
    jb .pmr_reload
    sub eax, 0x100000
    shr eax, 10
    cmp eax, 0xFFFF
    ja .pmr_reload
    cmp ax, [fs:S_EXTENDED_KIB]
    jae .pmr_reload
    mov [fs:S_EXTENDED_KIB], ax
.pmr_reload:
    mov bx, si
    add bx, di
    movzx edx, byte [fs:bx+1]
.pmr_enable:
    mov ax, di
    add al, 0x10
    out CHIPSET_INDEX, al
    mov al, dl
    out CHIPSET_DATA, al
    add di, 2
    cmp di, 21
    jb .pmr
    out CHIPSET_CONFIG_OFF, al
    call chipset_shadows
    call chipset_cpu_policy
    ; RAM test and shadow writes initialized parity before NMI can report it.
    in al, 0x61
    or al, 4
    test byte [fs:C_CHIP+4], 4
    jnz .parity
    test byte [fs:C_CHIP+10], 4
    jz .parity
    and al, ~4
.parity:
    out 0x61, al
    pop es
    pop ds
    pop fs
    popad
    popf
    ret

chipset_cpu_policy:
    out CHIPSET_CONFIG_ON, al
    test byte [fs:C_CHIP+23], 1
    jz .slow
    out FAST_CPU_PORT, al
    jmp .cache
.slow:
    out 0xF4, al
.cache:
    mov al, 7
    out CHIPSET_INDEX, al
    in al, CHIPSET_DATA
    and al, ~8
    mov ah, [fs:C_CHIP+4]
    and ah, 8
    or al, ah
    out CHIPSET_DATA, al
    out CHIPSET_CONFIG_OFF, al
    wbinvd
    mov eax, cr0
    or eax, 0x60000000
    test byte [fs:C_CHIP+4], 8
    jz .cr0
    and eax, 0x9FFFFFFF
.cr0:
    mov cr0, eax
    ret

; Optional C/D/E ROM shadows: copy from ISA ROM to DRAM before read switching.
; A/B VGA RAM and the mandatory system shadow retain their existing owners.
chipset_shadows:
    pushad
    push ds
    push es
    mov bp, [fs:C_CHIP+21]
    mov dx, 0xC000
    xor bx, bx
.segment:
    out CHIPSET_CONFIG_ON, al
    mov ax, bx
    shr al, 2
    add al, 0x0F
    out CHIPSET_INDEX, al
    in al, CHIPSET_DATA
    mov cx, bx
    and cl, 3
    shl cl, 1
    mov ah, 3
    shl ah, cl
    not ah
    and al, ah
    mov ah, al
    test bp, 1
    jz .disable
    mov al, 1
    shl al, cl
    or al, ah
    out CHIPSET_DATA, al
    wbinvd
    mov ds, dx
    mov es, dx
    push cx
    xor si, si
    xor di, di
    mov cx, 0x2000
    rep movsw
    pop cx
    mov al, 2
    shl al, cl
    or al, ah
    jmp .store
.disable:
    mov al, ah
.store:
    out CHIPSET_DATA, al
    wbinvd
    out CHIPSET_CONFIG_OFF, al
    shr bp, 1
    add dx, 0x400
    inc bx
    cmp bx, 12
    jb .segment
    pop es
    pop ds
    popad
    ret

; Called after the final Setup entry gate, as POST summary starts. Probe at known-good L2
; timings, then apply user policy without replacing detected bank/size controls.
chipset_late_cache:
    pushf
    cli
    pushad
    push fs
    call load_bios_state
.attempt:
    mov byte [fs:S_L2_PROBE], 0
    test byte [fs:C_CHIP+9], 1
    jz .done
    ; SRAM setup uses installed DRAM scratch, never a selected ISA window.
    wbinvd
    out CHIPSET_CONFIG_ON, al
    mov al, 0x21
    out CHIPSET_INDEX, al
    xor al, al
    out CHIPSET_DATA, al
    mov al, 0x23
    out CHIPSET_INDEX, al
    xor al, al
    out CHIPSET_DATA, al
    out CHIPSET_CONFIG_OFF, al
    call init_external_cache
    mov al, 0x15
    je .probe_result
    mov al, 0x14
    jb .probe_result
    mov al, 0x16
.probe_result:
    mov [fs:S_L2_PROBE], al
    out CHIPSET_CONFIG_ON, al
    mov al, 0x19
    out CHIPSET_INDEX, al
    in al, CHIPSET_DATA
    mov bl, al
    and al, 7
    jz .off
    cmp al, 7
    je .off
    wbinvd
    mov al, [fs:C_CHIP+9]
    and al, 0x48               ; User write wait and dirty-bit policy only.
    and bl, 0xB7               ; Detected banks, tag size, valid bit and capacity.
    or al, bl
    out CHIPSET_DATA, al
.off:
    out CHIPSET_CONFIG_OFF, al
.done:
    ; The probe restores OEM cacheability/CEN; restore the chosen policy.
    out CHIPSET_CONFIG_ON, al
    mov al, 7
    out CHIPSET_INDEX, al
    in al, CHIPSET_DATA
    and al, 0x40
    mov ah, [fs:C_CHIP+4]
    and ah, 0xBF
    or al, ah
    out CHIPSET_DATA, al
    mov bp, 11
.region:
    mov ax, bp
    add al, 8
    out CHIPSET_INDEX, al
    mov al, [fs:C_CHIP+bp]
    out CHIPSET_DATA, al
    inc bp
    cmp bp, 17
    jb .region
    wbinvd
    mov al, 0x21
    out CHIPSET_INDEX, al
    mov al, [fs:C_CHIP+18]
    out CHIPSET_DATA, al
    mov al, 0x23
    out CHIPSET_INDEX, al
    mov al, [fs:C_CHIP+20]
    out CHIPSET_DATA, al
    out CHIPSET_CONFIG_OFF, al
    call chipset_cpu_policy
    call chipset_runtime_ram_check
    jnc .passed
    mov al, 0x36
    call rtc_read
    and al, 0xBF
    cmp al, 0x1A
    je .failed
    mov ax, 0xD269
    call rtc_write
    mov ax, 0x5A36
    call rtc_write
    cmp byte [fs:P_PHASE], 0
    je .cache_retry_text
    call post_message_cursor
.cache_retry_text:
    mov si, chipset_cache_retry
    call print_string
    call chipset_recovery_ack
    jmp controlled_defaults_restart
.failed:
    cmp byte [fs:P_PHASE], 0
    je .cache_failure_text
    call post_message_cursor
.cache_failure_text:
    mov si, chipset_cache_failure
    call print_string
    post_code_early 0xE7
    jmp hard_halt
.passed:
    ; The acknowledged retry guard lasts until the next POST.
    pop fs
    popad
    popf
    ret

chipset_late_cache_end:

; Report an actual defaults restore, including one interrupted before video.
presario_shared "firmware/ram-test.inc"

; Normal 33 MHz/70 ns, raw 2-2-2/1; conservative cache waits and OEM phasing.
chipset_profiles db 0x04,0x12,0x12,0x16,0x16,0x16,0x16,0x26
chipset_default db 0x96,RAMSET_VALUE,0,0,0x88,0x38,0x30,0,0,0x31,0x28
    db 0x55,0x55,0x55,0x55,0x55,0xAA,0,0,0,0,3,0,3
chipset_masks db 0xFF,0x97,0xEF,0xFB,0xBF,0xBF,0x7F,0xFF,3,0x79,0xFF
    db 0xFF,0xFF,0xFF,0xFF,0xFF,0xFF,0x7F,0xFF,0x7F,0xFF,0xFF,15,3
chipset_cmos db 0x6B,0x6C,0x6D,0x6E,0x6F,0x70,0x71,0x72,0x73,0x74,0x75
    db 0x76,0x77,0x78,0x79,0x7A,0x7B,0x7C,0x7D,0x7E,0x7F,0x33,0x34,0x35
chipset_registers db 1,4,5,6,7,8,9,0x0B,0x0C
chipset_apply_masks db 0xFF,0x17,0xEF,0xFB,0xB7,0xBF,0x7F,0xFF,3
