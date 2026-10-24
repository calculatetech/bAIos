; Primary AT IDE policy. Hardware commands remain shared by CHS and EDD.
; CMOS40..5C is additive; the established38..3F record owns device enables.
ide_defaults:
    pushad
    mov si, ide_default_settings
    mov cx, IDE_SETTINGS_SIZE
.byte:
    mov al, [cs:si]
    mov [fs:di], al
    inc si
    inc di
    loop .byte
    popad
    ret
ide_copy_record:
    mov cx, IDE_RECORD_SIZE
ide_copy_bytes:
    pushad
.byte:
    mov al, [fs:si]
    mov [fs:di], al
    inc si
    inc di
    loop .byte
    popad
    ret

ide_type_valid:
    cmp al, 48
    ja .bad
    cmp al, 15
    je .bad
    cmp al, 33
    je .bad
    cmp al, 34
    je .bad
    cmp al, 45
    je .bad
    clc
    ret
.bad:
    stc
    ret

; SI=controller + two policies. Reject semantic-invalid, checksummed records.
ide_settings_valid:
    pushad
    cmp byte [fs:si], 1
    ja .bad
    inc si
    mov cx, 2
.drive:
    mov al, [fs:si + IDE_TYPE]
    call ide_type_valid
    jc .bad
    cmp byte [fs:si + IDE_TRANSLATION], 3
    ja .bad
    cmp byte [fs:si + IDE_BLOCK], 8
    ja .bad
    cmp byte [fs:si + IDE_EDD_OFF], 1
    ja .bad
    test al, al
    jz .next
    cmp al, 48
    jne .preset
    cmp word [fs:si + IDE_CYLINDERS], 0
    je .bad
    cmp byte [fs:si + IDE_HEADS], 1
    jb .bad
    cmp byte [fs:si + IDE_HEADS], 16
    ja .bad
    cmp byte [fs:si + IDE_SECTORS], 1
    jb .bad
    cmp byte [fs:si + IDE_SECTORS], 63
    ja .bad
    jmp .next
.preset:
    ; Presets are immutable numeric data, including precomp/landing zone.
    push cx
    push si
    movzx bx, al
    dec bx
    shl bx, 3
    add bx, ide_type_table
    add si, IDE_CYLINDERS
    mov cx, 8
.compare:
    mov al, [cs:bx]
    cmp al, [fs:si]
    jne .preset_bad
    inc bx
    inc si
    loop .compare
    pop si
    pop cx
    jmp .next
.preset_bad:
    pop si
    pop cx
    jmp .bad
.next:
    add si, IDE_RECORD_SIZE
    loop .drive
    popad
    clc
    ret
.bad:
    popad
    stc
    ret

ide_settings_load:
    pushad
    mov di, C_IDE
    call ide_defaults
    cmp byte [fs:C_VALID], 1
    jne .done
    mov al, 0x40
    call rtc_read
    cmp al, 'I'
    jne .done              ; Old firmware has no extension.
    mov bl, al
    mov al, 0x41
    call rtc_read
    cmp al, 'D'
    jne .invalid
    add bl, al
    mov al, 0x42
    call rtc_read
    cmp al, 1
    jne .invalid
    add bl, al
    mov al, 0x43
    call rtc_read
    add bl, al
    mov di, C_IDE
    mov dl, 0x44
    mov cx, IDE_SETTINGS_SIZE
.read:
    mov al, dl
    call rtc_read
    mov [fs:di], al
    add bl, al
    inc di
    inc dl
    loop .read
    test bl, bl
    jnz .invalid
    mov si, C_IDE
    call ide_settings_valid
    jnc .done
.invalid:
    mov di, C_IDE
    call ide_defaults
    mov byte [fs:C_VALID], 0
.done:
    popad
    ret

ide_settings_save:
    pushad
    mov si, U_IDE
    call ide_settings_valid
    jc .bad
    mov ax, 0x0040
    call rtc_write
    mov bl, 'I' + 'D' + 1
    mov si, U_IDE
    mov dl, 0x44
    mov cx, IDE_SETTINGS_SIZE
.write:
    mov ah, [fs:si]
    add bl, ah
    mov al, dl
    call rtc_write
    inc si
    inc dl
    loop .write
    neg bl
    mov al, 0x43
    mov ah, bl
    call rtc_write
    mov ax, 0x0142
    call rtc_write
    mov ax, ('D' << 8) | 0x41
    call rtc_write
    mov ax, ('I' << 8) | 0x40
    call rtc_write
    mov ax, ('I' << 8) | 0x40
    call settings_verify_byte
    jne .bad
    mov ax, ('D' << 8) | 0x41
    call settings_verify_byte
    jne .bad
    mov ax, 0x0142
    call settings_verify_byte
    jne .bad
    mov al, 0x43
    mov ah, bl
    call settings_verify_byte
    jne .bad
    mov si, U_IDE
    mov dl, 0x44
    mov cx, IDE_SETTINGS_SIZE
.verify:
    mov al, dl
    mov ah, [fs:si]
    call settings_verify_byte
    jne .bad
    inc si
    inc dl
    loop .verify
    popad
    clc
    ret
.bad:
    popad
    stc
    ret

; Late, after saved policy/recovery; preserve every non-IDE SuperIO bit.
ide_apply_controller:
    pushf
    cli
    pushad
    mov dx, SUPERIO_INDEX
    mov al, 0x55
    out dx, al
    out dx, al
    xor al, al
    out dx, al
    inc dx
    in al, dx
    and al, 0xFE
    or al, [fs:C_IDE]
    out dx, al
    dec dx
    mov al, 0xAA
    out dx, al
    popad
    popf
    ret

; IDENTIFY data is still at0000:0800. Native and translated geometry differ.
ide_identify_capacity:
    mov ax, [es:IDENTIFY_BUFFER + 2]
    mov [fs:S_NATIVE_CYLINDERS], ax
    mov al, [es:IDENTIFY_BUFFER + 6]
    mov [fs:S_NATIVE_HEADS], al
    mov al, [es:IDENTIFY_BUFFER + 12]
    mov [fs:S_NATIVE_SECTORS], al
    mov ax, [es:IDENTIFY_BUFFER + 94]
    cmp ah, 0x80
    jne .lba
    cmp al, 2
    jb .lba
    cmp al, 128
    ja .lba
    mov ah, al
    dec ah
    test al, ah
    jnz .lba
    mov [fs:S_MULTIPLE_MAX], al
.lba:
    test word [es:IDENTIFY_BUFFER + 98], 0x0200
    jz .chs
    mov eax, [es:IDENTIFY_BUFFER + 120]
    test eax, eax
    jz .bad
    cmp eax, 0x10000000
    jbe .capacity
    mov eax, 0x10000000
.capacity:
    mov [fs:S_CAPACITY], eax
    clc
    ret
.chs:
    mov byte [fs:S_CHS_ONLY], 1
    test word [es:IDENTIFY_BUFFER + 106], 1
    jz .native
    mov ax, [es:IDENTIFY_BUFFER + 108]
    mov [fs:S_NATIVE_CYLINDERS], ax
    mov al, [es:IDENTIFY_BUFFER + 110]
    mov [fs:S_NATIVE_HEADS], al
    mov al, [es:IDENTIFY_BUFFER + 112]
    mov [fs:S_NATIVE_SECTORS], al
.native:
    movzx eax, word [fs:S_NATIVE_CYLINDERS]
    movzx ecx, byte [fs:S_NATIVE_HEADS]
    cmp ecx, 1
    jb .bad
    cmp ecx, 16
    ja .bad
    imul eax, ecx
    movzx ecx, byte [fs:S_NATIVE_SECTORS]
    cmp ecx, 1
    jb .bad
    cmp ecx, 63
    ja .bad
    imul eax, ecx
    test eax, eax
    jnz .capacity
.bad:
    stc
    ret

ide_configure_disk:
    pushad
    cmp byte [fs:S_IDE + IDE_TYPE], 0
    je .translation
    mov ax, [fs:S_IDE + IDE_CYLINDERS]
    mov [fs:S_NATIVE_CYLINDERS], ax
    mov ax, [fs:S_IDE + IDE_HEADS]
    mov [fs:S_NATIVE_HEADS], ax
    movzx eax, word [fs:S_NATIVE_CYLINDERS]
    movzx ecx, byte [fs:S_NATIVE_HEADS]
    imul eax, ecx
    movzx ecx, byte [fs:S_NATIVE_SECTORS]
    imul eax, ecx
    cmp eax, [fs:S_CAPACITY]
    jae .translation
    mov [fs:S_CAPACITY], eax
.translation:
    call ide_initialize_geometry
    jc .geometry_failed
.mapping:
    mov al, [fs:S_IDE + IDE_TRANSLATION]
    test al, al
    jnz .explicit
    cmp byte [fs:S_IDE + IDE_TYPE], 0
    jne .large
    cmp byte [fs:S_CHS_ONLY], 0
    je .multiple          ; Keep the proven Auto BPB/capacity mapping.
.large:
    mov al, 2
.explicit:
    cmp al, 3
    je .lba
    movzx ecx, byte [fs:S_NATIVE_HEADS]
    movzx edx, byte [fs:S_NATIVE_SECTORS]
    test ecx, ecx
    jz .lba
    test edx, edx
    jz .lba
    mov bl, al
    mov eax, [fs:S_CAPACITY]
    push edx
    xor edx, edx
    ; Divide separately, so EDX can keep sector count after each division.
    div ecx
    pop edx
    push edx
    movzx ebx, bl
    mov esi, edx
    xor edx, edx
    div esi
    pop edx
    cmp bl, 1
    je .geometry
.halve:
    cmp eax, 1024
    jbe .geometry
    cmp ecx, 64
    ja .geometry
    shr eax, 1
    shl ecx, 1
    jmp .halve
.geometry:
    mov [fs:S_GEOMETRY], cl
    mov [fs:S_GEOMETRY + 1], dl
    jmp .multiple
.lba:
    mov word [fs:S_GEOMETRY], 0x3F20
    cmp dword [fs:S_CAPACITY], 0x001F8000
    jbe .multiple
    mov byte [fs:S_GEOMETRY], 64
    cmp dword [fs:S_CAPACITY], 0x003F0000
    jbe .multiple
    mov byte [fs:S_GEOMETRY], 128
    cmp dword [fs:S_CAPACITY], 0x007E0000
    jbe .multiple
    mov byte [fs:S_GEOMETRY], 255
.multiple:
    call ide_negotiate_multiple
    popad
    clc
    ret
.geometry_failed:
    mov byte [fs:S_PRESENT], 0
    mov dword [fs:S_CAPACITY], 0
    popad
    stc
    ret

; Auto CHS disks also need their accepted geometry initialized after reset.
ide_initialize_geometry:
    cmp byte [fs:S_CHS_ONLY], 1
    jne .unchanged
    call ata_select_ready
    jc .return
    mov al, [fs:S_NATIVE_HEADS]
    dec al
    or al, 0xA0
    or al, [fs:S_ATA_DEVICE]
    mov dx, ATA_DRIVE
    out dx, al
    mov al, [fs:S_NATIVE_SECTORS]
    mov dx, ATA_COUNT
    out dx, al
    mov al, 0x91
    call ata_no_data_command
    ret
.unchanged:
    clc
.return:
    ret

; Only a ready ATA device with an explicit type can use pre-IDENTIFY geometry.
ide_manual_fallback:
    cmp byte [fs:S_IDE + IDE_TYPE], 0
    je .done
    cmp byte [fs:S_IDENTIFY_TRACE], 3
    jne .done              ; Only a rejected EC; never a failed packet/data path.
    call ata_packet_signature
    jnc .done
    mov dx, ATA_STATUS
    in al, dx
    and al, 0xC0
    cmp al, 0x40
    jne .done
    mov byte [fs:S_CHS_ONLY], 1
    mov dword [fs:S_CAPACITY], 0x10000000
    mov byte [fs:S_PRESENT], 1
    call ide_configure_disk
    jnc .done
.bad:
    mov byte [fs:S_PRESENT], 0
    mov dword [fs:S_CAPACITY], 0
.done:
    ret

; Reassert before each multiple request. A loaded DOS driver may reset/change
; the channel between calls; no cached negotiation can prove device state.
ide_negotiate_multiple:
    pushad
    mov byte [fs:S_MULTIPLE], 0
    cmp byte [fs:S_PRESENT], 1
    jne .done
    mov bl, [fs:S_MULTIPLE_MAX]
    cmp bl, 2
    jb .done
    mov cl, [fs:S_IDE + IDE_BLOCK]
    cmp cl, 1
    je .done
    test cl, cl
    jnz .explicit
    cmp bl, 16
    jbe .negotiate
    mov bl, 16
    jmp .negotiate
.explicit:
    dec cl
    mov al, 1
    shl al, cl
    cmp al, bl
    ja .done
    mov bl, al
.negotiate:
    call ata_select_ready
    jc .fallback
    mov dx, ATA_COUNT
    mov al, bl
    out dx, al
    mov al, 0xC6
    call ata_no_data_command
    jc .fallback
    mov [fs:S_MULTIPLE], bl
    jmp .done
.fallback:
    mov byte [fs:S_STATUS], 0 ; Single-sector fallback occurs before data starts.
.done:
    popad
    ret

; Selected, ready drive; program one linear address in its supported transport.
ide_program_address:
    pushad
    mov eax, [fs:S_LBA]
    mov bl, 0xE0
    cmp byte [fs:S_CHS_ONLY], 1
    je .chs
    mov ecx, eax
    shr ecx, 24
    and cl, 15
    or bl, cl
    mov ecx, eax
    shr ecx, 8
    mov edx, eax
    shr edx, 16
    jmp .registers
.chs:
    movzx ecx, byte [fs:S_NATIVE_SECTORS]
    xor edx, edx
    div ecx
    inc dl
    push dx                  ; sector1-based
    movzx ecx, byte [fs:S_NATIVE_HEADS]
    xor edx, edx
    div ecx
    mov bl, 0xA0
    or bl, dl                ; native head
    mov ecx, eax              ; cylinder low
    shr eax, 8
    mov edx, eax              ; cylinder high
    pop ax                    ; sector
.registers:
    push ax
    mov al, bl
    or al, [fs:S_ATA_DEVICE]
    push dx
    mov dx, ATA_DRIVE
    out dx, al
    pop dx
    pop ax
    push dx
    mov dx, ATA_LBA0
    out dx, al
    inc dx
    mov al, cl
    out dx, al
    pop ax
    mov dx, ATA_LBA2
    out dx, al
    popad
    ret

ide_multiple_transfer:
    pushad
    push ds
    push es
    cld
    call ata_select_ready
    jc .error
    call ide_program_address
    mov dx, ATA_COUNT
    mov al, [fs:S_COUNT]
    out dx, al
    mov dx, ATA_COMMAND
    mov al, 0xC4
    cmp byte [fs:S_COMMAND], CMD_READ
    je .command
    inc al
.command:
    out dx, al
    mov ax, [fs:S_BUFFER_SEG]
    mov es, ax
    mov ds, ax
    mov di, [fs:S_BUFFER_OFF]
    mov si, di
.block:
    call ata_wait_drq
    jc .error
    movzx bp, byte [fs:S_COUNT]
    movzx ax, byte [fs:S_DONE]
    sub bp, ax
    movzx ax, byte [fs:S_MULTIPLE]
    cmp bp, ax
    jbe .size
    mov bp, ax
.size:
    mov cx, bp
    shl cx, 8                ;256words/sector; final block may be shorter.
    mov dx, ATA_DATA
    pushf
    cli
    cmp byte [fs:S_COMMAND], CMD_READ
    jne .write
    rep insw
    jmp .data_done
.write:
    rep outsw
.data_done:
    popf
    call ata_delay
    call ata_wait_complete
    jc .error
    mov ax, bp
    add [fs:S_DONE], al
    movzx eax, bp
    add [fs:S_LBA], eax
    mov al, [fs:S_DONE]
    cmp al, [fs:S_COUNT]
    jb .block
    clc
    jmp .done
.error:
    stc
.done:
    pop es
    pop ds
    popad
    ret

ide_default_settings:
    db 1
%rep 2
    db 0,0,0,0             ; Auto type/translation/block; EDD On.
    dw 1024
    db 16,63
    dw 0xFFFF,1024
%endrep

; Phoenix System BIOS1989 pp64..66. Eight bytes: C,H,S,precomp,landing.
; Reserved entries remain zero and cannot be selected. User is type48.
ide_type_table:
    ; Explicit rows avoid inheriting OEM-specific or translated type numbers.
    dw 306
    db 4,17
    dw 128,305
    dw 615
    db 4,17
    dw 300,615
    dw 615
    db 6,17
    dw 300,615
    dw 940
    db 8,17
    dw 512,940
    dw 940
    db 6,17
    dw 512,940
    dw 615
    db 4,17
    dw 65535,615
    dw 462
    db 8,17
    dw 256,511
    dw 733
    db 5,17
    dw 65535,733
    dw 900
    db 15,17
    dw 65535,901
    dw 820
    db 3,17
    dw 65535,820
    dw 855
    db 5,17
    dw 65535,855
    dw 855
    db 7,17
    dw 65535,855
    dw 306
    db 8,17
    dw 128,319
    dw 733
    db 7,17
    dw 65535,733
    dq 0
    dw 612
    db 4,17
    dw 0,663
    dw 977
    db 5,17
    dw 300,977
    dw 977
    db 7,17
    dw 65535,977
    dw 1024
    db 7,17
    dw 512,1023
    dw 733
    db 5,17
    dw 300,732
    dw 733
    db 7,17
    dw 300,732
    dw 733
    db 5,17
    dw 300,733
    dw 306
    db 4,17
    dw 0,336
    dw 1024
    db 7,17
    dw 65535,1024
    dw 615
    db 4,17
    dw 0,615
    dw 1024
    db 4,17
    dw 65535,1024
    dw 1024
    db 5,17
    dw 65535,1024
    dw 1024
    db 8,17
    dw 65535,1024
    dw 512
    db 8,17
    dw 256,512
    dw 615
    db 2,17
    dw 615,615
    dw 989
    db 5,17
    dw 0,989
    dw 1020
    db 15,17
    dw 65535,1024
    dq 0,0
    dw 1024
    db 9,17
    dw 1024,1024
    dw 1024
    db 5,17
    dw 512,1024
    dw 830
    db 10,17
    dw 65535,830
    dw 823
    db 10,17
    dw 256,824
    dw 615
    db 4,17
    dw 128,664
    dw 615
    db 8,17
    dw 128,664
    dw 917
    db 15,17
    dw 65535,918
    dw 1023
    db 15,17
    dw 65535,1024
    dw 823
    db 10,17
    dw 512,823
    dw 820
    db 6,17
    dw 65535,820
    dq 0
    dw 925
    db 9,17
    dw 65535,925
    dw 699
    db 7,17
    dw 256,700
