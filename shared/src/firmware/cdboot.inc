; Single-image El Torito; the board selects the represented ATAPI channel.
; This free EBDA gap does not enlarge the one-KB firmware reservation.
%define CD_EQUIP    0x27E
%define CD_PACKET   0x280            ; Standard19-byte AH4B status packet.
%define CD_OLD13    0x294
%define CD_ACTIVE   0x298
%define CD_DEVICE   0x299
%define CD_CAPACITY 0x29A
%define CD_LBA      0x29E
%define CD_SKIP     0x2A2
%define CD_KEEP     0x2A4
%define CD_EXPECT   0x2A6
%define CD_RECEIVED 0x2A8
%define CD_STATUS   0x2AA
%define CD_WIDTH    0x2AB
%define CD_CMD      0x2AC            ;16-byte command, zero padded.
%define CD_SENSE    0x2BC            ;18-byte response scratch, ends2CDh.

cd_boot_clear:
    pushad
    push ds
    call load_bios_state
    cmp byte [fs:CD_ACTIVE], 1
    jne .done
    xor ax, ax
    mov ds, ax
    cmp byte [fs:CD_PACKET+1], 0
    je .vector
    mov ax, [fs:CD_EQUIP]
    mov [0x410], ax
.vector:
    cmp dword [0x4C], (0xF000 << 16) + (cd_int13 - $$)
    jne .clear                    ; Preserve a later installed external hook.
    mov eax, [fs:CD_OLD13]
    mov [0x4C], eax
    mov dword [fs:CD_OLD13], 0     ; The wrapper is no longer in the chain.
.clear:
    mov byte [fs:CD_ACTIVE], 0
.done:
    pop ds
    popad
    ret

cd_boot:
    call load_bios_state
    xor bp, bp
.position:
    mov bx, bp
    shl bx, 9
    cmp byte [fs:bx+S_ATAPI], 1
    jne .next
    cmp byte [fs:bx+S_PACKET_CD], 1
    jne .next
    call hardware_cd_select
    mov al, [fs:bx+S_PACKET_BYTES]
    mov [fs:CD_WIDTH], al
    mov al, [fs:bx+S_ATA_DEVICE]
    mov [fs:CD_DEVICE], al
    push bp
    call cd_try_boot
    pop bp
.next:
    inc bp
    cmp bp, 2
    jb .position
    ret

cd_try_boot:
    call cd_ready
    jc .fail
    call cd_command_clear
    mov byte [fs:CD_CMD], 0x25      ; READ CAPACITY(10).
    mov ax, 8
    call cd_response
    jc .fail
    cmp dword [fs:CD_SENSE+4], 0x00080000 ; Big-endian2048.
    jne .fail
    mov eax, [fs:CD_SENSE]
    cpu_swap_eax
    inc eax
    jz .fail
    mov [fs:CD_CAPACITY], eax
    xor ax, ax
    mov es, ax
    mov di, 0x800
    mov eax, 17
    call cd_whole_block
    jc .fail
    cmp byte [es:0x800], 0
    jne .fail
    mov si, cd_descriptor
    mov di, 0x801
    mov cx, cd_descriptor_end-cd_descriptor
    cld
.descriptor:
    cs lodsb
    scasb
    jne .fail
    loop .descriptor
    mov eax, [es:0x847]
    mov di, 0x800
    call cd_whole_block
    jc .fail
    cmp word [es:0x800], 1         ; Validation header1, x86 platform0.
    jne .fail
    cmp word [es:0x81E], 0xAA55
    jne .fail
    xor ax, ax
    mov si, 0x800
    mov cx, 16
.checksum:
    add ax, [es:si]
    add si, 2
    loop .checksum
    test ax, ax
    jnz .fail
    cmp byte [es:0x820], 0x88
    jne .fail
    mov al, [es:0x821]
    cmp al, 3                    ; Hard-disk emulation is not provided.
    ja .fail
    mov byte [fs:CD_PACKET], 0x13
    mov [fs:CD_PACKET+1], al
    mov byte [fs:CD_PACKET+2], 0
    test al, al
    jnz .floppy
    mov byte [fs:CD_PACKET+2], 0xE0
.floppy:
    call hardware_cd_packet_controller
    mov [fs:CD_PACKET+3], al
    mov eax, [es:0x828]
    mov [fs:CD_PACKET+4], eax
    movzx ax, byte [fs:CD_DEVICE]
    shr ax, 4
    mov [fs:CD_PACKET+8], ax
    mov word [fs:CD_PACKET+10], 0
    mov ax, [es:0x822]
    test ax, ax
    jnz .segment
    mov ax, 0x7C0
.segment:
    cmp ax, 0x7C0                ; Never overwrite IVT/BDA, scratch or live stack.
    jb .fail
    mov [fs:CD_PACKET+12], ax
    movzx eax, ax
    shl eax, 4
    movzx ecx, word [es:0x826]
    test ecx, ecx
    jz .fail
    mov [fs:CD_PACKET+14], cx
    shl ecx, 9
    mov edx, eax
    add edx, ecx
    movzx ebx, word [es:0x413]    ; POST-published conventional memory.
    shl ebx, 10
    cmp edx, ebx
    ja .fail
    call check_disk_buffer      ; The EBDA can move below the reported RAM top.
    jc .fail
    mov eax, [fs:CD_PACKET+4]
    mov edx, ecx
    add edx, 2047
    shr edx, 11
    add edx, eax
    jc .fail
    cmp edx, [fs:CD_CAPACITY]
    ja .fail
    mov es, [fs:CD_PACKET+12]
    xor di, di
    xor edx, edx
    call cd_read_span
    jc .fail
    xor ax, ax
    mov ds, ax
    cli
    cmp dword [fs:CD_OLD13], 0
    jne .equipment_snapshot       ; Reuse the wrapper below a retained hook.
    mov eax, [0x4C]
    mov [fs:CD_OLD13], eax
    mov dword [0x4C], (0xF000 << 16) + (cd_int13 - $$)
.equipment_snapshot:
    mov ax, [0x410]
    mov [fs:CD_EQUIP], ax
    cmp byte [fs:CD_PACKET+1], 0
    je .hook
    and ax, 0xFF3E
    or ax, 1                     ; At least one virtual floppy, no physical FDC needed.
    cmp byte [fs:F_TYPES], 0
    jz .equipment
    cmp byte [fs:C_PORTS+P_FLOPPY], 0
    je .equipment
    or ax, 0x40                  ; Virtual A plus displaced physical A at B.
.equipment:
    mov [0x410], ax
    mov byte [fs:CD_PACKET+16], 79
    movzx bx, byte [fs:CD_PACKET+1]
    mov al, [cs:cd_spt+bx-1]
    mov [fs:CD_PACKET+17], al
    mov byte [fs:CD_PACKET+18], 1
.hook:
    cli
    mov byte [fs:CD_ACTIVE], 1
    mov byte [fs:CD_STATUS], 0
    mov byte [0x400+KB_POST_STATE], 0
    xor dx, dx
    mov dl, [fs:CD_PACKET+2]
    mov ax, [fs:CD_PACKET+12]
    xor bx, bx
    mov es, bx
    push ax
    push bx
    cld
    sti
    retf
.fail:
    ret

cd_command_clear:
    push ax
    push cx
    push di
    push es
    mov ax, fs
    mov es, ax
    mov di, CD_CMD
    xor ax, ax
    mov cx, 8
    cld
    rep stosw
    pop es
    pop di
    pop cx
    pop ax
    ret

; Small replies use the already reserved record, not an added low-memory buffer.
cd_response:
    push es
    push di
    mov word [fs:CD_SKIP], 0
    mov [fs:CD_KEEP], ax
    mov [fs:CD_EXPECT], ax
    push fs
    pop es
    mov di, CD_SENSE
    call cd_packet_command
    pop di
    pop es
    ret

cd_ready:
    mov bp, 15000                ; Cold optical spin-up, bounded by the PIT.
.retry:
    call cd_command_clear
    xor ax, ax                   ; TEST UNIT READY.
    call cd_response
    jnc .done
    call cd_command_clear
    mov byte [fs:CD_CMD], 3       ; REQUEST SENSE clears unit attention.
    mov byte [fs:CD_CMD+4], 18
    mov ax, 18
    call cd_response
    jc .fail
    cmp byte [fs:CD_SENSE+12], 0x3A ; No medium: immediately try next target.
    je .fail
    mov al, [fs:CD_SENSE+2]
    and al, 15
    cmp al, 6                    ; Unit attention after reset/media replacement.
    je .again
    cmp byte [fs:CD_SENSE+12], 4  ; Becoming ready.
    jne .fail
.again:
    call kbc_delay_2ms
    dec bp
    jnz .retry
.fail:
    stc
.done:
    ret

cd_whole_block:
    mov word [fs:CD_SKIP], 0
    mov word [fs:CD_KEEP], 2048
    jmp cd_read_block

; EAX=absolute CD block, ES:DI=destination, selected byte window in state.
cd_read_block:
    cmp eax, [fs:CD_CAPACITY]
    jae .bad
    call cd_command_clear
    push eax
    cpu_swap_eax
    mov [fs:CD_CMD+2], eax
    pop eax
    mov byte [fs:CD_CMD], 0x28    ; READ(10), one2048-byte block.
    mov byte [fs:CD_CMD+8], 1
    mov word [fs:CD_EXPECT], 2048
    jmp cd_packet_command
.bad:
    mov byte [fs:CD_STATUS], ERR_BAD_ADDRESS
    stc
    ret

; EAX=CD block, EDX=byte skip in first block, ECX=bytes to copy.
cd_read_span:
    push ebx
    push ebp
    mov ebp, ecx
    mov [fs:CD_SKIP], dx
.next:
    movzx ebx, word [fs:CD_SKIP]
    neg bx
    add bx, 2048
    cmp ebx, ebp
    jbe .window
    mov ebx, ebp
.window:
    mov [fs:CD_KEEP], bx
    call cd_read_block
    jc .done
    sub ebp, ebx
    inc eax
    mov word [fs:CD_SKIP], 0
    test ebp, ebp
    jnz .next
    clc
.done:
    pop ebp
    pop ebx
    ret

; Polled ATAPI PIO. Validate every phase, accept split data replies, and
; acknowledge pending device IRQ before restoring the established IRQ policy.
cd_packet_command:
    push eax
    push ebx
    push ecx
    push edx
    push esi
    push ebp
    mov byte [fs:CD_STATUS], 0
    mov word [fs:CD_RECEIVED], 0
    cd_port ATA_DRIVE
    mov al, 0xA0
    or al, [fs:CD_DEVICE]
    out dx, al
    call ata_delay
    call cd_wait_phase
    jc .return
    cd_port ATA_CONTROL
    mov al, 0x0A                ; nIEN, legacy control bit3.
    out dx, al
    cd_port ATA_ERROR
    xor al, al                  ; PIO, no DMA.
    out dx, al
    cd_port ATA_LBA1
    out dx, al
    inc dx
    mov al, 8                   ; Maximum data phase2048 bytes.
    out dx, al
    cd_port ATA_COMMAND
    mov al, 0xA0
    out dx, al
    call ata_delay
    mov ah, 8                  ; PACKET requires command DRQ, not merely !BSY.
    call cd_current_phase
    jc .return
    test al, 8
    jz .protocol
    cd_port ATA_COUNT
    in al, dx
    and al, 3
    cmp al, 1                  ; Command-out phase.
    jne .protocol
    mov si, CD_CMD
    movzx cx, byte [fs:CD_WIDTH]
    shr cx, 1
    cd_port ATA_DATA
.command:
    mov ax, [fs:si]
    out dx, ax
    add si, 2
    loop .command
.phase:
    call ata_delay
    xor ah, ah                 ; Data DRQ or command completion is allowed.
    call cd_current_phase
    jc .return
    test al, 8
    jz .complete
    cd_port ATA_COUNT
    in al, dx
    and al, 3
    cmp al, 2                  ; Data-in phase.
    jne .protocol
    cd_port ATA_LBA1
    in al, dx
    mov bl, al
    inc dx
    in al, dx
    mov bh, al
    test bx, bx
    jz .protocol
    test bl, 1
    jnz .protocol              ; All supported replies have even byte counts.
    mov ax, [fs:CD_RECEIVED]
    add ax, bx
    jc .protocol
    cmp ax, [fs:CD_EXPECT]
    ja .protocol
    mov cx, bx
    shr cx, 1
    cd_port ATA_DATA
.data:
    in ax, dx
    mov bx, [fs:CD_RECEIVED]
    add word [fs:CD_RECEIVED], 2
    cmp bx, [fs:CD_SKIP]
    jb .discard
    sub bx, [fs:CD_SKIP]
    cmp bx, [fs:CD_KEEP]
    jae .discard
    mov [es:di], ax
    add di, 2
    jnc .discard
    mov ax, es
    add ax, 0x1000
    mov es, ax
.discard:
    loop .data
    jmp .phase
.complete:
    cd_port ATA_COUNT
    in al, dx
    and al, 3
    cmp al, 3
    jne .protocol
    mov ax, [fs:CD_RECEIVED]
    cmp ax, [fs:CD_EXPECT]
    jne .protocol
    jmp .return
.protocol:
    mov byte [fs:CD_STATUS], ERR_CONTROLLER
    cd_port ATA_COMMAND
    mov al, 8                  ; Abort only the selected packet device.
    out dx, al
    call ata_delay
    call cd_wait_phase
    mov byte [fs:CD_STATUS], ERR_CONTROLLER
.return:
    cd_port ATA_STATUS
    in al, dx                  ; Release INTRQ before re-enabling device IRQs.
    cd_port ATA_CONTROL
    xor al, al
    out dx, al
    cmp byte [fs:CD_STATUS], 1
    cmc                        ; CF set iff nonzero status.
    pop ebp
    pop esi
    pop edx
    pop ecx
    pop ebx
    pop eax
    ret

cd_wait_phase:
    mov cx, 15000
    cd_port ATA_CONTROL
.wait:
    in al, dx
    test al, 0x80
    jz .settled
    call kbc_delay_2ms
    loop .wait
    mov byte [fs:CD_STATUS], ERR_TIMEOUT
    stc
    ret
.settled:
    ; ERR from the previous command is allowed before sending a new PACKET.
    ; A current command's ERR is checked separately by its phase owner.
    clc
    ret

cd_current_phase:
    mov cx, 15000
    cd_port ATA_CONTROL
.wait:
    in al, dx
    test al, 0x80
    jnz .next
    cd_port ATA_STATUS
    in al, dx                  ; Acknowledge each command/data/completion phase.
    test al, 0x80
    jnz .next
    test al, 0x21
    jnz .controller
    test ah, 8
    jz .done
    test al, 8
    jnz .done
.next:
    cd_port ATA_CONTROL
    call kbc_delay_2ms
    loop .wait
    mov byte [fs:CD_STATUS], ERR_TIMEOUT
    stc
    ret
.controller:
    mov byte [fs:CD_STATUS], ERR_CONTROLLER
    stc
.done:
    ret

cd_int13:
    push bp
    mov bp, sp
    pushad
    push es
    push fs
    call load_bios_state
    cld
    sti
    cmp byte [fs:CD_ACTIVE], 1
    jne .chain
    cmp ah, 0x4B
    je .information
    cmp dl, [fs:CD_PACKET+2]
    jne .chain
    cmp ah, 1
    je .status
    mov byte [fs:CD_STATUS], 0
    cmp ah, 0
    je .success
    cmp ah, 0x0D
    je .success
    cmp ah, 0x10
    je .success
    cmp ah, 0x16
    je .success
    cmp ah, 0x15
    je .type
    cmp byte [fs:CD_PACKET+1], 0
    jne .floppy_dispatch
    cmp ah, 0x41
    je .extensions
    cmp ah, 0x48
    je .parameters
    cmp ah, 0x42
    je .extended
    jmp .bad_command
.floppy_dispatch:
    cmp ah, 8
    je .geometry
    cmp ah, 2
    je .legacy
    cmp ah, 4
    je .legacy
    cmp ah, 3
    je .write_protected
    cmp ah, 5
    je .write_protected
    jmp .bad_command
.type:
    mov ah, 1
    jmp .ok
.status:
    mov ah, [fs:CD_STATUS]
    test ah, ah
    jnz .error
    jmp .ok
.geometry:
    mov ch, [fs:CD_PACKET+16]
    mov cl, [fs:CD_PACKET+17]
    mov dh, 1
    mov dl, 1
    cmp byte [fs:F_TYPES], 0
    jz .geometry_count
    cmp byte [fs:C_PORTS+P_FLOPPY], 0
    je .geometry_count
    inc dl
.geometry_count:
    mov bl, [fs:CD_PACKET+1]
    cmp bl, 1
    je .geometry_type
    add bl, 2                  ; Catalog2/3 => BIOS floppy type4/5.
.geometry_type:
    cmp bl, 1
    jne .geometry_result
    inc bl                     ; Catalog1 => BIOS floppy type2.
.geometry_result:
    mov [ss:bp-16], bx
    mov [ss:bp-8], cx
    mov [ss:bp-12], dx
    movzx bx, byte [fs:CD_PACKET+1]
    dec bx
    shl bx, 1
    mov di, [cs:cd_dpt+bx]
    mov [ss:bp-32], di
    mov word [ss:bp-34], 0xF000
    jmp .success
.legacy:
    test al, al
    jz .bad_address
    cmp al, 128
    ja .bad_address
    movzx edi, al
    shl edi, 9                 ; Requested bytes.
    mov al, cl
    and al, 0x3F
    jz .bad_address
    cmp al, [fs:CD_PACKET+17]
    ja .bad_address
    cmp dh, 1
    ja .bad_address
    movzx eax, ch
    test cl, 0xC0
    jnz .bad_address
    cmp al, 79
    ja .bad_address
    shl eax, 1
    movzx edx, dh
    add eax, edx
    movzx edx, byte [fs:CD_PACKET+17]
    imul eax, edx
    movzx edx, cl
    dec edx
    add eax, edx
    movzx ecx, byte [ss:bp-4]   ; Original AL.
    add ecx, eax
    movzx edx, byte [fs:CD_PACKET+17]
    imul edx, 160
    cmp ecx, edx
    ja .bad_address
    mov edx, eax
    and edx, 3
    shl edx, 9
    shr eax, 2
    add eax, [fs:CD_PACKET+4]
    mov ecx, edi
    cmp byte [ss:bp-3], 4
    je .success                ; VERIFY validates the virtual extent.
    jmp .read
.extensions:
    cmp bx, 0x55AA
    jne .bad_command
    mov word [ss:bp-16], 0xAA55
    mov word [ss:bp-8], 5       ; Extended access and removable media.
    mov ah, 0x30
    jmp .ok
.parameters:
    cmp word [ds:si], 26
    jb .bad_address
    push es
    push ds
    pop es
    mov di, si
    mov ecx, 26
    call cd_check_buffer
    pop es
    jc .bad_address
    mov word [ds:si], 26
    mov word [ds:si+2], 4       ; Removable; CHS geometry not supplied.
    mov dword [ds:si+4], 0
    mov dword [ds:si+8], 0
    mov dword [ds:si+12], 0
    mov eax, [fs:CD_CAPACITY]
    mov [ds:si+16], eax
    mov dword [ds:si+20], 0
    mov word [ds:si+24], 2048
    jmp .success
.extended:
    cmp si, 0xFFF0
    ja .bad_address
    cmp word [ds:si], 0x10
    jne .dap_bad
    movzx ecx, word [ds:si+2]
    test ecx, ecx
    jz .dap_bad
    cmp ecx, 127
    ja .dap_bad
    cmp dword [ds:si+12], 0
    jne .dap_bad
    mov eax, [ds:si+8]
    mov edx, eax
    add edx, ecx
    jc .dap_bad
    cmp edx, [fs:CD_CAPACITY]
    ja .dap_bad
    mov bx, [ds:si+4]
    mov es, [ds:si+6]
    shl ecx, 11
    xor edx, edx
.read:
    mov di, bx
    push eax
    push edx
    call cd_check_buffer
    pop edx
    pop eax
    jc .dap_bad
    call cd_read_span
    jc .read_error
    jmp .success
.dap_bad:
    cmp byte [ss:bp-3], 0x42
    jne .bad_address
    mov word [ds:si+2], 0
.bad_address:
    mov ah, ERR_BAD_ADDRESS
    jmp .error
.read_error:
    cmp byte [ss:bp-3], 0x42
    jne .read_status
    mov word [ds:si+2], 0       ; No partial result claimed on command failure.
.read_status:
    mov ah, [fs:CD_STATUS]
    jmp .error
.write_protected:
    mov ah, 3
    jmp .error
.bad_command:
    mov ah, ERR_BAD_COMMAND
    jmp .error
.information:
    cmp al, 1
    ja .bad_command
    cmp dl, 0x7F
    je .packet_buffer
    cmp dl, [fs:CD_PACKET+2]
    jne .chain
.packet_buffer:
    push es
    push ds
    pop es
    mov di, si
    mov ecx, 19
    call cd_check_buffer
    pop es
    jc .bad_address
    push es
    push ds
    pop es
    mov di, si
    mov bx, CD_PACKET
    mov cx, 19
.packet_copy:
    mov al, [fs:bx]
    stosb
    inc bx
    loop .packet_copy
    pop es
    cmp byte [ss:bp-4], 0
    jne .success
    call cd_boot_clear
.success:
    mov al, [ss:bp-4]
    xor ah, ah
.ok:
    mov byte [fs:CD_STATUS], 0
    and word [ss:bp+6], 0xFFFE
    jmp .return
.error:
    mov [fs:CD_STATUS], ah
    or word [ss:bp+6], 1
.return:
    mov [ss:bp-4], ax
    push ds
    push ax
    xor ax, ax
    mov ds, ax
    mov al, [fs:CD_STATUS]
    cmp byte [ss:bp-12], 0
    jne .cd_status
    mov [0x441], al
    jmp .published
.cd_status:
    mov [0x474], al
.published:
    pop ax
    pop ds
    or word [ss:bp+6], 0x200
    pop fs
    pop es
    popad
    pop bp
    iret
.chain:
    pop fs
    pop es
    popad
    pop bp
    jmp cd_chain13

; ES:DI, ECX bytes. Existing EBDA overlap guard, plus a64-KB segment bound.
cd_check_buffer:
    push eax
    push edx
    movzx eax, di
    add eax, ecx
    cmp eax, 0x10000
    ja .bad
    mov eax, es
    and eax, 0xFFFF
    shl eax, 4
    movzx edx, di
    add eax, edx
    mov edx, eax
    add edx, ecx
    call check_disk_buffer
    jmp .done
.bad:
    stc
.done:
    pop edx
    pop eax
    ret

; Forward to the installed owner with all original input registers, including
; BP and FS. A far pointer on the caller's stack works even after EBDA moves.
cd_chain13:
    ; Build the far entry/return frames with16-bit stack addresses. ESP's
    ; upper half is caller-owned and is not part of a real-mode stack offset.
    sub sp, 18
    push bp
    mov bp, sp
    mov [ss:bp+16], dx
    mov [ss:bp+18], ax
    push eax
    push fs
    call load_bios_state
    mov eax, [fs:CD_OLD13]
    mov [ss:bp+2], eax
    cmp byte [fs:CD_ACTIVE], 1
    jne .tail
    cmp byte [fs:CD_PACKET+1], 0
    je .tail
    cmp dl, 1
    jne .tail
    dec dl                      ; Physical A becomes B during floppy emulation.
    mov word [ss:bp+6], cd_chain13_return
    mov word [ss:bp+8], 0xF000
    mov ax, [ss:bp+24]          ; Preserve caller DF/IF in the synthetic IRQ frame.
    mov [ss:bp+10], ax
    pop fs
    pop eax
    pop bp
    retf                        ; Installed handler returns through its normal IRET.
.tail:
    pop fs
    pop eax
    pop bp
    retf 14

cd_chain13_return:
    push bp
    mov bp, sp
    push ax
    pushf
    pop ax
    mov [ss:bp+14], ax          ; Original interrupt flags.
    pop ax
    ; Only displaced floppy B reaches this return owner. AH15 returns a
    ; floppy type in AH; DX sector counts belong to HDD calls on the tail path.
    cmp byte [ss:bp+9], 8
    je .count
    mov dl, [ss:bp+6]
    jmp .forwarded
.count:
    mov dl, 2
.forwarded:
    pop bp
    add sp, 8
    iret

cd_spt db 15,18,36
cd_dpt dw floppy_dpt_1200,floppy_dpt_1440,floppy_dpt_2880
cd_descriptor db 'CD001',1,'EL TORITO SPECIFICATION',0
cd_descriptor_end:
