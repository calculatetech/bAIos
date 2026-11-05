; POST-only extension of the existing NV6 owner. Retire one pending rebuild
; bit only after complete reconstruction. Backup/verify the complete payload;
; write only that byte, its NV6 SUM8, and affected ordinary AT checksum.
; Normal write failure restores/verifies the old record. This does not add
; crash-atomic storage semantics or a second persistent progress marker.
settings_nv6_retire:
    pushad
    push es
    mov bp,sp
    sub sp,136
    lea di,[bp-136]
    call CFG_ROM_CODE_SEGMENT:pnp_nv_read_callback
    jc .failed
    mov al,0x35
    call CFG_ROM_CODE_SEGMENT:pnp_rtc_read_callback
    mov [ss:bp-2],al
    mov bx,NV6_PNP+12
    call CFG_ROM_CODE_SEGMENT:pnp_nv_index_callback
    mov [ss:bp-1],al
    mov ah,[ss:bp-136+NV6_PNP+12]
    test ah,0x20
    jz .retired
    and ah,~0x20
    call CFG_ROM_CODE_SEGMENT:pnp_nv_byte_callback
    jne .rollback
    mov al,0x35
    mov ah,[ss:bp-2]
    add ah,0x20
    call CFG_ROM_CODE_SEGMENT:pnp_nv_byte_callback
    jne .rollback
    call .checksum
    and byte [ss:bp-136+NV6_PNP+12],~0x20
    call .verify
    jnc .retired
    or byte [ss:bp-136+NV6_PNP+12],0x20
.rollback:
    mov al,[ss:bp-1]
    mov ah,[ss:bp-136+NV6_PNP+12]
    call CFG_ROM_CODE_SEGMENT:pnp_nv_byte_callback
    mov al,0x35
    mov ah,[ss:bp-2]
    call CFG_ROM_CODE_SEGMENT:pnp_nv_byte_callback
    call .checksum
    call .verify
    jnc .failed
    or byte [fs:C_ERROR],4    ; Existing storage-invalid result, never RAM notice.
.failed:
    mov sp,bp
    pop es
    popad
    stc
    ret
.retired:
    mov byte [fs:C_PNP+PNP_CLEAR],0
    mov ax,0x40
    mov es,ax
    and byte [es:PNP_PAYLOAD+NV6_PNP+12],~0x20
    mov sp,bp
    pop es
    popad
    clc
    ret
.checksum:
%if BOARD_ATA_DEVICE_COUNT = 4
    call CFG_ROM_CODE_SEGMENT:pnp_nv_checksum_callback
%endif
    ret
.verify:
    lea di,[bp-70]
    call CFG_ROM_CODE_SEGMENT:pnp_nv_read_callback
    jc .bad_verify
    xor si,si
.compare:
    mov al,[ss:bp+si-136]
    cmp al,[ss:bp+si-70]
    jne .bad_verify
    inc si
    cmp si,66
    jb .compare
    clc
    ret
.bad_verify:
    stc
    ret
settings_nv6_retire_code_end:
