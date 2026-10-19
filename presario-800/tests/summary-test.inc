; Test-only terminal assertions; production POST never waits for this fixture.
summary_test_begin:
    pushad
    push ds
    push es
    xor ax, ax
    mov ds, ax
    cmp byte [0x49E], 2
    jne hard_halt
    cmp word [0x44A], 80
    jne hard_halt
    cmp byte [0x484], 24
    jne hard_halt
    cmp word [0x485], 16
    jne hard_halt
    ; Compare actual publication against the corresponding rendered cells.
    cmp byte [fs:S_SETUP_REQUEST], 0
    jne hard_halt
    mov ax, 0xB800
    mov es, ax
    cmp dword [es:37*2], 0x1F411F62
    jne hard_halt
%ifdef EMULATOR_CHIPSET_SUMMARY
    ; Summary must retain the selected primary-cache policy.
    mov eax, cr0
    and eax, 0x60000000
    test byte [fs:C_CHIP+4], PRIMARY_CACHE_EN
    jnz .l1_on
    cmp eax, 0x60000000
    jne hard_halt
    jmp .l1_checked
.l1_on:
    test eax, eax
    jnz hard_halt
.l1_checked:
    ; Independent d824 fixture:4MB RAM,64MB primary disk, no floppies.
    cmp word [0x450], 0x0D00
    jne hard_halt
    cmp dword [es:2*160+58*2], 0x07330736 ;63[9] KiB
    jne hard_halt
    cmp dword [es:3*160+58*2], 0x07300733 ;30[72] KiB
    jne hard_halt
    cmp dword [es:3*160+20*2], 0x07650744 ;Detected x87
    jne hard_halt
    cmp dword [es:4*160+20*2], 0x076F074E ;Not detected L2
    jne hard_halt
    cmp dword [es:6*160+20*2], 0x076F074E ;Not installed A
    jne hard_halt
    cmp dword [es:7*160+20*2], 0x076F074E ;Not installed B
    jne hard_halt
    cmp dword [es:6*160+58*2], 0x07330730 ;03[F8] COM1
    jne hard_halt
    cmp dword [es:7*160+58*2], 0x07330730 ;03[78] LPT1
    jne hard_halt
%ifdef EMULATOR_CHIPSET_SUMMARY_LONG
    cmp dword [es:9*160+23*2], 0x07440753 ;SD adapter model at its new anchor.
    jne hard_halt
    cmp word [es:9*160+62*2], 0x0758 ;Fortieth model character.
    jne hard_halt
    mov si, summary_long_suffix
%else
    mov si, summary_short_suffix
%endif
    mov di, 9*160+64*2
    mov cx, 15
.suffix:
    cs lodsb
    mov ah, 7
    cmp al, '['
    je .bracket
    cmp al, ']'
    jne .suffix_check
.bracket:
    mov ah, 0x0B
.suffix_check:
    cmp [es:di], ax
    jne hard_halt
    add di, 2
    loop .suffix
    cmp word [es:9*160+63*2], 0x0720 ;Model/bracket separator.
    jne hard_halt
    cmp dword [es:10*160+23*2], 0x076F074E ;Not detected slave
    jne hard_halt
    ; All13 rows have the independent expected colors, including blank neighbors.
    mov si,summary_test_attributes
    mov di,1
.attribute_run:
    cs lodsw                     ; Independent count/color pairs save fixture ROM.
    test al,al
    jz .attributes_done
    movzx cx,al
    mov al,ah
.attributes:
    cmp [es:di],al
    jne hard_halt
    add di,2
    loop .attributes
    jmp .attribute_run
.attributes_done:
    cmp dword [es:2*160+40*2],0x0B610B42 ;Base
    jne hard_halt
    cmp dword [es:3*160+40*2],0x0B780B45 ;Extended
    jne hard_halt
    cmp dword [es:4*160+40*2],0x0B650B4D ;Memory Banks
    jne hard_halt
    cmp dword [es:6*160+40*2],0x0B4F0B43 ;COM
    jne hard_halt
    cmp dword [es:7*160+40*2],0x0B500B4C ;LPT
    jne hard_halt
    mov di,10*160+38*2 ;Absent slave leaves kind/capacity/PIO empty.
    mov cx,41
.slave_blank:
    cmp word [es:di],0x0720
    jne hard_halt
    add di,2
    loop .slave_blank
    cmp word [es:11*160],0x0BC8
    jne hard_halt
    cmp word [es:11*160+158],0x0BBC
    jne hard_halt
    mov di,12*160
    mov cx,13*80
.blank:
    cmp word [es:di],0x0720
    jne hard_halt
    add di,2
    loop .blank
    ; The external renderer needs a frame before its snapshot. Fixture only.
%ifdef EMULATOR_PAUSE_ONLY
    ; Pause directly over the completed summary, then with runtime state.
    ; Both must stop before the interrupt returns and consume the resume key.
    call post_pause_test_begin
    call post_pause_test_end
    mov byte [0x0400 + KB_POST_STATE], 0
    call post_pause_test_begin
    call post_pause_test_end
    mov byte [0x0400 + KB_POST_STATE], 2
%endif
    push bp
    push dword [0x46C]
    mov bp, sp
    sti
.frame:
    hlt
    mov eax, [0x46C]
    sub eax, [ss:bp]
    cmp eax, 2
    jb .frame
    add sp, 4
    pop bp
    call setup_test_snapshot
    mov byte [CT_CAPTURE], 1
    call chipset_test_capture_drain
%endif
    pop es
    pop ds
    popad
    ret

%ifdef EMULATOR_CHIPSET_SUMMARY
summary_short_suffix db '[64 MB PIO]    '
summary_long_suffix db '[131071 MB PIO]'
%ifdef EMULATOR_CHIPSET_SUMMARY_LONG
; Change only test publication before the production renderer runs.
summary_test_prepare_long:
    pushad
    push es
    mov ax, fs
    mov es, ax
    mov si, summary_long_model
    mov di, S_MODEL
    mov cx, 41
    cs rep movsb
    mov dword [fs:S_CAPACITY], 0x0FFFFFFF
    pop es
    popad
    ret
summary_long_model db 'SD ADAPTER MODEL WITH FULL NAME ', 'XXXXXXXX',0
%endif
; Fixture-only attribute grid. Character/value assertions above remain separate.
%macro summary_attribute_row 2
    db 1,0x0B, 2,7, %1,0x0B, 40-3-%1,7
%if %2
    db %2,0x0B
%endif
    db 79-40-%2,7, 1,0x0B
%endmacro
summary_test_attributes:
    db 3,0x1F, 19,0x1B, 36,0x1F, 10,0x1B, 12,0x1F
    db 80,0x0B                  ; Complete top border.
    summary_attribute_row 9,11
    summary_attribute_row 3,15
    summary_attribute_row 8,12
    db 80,0x0B
    summary_attribute_row 14,9
    summary_attribute_row 14,9
    db 80,0x0B
    db 1,0x0B, 2,7, 18,0x0B, 43,7, 1,0x0B ; Through opening bracket64.
%ifdef EMULATOR_CHIPSET_SUMMARY_LONG
    db 13,7, 2,0x0B ;Closing bracket78 and border79.
%else
    db 9,7, 1,0x0B, 4,7, 1,0x0B ;Closing bracket74 and border79.
%endif
    summary_attribute_row 17,0
    db 80,0x0B
    db 0,0                      ; End of all960 expected attributes.
%unmacro summary_attribute_row 2
%endif
