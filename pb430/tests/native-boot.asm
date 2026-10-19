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
    jnz bad
    cmp sp,0x7000
    jne bad
    pushf
    pop ax
    and ax,0x600
    cmp ax,0x200
    jne bad
    xor ax,ax
    mov ds,ax
%if TEST_DIRTY_VGA
    cmp byte [0xB49],1
    jne bad
%endif
%if TEST_DIRTY_OPTION
    cmp byte [0xB48],1
    jne bad
%endif
%if TEST_BOOT_PROVIDER
    cmp word [0x620],1
    jne bad
    cmp word [0x622],1
    jne bad
%endif
    mov ax,[0x40E]
    mov fs,ax
    mov al,0x61
%if TEST_BOOT_PROVIDER
    cmp byte [fs:0x48],2
    jne bad
%endif
%if TEST_OPTION_SCAN
    cmp word [0x600],TEST_ROM_COUNT0
    jne bad
    cmp word [0x602],TEST_ROM_COUNT1
    jne bad
    cmp word [0x604],TEST_ROM_COUNT2
    jne bad
    cmp word [0x606],TEST_ROM_COUNT3
    jne bad
    cmp byte [fs:0x52],TEST_ROM_COUNT0+TEST_ROM_COUNT1+TEST_ROM_COUNT2+TEST_ROM_COUNT3
    jne bad
    cmp byte [fs:0x175],TEST_ROM_ERROR
    jne bad
%endif
    cmp byte [fs:0],8
    jne terminal
    cmp byte [fs:0x50],TEST_RAM_FLAGS
    jne bad
%if TEST_RAM_OBSERVER
    cmp byte [0xB34],1
    jne bad
    call 0xF000:TEST_RAM_RESTORE_OFFSET
    jc bad
%endif
    int 0x12
    cmp ax,632
    jne bad
    mov ah,0x88
    int 0x15
    jc bad
    cmp ax,TEST_RAM_KIB-1024
    jne bad
    xor ax,ax
    mov es,ax
    cmp word [0x42],0xC000
    jne bad
    mov eax,[0x40]
%if TEST_VGA60
    mov eax,0xF000F065
%endif
    cmp eax,[0x108]
    jne bad
%if TEST_VGA60
    ; DOS applications probe unsupported video extensions before drawing UI.
    mov ax,0xFE01
    int 0x10
    cmp ax,0xFE01
    jne bad
    mov ax,0xFF08
    int 0x10
    cmp ax,0xFF08
    jne bad
    int 0x42
    cmp ax,0xFF08
    jne bad
    mov ah,0x0F
    int 0x42
    cmp ax,0x5003
    jne bad
    mov dx,0x3C4
    mov al,0x1F
    out dx,al
    inc dx
    in al,dx
    and al,0x3F
    cmp al,0x22
    jne bad
%endif
%if TEST_SHADOW_CHECK
    cmp byte [fs:0x1007],TEST_ONBOARD_ORIGIN
    jne bad
    mov al,2
    out 0xF2,al
    in al,0xF3
    and al,0x11
    cmp al,TEST_SHADOW_MASK
    jne bad
%endif
%if TEST_CHIP_REFRESH_CHECK
    mov al,5
    out 0xF2,al
    in al,0xF3
    and al,3
    cmp al,TEST_CHIP_REFRESH_VALUE
    jne bad
%endif
%if TEST_CHIP_ADS_CHECK
    mov al,0x1A
    out 0xF2,al
    in al,0xF3
    and al,0x80
    cmp al,TEST_CHIP_ADS_VALUE
    jne bad
    cmp byte [fs:0x60],1
    jne bad
%endif
    mov bx,0x55AA
    mov ax,0x4100
    mov dl,0x80
    int 0x13
    jc bad
    cmp bx,0xAA55
    jne bad
    test cx,1
    jz bad
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
    mov ax,0x0800
    xor dx,dx
    int 0x13
    jc bad
    cmp ah,0
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
    xor ax,ax
    mov es,ax
    mov bx,0x8000
    mov ax,0x0201
    mov cx,2
    xor dx,dx
    int 0x13
    jc bad
    cmp ax,1
    jne bad
    cmp word [0x8000],TEST_FLOPPY_WORD
    jne bad
%if TEST_FLOPPY_B
    mov ax,0x0800
    mov dx,1
    int 0x13
    jc bad
    cmp ah,0
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
    xor ax,ax
    mov es,ax
    mov bx,0x8000
    mov ax,0x0201
    mov cx,2
    mov dx,1
    int 0x13
    jc bad
    cmp ax,1
    jne bad
    cmp word [0x8000],TEST_FLOPPY_WORD_B
    jne bad
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
    mov si,dump_packet
    mov ax,0x4300
    mov dl,0x80
    int 0x13
    jc bad
    push ds
    mov ax,0x1130
    mov bh,6
    int 0x10
    pop ds
    mov [dump_packet+4],bp
    mov [dump_packet+6],es
    mov dword [dump_packet+8],9
    mov si,dump_packet
    mov ax,0x4300
    mov dl,0x80
    int 0x13
    jc bad
%if TEST_SHADOW_CHECK
    mov word [dump_packet+2],64
    mov word [dump_packet+4],0
    mov word [dump_packet+6],0xF000
    mov dword [dump_packet+8],17
    mov si,dump_packet
    mov ax,0x4300
    mov dl,0x80
    int 0x13
    jc bad
    mov word [dump_packet+4],0x8000
    mov dword [dump_packet+8],81
    mov ax,0x4300
    int 0x13
    jc bad
%endif
    mov al,0x60
    jmp terminal
bad:
    mov al,0x62
    jmp terminal
dump_packet db 0x10,0
    dw 8,0,0xB800
    dq 1
%include "test-terminal.inc"
times 510-($-$$) db 0
dw 0xAA55
