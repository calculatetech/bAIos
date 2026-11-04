; Common guarded register access and mode-persistence check for S3DAC/S3WAIT.
bits 16
org 0x100
start:
    cld
    push cs
    pop ds
    mov si,0x81
    xor cx,cx
    mov cl,[0x80]
.argument:
    jcxz .parsed
    lodsb
    dec cx
    cmp al,' '
    je .argument
    cmp al,9
    je .argument
    cmp byte [argument],0xFF
    jne usage
%ifdef CONTROL_WAIT
    cmp al,'2'
    je .late
    cmp al,'1'
    jne usage
    mov al,3
    jmp .save
.late:
    mov al,2
%else
    cmp al,'0'
    je .zero
    cmp al,'1'
    je .one
    and al,0xDF
    cmp al,'T'
    jne usage
    jmp .save
.zero:
    xor al,al
    jmp .save
.one:
    mov al,1
%endif
.save:
    mov [argument],al
    jmp .argument
.parsed:
    smsw ax
    test al,1
    jnz real_required
    mov ah,0x0F
    int 0x10
    and al,0x7F
    cmp al,3
    je .text
    cmp al,7
    jne text_required
.text:
    mov [old_mode],al
    call access_controls
    cmp byte [status],0
    jne report_error
    mov al,[current]
    mov [original_bit],al
    cmp byte [argument],0xFF
    je report_read
    cmp byte [argument],'T'
    je .toggle
    mov al,[argument]
    jmp .apply
.toggle:
    xor al,1
.apply:
    mov [wanted],al
    mov byte [operation],1
    call access_controls
    cmp byte [status],0
    jne report_error

    ; A BIOS mode set could undo the experiment before Doom starts.
    mov al,0x13
    call set_mode
    mov byte [operation],0
    call access_controls
    mov al,[status]
    mov [graphics_status],al
    mov al,[current]
    mov [graphics_bit],al
    mov al,[old_mode]
    call set_mode
    cmp byte [graphics_status],0
    jne .mode_changed
    mov al,[graphics_bit]
    cmp al,[wanted]
    jne .mode_changed
    ; Restore the chosen bit in text too, preserving that mode's peer bits.
    mov byte [operation],1
    call access_controls
    cmp byte [status],0
    jne .restore_original
    mov si,success
    mov al,[original_bit]
    call bit_character
    mov [before_digit],al
    mov al,[wanted]
    call bit_character
    mov [after_digit],al
    jmp print_exit
.mode_changed:
    mov byte [status],4
.restore_original:
    mov al,[status]
    mov [failure],al
    mov al,[original_bit]
    mov [wanted],al
    mov byte [operation],1
    call access_controls
    cmp byte [status],0
    jne .restore_failed
    mov al,[failure]
    mov [status],al
    jmp report_error
.restore_failed:
    mov byte [status],5
    jmp report_error

report_read:
    mov al,[original_bit]
    call bit_character
    mov [current_digit],al
    mov si,read_message
    jmp print_exit
bit_character:
%ifdef CONTROL_WAIT
    test al,2
    jz .zero
    test al,1
    jz .late
    mov al,1
    jmp .digit
.late:
    mov al,2
    jmp .digit
.zero:
    xor al,al
.digit:
%endif
    add al,'0'
    ret
usage:
    mov si,usage_message
    mov byte [status],2
    jmp print_exit
real_required:
    mov si,real_message
    mov byte [status],1
    jmp print_exit
text_required:
    mov si,text_message
    mov byte [status],2
    jmp print_exit
report_error:
    mov si,card_message
    cmp byte [status],2
    je print_exit
    mov si,write_message
    cmp byte [status],3
    je print_exit
    mov si,mode_message
    cmp byte [status],4
    je print_exit
    mov si,restore_message
print_exit:
    mov dx,si
    xor cx,cx
.length:
    lodsb
    test al,al
    jz .write
    inc cx
    jmp .length
.write:
    mov bx,1
    mov ah,0x40
    int 0x21
    jc .output_error
    cmp ax,cx
    jne .output_error
    mov al,[status]
    mov ah,0x4C
    int 0x21
.output_error:
    mov ax,0x4C01
    int 0x21

set_mode:
    pushad
    push ds
    push es
    push fs
    push gs
    xor ah,ah
    int 0x10
    pop gs
    pop fs
    pop es
    pop ds
    popad
    cld
    ret

; Byte I/O only. No PCI access, DAC data access or CRTC register sweep.
access_controls:
    pushf
    cli
    pushad
    mov byte [status],2
    mov dx,0x3CC
    in al,dx
    test al,1
    mov dx,0x3B4
    jz .port
    mov dx,0x3D4
.port:
    mov [cr_port],dx
    in al,dx
    mov [cr_index],al
    mov al,0x38
    call cr_read
    mov [lock38],al
    mov ax,0x4838
    call cr_write
    mov al,0x39
    call cr_read
    mov [lock39],al
    mov ax,0xA539
    call cr_write
    mov al,0x2D
    call cr_read
    cmp al,0x88
    jne .cleanup
    mov al,0x2E
    call cr_read
    cmp al,0x11
    jne .cleanup
    mov al,0x36
    call cr_read
    and al,3
    cmp al,1
    jne .cleanup
    xor bx,bx
    mov bp,1
    mov byte [current],0
.read:
    mov al,[control_regs+bx]
    call cr_read
    mov [saved+bx],al
    mov cl,[control_masks+bx]
    mov dx,bp
    test al,cl
    jz .clear
    or [current],dl
.clear:
    mov ah,cl
    not ah
    and al,ah
    test [wanted],dl
    jz .expected
    or al,cl
.expected:
    mov [expected+bx],al
    shl bp,1
    inc bx
    cmp bx,control_count
    jb .read
    mov byte [status],0
    cmp byte [operation],0
    je .cleanup
    xor bx,bx
.write:
    mov ah,[expected+bx]
    mov al,[control_regs+bx]
    call cr_write
    inc bx
    cmp bx,control_count
    jb .write
    xor bx,bx
.verify:
    mov al,[control_regs+bx]
    call cr_read
    cmp al,[expected+bx]
    jne .rollback
    inc bx
    cmp bx,control_count
    jb .verify
    jmp .cleanup
.rollback:
    mov byte [status],3
    mov bx,control_count-1
.undo:
    mov ah,[saved+bx]
    mov al,[control_regs+bx]
    call cr_write
    dec bx
    jns .undo
    xor bx,bx
.verify_undo:
    mov al,[control_regs+bx]
    call cr_read
    cmp al,[saved+bx]
    je .restored
    mov byte [status],5
.restored:
    inc bx
    cmp bx,control_count
    jb .verify_undo
.cleanup:
    mov ah,[lock39]
    mov al,0x39
    call cr_write
    mov ah,[lock38]
    mov al,0x38
    call cr_write
    mov dx,[cr_port]
    mov al,[cr_index]
    out dx,al
    popad
    popf
    ret
cr_read:
    mov dx,[cr_port]
    out dx,al
    inc dx
    in al,dx
    ret
cr_write:
    mov dx,[cr_port]
    out dx,al
    inc dx
    mov al,ah
    out dx,al
    ret

%ifdef CONTROL_WAIT
%define PREFIX 'W'
%else
%define PREFIX 'D'
%endif
success db PREFIX,'0 '
before_digit db '0'
    db '>'
after_digit db '0'
    db ' Mode13 retained. Run Doom with sound effects.',13,10,0
read_message db PREFIX,'0 current='
current_digit db '0'
%ifdef CONTROL_WAIT
    db ' (0=no wait, 1=one wait/T1, 2=one wait/T2)',13,10,0
usage_message db 'W2 Usage: S3WAIT [1|2]. No argument reads only.',13,10,0
%else
    db ' (S3DAC T toggles; S3DAC 0 or 1 selects)',13,10,0
usage_message db 'D2 Usage: S3DAC [0|1|T]. No argument reads only.',13,10,0
%endif
real_message db PREFIX,'1 Use plain DOS without EMM386 or another protected manager.',13,10,0
text_message db PREFIX,'2 Start in text mode 3 or 7.',13,10,0
card_message db PREFIX,'2 VLB Trio64 (8811) required. No trial controls changed.',13,10,0
write_message db PREFIX,'3 Write did not verify; original controls restored.',13,10,0
mode_message db PREFIX,'4 Graphics mode did not retain the controls; original choice restored.',13,10,0
restore_message db PREFIX,'5 Could not restore the controls. Reboot.',13,10,0
%ifdef CONTROL_WAIT
; Set latch phase before the wait selector; undo in reverse order.
control_regs db 0x58,0x40
control_masks db 0x08,0x10
%else
control_regs db 0x37
control_masks db 0x10
%endif
control_count equ control_masks-control_regs
saved times control_count db 0
expected times control_count db 0
argument db 0xFF
status db 0
operation db 0
wanted db 0
original_bit db 0
current db 0
old_mode db 0
graphics_status db 0
graphics_bit db 0
failure db 0
cr_port dw 0
cr_index db 0
lock38 db 0
lock39 db 0
