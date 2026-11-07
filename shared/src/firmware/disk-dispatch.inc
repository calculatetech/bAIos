.invalid_drive:
    call .clear_dap_if_packet
    jmp .bad_command
.drive_ok:
    cmp ah, 0x01
    je .status
    cmp ah, 0x00
    je .reset
    cmp ah, 0x0D
    je .reset
    cmp ah, 0x04
    je .known_function
    cmp ah, 0x05
    je .known_function
    cmp ah, 0x09
    je .known_function
    cmp ah, 0x0A
    je .known_function
    cmp ah, 0x0B
    je .known_function
    cmp ah, 0x0C
    je .known_function
    cmp ah, 0x10
    je .known_function
    cmp ah, 0x11
    je .known_function
    cmp ah, 0x14
    je .known_function
    cmp ah, 0x02
    je .known_function
    cmp ah, 0x03
    je .known_function
    cmp ah, 0x08
    je .known_function
    cmp ah, 0x15
    je .known_function
    cmp ah, 0x41
    je .known_function
    cmp ah, 0x42
    je .known_function
    cmp ah, 0x43
    je .known_function
    cmp ah, 0x44
    je .known_function
    cmp ah, 0x47
    je .known_function
    cmp ah, 0x48
    jne .bad_command
.known_function:
    cmp byte [fs:S_PRESENT], 1
    je .present
    call .clear_dap_if_packet
    jmp .timeout
.present:
    cmp ah, 0x41
    jb .extensions_allowed
    cmp byte [fs:S_IDE + IDE_EDD_OFF], 1
    je .bad_command
.extensions_allowed:
    cmp ah, 0x04
    je .legacy_verify
    cmp ah, 0x05
    je .legacy_format
    cmp ah, 0x09
    je .initialize_parameters
    cmp ah, 0x0A
    je .legacy_read_long
    cmp ah, 0x0B
    je .legacy_write_long
    cmp ah, 0x0C
    je .legacy_seek
    cmp ah, 0x10
    je .ready
    cmp ah, 0x11
    je .recalibrate
    cmp ah, 0x14
    je .diagnostic
    cmp ah, 0x02
    je .legacy_read
    cmp ah, 0x03
    je .legacy_write
    cmp ah, 0x08
    je .geometry
    cmp ah, 0x15
    je .type
    cmp ah, 0x41
    je .extensions
    cmp ah, 0x42
    je .extended_read
    cmp ah, 0x43
    je .extended_write
    cmp ah, 0x44
    je .extended_verify
    cmp ah, 0x47
    je .extended_seek
    cmp ah, 0x48
    je .parameters
    jmp .bad_command

.status:
    mov ah, [fs:S_STATUS]
    mov al, ah
    test ah, ah
    jnz .return_error
    jmp .success

.reset:
    cmp byte [fs:S_PRESENT], 1
    jne .timeout
    call ata_reset
    jc .return_error
    xor ah, ah
    jmp .success

.ready:
    call ata_select_ready
    jc .return_error
    xor ah, ah
    jmp .success

.initialize_parameters:
    ; Program native ATA geometry, never the translated BIOS geometry.
    call ata_select_ready
    jc .return_error
    mov al, [fs:S_NATIVE_HEADS]
    test al, al
    jz .bad_address
    cmp al, 16
    ja .bad_address
    dec al
    or al, 0xA0
    or al, [fs:S_ATA_DEVICE]
    ata_port ATA_DRIVE
    out dx, al
    mov al, [fs:S_NATIVE_SECTORS]
    ata_port ATA_COUNT
    out dx, al
    mov al, 0x91
    jmp .controller_command
.recalibrate:
    call ata_select_ready
    jc .return_error
    mov al, 0x10
    jmp .controller_command
.diagnostic:
    call ata_select_ready
    jc .return_error
    mov al, 0x90
    call ata_no_data_command
    jc .return_error
    ata_port ATA_DATA + 1
    in al, dx
    cmp al, 1
    jne .controller_error
    xor ah, ah
    jmp .success
.controller_command:
    call ata_no_data_command
    jc .return_error
    xor ah, ah
    jmp .success
.controller_error:
    mov byte [fs:S_STATUS], ERR_CONTROLLER
    jmp .return_error

.legacy_seek:
    ; AH0C specifies a cylinder/head; AL, sector bits and ES:BX are not data.
    and cl, 0xC0
    or cl, 1
    call chs_to_lba
    jc .return_error
    cmp eax, [fs:S_CAPACITY]
    jae .bad_address
    mov [fs:S_LBA], eax
    mov byte [fs:S_COMMAND], CMD_SEEK
    mov byte [fs:S_COUNT], 1
    mov byte [fs:S_DONE], 0
    call ata_transfer
    jc .return_error
    xor ah, ah
    jmp .success

.legacy_format:
    test al, al
    jz .bad_address
    push ax
    call get_chs_geometry
    mov dl, ah
    pop ax
    cmp al, dl
    ja .bad_address
    ; ATA FORMAT TRACK consumes one 512-byte interleave descriptor block.
    ; Device ABRT is a real controller error, never a fabricated success.
    mov al, 1
    and cl, 0xC0
    or cl, 1
    mov byte [fs:S_COMMAND], CMD_FORMAT
    jmp .legacy
.legacy_verify:
    mov byte [fs:S_COMMAND], CMD_VERIFY
    jmp .legacy
.legacy_read_long:
    mov word [fs:S_BLOCK_SIZE], 516
    mov byte [fs:S_COMMAND], CMD_READ_LONG
    jmp .legacy
.legacy_write_long:
    mov word [fs:S_BLOCK_SIZE], 516
    mov byte [fs:S_COMMAND], CMD_WRITE_LONG
    jmp .legacy
.legacy_read:
    mov byte [fs:S_COMMAND], CMD_READ
    jmp .legacy
.legacy_write:
    mov byte [fs:S_COMMAND], CMD_WRITE
.legacy:
    call prepare_chs
    jc .legacy_chs_error
    call ata_transfer
    jc .legacy_io_error
    mov al, [fs:S_DONE]
    cmp byte [fs:S_COMMAND], CMD_READ
    jne .legacy_success
    push ax
    call get_chs_geometry
    shr al, 4
    or al, 0xA0
    out POST_PORT, al
    pop ax
.legacy_success:
    xor ah, ah
    jmp .success
.legacy_chs_error:
    cmp byte [fs:S_COMMAND], CMD_READ
    jne .return_error_al
    post_code 0xB2
    jmp .return_error_al
.legacy_io_error:
    cmp byte [fs:S_COMMAND], CMD_READ
    jne .return_error_al
    post_code 0xB3
    jmp .return_error_al

.geometry:
    call publish_disk_table
    call get_chs_geometry
    movzx ecx, al
    movzx edx, ah
    imul ecx, edx
    push ax
    mov eax, [fs:S_CAPACITY]
    xor edx, edx
    div ecx
    test eax, eax
    jnz .geometry_present
    pop ax
    jmp .bad_address
.geometry_present:
    dec eax
    cmp eax, 1023
    jbe .geometry_cylinder
    mov eax, 1023
.geometry_cylinder:
    ; OEM B0DA/B0DB reports count minus two: last cylinder number plus
    ; one reserved cylinder. WDCTRL compares this with the fixed table.
    ; A one-cylinder disk must still report cylinder zero.
    test eax, eax
    jz .geometry_encoded
    dec eax
.geometry_encoded:
    mov ch, al
    mov dl, ah
    and dl, 3
    shl dl, 6
    pop ax
    mov cl, ah
    or cl, dl
    mov dh, al
    dec dh
    push es
    xor dx, dx
    mov es, dx
    mov dl, [es:0x0475]
    pop es
    mov dh, al
    dec dh
    xor ah, ah
    jmp .cx_dx_result

.type:
    mov eax, [fs:S_CAPACITY]
    mov dx, ax
    shr eax, 16
    mov cx, ax
    mov ah, 3
.cx_dx_result:
    mov [ss:bp - 8], cx
    mov [ss:bp - 12], dx
    jmp .success

.extensions:
    cmp bx, 0x55AA
    jne .bad_command
    mov bx, 0xAA55
    mov ah, 0x11
    mov cx, 1
    mov [ss:bp - 16], bx
    mov [ss:bp - 8], cx
    jmp .success

.extended_read:
    mov byte [fs:S_COMMAND], CMD_READ
    jmp .extended_transfer
.extended_write:
    test al, al
    jz .write_option_ok
    mov word [ds:si + 2], 0
    jmp .bad_command
.write_option_ok:
    mov byte [fs:S_COMMAND], CMD_WRITE
    jmp .extended_transfer
.extended_verify:
    mov byte [fs:S_COMMAND], CMD_VERIFY
.extended_transfer:
    call prepare_dap
    jc .return_error_dap
    call ata_transfer
    push ax
    mov al, [fs:S_DONE]
    mov [ds:si + 2], al
    mov byte [ds:si + 3], 0
    pop ax
    jc .return_error
    xor ah, ah
    jmp .success

.extended_seek:
    mov byte [fs:S_COMMAND], 0
    call prepare_dap
    jc .return_error_dap
    mov word [ds:si + 2], 0
    xor ah, ah
    jmp .success

.parameters:
    call fill_edd_parameters
    jc .return_error
    xor ah, ah
    jmp .success

.bad_address:
    mov byte [fs:S_STATUS], ERR_BAD_ADDRESS
    jmp .return_error
.bad_command:
    mov byte [fs:S_STATUS], ERR_BAD_COMMAND
    jmp .return_error
.timeout:
    mov byte [fs:S_STATUS], ERR_TIMEOUT
.return_error:
    mov ah, [fs:S_STATUS]
    or word [ss:bp + 6], 1
    jmp .return
.return_error_al:
    mov al, [fs:S_DONE]
    jmp .return_error
.return_error_dap:
    mov word [ds:si + 2], 0
    jmp .return_error
.success:
    mov byte [fs:S_STATUS], 0
    and word [ss:bp + 6], 0xFFFE
.return:
    push ax
    push ds
    xor ax, ax
    mov ds, ax
    mov al, [fs:S_STATUS]
    mov [0x0474], al
    pop ds
    pop ax
    ; OEM AE4A: DOS drive services can enter with IF=0 and require IF=1 back.
    or word [ss:bp + 6], 0x0200
    mov [ss:bp - 4], ax
    pop fs
    popad
    pop bp
    iret

.clear_dap_if_packet:
    cmp ah, 0x42
    je .clear_packet_count
    cmp ah, 0x43
    je .clear_packet_count
    cmp ah, 0x44
    je .clear_packet_count
    cmp ah, 0x47
    jne .packet_done
.clear_packet_count:
    mov word [ds:si + 2], 0
.packet_done:
    ret

