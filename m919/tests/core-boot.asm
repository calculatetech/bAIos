bits 16
org 0x7C00
%include "test-configuration.inc"
jmp short start
times 11-($-$$) db 0
dw 512
db 1
dw 1
times 24-($-$$) db 0
dw 63,TEST_BPB_HEADS
dd 0
times 62-($-$$) db 0
start:
xor ax,ax
mov ds,ax
mov ax,[0x40E]
mov fs,ax
%if TEST_DIRTY_VGA_INIT
cmp byte [0xB49],1          ; The synthetic C000:0003 entry really returned.
jne .geometry_bad
mov ax,ss
test ax,ax
jnz .geometry_bad
cmp sp,0x7000
jne .geometry_bad
%endif
%ifndef TEST_RAM_FLAGS
%define TEST_RAM_FLAGS 4
%endif
%ifndef TEST_LOGICAL_RECORD
%define TEST_LOGICAL_RECORD 0
%endif
%ifndef TEST_CPU_FIRST
%define TEST_CPU_FIRST 'A'
%endif
mov al,0x71
%assign LEGACY_EXT_KIB (TEST_RAM_BYTES/1024)-1024
%if LEGACY_EXT_KIB > 0xFC00
%assign LEGACY_EXT_KIB 0xFC00
%endif
cmp word [fs:0xD0],LEGACY_EXT_KIB
jne terminal
cmp dword [fs:0xDC],(TEST_RAM_BYTES/1024)-1024
jne terminal
cmp dword [fs:0xD8],(TEST_RAM_BYTES/1024)-1024
jne terminal
mov ah,0x88
int 0x15
jc .geometry_bad
cmp ax,LEGACY_EXT_KIB
jne .geometry_bad
mov al,0x72
cmp byte [fs:0x175],TEST_ERROR_BITS
jne terminal
mov ax,0x0800
mov dl,0x80
int 0x13
jc .geometry_bad
and cl,63
cmp cl,63
jne .geometry_bad
inc dh
cmp dh,TEST_EXPECT_HEADS
jne .geometry_bad
jmp .geometry_ok
.geometry_bad:
mov al,0x78
jmp terminal
.geometry_ok:
%if TEST_FLOPPY_FAILED
cmp byte [fs:0x176],1         ; Real seek failure identifies configured logical A.
jne terminal
%endif
%if TEST_CLOCK_NO_ERRORS
cmp byte [fs:0x17F],1
jne terminal
cmp byte [0xB1E],0          ; Actual IRQ0 observer saw no error-tone speaker gate.
jne terminal
cmp word [0xB1C],0
je terminal
%endif
%if TEST_LOGICAL_RECORD
cmp byte [fs:0x169],1
jne terminal
mov ax,fs
add ax,0x20
mov fs,ax
%endif
mov al,0x73
cmp byte [fs:0x20],1
jne terminal
mov al,0x74
cmp byte [fs:0x1052],TEST_BOOT_POSITION
jne terminal
mov ax,[0x40E]
mov fs,ax
mov al,0x75
mov dx,0xCF8
mov eax,0x80008050
out dx,eax
mov dx,0xCFC
in eax,dx
test al,0x80                ; Observe the effective hostbridge cache gate.
%if TEST_L2_ENABLED
jz .geometry_bad
%else
jnz .geometry_bad
%endif
mov al,0x75
cmp byte [fs:0x50],TEST_RAM_FLAGS
jne terminal
%if TEST_RAM_FLAGS = 2
cmp byte [0xB34],1            ; Observed actual progress before physical Esc.
jne terminal
%endif
mov ax,0xB800
mov es,ax
mov al,0x76
cmp word [es:2*160+20*2],0x0700 | TEST_CPU_FIRST
jne terminal
mov al,0x77
cmp word [es:12*160],0x0720
jne terminal
mov di,12*160
mov cx,80                   ; Clear separator after the frame.
cld
.blank:
cmp word [es:di],0x0720
jne terminal
add di,2
loop .blank
%if TEST_ERROR_BITS
%if !TEST_FLOPPY_FAILED
cmp word [es:13*160+3*2],0x0E50 ; Actual POST warnings, not an absent flag alone.
jne terminal
%endif
%else
mov di,13*160
mov cx,80
.warning_blank:
cmp word [es:di],0x0720
jne terminal
add di,2
loop .warning_blank
%endif
%if TEST_FLOPPY_FAILED
mov di,15*160               ; Row14 has the normal failed-FDC evidence tuple.
mov cx,0
%else
mov di,14*160
mov cx,9*80
%endif
.rest_blank:
jcxz .blank_done
cmp word [es:di],0x0720
jne terminal
add di,2
loop .rest_blank
.blank_done:
%if TEST_DIRTY_DISPLAY
cmp byte [0xB48],1            ; The real external INT10 poisoned the return.
jne terminal
%endif
; Preserve actual text cells and the installed BIOS font on disposable media.
mov si,dump_packet
mov ax,0x4300
mov dl,0x80
int 0x13
jc .dump_failed
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
jc .dump_failed
mov al,0x60
jmp terminal
.dump_failed:
mov al,0x70
jmp terminal
dump_packet db 0x10,0
    dw 8,0,0xB800
    dq 1
%include "test-terminal.inc"
times 510-($-$$) db 0
dw 0xAA55
