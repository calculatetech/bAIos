bits 16
org 0x7C00
%include "test-configuration.inc"
xor ax,ax
mov ds,ax
mov es,ax
cmp byte [0x475],TEST_DISK_UNITS
jne bad_geometry
mov byte [0x61A],0x80
.unit:
mov dl,[0x61A]
mov ax,0x0800
int 0x13
jc bad_geometry
cmp ah,0
jne bad_geometry
cmp ch,30
jne bad_geometry
cmp dh,15
jne bad_geometry
and cl,63
cmp cl,63
jne bad_geometry
cmp dl,TEST_DISK_UNITS
jne bad_geometry
mov dl,[0x61A]
mov word [0x600],0x1E
mov si,0x600
mov ax,0x4800
int 0x13
jc bad_edd_geometry
cmp ah,0
jne bad_edd_geometry
cmp word [0x618],512
jne bad_edd_geometry
cmp dword [0x610],32256
jne bad_edd_geometry
cmp dword [0x604],32
jne bad_edd_geometry
cmp dword [0x608],16
jne bad_edd_geometry
cmp dword [0x60C],63
jne bad_edd_geometry
mov word [0x600],0x10
mov word [0x602],1
mov dword [0x604],0x8000
mov dword [0x608],17
mov dword [0x60C],0
mov si,0x600
mov ax,0x4200
int 0x13
jc bad_read
cmp ah,0
jne bad_read
cmp word [0x602],1
jne bad_read
mov eax,TEST_DISK_FIRST
cmp dl,0x80
je .payload
mov eax,0x31564C53
.payload:
cmp [0x8000],eax
jne bad_read
mov [0x8000],edx
inc dword [0x608]
mov ax,0x4300
int 0x13
jc bad_write
cmp ah,0
jne bad_write
cmp word [0x602],1
jne bad_write
mov dword [0x8000],0
mov ax,0x4200
int 0x13
jc bad_back
cmp ah,0
jne bad_back
cmp [0x8000],edx
jne bad_back
cmp word [0x602],1
jne bad_back
mov dword [0x608],32256
mov ax,0x4200
int 0x13
jnc bad
cmp ah,4
jne bad
cmp word [0x602],0
jne bad
inc byte [0x61A]
mov dl,[0x61A]
cmp dl,0x80+TEST_DISK_UNITS
jb .unit
mov al,0x65
jmp terminal
bad_geometry:
mov al,0x71
jmp terminal
bad_edd_geometry:
mov al,0x72
jmp terminal
bad_read:
mov al,0x73
jmp terminal
bad_write:
mov al,0x74
jmp terminal
bad_back:
mov al,0x75
jmp terminal
bad:
mov al,0x76
%include "test-terminal.inc"
times 510-($-$$) db 0
dw 0xAA55
