bits 16
org 0x100
    push cs
    pop ds
    push cs
    pop es
    cld
    mov byte [failure],0x71
    mov ax,0x3000
    int 0x21
    cmp ax,0x1606                 ; Actual DOS6.22, not a boot-sector lookalike.
    jne fail
    cmp byte [0x82],'X'
    je .himem
    cmp byte [0x82],'Y'
    jne .normal
.himem:
    call xms_check
.normal:
    cmp byte [0x82],'W'
    jne .services
    mov byte [failure],0x77
    mov eax,cr0
    test eax,0x60000000           ; This fixture explicitly enables internal L1.
    jnz fail
    xor ax,ax
    mov es,ax
    mov al,0x37
    out 0x70,al
    in al,0x71
    cmp al,0x5A
    jne .request_reset
    mov byte [failure],0x78
    xor dl,dl
    call dirty_memory
    cmp dword [marker_value],0xC0DEFACE
    jne fail
    call warm_state
    mov al,0x37
    out 0x70,al
    xor al,al
    out 0x71,al
    push cs
    pop es
.services:
    mov byte [failure],0x72
    mov dx,filename
    xor cx,cx
    mov ah,0x3C
    int 0x21
    jc fail
    mov bx,ax
    mov dx,payload
    mov cx,32
    mov ah,0x40
    int 0x21
    jc fail
    cmp ax,32
    jne fail
    mov ah,0x3E
    int 0x21
    jc fail
    mov dx,filename
    mov ax,0x3D00
    int 0x21
    jc fail
    mov bx,ax
    mov dx,read_buffer
    mov cx,32
    mov ah,0x3F
    int 0x21
    jc fail
    mov ah,0x3E
    int 0x21
    mov si,payload
    mov di,read_buffer
    mov cx,16
    repe cmpsw
    jne fail
    mov dx,filename
    mov ah,0x41
    int 0x21
    jc fail
    mov byte [failure],0x73
    mov di,read_buffer
    mov cx,512
    mov ax,0xA55A
    rep stosw
    mov ax,0x0202
    mov bx,read_buffer
    mov cx,1
    mov dx,0x80
    int 0x13                      ; Multi-sector native CHS.
    jc fail
    cmp al,2
    jne fail
    cmp word [read_buffer+510],0xAA55
    jne fail
    mov si,read_buffer+512
    mov cx,256                   ; Fixture sector1 is independently checked zero.
.second_sector:
    cmp word [si],0
    jne fail
    add si,2
    loop .second_sector
    mov byte [failure],0x6C
    mov si,read_buffer+446
    mov cx,4
.active_partition:
    cmp byte [si],0x80
    je .partition_found
    add si,16
    loop .active_partition
    jmp fail
.partition_found:
    cmp dword [si+8],8064         ; Retained disposable FAT16 partition start.
    jne fail
    mov dword [packet+8],8064
    mov word [packet+4],original
    mov ax,cs
    mov [packet+6],ax
    mov ax,0x4200
    call edd
    jc fail
    cmp word [original+24],63
    jne fail
    cmp word [original+26],64
    jne fail
    cmp dword [original+28],8064
    jne fail
    push es
    mov ax,0x0800
    mov dl,0x80
    int 0x13
    pop es
    jc fail
    and cl,63
    cmp cl,63
    jne fail
    inc dh
    cmp dh,64
    jne fail
    mov byte [failure],0x74
    mov ax,0x4100
    mov bx,0x55AA
    mov dl,0x80
    int 0x13
    jc fail
    cmp bx,0xAA55
    jne fail
    mov si,parameters
    mov ax,0x4800
    mov dl,0x80
    int 0x13
    jc fail
    cmp word [parameters+24],512
    jne fail
    mov eax,[parameters+16]
    dec eax
    mov [packet+8],eax
    mov ax,cs
    mov [packet+6],ax
    mov word [packet+4],original
    mov ax,0x4200
    call edd
    jc fail
    mov di,written
    mov cx,256
    mov ax,0xA55A
.pattern:
    stosw
    inc ax
    loop .pattern
    mov byte [failure],0x75
    mov word [packet+4],written
    mov ax,0x4300
    call edd
    jc fail
    mov word [packet+4],read_buffer
    mov ax,0x4200
    call edd
    jc fail
    mov si,written
    mov di,read_buffer
    mov cx,256
    repe cmpsw
    jne fail
    mov word [packet+4],original
    mov ax,0x4300
    call edd                      ; Restore the disposable HDD test sector.
    jc fail
    mov word [packet+4],read_buffer
    mov ax,0x4200
    call edd
    jc fail
    mov si,original
    mov di,read_buffer
    mov cx,256
    repe cmpsw
    jne fail
    cmp byte [0x82],'F'
    je .floppy
    cmp byte [0x82],'X'
    jne .pass
.floppy:
    mov byte [failure],0x76
    mov ax,0x0201
    mov bx,original
    mov cx,0x4F12                 ; 1.44MB: cylinder79, head1, sector18.
    mov dx,0x0100
    int 0x13
    jc fail
    mov ax,0x0301
    mov bx,written
    mov cx,0x4F12
    mov dx,0x0100
    int 0x13
    jc fail
    mov ax,0x0201
    mov bx,read_buffer
    mov cx,0x4F12
    mov dx,0x0100
    int 0x13
    jc fail
    mov si,written
    mov di,read_buffer
    mov cx,256
    repe cmpsw
    jne fail
    mov ax,0x0301
    mov bx,original
    mov cx,0x4F12
    mov dx,0x0100
    int 0x13                      ; Restore the disposable floppy test sector.
    jc fail
    mov ax,0x0201
    mov bx,read_buffer
    mov cx,0x4F12
    mov dx,0x0100
    int 0x13
    jc fail
    mov si,original
    mov di,read_buffer
    mov cx,256
    repe cmpsw
    jne fail
.pass:
    mov al,0x67
    jmp terminal
.request_reset:
    push fs
    xor ax,ax
    mov fs,ax
    mov fs,[fs:0x40E]
    mov word [fs:0x1FFE],0xA55A ; Startup must clear its whole reserved state.
    pop fs
    mov dl,1
    call dirty_memory             ; DOS reload owns low RAM; use preserved DRAM.
    mov al,0x37
    out 0x70,al
    mov al,0x5A
    out 0x71,al
    sti
    mov si,warm_scans
    mov bp,3
.warm_key:
    lodsb
    call inject_scan
    cmp bp,1
    je .reset_wait
    mov ah,4
    cmp bp,3
    je .expected
    mov ah,0x0C
.expected:
    mov ecx,0x2000000
.modifier:
    mov al,[es:0x417]
    and al,0x0C
    cmp al,ah
    je .ready
    dec ecx
    jnz .modifier
    mov byte [failure],0x79
    jmp fail
.ready:
    dec bp
    jmp .warm_key
.reset_wait:
    hlt
    jmp .reset_wait
warm_state:
    pushad
    push ds
    push fs
    xor ax,ax
    mov ds,ax
    mov byte [cs:failure],81
    cmp word [0x40E],0x9E00
    jne .bad
    mov byte [cs:failure],82
    cmp word [0x413],632
    jne .bad
    mov fs,[0x40E]
    mov byte [cs:failure],83
    cmp byte [fs:0],8
    jne .bad
    mov byte [cs:failure],84
    cmp word [fs:0x1FFE],0
    jne .bad
    mov byte [cs:failure],85
    cmp word [fs:0xD0],15360
    jne .bad
    mov byte [cs:failure],86
    cmp byte [fs:0x20],1
    jne .bad
    mov byte [cs:failure],87
    cmp byte [fs:0x1052],0
    jne .bad
    mov byte [cs:failure],88
    cmp word [fs:0x1FFC],0xC0DE ; BIOS-owned vector oracle passed before DOS hooks.
    jne .bad
    mov dx,0xCF8
    mov eax,0x80008054
    out dx,eax
    mov dx,0xCFC
    in eax,dx
    mov byte [cs:failure],91
    cmp ax,0xC002
    jne .bad
    mov dx,0xCF8
    mov eax,0x80008050
    out dx,eax
    mov dx,0xCFC
    in eax,dx
    mov byte [cs:failure],92
    test al,0x80
    jnz .bad
    pop fs
    pop ds
    popad
    ret
 .bad:
    pop fs
    pop ds
    popad
    jmp fail
dirty_memory:
    pushf
    cli
    pushad
    push fs
    sgdt [saved_gdtr]
    mov ax,cs
    mov [real_pointer+2],ax
    movzx eax,ax
    shl eax,4
    mov [test_code+2],ax
    shr eax,16
    mov [test_code+4],al
    mov ax,cs
    movzx eax,ax
    shl eax,4
    add eax,test_gdt
    mov [test_gdtr+2],eax
    lgdt [test_gdtr]
    mov ebx,cr0
    mov eax,ebx
    or al,1
    mov cr0,eax
    jmp 0x08:.flat
.flat:
    mov ax,0x10
    mov fs,ax
    mov eax,ebx
    mov cr0,eax
    jmp far [cs:real_pointer]
.real:
    test dl,dl
    jz .read
    a32 mov dword [fs:0x512340],0xC0DEFACE
.read:
    a32 mov eax,[fs:0x512340]
    mov [marker_value],eax
    lgdt [saved_gdtr]
    pop fs
    popad
    popf
    ret
xms_check:
    mov byte [failure],0x7A
    mov ax,0x4300
    int 0x2F
    cmp al,0x80
    jne fail                    ; HIMEM initialized and installed its real API.
    mov ax,0x4310
    int 0x2F
    mov [xms_entry],bx
    mov [xms_entry+2],es
    push cs
    pop es
    cmp byte [0x82],'Y'
    jne .toggle
    mov ax,0x3306
    int 0x21
    test bh,0x10                ; DOS reports that its real kernel uses HMA.
    jz fail
    mov ah,7
    call far [xms_entry]
    cmp ax,1
    jne fail
    call a20_alias
    je fail
    jmp .free
.toggle:
    mov ah,3
    call far [xms_entry]
    cmp ax,1
    jne fail
    call a20_alias
    je fail                     ; Enable must actually remove the1MiB alias.
    mov ah,4
    call far [xms_entry]
    cmp ax,1
    jne fail
    call a20_alias
    jne fail                    ; Disable must physically restore the alias.
.free:
    mov ah,8
    call far [xms_entry]
    test ax,ax
    jz fail                     ; Extended memory is managed by the driver.
    ret
a20_alias:
    pushf
    cli
    push ds
    push es
    push dx
    xor ax,ax
    mov ds,ax
    mov ax,0xFFFF
    mov es,ax
    mov dl,[0x500]
    mov dh,[es:0x510]
    mov byte [0x500],0
    mov byte [es:0x510],0xFF
    cmp byte [0x500],0xFF
    mov [es:0x510],dh
    mov [0x500],dl
    pushf
    pop ax
    pop dx
    pop es
    pop ds
    popf
    and ax,0x40
    xor ax,0x40                 ; Return ZF=1 for wrapped A20, ZF=0 for open.
    ret
inject_scan:
    push cx
    mov ah,al
    mov cx,0xFFFF
.command:
    in al,0x64
    test al,2
    loopnz .command
    mov al,0xD2
    out 0x64,al
    mov cx,0xFFFF
.data:
    in al,0x64
    test al,2
    loopnz .data
    mov al,ah
    out 0x60,al
    mov cx,0xFFFF
.consumed:
    in al,0x64
    test al,3
    loopnz .consumed
    pop cx
    ret
edd:
    mov word [packet+2],1
    mov si,packet
    mov dl,0x80
    int 0x13
    ret
fail:
    mov al,[failure]
    jmp terminal
filename db 'C:\CORECHK.TMP',0
warm_scans db 0x1D,0x38,0x53
align 8
test_gdt:
    dq 0
test_code:
    dw 0xFFFF,0
    db 0,0x9A,0,0
    dq 0x00CF92000000FFFF
test_gdtr dw $-test_gdt-1
    dd 0
saved_gdtr times 6 db 0
real_pointer dw dirty_memory.real,0
marker_value dd 0
xms_entry dw 0,0
payload times 16 dw 0x693C
failure db 0
packet db 0x10,0
    dw 1,0,0
    dq 0
parameters dw 0x1E
    times 28 db 0
%include "test-terminal.inc"
original times 512 db 0
written times 512 db 0
read_buffer times 1024 db 0
