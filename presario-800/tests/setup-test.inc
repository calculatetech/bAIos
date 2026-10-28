; External keyboard stimuli and terminal observers, never setup-state setters.
%define ST_PHASE  0x0600
%define ST_WAIT   0x0601
%define ST_KEY    0x0602
%define ST_SECOND 0x0604
%define ST_CLOCK 0x0606
%define ST_WIDTH  0x0616
%define ST_HEIGHT 0x0618
%define ST_SHOT   0x061A

%ifdef EMULATOR_SETUP_INVALID_NOTICE
setup_test_alert_begin:
%ifdef EMULATOR_SETUP_BAD_CMOS
    push fs
    call load_bios_state
    cmp byte [fs:C_VALID], 1
    pop fs
    je .done                  ; Controlled restart already accepted the warning.
%endif
    mov byte [ST_WAIT], 0
    set_vector 0x1C, setup_test_alert_tick
.done:
    ret

setup_test_alert_tick:
    pushad
    push ds
    push es
    xor ax, ax
    mov ds, ax
    ; Progressive RAM POST may take longer than the former fixed key delay.
    ; Inject the notice key only after the actual warning reaches the screen.
    mov ax, 0xB800
    mov es, ax
    cmp dword [es:22*160+3*2], 0x07410757 ; WA
    jne .done
    cmp dword [es:22*160+5*2], 0x074E0752 ; RN
    jne .done
    inc byte [ST_WAIT]
    cmp byte [ST_WAIT], 8      ; Wait well beyond the tone before dismissing.
    jb .done
%ifdef EMULATOR_SETUP_BAD_CMOS
    call setup_test_warning_visible ; Prove the real warning before VGA rebuild.
%endif
%ifdef EMULATOR_SETUP_POWERLOSS
    mov bl, 0xE0
    cmp byte [ST_WAIT], 8
    je .send
    mov bl, 0x53              ; Delete alone dismisses and requests setup.
.send:
%else
    mov bl, 28                ; Enter releases the warning, not setup itself.
%endif
    mov al, 0xD2
    call kbc_command
    jc setup_test_tick.fail
    mov al, bl
    call kbc_write_data
    jc setup_test_tick.fail
%ifdef EMULATOR_SETUP_POWERLOSS
    cmp byte [ST_WAIT], 8
    je .done
%endif
    set_vector 0x1C, default_iret
.done:
    pop es
    pop ds
    popad
    iret

setup_test_warning_visible:
    pushad
    push es
    mov ax, 0xB800
    mov es, ax
    xor di, di
    mov cx, 1994
.warning:
    cmp dword [es:di], 0x07410757 ; WA
    jne .next
    cmp dword [es:di + 4], 0x074E0752 ; RN
    jne .next
    cmp dword [es:di + 8], 0x074E0749 ; IN
    jne .next
    cmp word [es:di + 12], 0x0747 ; G
    je .seen
.next:
    add di, 2
    loop .warning
    mov al, 0x6E
    call emulator_exit
    jmp hard_halt
.seen:
    pop es
    popad
    ret
%endif

%ifndef EMULATOR_CHIPSET_TEST
setup_test_begin:
%ifdef EMULATOR_SETUP_RECOVERY
    ; Observe persisted defaults, then exercise the real warm-reset entry.
    cmp byte [fs:C_VALID], 1
    jne setup_test_tick.fail
    mov ah, 4
    int 0x1A
    jc setup_test_tick.fail
    cmp cx, 0x1980
    jne setup_test_tick.fail
    cmp dx, 0x0101
    jne setup_test_tick.fail
    mov ah, 2
    int 0x1A
    jc setup_test_tick.fail
    cmp cx, 0
    jne setup_test_tick.fail
    cmp dh, 10
    ja setup_test_tick.fail
    test byte [fs:C_ERROR], 5
    jz .recovered
    mov ax, 0x0040
    mov ds, ax
    jmp warm_reset
.recovered:
    mov al, 0x67
    call emulator_exit
    jmp hard_halt
%endif
    pushad
    push es
    xor ax, ax
    mov es, ax
%ifdef EMULATOR_SETUP_INVALID_NOTICE
%ifndef EMULATOR_SETUP_BAD_CMOS
    call setup_test_warning_visible
%endif
%endif
%ifdef EMULATOR_SETUP_POWERLOSS
    mov dword [es:ST_PHASE], 2 ; Notice Delete already supplied the request.
%else
    mov dword [es:ST_PHASE], 0
%endif
    mov byte [es:0x0626], 0
    mov dword [es:0x046C], 123 ; Different from the time confirmed below.
%ifdef EMULATOR_SETUP_POWERLOSS
    cmp byte [fs:S_SETUP_REQUEST], 1
    jne setup_test_tick.fail
%endif
    set_vector 0x1C, setup_test_tick
    pop es
    popad
    ret

setup_test_tick:
    pushad
    push ds
    push es
    push fs
    xor ax, ax
    mov ds, ax
    inc byte [0x0626]
    cmp byte [0x0626], 180
    jb .start
    mov al, 0x75              ; Bounded failure for stalled scripted input.
    call emulator_exit
.start:
%ifndef EMULATOR_SETUP_POWERLOSS
    cmp byte [ST_PHASE], 0
    jne .delete
    inc byte [ST_PHASE]
    mov al, 0xE0
    jmp .scan
.delete:
    cmp byte [ST_PHASE], 1
    jne .ui
    inc byte [ST_PHASE]
    mov al, 0x53
    jmp .scan
%endif
.ui:
    cmp word [0x044A], 80
    jne .fail
    cmp byte [0x0484], 24
    jne .done
    cmp word [0x0485], 16
    jne .done                 ; Mode/font change may be interrupted mid-update.
    mov ax, 0xB800
    mov es, ax
    cmp word [es:(0 * 80 + 34) * 2], 0x1F62 ; bAIos Setup real text cell.
    jne .done                 ; Wait for rendering, not just the mode switch.
    cmp byte [ST_PHASE], 2
    jne .idle
%ifdef EMULATOR_SETUP_CLOCK24
    cmp byte [fs:U_CLOCK24], 1 ; Saved24-hour input survived actual POST seeking.
    jne .fail
    cmp dword [es:7 * 160 + UI_VALUE_COL * 2], 0x07340732 ;24
    jne .done                 ; IRQ0 may interrupt before this field is drawn.
%endif
%ifdef EMULATOR_SETUP_INVALID_DATE
    cmp dword [es:5 * 160 + 49 * 2], 0x07310730 ; 01
    jne .done
%endif
%ifdef EMULATOR_SETUP_POWERLOSS
    cmp dword [es:6 * 160 + 49 * 2], 0x07320731
    jne .done
    cmp dword [es:6 * 160 + 51 * 2], 0x0730073A
    jne .done
    cmp dword [es:6 * 160 + 53 * 2], 0x073A0730
    jne .done
    cmp dword [es:6 * 160 + 55 * 2], 0x07300730
    jne .done
%endif
    inc byte [ST_WAIT]
    cmp byte [ST_WAIT], 3
    jb .done                    ; Allow actual VGA retraces before snapshot.
%ifndef EMULATOR_SETUP_IDE_SCREEN
    call setup_test_snapshot
%endif
    xor bx, bx
.save_clock:
    mov ax, [es:6 * 160 + 49 * 2 + bx]
    mov [ST_CLOCK + bx], ax
    add bx, 2
    cmp bx, 16
    jb .save_clock
    mov ax, [0x046C]
    mov [ST_SECOND], ax
    inc byte [ST_PHASE]
    jmp .done
.idle:
    cmp byte [ST_PHASE], 3
    jne .script
    mov ax, [0x046C]
    sub ax, [ST_SECOND]
    cmp ax, 22
    jb .done
    xor bx, bx
.compare_clock:
    mov ax, [es:6 * 160 + 49 * 2 + bx]
    cmp ax, [ST_CLOCK + bx]
%ifdef EMULATOR_SETUP_POWERLOSS
    jne .fail                 ; Unconfirmed time remains its default.
%else
    jne .advanced
%endif
    add bx, 2
    cmp bx, 16
    jb .compare_clock
%ifndef EMULATOR_SETUP_POWERLOSS
    jmp .fail
%endif
.advanced:
    inc byte [ST_PHASE]
.script:
    cmp byte [ST_PHASE], 4
    jne .done
    movzx bx, byte [ST_KEY]
%ifdef EMULATOR_SETUP_CLOCK24
    cmp bx, 7                ; Format toggled twice, focus returned to Date.
    jne .format_captured
    cmp byte [fs:U_CLOCK24], 1
    jne .done
    cmp byte [fs:U_FIELD], 0
    jne .done
    inc byte [ST_WAIT]
    cmp byte [ST_WAIT], 6
    jb .done
    call setup_test_snapshot
.format_captured:
%endif
%ifdef EMULATOR_SETUP_IDE_SCREEN
    cmp bx, setup_test_capture_key
    jne .ide_key
    ; Wait for the actual target text and VGA retraces, not just queued input.
%if EMULATOR_SETUP_IDE_SCREEN = 1
    cmp dword [es:4 * 160 + UI_LABEL_COL * 2], 0x0B490B44 ; DI(sk)
%elif EMULATOR_SETUP_IDE_SCREEN = 2
    cmp dword [es:5 * 160 + UI_POPUP_TEXT * 2], 0x1B481B50 ; PH(oenix)
%elif EMULATOR_SETUP_IDE_SCREEN = 4
    cmp dword [es:11 * 160 + UI_LABEL_COL * 2], 0x07720750 ; Pr(imary controller)
%elif EMULATOR_SETUP_IDE_SCREEN = 5
    cmp dword [es:8 * 160 + UI_VALUE_COL * 2], 0x1F751F41 ; Au(to selected)
%elif EMULATOR_SETUP_IDE_SCREEN = 6
    cmp dword [es:6 * 160 + UI_VALUE_COL * 2], 0x1F6F1F4E ; No(ne selected)
%else
    cmp dword [es:8 * 160 + UI_POPUP_TEXT * 2], 0x1B451B53 ; SE(lect)
%endif
    jne .done
    inc byte [ST_WAIT]
    cmp byte [ST_WAIT], 6
    jb .done
    call setup_test_snapshot
.ide_key:
    mov al, [cs:setup_test_keys + bx]
    test al, al
    jz .done
    inc byte [ST_KEY]
    jmp .scan
%endif
    cmp bx, setup_test_time_key
    jne .time_checked
    cmp byte [fs:U_EDIT], 0
    jne .done                 ; Enter queued; wait for the actual setter to return.
    pushad
    mov ah, 2
    int 0x1A
    jc .fail
%ifdef EMULATOR_SETUP_POWERLOSS
    cmp cx, 0x1200
    jne .fail
    cmp dh, 1
%else
    cmp cx, 0x1345
    jne .fail
    cmp dh, 0x56
    jb .fail
    cmp dh, 0x57              ; The free-running RTC may advance before this tick.
%endif
    ja .fail
    popad
.time_checked:
%ifndef EMULATOR_SETUP_POWERLOSS
    cmp bx, setup_test_popup_key
    jne .popup_checked
    cmp dword [es:8 * 160 + UI_POPUP_TEXT * 2], 0x1B451B53 ; SELECT VALUE actual text.
    jne .done
    cmp dword [es:10 * 160 + UI_POPUP_TEXT * 2], 0x176F174E ; Not installed
    jne .done
    cmp word [es:15 * 160 + UI_POPUP_TEXT * 2], 0x1732 ;2.88 MB
    jne .done
%endif
.popup_checked:
%ifdef EMULATOR_SETUP_POWERLOSS
    cmp bx, 11                ; Date confirmed, time not confirmed yet.
    jne .next_key
    cmp byte [fs:U_EDIT], 0
    jne .done
    cmp dword [es:5 * 160 + 49 * 2], 0x1F301F31 ; 10
    jne .fail
    cmp dword [es:5 * 160 + 51 * 2], 0x1F301F2F ; /0
    jne .fail
    cmp dword [es:5 * 160 + 54 * 2], 0x1F321F2F ; /2
    jne .fail
    cmp dword [es:5 * 160 + 57 * 2], 0x1F361F32 ; 26
    jne .fail
    mov al, 0x0E
    call rtc_read
    test al, 0x80
    jz .fail                  ; Date alone must not clear the loss diagnostic.
.next_key:
%endif
    mov al, [cs:setup_test_keys + bx]
    test al, al
    jz .done
    inc byte [ST_KEY]
.scan:
    push ax
    mov al, 0xD2
    call kbc_command
    pop ax
    jc .fail
    call kbc_write_data
    jc .fail
.done:
    pop fs
    pop es
    pop ds
    popad
    iret
.fail:
    mov al, 0x7A
    call emulator_exit
    jmp hard_halt

%endif
; Unit tester captures the actual retained-VGA output, not just BDA state.
setup_test_snapshot:
    mov dx, POST_PORT
    mov si, setup_test_trigger
    mov cx, 7
.trigger:
    cs lodsb
    out dx, al
    loop .trigger
    mov dx, 0x0501
    mov al, 1
    out dx, al
    inc dx
    mov al, 1
    out dx, al
    mov di, ST_SHOT
    mov cx, 12
.read:
    in al, dx
    mov [di], al
    inc di
    loop .read
    mov ax, [ST_SHOT]
    mov [ST_WIDTH], ax
    cmp ax, 720
    je .height
    cmp ax, 640
    jne .fail
.height:
    mov ax, [ST_SHOT + 2]
    mov [ST_HEIGHT], ax
    cmp ax, 400
    jne .fail
    ret
.fail:
    mov al, 0x7A
    call emulator_exit
    jmp hard_halt

%ifndef EMULATOR_CHIPSET_TEST
setup_test_end:
    pushad
    push es
    xor ax, ax
    mov es, ax
    mov bl, 0x7B
    cmp byte [es:ST_PHASE], 4
    jne .fail
    mov bl, 0x7C
    cmp byte [es:ST_KEY], setup_test_keys_end - setup_test_keys - 1
    jne .fail
    mov bl, 0x7D
    cmp byte [es:0x0484], 24
    jne .fail
    mov bl, 0x7E
    cmp word [es:0x0485], 16
    jne .fail
%ifdef EMULATOR_SETUP_CLOCK24
    cmp byte [fs:C_CLOCK24], 1 ; Actual POST seek and summary retained the preference.
    jne .fail
%endif
    mov bl, 0x7F
    cmp word [es:0x0068], int1a
    jne .vector_fail
    cmp word [es:0x006A], 0xF000
    jne .vector_fail
%ifdef EMULATOR_SETUP_IDE_SCREEN
setup_test_time_key equ 20
setup_test_popup_key equ 24
    set_vector 0x1C, default_iret
    call setup_test_dump
    jmp .pass
%endif
    mov ah, 4
    int 0x1A
    jc .fail
    mov bl, 0x77
%ifdef EMULATOR_SETUP_POWERLOSS
    cmp cx, 0x2026
%else
    cmp cx, 0x2028
%endif
    jne .fail
    mov bl, 0x78
%ifdef EMULATOR_SETUP_POWERLOSS
    cmp dx, 0x1001
%else
    cmp dx, 0x0229
%endif
    jne .fail
    ; Actual startup called rtc_sync_ticks after UI exit, not before the edit.
    mov bl, 0x76
    mov ah, 2
    int 0x1A
    jc .fail
%ifdef EMULATOR_SETUP_POWERLOSS
    cmp cx, 0x1200
    jne .fail
    cmp dh, 3
%else
    cmp cx, 0x1345
    jne .fail
    cmp dh, 0x59
%endif
    ja .fail
    mov al, dh
    call rtc_from_bcd
    movzx eax, al
    ; CX was checked above: use its exact hour/minute base in seconds.
%ifdef EMULATOR_SETUP_POWERLOSS
    add eax, 43200           ;12:00
%else
    add eax, 49500           ;13:45
%endif
    mov ecx, 1193182
    mul ecx
    shrd eax, edx, 16
    sub eax, [es:0x046C]
    add eax, 20              ; At most one second between the samples.
    cmp eax, 40
    ja .fail
    set_vector 0x1C, default_iret
    cmp byte [fs:S_PRESENT], 1
    jne .pass
    call setup_test_dump
.pass:
    mov al, 0x67
    call emulator_exit
.fail:
    mov al, bl
    call emulator_exit
    jmp hard_halt
.vector_fail:
    mov bl, 0x79
    jmp .fail

setup_test_keys:
%ifdef EMULATOR_SETUP_RECOVERY
    ; Recovery exits or resets before installing the normal editor stimulus.
setup_test_time_key equ 0
setup_test_popup_key equ 0
    db 0
%else
%ifdef EMULATOR_SETUP_IDE_SCREEN
    ; Drives -> master. Auto geometry is gray and unselectable.
%if EMULATOR_SETUP_IDE_SCREEN = 4
    db 0x50,28
%elif EMULATOR_SETUP_IDE_SCREEN = 5
    db 0x50,28,0x50,0x50
%else
    db 0x50,28,0x50,0x50,28
%endif
%if EMULATOR_SETUP_IDE_SCREEN = 2
    db 0x50,28,0x50 ; Type menu, select Type1 so numeric colors are visible.
%elif EMULATOR_SETUP_IDE_SCREEN = 3
    db 0x50,0x50,0x50,28 ; Auto skips geometry -> translation -> block menu.
%elif EMULATOR_SETUP_IDE_SCREEN = 6
    db 0x50,0x4B ; Auto -> None; type stays selectable, other values gray.
%endif
setup_test_capture_key equ $ - setup_test_keys
%if EMULATOR_SETUP_IDE_SCREEN = 2 || EMULATOR_SETUP_IDE_SCREEN = 3
    db 1 ; Dismiss popup before leaving the device page.
%endif
%if EMULATOR_SETUP_IDE_SCREEN = 4 || EMULATOR_SETUP_IDE_SCREEN = 5
    db 1,1,28,0 ; Pane back, discard, confirm.
%else
    db 1,1,1,28,0 ; Device back, pane back, discard, confirm.
%endif
%else
%ifdef EMULATOR_SETUP_POWERLOSS
    ; MM/DD/YYYY; then noon with explicit PM.
    db 15,28,2,11,11,2,3,11,3,7,28
    db 0x50,28,2,3,11,11,11,11,0x19,28
%else
%ifdef EMULATOR_SETUP_CLOCK24
    ; Retained24-hour input -> quick-change12 ->24 -> actual date/time edit.
    db 15,0x50,0x50,0x4D,0x4D,0x48,0x48,28
%else
    db 15,28
%endif
    ; 02/29/2028: immediate leap-day edit.
    db 11,3,3,10,3,11,3,9,28
    ; Confirm a different time before exit, including without a disk.
%ifdef EMULATOR_SETUP_CLOCK24
    db 0x50,28,2,4,5,6,6,7,28 ; 13:45:56
%else
    db 0x50,28,11,2,5,6,6,7,0x19,28 ; 01:45:56 PM
%endif
%endif
setup_test_time_key equ $ - setup_test_keys
%ifdef EMULATOR_SETUP_POWERLOSS
setup_test_popup_key equ 0
    ; Return to sidebar, cancel discard once, then reopen and confirm.
    db 1,1,1,1,28,0
%else
    ; Drives popup lists all six types; cancel it. Then cancel/confirm discard.
    db 1,0x50,15,28
setup_test_popup_key equ $ - setup_test_keys
    db 1,1,1,1,1,28,0
%endif
%endif
%endif
setup_test_keys_end:
%endif
setup_test_trigger db '86Box',1,5

; Export actual captured VGA pixels to the disposable HDD after UI exit.
; 16 rows fit below64KiB; no BIOS disk transaction happens inside an IRQ.
setup_test_dump:
    pushad
    push ds
    push es
    xor ax, ax
    mov ds, ax
    mov es, ax
    mov eax, [ST_WIDTH]
    mov [0x0A00], eax
    mov word [0x0800], 0x0010
    mov word [0x0802], 1
    mov word [0x0804], 0x0A00
    mov word [0x0806], 0
    mov dword [0x0808], 63
    mov dword [0x080C], 0
    mov si, 0x0800
    mov ax, 0x4300
    mov dl, 0x80
    int 0x13
    jc .fail
    mov word [0x0804], 0
    mov word [0x0806], 0x1000
    mov dword [0x0808], 64
    mov ax, [ST_WIDTH]
    shr ax, 3                 ; width*16*4 /512 sectors per tile.
    mov [0x0802], ax
    xor bp, bp
.tile:
    mov dx, 0x0501
    mov al, 2
    out dx, al
    inc dx
    mov ax, [ST_WIDTH]
    call .word
    mov ax, 16
    call .word
    mov ax, [ST_SHOT + 8]
    call .word
    mov ax, bp
    add ax, [ST_SHOT + 10]
    call .word
    mov ax, 0x1000
    mov es, ax
    xor di, di
    mov cx, [ST_WIDTH]
    shl cx, 6
    rep insb
    mov si, 0x0800
    mov ax, 0x4300
    mov dl, 0x80
    int 0x13
    jc .fail
    movzx eax, word [0x0802]
    add [0x0808], eax
    add bp, 16
    cmp bp, 400
    jb .tile
    pop es
    pop ds
    popad
    ret
.word:
    out dx, al
    mov al, ah
    out dx, al
    ret
.fail:
    mov al, 0x73
    call emulator_exit
    jmp hard_halt
