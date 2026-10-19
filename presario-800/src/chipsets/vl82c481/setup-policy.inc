chipset_ui_parameters:
    call chipset_ui_descriptor
    movzx bx, byte [cs:si+2]
    mov cl, [cs:si+3]
    mov al, [fs:U_CHIP+bx]
    shr al, cl
    and al, [cs:si+4]
    mov [fs:U_CHIP_VALUE], al
    mov cx, [cs:si+5]
    cmp byte [fs:U_CHIP_SCREEN], 1
    jne .values
    cmp byte [fs:U_FIELD], 2
    jne .values
    push si
    mov si, U_CHIP
    call chipset_fast_available
    pop si
    mov si, chip_mode_choices
    jc .without_fast
    inc al                  ; Stored Normal/Compatibility/Manual/Fast -> display order.
    and al, 3
    mov [fs:U_CHIP_VALUE], al
    jmp .ready
.without_fast:
    add si, 2               ; Normal, Compatibility, Manual when Fast is unavailable.
    mov cx, 3
    jmp .ready
.values:
    mov si, [cs:si+7]
.ready:
    mov bx, U_CHIP_VALUE
    ret

; CL=field. Preset access timings use the shared unavailable-field rule.
chipset_ui_editable:
    cmp byte [fs:U_CHIP_SCREEN], 1
    jne .good
    cmp cl, 3
    jb .good
    cmp cl, 7
    jbe .timing
    jmp .good
.timing:
    push ax
    mov al, [fs:U_CHIP+10]
    and al, 0xC0
    cmp al, 0x80
    pop ax
    jne .bad
.good:
    clc
    ret
.bad:
    stc
    ret

chipset_ui_commit:
    pushad
    mov cl, [fs:U_FIELD]
    call chipset_ui_editable
    jc .done
    call chipset_ui_descriptor
    movzx bx, byte [cs:si+2]
    mov cl, [cs:si+3]
    mov al, [cs:si+4]
    shl al, cl
    not al
    and [fs:U_CHIP+bx], al
    mov al, [fs:U_CHIP_VALUE]
    cmp byte [fs:U_CHIP_SCREEN], 1
    jne .value
    cmp byte [fs:U_FIELD], 2
    jne .value
    push si
    mov si, U_CHIP
    call chipset_fast_available
    pop si
    jc .value
    dec al                  ; Convert menu order back to the stable CMOS mode codes.
    and al, 3
.value:
    shl al, cl
    or [fs:U_CHIP+bx], al
    test bx, bx
    jnz .metadata
    ; Every RAMTMG edit explicitly becomes Manual, including cycle start.
    and byte [fs:U_CHIP+10], 0x3F
    or byte [fs:U_CHIP+10], 0x80
    jmp .done
.metadata:
    cmp byte [fs:U_CHIP_SCREEN], 1
    jne .done
    cmp byte [fs:U_FIELD], 3
    jae .done
    mov si, U_CHIP
    call chipset_profile_apply
.done:
    popad
    ret

chipset_ui_change:
    cmp byte [fs:U_CHIP_SCREEN], 0
    je .done
    mov cl, [fs:U_FIELD]
    call chipset_ui_editable
    jc .done
    pushad
    mov dl, 1
    cmp ah, 0x4B
    jne .parameters
    mov dl, -1
.parameters:
    call chipset_ui_parameters
    movzx ax, byte [fs:U_CHIP_VALUE]
    movsx dx, dl
    add ax, dx
    test ax, ax
    jns .upper
    mov ax, cx
    dec ax
.upper:
    cmp ax, cx
    jb .store
    xor ax, ax
.store:
    mov [fs:U_CHIP_VALUE], al
    call chipset_ui_commit
    popad
.done:
    ret

; Carry set when the board rendered a special choice popup; otherwise use enums.
chipset_ui_choice_draw:
    cmp byte [fs:U_CHIP_SCREEN], 1
    jne .ordinary
    cmp byte [fs:U_FIELD], 6
    jne .ordinary
    call chipset_ui_cas_draw
    stc
    ret
.ordinary:
    clc
    ret

; AX=choice index, SI=values word, BH=logical color, ES:DI=position.
; Both field and popup rendering use this owner; no draft buffer is borrowed.
chipset_ui_option_text:
    pushad
    cmp si, CHIP_VALUES_FAST_REGION
    je .fast_region
    cmp si, CHIP_VALUES_CACHE_REGION
    je .cache_region
    mov bp, ax
    shl bp, 1
    mov si, [cs:si+bp]
    call setup_text
    jmp .done
.fast_region:
    movzx eax, al
    shl eax, 16
    mov cl, 6
    call setup_hex_number
    add di, 6*2
    mov si, chip_range_dash
    call setup_text
    add di, 2
    or eax, 0xFFFF
    call setup_hex_number
    jmp .done
.cache_region:
    movzx eax, al
    mov cl, 7
    mov si, chip_range_512k
    cmp al, 32
    jae .large_region
    shl eax, 19
    jmp .cache_text
.large_region:
    mov si, chip_range_8m
    cmp al, 48
    jae .rom_region
    sub eax, 32
    shl eax, 23
    jmp .cache_text
.rom_region:
    mov si, chip_range_16k
    sub eax, 48
    shl eax, 14
    add eax, 0xC0000
    mov cl, 5
.cache_text:
    call setup_hex_number
    movzx dx, cl
    shl dx, 1
    add di, dx
    call setup_text
.done:
    popad
    ret
