post_ui_setup_pair:
    push ax
    mov ah, al
    shr al, 4
    add al, '0'
    mov [fs:di], al
    inc di
    mov al, ah
    and al, 15
    add al, '0'
    mov [fs:di], al
    inc di
    pop ax
    ret

; Read live RTC on idle iterations. Edit buffer is separate and never touched.
post_ui_setup_clock:
    pushad
    mov di, U_DATE
    mov ah, 4
    int 0x1A
    jc .bad_date
    and byte [fs:U_CONFIRMED], 0xFD
    mov al, dh
    call post_ui_setup_pair
    mov byte [fs:di], '/'
    inc di
    mov al, dl
    call post_ui_setup_pair
    mov byte [fs:di], '/'
    inc di
    mov al, ch
    call post_ui_setup_pair
    mov al, cl
    call post_ui_setup_pair
    mov byte [fs:di], 0
    jmp .time
.bad_date:
    test byte [fs:U_CONFIRMED], 2
    jnz .time
    mov dword [fs:U_DATE], '01/0'
    mov dword [fs:U_DATE + 4], '1/19'
    mov word [fs:U_DATE + 8], '80'
    mov byte [fs:U_DATE + 10], 0
.time:
    mov ah, 2
    int 0x1A
    jc .bad_time
    and byte [fs:U_CONFIRMED], 0xFE
    mov [fs:U_DST], dl
    mov [fs:U_HOUR], ch
    mov [fs:U_MINUTE], cl
    mov [fs:U_SECOND], dh
    jmp .display
.bad_time:
    mov al, 0x0B
    call post_ui_rtc_read
    and al, 1
    mov [fs:U_DST], al
    test byte [fs:U_CONFIRMED], 1
    jnz .display
    mov word [fs:U_HOUR], 0
    mov byte [fs:U_SECOND], 0
.display:
    call post_ui_setup_format_time
    cmp byte [fs:U_PAGE], 0
    jne .done
    mov si, U_DATE
    mov di, 5 * 160 + 49 * 2
    mov bh, 7
    cmp byte [fs:U_FOCUS], 1
    jne .date
    cmp byte [fs:U_FIELD], 0
    jne .date
    mov bh, 0x1F
.date:
    call post_ui_setup_value
    mov si, U_TIME
    mov di, 6 * 160 + 49 * 2
    mov bh, 7
    cmp byte [fs:U_FOCUS], 1
    jne .time_field
    cmp byte [fs:U_FIELD], 1
    jne .time_field
    mov bh, 0x1F
.time_field:
    call .clear_suffix
    call post_ui_setup_value
.done:
    popad
    ret
.clear_suffix:
    push ax
    mov ah, bh
    mov al, ' '
    call post_ui_setup_color
    ; Shortening24-hour text must also erase the previous AM/PM suffix.
    mov byte [es:di + 16], ' '
    mov byte [es:di + 17], ah
    mov byte [es:di + 18], ' '
    mov byte [es:di + 19], ah
    mov byte [es:di + 20], ' '
    mov byte [es:di + 21], ah
    pop ax
    ret

post_ui_setup_format_time:
    pushad
    mov di, U_TIME
    mov al, [fs:U_HOUR]
    cmp byte [fs:U_CLOCK24], 1
    je .hour
    test al, al
    jnz .afternoon
    mov al, 0x12
    jmp .hour
.afternoon:
    cmp al, 0x12
    jbe .hour
    sub al, 0x12
    das
.hour:
    call post_ui_setup_pair
    mov byte [fs:di], ':'
    inc di
    mov al, [fs:U_MINUTE]
    call post_ui_setup_pair
    mov byte [fs:di], ':'
    inc di
    mov al, [fs:U_SECOND]
    call post_ui_setup_pair
    cmp byte [fs:U_CLOCK24], 1
    je .end
    mov byte [fs:di], ' '
    inc di
    mov al, 'A'
    cmp byte [fs:U_HOUR], 0x12
    jb .suffix
    mov al, 'P'
.suffix:
    mov [fs:di], al
    inc di
    mov byte [fs:di], 'M'
    inc di
.end:
    mov byte [fs:di], 0
    popad
    ret

post_ui_setup_edit_begin:
    mov byte [fs:U_POSITION], 0
    mov si, U_DATE
    mov di, U_BUFFER
    mov cx, 11
    mov al, 1
    cmp byte [fs:U_FIELD], 0
    je .copy
    mov si, U_TIME
    mov cx, 12
    mov al, 2
.copy:
    mov [fs:U_EDIT], al
.byte:
    mov al, [fs:si]
    mov [fs:di], al
    inc si
    inc di
    loop .byte
    ret

post_ui_setup_parse_pair:
    mov al, [fs:si]
    sub al, '0'
    shl al, 4
    inc si
    mov ah, [fs:si]
    sub ah, '0'
    or al, ah
    inc si
    ret

post_ui_setup_edit_apply:
    mov si, U_BUFFER
    call post_ui_setup_parse_pair
    cmp byte [fs:U_EDIT], 1
    jne .time
    mov dh, al
    inc si
    call post_ui_setup_parse_pair
    mov dl, al
    inc si
    call post_ui_setup_parse_pair
    mov ch, al
    call post_ui_setup_parse_pair
    mov cl, al
    mov ah, 5
    int 0x1A
    jc .done
    mov di, U_DATE
    mov cx, 11
    or byte [fs:U_CONFIRMED], 2
    jmp .copy
.time:
    mov ch, al
    cmp byte [fs:U_CLOCK24], 1
    je .minutes
    cmp al, 1
    jb .invalid
    cmp al, 0x12
    ja .invalid
    cmp al, 0x12
    jne .period
    xor al, al
.period:
    cmp byte [fs:U_BUFFER + 9], 'P'
    jne .converted
    add al, 0x12
    daa
.converted:
    mov ch, al
.minutes:
    inc si
    call post_ui_setup_parse_pair
    mov cl, al
    inc si
    call post_ui_setup_parse_pair
    mov dh, al
    mov dl, [fs:U_DST]
    push cx
    push dx
    mov ah, 3
    int 0x1A
    pop dx
    pop cx
    jc .done
    mov [fs:U_HOUR], ch
    mov [fs:U_MINUTE], cl
    mov [fs:U_SECOND], dh
    or byte [fs:U_CONFIRMED], 1
    call post_ui_setup_format_time
    clc
    ret
.copy:
    ; A valid setter can succeed before the other power-lost domain is repaired.
    ; Keep its confirmed display without relaxing the shared RTC getter policy.
    mov si, U_BUFFER
.byte:
    mov al, [fs:si]
    mov [fs:di], al
    inc si
    inc di
    loop .byte
    clc
.done:
    ret
.invalid:
    stc
    ret

post_ui_setup_confirm:
    call post_ui_setup_modal_footer
    mov di, 21 * 160 + 23 * 2
    mov bh, 0x1E
    call post_ui_setup_text
.wait:
    call post_ui_setup_clock
    mov ah, 1
    int 0x16
    jnz .key
    sti
    hlt
    jmp .wait
.key:
    xor ah, ah
    int 0x16
    cmp al, 13
    je .yes
    cmp al, 'y'
    je .yes
    cmp al, 'Y'
    je .yes
    cmp al, 27
    je .no
    cmp al, 'n'
    je .no
    cmp al, 'N'
    jne .wait
.no:
    stc
    ret
.yes:
    clc
    ret

