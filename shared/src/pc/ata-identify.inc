; POST identification can wait for a cold ATAPI drive without a CPU-speed limit.
; Runtime ATA transfer waits retain their existing fast owner.
ata_identify_wait_drq:
    mov cx, 15000
    ata_port ATA_STATUS
    cmp byte [fs:S_IDENTIFY_TRACE], 3
    je .poll
    ata_port ATA_CONTROL     ; Packet polling must not acknowledge INTRQ.
.poll:
    call ata_read_status
    cmp byte [fs:S_IDENTIFY_TRACE],3
    jne .status
    ; An empty ATA position can briefly retain the preceding drive's status.
    test al,al
    jz .absent
    cmp al,0xFF
    je .absent
.status:
    test al, 0x80
    jnz .next
    test al, 0x21
    jnz .controller
    test al, 8
    jnz .ok
.next:
    call kbc_delay_2ms
    loop .poll
    mov byte [fs:S_STATUS], ERR_TIMEOUT
    stc
    ret
.controller:
    mov byte [fs:S_STATUS], ERR_CONTROLLER
    stc
    ret
.absent:
    stc
    ret
.ok:
    clc
    ret
