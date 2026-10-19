; Intel/Microsoft APM 1.2, sections4.1/4.6 and AppendixC.
; CPU HLT only: no chipset clocks, CMOS, devices or global power states.
; POST clears these spare EBDA bytes. Zero means enabled/engaged/disconnected.
APM_CONNECTION equ 0x27A         ; 0 none,1 real,2 PM16,3 PM32.
APM_VERSION equ 0x27B            ; Negotiated minor:0,1,2; BIOS version is1.2.
APM_FLAGS equ 0x27C              ; Disabled1,disengaged2.
%ifdef EMULATOR_APM_TEST
APM_TEST_IDLE equ 0x27D          ; Test-only observations; not production state.
APM_TEST_WAKE equ 0x281
APM_DATA_LENGTH equ APM_TEST_WAKE+4
%else
APM_DATA_LENGTH equ APM_FLAGS+1
%endif

; Common INT15 BP frame. Real/v86 callers follow the current BDA pointer.
apm_int15:
    cli
    push ds
    push fs
    push ax
    call load_bios_state
    mov ax, fs
    mov ds, ax
    pop ax
    call apm_dispatch16
    pop fs
    pop ds
    jc .error
    and word [ss:bp+6], 0xFFFE
    pop bp
    iret
.error:
    or word [ss:bp+6], 1
    pop bp
    iret

; Protected callers own valid consecutive code/data selectors and their stack.
; No real-mode segment loads or BIOS interrupts occur in these entries.
apm_pm16:
    pushf
    cli
    push ds
    push eax
    mov ax, cs
    add ax, 8
    mov ds, ax
    pop eax
    cmp byte [ds:APM_CONNECTION], 2
    jne .disconnected
    cmp ah, 0x53
    jne .unsupported
    cmp al, 4
    jb .unsupported              ; Installation/connect are real-mode only.
    call apm_dispatch16
    jmp .return
.disconnected:
    mov ah, 3
    stc
    jmp .return
.unsupported:
    mov ah, 0xFF
    stc
.return:
    pop ds
    jc .error
    popf
    clc
    retf
.error:
    popf
    stc
    retf

; Author the contract once; NASM supplies each mode's operand/address sizes.
%macro apm_dispatch 1
%1:
    cmp al, 0
    je %%installation
    cmp al, 3
    jbe %%connect
    cmp al, 0x0A
    je %%status
    cmp al, 0x0C
    je %%get_state
    cmp al, 0x10
    je %%capabilities
    cmp al, 0x13
    jae %%undefined
    cmp byte [ds:APM_CONNECTION], 0
    je %%disconnected
    cmp al, 4
    je %%disconnect
    cmp al, 0x0F
    je %%engage
    test byte [ds:APM_FLAGS], 2
    jnz %%disengaged
    cmp al, 5
    je %%idle
    cmp al, 6
    je %%ok                      ; Busy never changes the selected clock.
    cmp al, 7
    je %%set_state
    cmp al, 8
    je %%enable
    cmp al, 9
    je %%defaults
    cmp al, 0x0B
    je %%events
    cmp al, 0x0D
    je %%device
    cmp al, 0x0E
    je %%version
    ; Only optional Resume Timer and Resume on Ring permit error0Ch.
    cmp byte [ds:APM_VERSION], 2
    jb %%undefined
    test bx, bx
    jnz %%bad_device
    mov ah, 0x0C
    stc
    ret
%%installation:
    test bx, bx
    jnz %%bad_device
    mov ax, 0x0102
    mov bx, 0x504D
    mov cx, 3                    ; Both PM interfaces; Idle does not slow clocks.
    test byte [ds:APM_FLAGS], 1
    jz %%install_engaged
    or cl, 8
%%install_engaged:
    test byte [ds:APM_FLAGS], 2
    jz %%ok
    or cl, 16
    jmp %%ok
%%connect:
    test bx, bx
    jnz %%bad_device
    cmp byte [ds:APM_CONNECTION], 0
    jne %%duplicate
    mov [ds:APM_CONNECTION], al
    mov byte [ds:APM_VERSION], 0
    cmp al, 1
    je %%ok
    cmp al, 2
    je %%connect16
    mov ax, 0xF000
    mov ebx, apm_pm32
    mov cx, ax
    mov dx, ds
    mov esi, ((apm16_end-$$) << 16) | (apm32_end-$$)
    mov di, APM_DATA_LENGTH
    jmp %%ok
%%connect16:
    mov ax, 0xF000
    mov bx, apm_pm16
    mov cx, ds
    mov si, apm16_end
    mov di, APM_DATA_LENGTH
    jmp %%ok
%%duplicate:
    mov ah, 2
    cmp byte [ds:APM_CONNECTION], 1
    je %%error
    mov ah, 5
    cmp byte [ds:APM_CONNECTION], 2
    je %%error
    mov ah, 7
    jmp %%error
%%disconnect:
    test bx, bx
    jnz %%bad_device
    mov word [ds:APM_CONNECTION], 0
    jmp %%ok
%%idle:
    test byte [ds:APM_FLAGS], 1
    jnz %%ok                     ; Disabled Idle succeeds without saving power.
%ifdef EMULATOR_APM_TEST
    inc dword [ds:APM_TEST_IDLE]
%endif
    pushf
    sti
    hlt                          ; Exactly one wake; caller decides whether idle continues.
    popf
%ifdef EMULATOR_APM_TEST
    inc dword [ds:APM_TEST_WAKE]
%endif
    jmp %%ok
%%set_state:
    cmp bx, 1
    jne %%bad_device
    test byte [ds:APM_FLAGS], 1
    jnz %%disabled
    cmp cx, 1
    jb %%bad_parameter
    cmp cx, 3
    ja %%bad_parameter
    mov ah, 0x60                 ; No supported whole-system low-power hardware.
    jmp %%error
%%enable:
    cmp bx, 1
    je %%enable_parameter
    cmp bx, 0xFFFF               ; Required legacy1.0 all-device ID.
    jne %%bad_device
%%enable_parameter:
    cmp cx, 1
    ja %%bad_parameter
    jcxz %%disable
    and byte [ds:APM_FLAGS], 0xFE
    jmp %%ok
%%disable:
    or byte [ds:APM_FLAGS], 1
    jmp %%ok
%%defaults:
    cmp bx, 1
    je %%restore
    cmp bx, 0xFFFF
    jne %%bad_device
%%restore:
    mov byte [ds:APM_FLAGS], 0
    jmp %%ok
%%status:
    cmp bx, 1
    jne %%bad_device
    mov bx, 0x01FF               ; AC online; battery charge unknown.
    mov cl, 0xFF
    cmp byte [ds:APM_CONNECTION], 0
    je %%status12
    cmp byte [ds:APM_VERSION], 0
    je %%ok                      ; Preserve1.0 caller CH/DX/SI.
    mov ch, 0x80                 ; No system battery.
    mov dx, 0xFFFF
    cmp byte [ds:APM_VERSION], 2
    jb %%ok
%%status12:
    mov ch, 0x80
    mov dx, 0xFFFF
    xor si, si                   ; No battery units installed.
    jmp %%ok
%%events:
    mov ah, 0x80                 ; CPU Idle wake is not a system-resume event.
    jmp %%error
%%get_state:
    cmp byte [ds:APM_CONNECTION], 0
    je %%state_enabled
    cmp byte [ds:APM_VERSION], 1
    jb %%undefined
%%state_enabled:
    cmp bx, 1
    jne %%bad_device
    test byte [ds:APM_FLAGS], 1
    jnz %%disabled
    jmp %%bad_device             ; No aggregate state was successfully set.
%%device:
    cmp byte [ds:APM_VERSION], 1
    jb %%undefined
    cmp bx, 1
    jne %%bad_device
    cmp cx, 1
    ja %%bad_parameter
    test byte [ds:APM_FLAGS], 1
    jnz %%disabled
    jmp %%ok                     ; Empty device set; global CPU policy is unchanged.
%%version:
    test bx, bx
    jnz %%bad_device
    mov ax, 0x0100
    cmp cx, 0x0101
    jb %%set_version
    inc al
    cmp cx, 0x0102
    jb %%set_version
    inc al
%%set_version:
    mov [ds:APM_VERSION], al
    jmp %%ok
%%engage:
    ; Reconnect retains disengagement but resets version to1.0. This control
    ; must reopen cooperation before DriverVersion (which rejects disengagement).
    cmp bx, 1
    jne %%bad_device
    cmp cx, 1
    ja %%bad_parameter
    test byte [ds:APM_FLAGS], 1
    jnz %%disabled
    jcxz %%disengage
    and byte [ds:APM_FLAGS], 0xFD
    jmp %%ok
%%disengage:
    or byte [ds:APM_FLAGS], 2
    jmp %%ok
%%capabilities:
    test bx, bx
    jnz %%bad_device
    cmp byte [ds:APM_CONNECTION], 0
    je %%caps
    cmp byte [ds:APM_VERSION], 2
    jb %%undefined
%%caps:
    xor bx, bx
    xor cx, cx                   ; No batteries/global states/wake sources.
%%ok:
    clc
    ret
%%disconnected:
    mov ah, 3
    jmp %%error
%%disengaged:
    mov ah, 0x0B
    jmp %%error
%%disabled:
    mov ah, 1
    jmp %%error
%%bad_device:
    mov ah, 9
    jmp %%error
%%bad_parameter:
    mov ah, 0x0A
    jmp %%error
%%undefined:
    mov ah, 0xFF
%%error:
    stc
    ret
%endmacro

apm_dispatch apm_dispatch16
apm16_end:

bits 32
apm_pm32:
    pushfd
    cli
    push ds
    push eax
    mov ax, cs
    add ax, 16
    mov ds, ax
    pop eax
    cmp byte [ds:APM_CONNECTION], 3
    jne .disconnected
    cmp ah, 0x53
    jne .unsupported
    cmp al, 4
    jb .unsupported
    call apm_dispatch32
    jmp .return
.disconnected:
    mov ah, 3
    stc
    jmp .return
.unsupported:
    mov ah, 0xFF
    stc
.return:
    pop ds
    jc .error
    popfd
    clc
    retf
.error:
    popfd
    stc
    retf

apm_dispatch apm_dispatch32
apm32_end:
bits 16
