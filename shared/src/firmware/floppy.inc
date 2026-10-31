; AT diskette services, 82077-compatible FDC, IRQ6 and DMA channel 2.
; State follows the relocatable EBDA. BDA 3Eh/3Fh/40h/41h/42h retain
; standard interrupt, motor, timeout, status and controller-result meanings.
%define F_MEDIA      0x82          ; Current media code per drive, 0 = unknown.
%define F_CAL        0x84          ; Recalibrated drive bit mask.
%define F_READY      0x85
%define F_BUSY       0x86
%define F_DRIVE      0x87
%define F_STATUS     0x88
%define F_DONE       0x89
%define F_FUNC       0x8A
%define F_CYL        0x8B
%define F_HEAD       0x8C
%define F_SECTOR     0x8D
%define F_LEFT       0x8E
%define F_CHUNK      0x8F
%define F_ADDR       0x90          ; Physical DMA address, dword.
%define F_RESULT     0x94          ; Seven result bytes.
%define F_STAGE      0x9B          ; Last operation, useful to the read-only diagnostic.
%define F_IRQS       0x9C          ; IRQ6 count (word).
%define F_RATE       0x9E
%define F_DOUBLE     0x9F
%define F_SPT        0xA0
%define F_TRACKS     0xA1
%define F_GAP        0xA2
%define F_FMTGAP     0xA3
%define F_DPT        0xA4          ; ROM offset.
%define F_RECAL      0xA6          ; Attempts in the latest calibration (0..2).
%define F_RECAL_ST0  0xA7          ; First attempt, retained for diagnostics.

int11:
    push ds
    xor ax, ax
    mov ds, ax
    mov ax, [0x0410]
    pop ds
    iret

int0e:
    push ax
    push ds
    push fs
    xor ax, ax
    mov ds, ax
    or byte [0x043E], 0x80
    call load_bios_state
    inc word [fs:F_IRQS]
    mov al, 0x20
    out 0x20, al
    pop fs
    pop ds
    pop ax
    iret

; Called by IRQ0 with DS=0040h. Do not stop a motor during an active call.
floppy_motor_tick:
    push fs
    push dx
    call load_bios_state
    cmp byte [fs:C_PORTS + P_FLOPPY], 0
    je .done
    cmp byte [fs:F_BUSY], 0
    jne .done
    cmp byte [0x0040], 0
    je .done
    dec byte [0x0040]
    jnz .done
    mov dx, FDC_DOR
    mov al, 0x0C
    out dx, al
    mov byte [0x003F], 0
.done:
    pop dx
    pop fs
    ret

init_floppy:
    pushf
    cli
    pushad
    push ds
    push fs
    xor ax, ax
    mov ds, ax
    call load_bios_state
    mov di, F_TYPES
    mov cx, 0x30
.clear:
    mov byte [fs:di], 0
    inc di
    loop .clear
    and word [0x0410], 0xFF3E
    ; DMA1 reaches the ISA bus through DMA2 channel 4, even with no FDC.
    ; A master-clear leaves that global cascade masked.
    mov al, 0xC0
    out 0xD6, al
    xor al, al
    out 0xD2, al
    out 0xD4, al
    cmp byte [fs:C_PORTS + P_FLOPPY], 0
    je .done
    mov al, [fs:C_TYPES]
    cmp byte [fs:C_SWAP], 0
    je .logical_types
    ror al, 4
.logical_types:
    mov ah, al
    and al, 0x0F
    shr ah, 4
.types:
    mov [fs:F_TYPES], ah
    mov [fs:F_TYPES + 1], al
    xor bx, bx
    test ah, ah
    jz .second
    inc bl
.second:
    test al, al
    jz .count
    mov bl, 2               ; DOS must retain B's identity when A is None.
.count:
    and word [0x0410], 0xFF3E
    test bl, bl
    jz .controller
    dec bl
    shl bl, 6
    or bl, 1
    or [0x0410], bl
.controller:
    call floppy_controller_mode
    in al, 0x21
    and al, 0xBF
    out 0x21, al
    call fdc_reset
.done:
    pop fs
    pop ds
    popad
    popf
    ret

; Saved PUSHAD registers: AX=-4, CX=-8, DX=-12, BX=-16, DI=-32.
floppy_int13:
    push bp
    mov bp, sp
    pushad
    push ds
    push es
    push fs
    cld
    xor ax, ax
    mov ds, ax
    call load_bios_state
    mov byte [fs:F_BUSY], 1
    mov byte [fs:F_DONE], 0
    mov al, [ss:bp-3]
    mov [fs:F_FUNC], al
    cmp byte [fs:C_PORTS + P_FLOPPY], 0
    je .absent
    cmp al, 1
    je .status
    mov byte [fs:F_STATUS], 0
    movzx si, byte [ss:bp-12]
    cmp si, 1
    ja .bad
    mov ax, si
    mov [fs:F_DRIVE], al
    cmp byte [fs:F_TYPES+si], 0
    je .absent
    cmp byte [fs:F_FUNC], 8
    je .parameters
    cmp byte [fs:F_FUNC], 0x15
    je .type
    cmp byte [fs:F_FUNC], 0
    je .reset
    cmp byte [fs:F_FUNC], 0x16
    je .change
    cmp byte [fs:F_FUNC], 0x17
    je .old_media
    cmp byte [fs:F_FUNC], 0x18
    je .set_media
    cmp byte [fs:F_FUNC], 2
    jb .bad
    cmp byte [fs:F_FUNC], 5
    ja .bad
    mov al, [ss:bp-7]
    mov [fs:F_CYL], al
    mov al, [ss:bp-8]
    test al, 0xC0
    jnz .address
    mov [fs:F_SECTOR], al
    mov al, [ss:bp-11]
    cmp al, 1
    ja .address
    mov [fs:F_HEAD], al
    mov al, [ss:bp-4]
    test al, al
    jz .address
    cmp al, 72
    ja .address
    mov [fs:F_LEFT], al
    ; AH=04h has no caller buffer on AT-compatible BIOSes. DOS deliberately
    ; supplies 0000:0000; its range can cover the EBDA after DOS relocates it.
    ; Native FDC VERIFY transfers no data. Do not apply DMA buffer guards.
    cmp byte [fs:F_FUNC], 4
    jne .data_buffer
    mov dword [fs:F_ADDR], 0
    jmp .prepared_buffer
.data_buffer:
    ; Classic ISA DMA callers must stay in one physical 64 KiB page.
    ; Reject HMA and private EBDA; unlike ATA this is not CPU-driven PIO.
    movzx ecx, al
    shl ecx, 9
    cmp byte [fs:F_FUNC], 5
    jne .buffer
    shr ecx, 7                ; CHRN table: four bytes per sector.
.buffer:
    xor eax, eax
    mov ax, es
    shl eax, 4
    movzx edx, word [ss:bp-16]
    add eax, edx
    mov [fs:F_ADDR], eax
    mov edx, eax
    add edx, ecx
    cmp edx, 0x100000
    ja .dma_boundary
    push eax
    and eax, 0xFFFF
    add eax, ecx
    cmp eax, 0x10000
    pop eax
    ja .dma_boundary
    call check_disk_buffer
    jc .dma_boundary
.prepared_buffer:
    call fdc_prepare
    jc .finish
    call floppy_media
    jc .finish
    mov al, [fs:F_CYL]
    cmp al, [fs:F_TRACKS]
    jae .address
    cmp byte [fs:F_FUNC], 5
    je .format
    cmp byte [fs:F_SECTOR], 1
    jb .address
    mov al, [fs:F_SECTOR]
    cmp al, [fs:F_SPT]
    ja .address
.transfer:
    mov al, [fs:F_SPT]
    sub al, [fs:F_SECTOR]
    inc al
    cmp al, [fs:F_LEFT]
    jbe .chunk
    mov al, [fs:F_LEFT]
.chunk:
    mov [fs:F_CHUNK], al
    call fdc_seek
    jc .finish
    movzx ecx, byte [fs:F_CHUNK]
    shl ecx, 9
    mov al, 0x06             ; OEM EFD5: demand-mode DMA write to memory.
    cmp byte [fs:F_FUNC], 3
    jne .dma
    mov al, 0x0A             ; OEM EFD7: demand-mode DMA read from memory.
.dma:
    cmp byte [fs:F_FUNC], 4
    jne .program_dma
    jmp .verify_command     ; FIFO-enabled FDC VERIFY needs no DMA service.
.program_dma:
    call floppy_dma
    call fdc_begin
    mov al, 0x46             ; MFM read, explicit seek, no head crossing.
    cmp byte [fs:F_FUNC], 3
    jne .command
    mov al, 0x45
.command:
    call fdc_write
    jc .finish
    call fdc_unit_head
    cmp byte [fs:F_FUNC], 4
    jne .unit
    or al, 0x80             ; EC: stop after the requested sector count.
.unit:
    call fdc_write
    mov al, [fs:F_CYL]
    call fdc_write
    mov al, [fs:F_HEAD]
    call fdc_write
    mov al, [fs:F_SECTOR]
    call fdc_write
    mov al, 2
    call fdc_write
    mov al, [fs:F_SPT]
    call fdc_write
    mov al, [fs:F_GAP]
    call fdc_write
    mov al, 0xFF
    cmp byte [fs:F_FUNC], 4
    jne .length
    mov al, [fs:F_CHUNK]    ; Native VERIFY uses SC rather than DMA terminal count.
.length:
    call fdc_write
    call fdc_data_result
    jc .finish
    mov al, [fs:F_CHUNK]
    add [fs:F_DONE], al
    sub [fs:F_LEFT], al
    jz .finish
    movzx eax, al
    shl eax, 9
    add [fs:F_ADDR], eax
    mov byte [fs:F_SECTOR], 1
    xor byte [fs:F_HEAD], 1
    jnz .transfer
    inc byte [fs:F_CYL]
    mov al, [fs:F_CYL]
    cmp al, [fs:F_TRACKS]
    jb .transfer
    jmp .address
.verify_command:
    call fdc_begin
    mov al, 0x56             ; SMC datasheet p38/p61: MFM VERIFY with FIFO enabled.
    jmp .command
.format:
    mov al, [fs:F_LEFT]
    cmp al, [fs:F_SPT]
    jne .address
    call fdc_seek
    jc .finish
    movzx ecx, byte [fs:F_LEFT]
    shl ecx, 2
    mov al, 0x0A             ; Format drains memory into the same FDC FIFO.
    call floppy_dma
    call fdc_begin
    mov al, 0x4D
    call fdc_write
    call fdc_unit_head
    call fdc_write
    mov al, 2
    call fdc_write
    mov al, [fs:F_SPT]
    call fdc_write
    mov al, [fs:F_FMTGAP]
    call fdc_write
    mov al, 0xF6
    call fdc_write
    call fdc_data_result
    jc .finish
    mov al, [fs:F_LEFT]
    mov [fs:F_DONE], al
    jmp .finish
.reset:
    call fdc_reset
    jmp .finish
.parameters:
    mov al, [fs:F_TYPES+si]
    mov [ss:bp-16], al       ; BL drive type.
    mov byte [ss:bp-15], 0
    call floppy_profile
    mov al, [fs:F_TRACKS]
    dec al
    mov [ss:bp-7], al
    mov al, [fs:F_SPT]
    mov [ss:bp-8], al
    mov byte [ss:bp-11], 1
    xor ax, ax
    cmp byte [fs:F_TYPES], 0
    je .count_b
    inc al
.count_b:
    cmp byte [fs:F_TYPES+1], 0
    je .params_done
    mov al, 2
.params_done:
    mov [ss:bp-12], al
    jmp .return_dpt
.type:
    mov byte [ss:bp-3], 1
    cmp byte [fs:F_TYPES+si], 1
    je .success_raw
    mov byte [ss:bp-3], 2
    jmp .success_raw
.absent:
    cmp byte [fs:F_FUNC], 0x15
    jne .bad
    mov byte [ss:bp-3], 0
    jmp .success_raw
.change:
    call fdc_select
    cmp byte [fs:F_TYPES+si], 1
    je .finish             ; 360K drives have no disk-change line.
    mov dx, FDC_CCR
    in al, dx
    test al, 0x80
    jz .finish
    mov byte [fs:F_MEDIA+si], 0
    mov byte [fs:F_STATUS], 6
    jmp .finish
.old_media:
    mov al, [ss:bp-4]
    cmp al, 1
    jb .bad
    cmp al, 4
    ja .bad
    mov bx, floppy_old_media
    cs xlatb
    jmp .accept_media
.set_media:
    mov ah, [ss:bp-7]
    mov al, [ss:bp-8]
    cmp ah, 39
    jne .eighty
    cmp al, 9
    jne .address
    mov al, 1
    jmp .accept_media
.eighty:
    cmp ah, 79
    jne .address
    mov bl, 3
    cmp al, 9
    je .chosen
    mov bl, 2
    cmp al, 15
    je .chosen
    mov bl, 4
    cmp al, 18
    je .chosen
    mov bl, 5
    cmp al, 36
    jne .address
.chosen:
    mov al, bl
.accept_media:
    call floppy_compatible
    jc .address
    mov [fs:F_MEDIA+si], al
    call floppy_profile
.return_dpt:
    mov ax, [fs:F_DPT]
    mov [ss:bp-32], ax
    mov word [ss:bp-36], 0xF000
    jmp .finish
.status:
    mov al, [0x0441]
    mov [fs:F_STATUS], al
    jmp .finish
.bad:
    mov byte [fs:F_STATUS], 1
    jmp .finish
.address:
    mov byte [fs:F_STATUS], 4
    jmp .finish
.dma_boundary:
    mov byte [fs:F_STATUS], 9
.finish:
    mov al, [fs:F_STATUS]
    mov [0x0441], al
    mov [ss:bp-3], al
    mov al, [fs:F_DONE]
    mov [ss:bp-4], al
    cmp byte [fs:F_STATUS], 0
    je .success_raw
    or word [ss:bp+6], 1
    jmp .return
.success_raw:
    and word [ss:bp+6], 0xFFFE
.return:
    cli
    ; OEM ECD0 re-enables interrupts in the caller's return frame, even
    ; for parameter/status calls that never enter the FDC IRQ wait path.
    or word [ss:bp+6], 0x0200
    mov al, 6
    out 0x0A, al             ; Always mask DMA2 when not transferring.
    mov byte [0x0440], 37
    mov byte [fs:F_BUSY], 0
    pop fs
    pop es
    pop ds
    popad
    pop bp
    iret

; AL media code, SI drive. CF for an unsupported drive/media pair.
floppy_compatible:
    cmp al, [fs:F_TYPES+si]
    je .yes
    cmp byte [fs:F_TYPES+si], 2
    jne .three_inch
    cmp al, 1
    je .yes
    stc
    ret
.three_inch:
    cmp byte [fs:F_TYPES+si], 4
    jb .no
    cmp al, 3
    je .yes
    cmp byte [fs:F_TYPES+si], 5
    jne .no
    cmp al, 4
    je .yes
.no:
    stc
    ret
.yes:
    clc
    ret

floppy_profile:
    push ax
    push bx
    movzx bx, al
    shl bx, 3
    mov al, [cs:floppy_profiles+bx]
    mov [fs:F_TRACKS], al
    mov al, [cs:floppy_profiles+bx+1]
    mov [fs:F_SPT], al
    mov al, [cs:floppy_profiles+bx+2]
    mov [fs:F_RATE], al
    mov al, [cs:floppy_profiles+bx+3]
    mov [fs:F_GAP], al
    mov al, [cs:floppy_profiles+bx+4]
    mov [fs:F_FMTGAP], al
    mov ax, [cs:floppy_profiles+bx+6]
    mov [fs:F_DPT], ax
    mov byte [fs:F_DOUBLE], 0
    cmp byte [fs:F_TYPES+si], 2
    jne .done
    cmp byte [fs:F_TRACKS], 40
    jne .done
    mov byte [fs:F_RATE], 1  ; 360 RPM, 300 kb/s, double step for 360K in 1.2M.
    mov byte [fs:F_DOUBLE], 1
.done:
    pop bx
    pop ax
    ret

floppy_media:
    mov al, [fs:F_MEDIA+si]
    test al, al
    jnz .known
    ; Probe encoding rate with READ ID, independently for each drive.
    mov al, [fs:F_TYPES+si]
.probe:
    mov [fs:F_MEDIA+si], al
    call floppy_profile
    call fdc_specify
    jc .failed
    call fdc_begin
    mov al, 0x4A
    call fdc_write
    mov al, [fs:F_DRIVE]
    call board_floppy_unit
    call fdc_write
    call fdc_data_result
    jnc .known_reload
    cmp byte [fs:F_STATUS], 0x80
    je .failed
    mov byte [fs:F_STATUS], 0
    mov al, [fs:F_MEDIA+si]
    cmp al, 5
    jne .not_ed
    mov al, 4
    jmp .probe
.not_ed:
    cmp al, 4
    jne .not_hd
    mov al, 3
    jmp .probe
.not_hd:
    cmp al, 2
    jne .failed_address
    mov al, 1
    jmp .probe
.failed_address:
    mov byte [fs:F_STATUS], 4
.failed:
    mov byte [fs:F_MEDIA+si], 0
    stc
    ret
.known_reload:
    mov al, [fs:F_MEDIA+si]
.known:
    call floppy_profile
    jmp fdc_specify

fdc_begin:
    cli
    and byte [0x043E], 0x7F
    ret

; Commands are bounded using the existing PIT-based delay, not CPU loops.
fdc_write:
    push ax
    push cx
    push dx
    mov cx, 100
.poll:
    mov dx, FDC_MSR
    in al, dx
    and al, 0xC0
    cmp al, 0x80
    je .ready
    call kbc_delay_2ms
    loop .poll
    mov byte [fs:F_STATUS], 0x80
    stc
    jmp .done
.ready:
    clc
.done:
    pop dx
    pop cx
    pop ax
    jc .return
    push dx
    mov dx, FDC_FIFO
    out dx, al
    pop dx
.return:
    ret

fdc_read:
    push cx
    push dx
    mov cx, 100
.poll:
    mov dx, FDC_MSR
    in al, dx
    and al, 0xC0
    cmp al, 0xC0
    je .ready
    call kbc_delay_2ms
    loop .poll
    mov byte [fs:F_STATUS], 0x80
    stc
    jmp .done
.ready:
    mov dx, FDC_FIFO
    in al, dx
    clc
.done:
    pop dx
    pop cx
    ret

fdc_wait_irq:
    push cx
    mov cx, 1500
    sti
.poll:
    test byte [0x043E], 0x80
    jnz .ready
    call kbc_delay_2ms
    loop .poll
    mov byte [fs:F_STATUS], 0x80
    mov byte [fs:F_READY], 0
    stc
    jmp .done
.ready:
    clc
.done:
    pop cx
    ret

fdc_sense:
    mov al, 8
    call fdc_write
    jc .done
    call fdc_read
    jc .done
    call board_floppy_result
    mov [fs:F_RESULT], al
    call fdc_read
    mov [fs:F_RESULT+1], al
.done:
    ret

fdc_policy_absent:
    mov byte [fs:F_STATUS], 1
    stc
    ret

fdc_reset:
    cmp byte [fs:C_PORTS + P_FLOPPY], 0
    je fdc_policy_absent
    mov byte [fs:F_STAGE], 1
    mov byte [fs:F_CAL], 0
    mov byte [fs:F_READY], 0
    mov word [fs:F_MEDIA], 0
    call fdc_begin
    mov dx, FDC_DOR
    xor al, al
    out dx, al
    call kbc_delay_2ms
    mov al, 0x0C
    out dx, al
    mov byte [0x043F], 0
    call fdc_wait_irq
    jc .done
    mov cx, 4
.sense:
    call fdc_sense
    jc .done
    loop .sense
    call board_floppy_configure
    jc .done
    mov byte [fs:F_READY], 1
.done:
    ret

fdc_select:
    push cx
    mov cl, [fs:F_DRIVE]
    mov al, 1
    shl al, cl
    mov ah, al
    and ah, [0x043F]
    or [0x043F], al
    mov al, [0x043F]
    shl al, 4
    or al, 0x0C
    or al, [fs:F_DRIVE]
    call board_floppy_dor
    mov dx, FDC_DOR
    out dx, al
    test ah, ah
    jnz .ready
    mov cx, 250             ; 500 ms motor start at either CPU speed.
.spin:
    call kbc_delay_2ms
    loop .spin
.ready:
    mov byte [0x0440], 37
    pop cx
    ret

fdc_prepare:
    cmp byte [fs:C_PORTS + P_FLOPPY], 0
    je fdc_policy_absent
    mov byte [fs:F_RECAL], 0
    mov byte [fs:F_RECAL_ST0], 0
    cmp byte [fs:F_READY], 0
    jne .select
    call fdc_reset
    jc .done
.select:
    call fdc_select
    mov al, [fs:F_TYPES+si]
    call floppy_profile
    call fdc_specify
    jc .done
    cmp byte [fs:F_TYPES+si], 1
    je .calibration
    mov dx, FDC_CCR
    in al, dx
    test al, 0x80
    jz .calibration
    ; A step clears the disk-change latch even when already at track zero.
    ; Retain AH=18h's chosen geometry for formatting an unformatted disk.
    cmp byte [fs:F_FUNC], 5
    je .changed
    mov byte [fs:F_MEDIA+si], 0
.changed:
    mov cx, si
    mov al, 1
    shl al, cl
    not al
    and [fs:F_CAL], al
    mov byte [fs:F_STAGE], 3
    call fdc_begin
    mov al, 0x0F
    call fdc_write
    mov al, [fs:F_DRIVE]
    call board_floppy_unit
    call fdc_write
    mov al, 1
    call fdc_write
    call fdc_wait_irq
    jc .done
    call fdc_sense
    jc .done
.calibration:
    mov cx, si
    mov al, 1
    shl al, cl
    test [fs:F_CAL], al
    jnz .good
    mov byte [fs:F_STAGE], 2
.recalibrate:
    inc byte [fs:F_RECAL]
    call fdc_begin
    mov al, 7
    call fdc_write
    mov al, [fs:F_DRIVE]
    call board_floppy_unit
    call fdc_write
    call fdc_wait_irq
    jc .done
    call fdc_sense
    jc .done
    mov al, [fs:F_RESULT]
    cmp byte [fs:F_RECAL], 1
    jne .check_recal
    mov [fs:F_RECAL_ST0], al
    ; OEM F000:EEC1-EECF retries once for SE+EC+abnormal termination.
    ; RECAL stops after about 80 pulses; PCN=0 does not prove TRK0.
    and al, 0x70
    cmp al, 0x70
    je .recalibrate
.check_recal:
    mov al, [fs:F_RESULT]
    and al, 0xE0
    cmp al, 0x20
    jne .bad
    cmp byte [fs:F_RESULT+1], 0
    jne .bad
    mov cx, si
    mov al, 1
    shl al, cl
    or [fs:F_CAL], al
.good:
    clc
.done:
    ret
.bad:
    mov byte [fs:F_STATUS], 0x40
    stc
    ret

fdc_specify:
    mov dx, FDC_CCR
    mov al, [fs:F_RATE]
    out dx, al
    mov al, 3
    call fdc_write
    jc .done
    mov al, 0xDF             ; OEM step-rate and head-unload settings.
    call fdc_write
    jc .done
    mov al, 2               ; OEM head-load setting, DMA enabled.
    call fdc_write
    jc .done
    jmp board_floppy_perpendicular
.done:
    ret

fdc_seek:
    mov byte [fs:F_STAGE], 3
    call fdc_begin
    mov al, 0x0F
    call fdc_write
    call fdc_unit_head
    call fdc_write
    mov al, [fs:F_CYL]
    cmp byte [fs:F_DOUBLE], 0
    je .target
    shl al, 1
.target:
    push ax
    call fdc_write
    call fdc_wait_irq
    jc .pop
    call fdc_sense
    jc .pop
    pop ax
    cmp al, [fs:F_RESULT+1]
    jne .bad
    mov al, [fs:F_RESULT]
    and al, 0xE0
    cmp al, 0x20
    jne .bad
    ; Let the head settle after an explicit seek.
    mov cx, 8
.settle:
    call kbc_delay_2ms
    loop .settle
    clc
    ret
.pop:
    pop ax
    stc
    ret
.bad:
    mov byte [fs:F_STATUS], 0x40
    stc
    ret

fdc_unit_head:
    mov al, [fs:F_HEAD]
    shl al, 2
    or al, [fs:F_DRIVE]
    call board_floppy_unit
    ret

fdc_data_result:
    mov byte [fs:F_STAGE], 4
    call fdc_wait_irq
    jc .done
    mov di, F_RESULT
    mov bx, 0x0442
    mov cx, 7
.read:
    call fdc_read
    jc .done
    cmp di,F_RESULT
    jne .result_byte
    call board_floppy_result
.result_byte:
    mov [fs:di], al
    mov [bx], al
    inc di
    inc bx
    loop .read
    test byte [fs:F_RESULT], 0xC0
    jnz .error
    clc
.done:
    ret
.error:
    mov al, 0x20
    test byte [fs:F_RESULT+1], 0x02
    jz .crc
    mov al, 3
    jmp .save
.crc:
    test byte [fs:F_RESULT+1], 0x20
    jz .dma
    mov al, 0x10
    jmp .save
.dma:
    test byte [fs:F_RESULT+1], 0x10
    jz .sector
    mov al, 8
    jmp .save
.sector:
    test byte [fs:F_RESULT+1], 0x05
    jz .save
    mov al, 4
.save:
    mov [fs:F_STATUS], al
    stc
    ret

; ECX byte count, AL DMA mode. Address/count registers are shared flip-flops.
floppy_dma:
    pushf
    cli
    push ax
    mov al, 6
    out 0x0A, al
    xor al, al
    out 0x0C, al
    pop ax
    out 0x0B, al
    mov eax, [fs:F_ADDR]
    out 0x04, al
    mov al, ah
    out 0x04, al
    shr eax, 16
    out 0x81, al
    dec cx
    mov ax, cx
    out 0x05, al
    mov al, ah
    out 0x05, al
    mov al, 2
    out 0x0A, al
    popf
    ret

floppy_old_media: db 0,1,1,2,3
; tracks, sectors, rate, read gap, format gap, pad, DPT pointer
floppy_profiles:
    times 8 db 0
    db 40,9,2,0x2A,0x50,0
    dw floppy_dpt_360
    db 80,15,0,0x1B,0x54,0
    dw floppy_dpt_1200
    db 80,9,2,0x2A,0x50,0
    dw floppy_dpt_720
    db 80,18,0,0x1B,0x6C,0
    dw floppy_dpt_1440
    db 80,36,3,0x1B,0x53,0
    dw floppy_dpt_2880
floppy_dpt_360:  db 0xDF,2,37,2,9,0x2A,0xFF,0x50,0xF6,15,8
floppy_dpt_1200: db 0xDF,2,37,2,15,0x1B,0xFF,0x54,0xF6,15,8
floppy_dpt_720:  db 0xDF,2,37,2,9,0x2A,0xFF,0x50,0xF6,15,8
floppy_dpt_1440: db 0xDF,2,37,2,18,0x1B,0xFF,0x6C,0xF6,15,8
floppy_dpt_2880: db 0xDF,2,37,2,36,0x1B,0xFF,0x53,0xF6,15,8

%ifdef FLOPPY_DIAGNOSTIC
; No media writes. Run before DOS so an unresponsive drive cannot hide
; the controller/IRQ/recalibration/seek evidence behind a DOS error message.
floppy_diagnostics:
    pushf
    pushad
    push ds
    push es
    push fs
    xor ax, ax
    mov ds, ax
    call load_bios_state
    mov si, floppy_diag_title
    call print_string
    mov si, floppy_diag_sio
    call print_string
    call board_sio_diagnostic_begin
    xor cx, cx
.sio:
    call board_sio_diagnostic_index
    out dx, al
    inc dx
    in al, dx
    push dx
    call floppy_diag_hex
    mov al, ' '
    call floppy_diag_char
    pop dx
    dec dx
    inc cx
    cmp cx, 4
    jb .sio
    call board_sio_diagnostic_end
    mov si, floppy_diag_newline
    call print_string
    mov si, floppy_diag_types
    call print_string
    mov al, [fs:F_TYPES]
    call floppy_diag_hex
    mov al, '/'
    call floppy_diag_char
    mov al, [fs:F_TYPES+1]
    call floppy_diag_hex
    mov si, floppy_diag_newline
    call print_string
    mov byte [fs:F_BUSY], 1
    mov byte [fs:F_DRIVE], 0
    mov byte [fs:F_STATUS], 0
    call fdc_reset
    call floppy_diag_line
    xor si, si
.drive:
    mov ax, si
    mov [fs:F_DRIVE], al
    mov byte [fs:F_STATUS], 0
    mov byte [fs:F_HEAD], 0
    call fdc_prepare
    call floppy_diag_line
    cmp byte [fs:F_STATUS], 0
    jne .next
    mov byte [fs:F_CYL], 1
    call fdc_seek
    call floppy_diag_line
    cmp byte [fs:F_STATUS], 0
    jne .next
    mov byte [fs:F_CYL], 0
    call fdc_seek
    call floppy_diag_line
    cmp byte [fs:F_STATUS], 0
    jne .next
    call floppy_diag_data
.next:
    inc si
    cmp si, 2
    jb .drive
    mov byte [fs:F_BUSY], 0
    mov dx, FDC_DOR
    mov al, 0x0C
    out dx, al
    mov byte [0x043F], 0
    mov si, floppy_diag_end
    call print_string
    mov cx, 2500            ; Diagnostic only: time to photograph the report.
.hold:
    call kbc_delay_2ms
    loop .hold
    pop fs
    pop es
    pop ds
    popad
    popf
    ret

; Read existing media only. Keep native-rate READ ID evidence separate from
; the normal INT13 read, which can try a lower-density media profile.
floppy_diag_data:
    pushad
    push es
    mov byte [fs:F_HEAD], 0
.head:
    push si
    mov si, floppy_diag_probe
    call print_string
    mov al, [fs:F_DRIVE]
    add al, 'A'
    call floppy_diag_char
    mov si, floppy_diag_head
    call print_string
    mov al, [fs:F_HEAD]
    call floppy_diag_hex
    mov si, floppy_diag_id
    call print_string
    pop si
    mov al, [fs:F_TYPES+si]
    call floppy_profile
    call floppy_diag_clear_result
    call fdc_specify
    jc .id_done
    call fdc_begin
    mov al, 0x4A
    call fdc_write
    jc .id_done
    call fdc_unit_head
    call fdc_write
    jc .id_done
    call fdc_data_result
.id_done:
    sti
    call floppy_diag_data_result
    push si
    mov si, floppy_diag_read
    call print_string
    pop si
    call floppy_diag_clear_result
    mov ax, 0x1000          ; One sector at physical 10000h; POST-only scratch.
    mov es, ax
    xor bx, bx
    mov cx, 1              ; Cylinder 0, sector 1, current head and drive.
    mov dh, [fs:F_HEAD]
    mov dl, [fs:F_DRIVE]
    mov ax, 0x0201
    int 0x13
    mov byte [fs:F_BUSY], 1
    call floppy_diag_data_result
    push si
    mov si, floppy_diag_newline
    call print_string
    pop si
    inc byte [fs:F_HEAD]
    cmp byte [fs:F_HEAD], 2
    jb .head
    pop es
    popad
    ret

floppy_diag_clear_result:
    push cx
    push di
    mov byte [fs:F_STATUS], 0
    mov di, F_RESULT
    mov cx, 7
.clear:
    mov byte [fs:di], 0xFF   ; Distinguish missing result bytes from success.
    inc di
    loop .clear
    pop di
    pop cx
    ret

floppy_diag_data_result:
    pushad
    mov al, [fs:F_STATUS]
    call floppy_diag_hex
    mov al, '/'
    call floppy_diag_char
    mov al, [fs:F_RATE]
    call floppy_diag_hex
    mov al, ':'
    call floppy_diag_char
    mov di, F_RESULT
    mov cx, 7
.byte:
    mov al, [fs:di]
    call floppy_diag_hex
    inc di
    loop .byte
    popad
    ret

floppy_diag_line:
    pushad
    mov si, floppy_diag_drive
    call print_string
    mov al, [fs:F_DRIVE]
    add al, 'A'
    call floppy_diag_char
    mov si, floppy_diag_stage
    call print_string
    mov al, [fs:F_STAGE]
    call floppy_diag_hex
    mov si, floppy_diag_status
    call print_string
    mov al, [fs:F_STATUS]
    call floppy_diag_hex
    mov si, floppy_diag_result
    call print_string
    mov al, [fs:F_RESULT]
    call floppy_diag_hex
    mov al, '/'
    call floppy_diag_char
    mov al, [fs:F_RESULT+1]
    call floppy_diag_hex
    mov si, floppy_diag_irq
    call print_string
    mov al, [fs:F_IRQS]
    call floppy_diag_hex
    mov si, floppy_diag_recal
    call print_string
    mov al, [fs:F_RECAL]
    call floppy_diag_hex
    mov al, '/'
    call floppy_diag_char
    mov al, [fs:F_RECAL_ST0]
    call floppy_diag_hex
    mov si, floppy_diag_st3
    call print_string
    mov al, 4
    call fdc_write
    mov al, [fs:F_DRIVE]
    call board_floppy_unit
    call fdc_write
    call fdc_read
    call floppy_diag_hex
    mov si, floppy_diag_newline
    call print_string
    popad
    ret
floppy_diag_hex:
    push ax
    shr al, 4
    call .nibble
    pop ax
    and al, 0x0F
.nibble:
    add al, '0'
    cmp al, '9'
    jbe floppy_diag_char
    add al, 7
floppy_diag_char:
    push ax
    push bx
    mov ah, 0x0E
    mov bx, 7
    int 0x10
    pop bx
    pop ax
    ret
floppy_diag_title: db 13,10,'FDC read-only probe: stage 1=reset 2=recal 3=seek',13,10,0
floppy_diag_drive: db 'Drive ',0
floppy_diag_sio: db 'SuperIO CR0..3: ',0
floppy_diag_types: db 'Configured A/B types: ',0
floppy_diag_stage: db ' stage=',0
floppy_diag_status: db ' BIOS=',0
floppy_diag_result: db ' ST0/PCN=',0
floppy_diag_irq: db ' IRQ6=',0
floppy_diag_recal: db ' R=',0
floppy_diag_st3: db ' ST3=',0
floppy_diag_probe: db 'Probe ',0
floppy_diag_head: db ' H=',0
floppy_diag_id: db ' ID=',0
floppy_diag_read: db ' RD=',0
floppy_diag_newline: db 13,10,0
floppy_diag_end: db 'FDC probe complete; no sectors written.',13,10
    db 'Boot continues in 5 seconds.',13,10,0
%endif
