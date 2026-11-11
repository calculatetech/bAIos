ata_transfer:
    cmp byte [fs:S_COUNT], 1
    jbe .single
    cmp byte [fs:S_COMMAND], CMD_READ
    je .multiple
    cmp byte [fs:S_COMMAND], CMD_WRITE
    jne .single
.multiple:
    call ide_negotiate_multiple
    cmp byte [fs:S_MULTIPLE], 2
    jae ide_multiple_transfer
.single:
    push ds
    push es
    push si
    push di
    push bx
    push cx
    push dx
    cld
    mov ax, [fs:S_BUFFER_SEG]
    mov es, ax
    mov bx, [fs:S_BUFFER_OFF]
.sector:
    call ata_select_ready
    jc .error
    call ide_program_address
    ata_port ATA_COUNT
    mov al, 1
    cmp byte [fs:S_COMMAND], CMD_FORMAT
    jne .count_ready
    push ax
    call get_chs_geometry
    mov dl, ah
    pop ax
    mov al, dl
    ata_port ATA_COUNT
.count_ready:
    out dx, al
    ata_port ATA_COMMAND
    mov al, [fs:S_COMMAND]
    out dx, al
    cmp al, CMD_VERIFY
    je .verify
    cmp al, CMD_SEEK
    je .verify
    call ata_wait_drq
    jc .error
    ata_port ATA_DATA
    mov cx, 256
    cmp byte [fs:S_COMMAND], CMD_READ
    je .read
    cmp byte [fs:S_COMMAND], CMD_READ_LONG
    jne .write
.read:
    mov di, bx
    pushf
    cli
    call ide_pio_read
    cmp byte [fs:S_COMMAND], CMD_READ_LONG
    jne .read_data_done
    mov cx, 4                 ; OEM A343/A34C: data words, then ECC bytes.
    rep insb
.read_data_done:
    popf
%ifdef EMULATOR_TEST
    call ata_test_after_read
%endif
    call ata_wait_complete
    jc .error
    jmp .sector_done
.write:
    push ds
    mov ax, es
    mov ds, ax
    mov si, bx
    pushf
    cli
    call ide_pio_write
    cmp byte [fs:S_COMMAND], CMD_WRITE_LONG
    jne .write_data_done
    mov cx, 4                 ; OEM A318/A325: ECC uses byte-sized port I/O.
    rep outsb
.write_data_done:
    popf
    pop ds
    call ata_wait_complete
    jc .error
    jmp .sector_done
.verify:
    call ata_wait_complete
    jc .error
.sector_done:
    add bx, [fs:S_BLOCK_SIZE]
    inc dword [fs:S_LBA]
    inc byte [fs:S_DONE]
    mov al, [fs:S_DONE]
    cmp al, [fs:S_COUNT]
    jb .sector
    clc
    jmp .finish
.error:
    stc
.finish:
    pop dx
    pop cx
    pop bx
    pop di
    pop si
    pop es
    pop ds
    ret

