bits 16
org 0x7C00
%include "test-configuration.inc"
jmp short start
times 11-($-$$) db 0
dw 512
db 1
dw 1
times 24-($-$$) db 0
dw 63,16
dd 0
times 62-($-$$) db 0
start:
    mov ax,ss
    test ax,ax
    jnz .bad_early
    cmp sp,0x7000
    jne .bad_early
    pushf
    pop ax
    and ax,0x600
    cmp ax,0x200
    jne .bad_early
    xor ax,ax
    mov ds,ax
%if TEST_DIRTY_VGA
    cmp byte [0xB49],1
    jne .bad_early
%endif
%if TEST_DIRTY_OPTION
    cmp byte [0xB48],1
    jne .bad_early
%endif
%if TEST_BOOT_PROVIDER
    cmp word [0x620],1
    jne .bad_early
    cmp word [0x622],1
    jne .bad_early
%endif
    mov ax,[0x40E]
    mov fs,ax
    mov al,0x61
%if TEST_BOOT_PROVIDER
    cmp byte [fs:0x48],2
    jne .bad_early
%endif
%if TEST_OPTION_SCAN
    cmp word [0x600],TEST_ROM_COUNT0
    jne .bad_early
    cmp word [0x602],TEST_ROM_COUNT1
    jne .bad_early
    cmp word [0x604],TEST_ROM_COUNT2
    jne .bad_early
    cmp word [0x606],TEST_ROM_COUNT3
    jne .bad_early
    cmp byte [fs:0x52],TEST_ROM_COUNT0+TEST_ROM_COUNT1+TEST_ROM_COUNT2+TEST_ROM_COUNT3
    jne .bad_early
    cmp byte [fs:0x175],TEST_ROM_ERROR
    jne .bad_early
%endif
    cmp byte [fs:0],8
    jb terminal
    ; The controlled machine has640KiB before firmware allocations. The
    ; complete advertised runtime region must still end at that ceiling.
    movzx bx,byte [fs:0]
    shl bx,6
    mov ax,fs
    add bx,ax
    jc .bad_early
    cmp bx,0xA000
    jne .bad_early
    cmp byte [fs:0x50],TEST_RAM_FLAGS
    jne .bad_early
%if TEST_RAM_OBSERVER
    cmp byte [0xB34],1
    jne .bad_early
    call 0xF000:TEST_RAM_RESTORE_OFFSET
    jc .bad_early
%endif
    int 0x12
    cmp ax,[0x413]
    jne .bad_early
    mov bx,fs
    shr bx,6
    cmp ax,bx
    jne .bad_early
    push es
    mov ax,0xC100
    int 0x15
    jc .bad_early
    mov ax,es
    cmp ax,[0x40E]
    jne .bad_early
    pop es
    jmp short .memory_services
.bad_early:
    jmp bad
.memory_services:
    mov ah,0x88
    int 0x15
    jc .bad_early
    cmp ax,TEST_RAM_KIB-1024
    jne .bad_early
    xor ax,ax
    mov es,ax
    cmp word [0x42],0xC000
    jne .bad_early
    mov eax,[0x40]
%if TEST_VGA60
    mov eax,0xF000F065
%endif
    cmp eax,[0x108]
    jne .bad_early
%if TEST_VGA60
    ; DOS applications probe unsupported video extensions before drawing UI.
    mov ax,0xFE01
    int 0x10
    cmp ax,0xFE01
    jne .bad_early
    mov ax,0xFF08
    int 0x10
    cmp ax,0xFF08
    jne .bad_early
    int 0x42
    cmp ax,0xFF08
    jne .bad_early
    mov ah,0x0F
    int 0x42
    cmp ax,0x5003
    jne .bad_early
    mov dx,0x3C4
    mov al,0x1F
    out dx,al
    inc dx
    in al,dx
    and al,0x3F
    cmp al,0x22
    jne .bad_early
%endif
%if TEST_SHADOW_CHECK
    cmp byte [fs:0x1007],TEST_ONBOARD_ORIGIN
    jne .bad_early
    mov al,2
    out 0xF2,al
    in al,0xF3
    and al,0x11
    cmp al,TEST_SHADOW_MASK
    jne .bad_early
%endif
%if TEST_CHIP_REFRESH_CHECK
    mov al,5
    out 0xF2,al
    in al,0xF3
    and al,3
    cmp al,TEST_CHIP_REFRESH_VALUE
    jne .bad_early
%endif
%if TEST_CHIP_ADS_CHECK
    mov al,0x1A
    out 0xF2,al
    in al,0xF3
    and al,0x80
    cmp al,TEST_CHIP_ADS_VALUE
    jne .bad_early
    cmp byte [fs:0x60],1
    jne .bad_early
%endif
    mov bx,0x55AA
    mov ax,0x4100
    mov dl,0x80
    int 0x13
    jc .bad_early
    cmp bx,0xAA55
    jne .bad_early
    test cx,1
    jz .bad_early
%if TEST_DISK_SERVICES
    mov word [0x600],0x1E
    mov si,0x600
    mov ax,0x4800
    mov dl,0x80
    int 0x13
    jc bad
    cmp word [0x600+24],512
    jne bad
    cmp dword [0x600+16],32256
    jne bad
    mov word [0x600],0x10
    mov word [0x602],1
    mov dword [0x604],0x8000
    mov dword [0x608],17
    mov dword [0x60C],0
    mov si,0x600
    mov ax,0x4200
    int 0x13
    jc bad
    cmp dword [0x8000],0x41544144
    jne bad
    mov dword [0x8000],0xD00DFEED
    inc dword [0x608]
    mov ax,0x4300
    int 0x13
    jc bad
    mov dword [0x8000],0
    mov ax,0x4200
    int 0x13
    jc bad
    cmp dword [0x8000],0xD00DFEED
    jne bad
    mov dword [0x608],32256
    mov ax,0x4200
    int 0x13
    jnc bad
    cmp ah,4
    jne bad
    cmp word [0x602],0
    jne bad
%endif
%if TEST_FLOPPY
    xor dx,dx
    mov bp,TEST_FLOPPY_WORD
    call .floppy_check
%if TEST_FLOPPY_B
    mov dx,1
    mov bp,TEST_FLOPPY_WORD_B
    call .floppy_check
%endif
%endif
%if TEST_RUNTIME_INPUT
.wait_command:
    in al,0x64
    test al,2
    jnz .wait_command
    mov al,0xD2
    out 0x64,al
.wait_data:
    in al,0x64
    test al,2
    jnz .wait_data
    mov al,0x1E
    out 0x60,al
    xor ax,ax
    int 0x16
    cmp ax,0x1E61
    jne bad
%endif
%include "native-memory-result.inc"
    mov al,[fs:0]
    mov [es:4064],al
    call .write_dump
    push ds
    mov ax,0x1130
    mov bh,6
    int 0x10
    pop ds
    mov [dump_packet+4],bp
    mov [dump_packet+6],es
    mov dword [dump_packet+8],9
    call .write_dump
%if TEST_SHADOW_CHECK
    mov word [dump_packet+2],64
    mov word [dump_packet+4],0
    mov word [dump_packet+6],0xF000
    mov dword [dump_packet+8],17
    call .write_dump
    mov word [dump_packet+4],0x8000
    mov dword [dump_packet+8],81
    mov ax,0x4300
    int 0x13
    jc bad
%endif
    mov al,0x60
    jmp terminal
; Result writes share the same real EDD request and error owner.
.write_dump:
    mov si,dump_packet
    mov ax,0x4300
    mov dl,0x80
    int 0x13
    jc bad
    ret
%if TEST_FLOPPY
.floppy_check:
    push dx
    push bp
    mov ax,0x0800
    int 0x13
    jc bad
    test ah,ah
    jne bad
    cmp ch,79
    jne bad
    cmp dl,TEST_FLOPPY_COUNT
    jne bad
    cmp bl,4
    jne bad
    and cl,63
    cmp cl,18
    jne bad
    cmp dh,1
    jne bad
    pop bp
    pop dx
    push bp
    push ds
    pop es
    mov bx,0x8000
    mov ax,0x0201
    mov cx,2
    int 0x13
    jc bad
    cmp ax,1
    jne bad
    pop bp
    cmp word [0x8000],bp
    jne bad
    ret
%endif
bad:
    mov al,0x62
    jmp terminal
dump_packet db 0x10,0
    dw 8,0,0xB800
    dq 1
%include "test-terminal.inc"
times 510-($-$$) db 0
dw 0xAA55
