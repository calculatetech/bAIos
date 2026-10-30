; Shared PIO polling. Completion requires the final data phase to end.
ata_wait_ready:
    mov ecx, 0x00100000
    ata_port ATA_STATUS
.loop:
    call ata_read_status
    test al, 0x80
    jnz .next
    test al, 0x40
    jnz .ok
.next:
    dec ecx
    jnz .loop
    mov byte [fs:S_STATUS], ERR_TIMEOUT
    stc
    ret
.ok:
    clc
    ret

ata_wait_complete:
    call ata_delay              ; Status can still describe the preceding data phase.
    mov ecx, 0x00100000
    ata_port ATA_STATUS
.loop:
    call ata_read_status
    test al, 0x80
    jnz .next
    test al, 0x21
    jnz .controller
    test al, 0x08
    jnz .next
    clc
    ret
.next:
    dec ecx
    jnz .loop
    mov byte [fs:S_STATUS], ERR_TIMEOUT
    stc
    ret
.controller:
    mov byte [fs:S_STATUS], ERR_CONTROLLER
    stc
    ret

ata_wait_drq:
    call ata_delay              ; Allow the command or previous block to settle.
    mov ecx, 0x00100000
    ata_port ATA_STATUS
.loop:
    call ata_read_status
    test al, 0x80
    jnz .next
    test al, 0x21
    jnz .controller
    test al, 0x08
    jnz .ok
.next:
    dec ecx
    jnz .loop
    mov byte [fs:S_STATUS], ERR_TIMEOUT
    stc
    ret
.controller:
    mov byte [fs:S_STATUS], ERR_CONTROLLER
    stc
    ret
.ok:
    clc
    ret
