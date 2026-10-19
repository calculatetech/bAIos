; The checksummed policy contains this exact ROM/CPU/geometry certificate.
cache_validation_identity:
    pushad
    push ds
    push cs
    pop ds
    xor esi,esi
    mov ecx,0x10000
    call checksum_crc32
    mov [fs:HW_ROM_CRC],eax
    pop ds
    call cpu_detect_name
    mov [fs:HW_CPU_NAME],si
    mov byte [fs:HW_CACHE_KEY],CHIP_CERT_TAG
    mov al,[fs:HW_CACHE_MAP]
    mov [fs:HW_CACHE_KEY+1],al
    mov al,[fs:HW_HB52]
    mov [fs:HW_CACHE_KEY+2],al
    mov al,[fs:HW_HB53]
    and al,0x3F
    mov [fs:HW_CACHE_KEY+3],al
    mov al,[fs:HW_HB61]
    and al,0x30
    mov [fs:HW_CACHE_KEY+4],al
    cache_read 0x08
    mov [fs:HW_CACHE_KEY+5],al
    mov ax,[fs:S_CPU_SIGNATURE]
    mov [fs:HW_CACHE_KEY+6],ax
    mov ax,[fs:HW_CPU_NAME]
    mov [fs:HW_CACHE_KEY+8],ax
    mov eax,[fs:HW_ROM_CRC]
    mov [fs:HW_CACHE_KEY+10],eax
    popad
    ret
cache_validation_reuse:
    pushad
    cmp byte [fs:C_VALID],1
    jne .miss
    mov al,0x69
    call rtc_read
    cmp al,CHIP_RECORD_TAG
    jne .miss
    ; Active profile normalization must not reuse a result for the stored tuple.
    mov dl,CHIP_RECORD_TAG
    xor bx,bx
.checksum:
    add dl,[fs:C_CHIP+bx]
    inc bx
    cmp bx,CHIP_SIZE
    jb .checksum
    mov al,0x6A
    call rtc_read
    add dl,al
    jnz .miss
    xor bx,bx
.byte:
    mov al,[fs:HW_CACHE_KEY+bx]
    cmp al,[fs:C_CHIP+CHIP_CERT_OFFSET+bx]
    jne .miss
    inc bx
    cmp bx,CHIP_SIZE-CHIP_CERT_OFFSET
    jb .byte
    mov byte [fs:HW_CACHE_FLAGS],1
    popad
    clc
    ret
.miss:
    popad
    stc
    ret
cache_validation_save:
    pushad
    cmp byte [fs:C_VALID],1
    jne .done
    mov al,0x69
    call rtc_read
    cmp al,0xD2
    je .done
    xor bx,bx
.byte:
    mov al,[fs:HW_CACHE_KEY+bx]
    mov [fs:C_CHIP+CHIP_CERT_OFFSET+bx],al
    inc bx
    cmp bx,CHIP_SIZE-CHIP_CERT_OFFSET
    jb .byte
    mov si,C_CHIP
    call chipset_record_save
.done:
    popad
    ret
; SI=record. Clearing a result does not change the selected timing parameters.
cache_validation_clear:
    pushad
    mov bx,CHIP_CERT_OFFSET
.byte:
    mov byte [fs:si+bx],0
    inc bx
    cmp bx,CHIP_SIZE
    jb .byte
    popad
    ret

chipset_parity_apply:
    cmp byte [fs:C_CHIP+6],0
    jne .initialize
    in al,0x61
    or al,4
    out 0x61,al
    ret
.initialize:
    pushf
    cli
    pushad
    in al,0x61
    push ax
    or al,0x0C
    out 0x61,al
    wbinvd
    mov ebp,cr0
    mov eax,ebp
    or eax,0x60000000
    mov cr0,eax
    cache_data_enter
    ; Refresh existing values: cover live low RAM without destroying its state.
    xor edi,edi
    mov esi,0xA0000
.seed:
    mov eax,[gs:edi]
    mov [gs:edi],eax
    add edi,4
    cmp edi,esi
    jb .seed
    cmp edi,0xA0000
    jne .seeded
    test byte [fs:P_RAM_FLAGS],4
    jnz .seeded
    ; Esc skips the ordinary RAM test, but parity still requires initialized data.
    mov edi,0x100000
    memory_installed_kib esi
    add esi,1024
    shl esi,10
    cmp edi,esi
    jb .seed
.seeded:
    wbinvd
    cache_data_leave
    mov cr0,ebp
    pop ax
    or al,4
    out 0x61,al
    and al,0xFB
    out 0x61,al
    popad
    popf
    ret
