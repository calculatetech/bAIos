; Diagnostic for the hash-identified supplied SVGABNCH.EXE only.
; This replaces later frame-rendering code that the probe never reaches.
; Entry hooks retain each original call's stack layout and argument cleanup.
bits 32
org 0x5A00
    dd load_object, delay, allegro_init, graphics, completed
    dd video_query, vesa_info, vesa_mode_info, vesa_mode_fallback
    dd vesa_set_mode, vesa_pitch
load_object:
    mov al, 0xD1
    call marker
    call 0x2C0C
    push eax
    mov al, 0xD2
    call marker
    pop eax
    ret
delay:
    mov al, 0xD3
    call marker
    jmp 0xDA08
allegro_init:
    mov al, 0xD4
    call marker
    call 0x5F48
    mov al, 0xD5
    call marker
    ret
graphics:
    pushfd
    pushad
    push dword [0xD66DC]        ; Original DJGPP DOS transfer-buffer address.
    push buffer_message
    call 0xE52C
    add esp, 8
    popad
    popfd
    mov al, 0xD6
    call marker
    jmp 0x6598
; Tail hooks keep the real DPMI call's original argument/return stack intact.
%macro video_hook 2
%1:
    push eax
    mov al, %2
    out 0x80, al
    pop eax
    jmp 0x10524
%endmacro
video_hook video_query,        0xE0 ; INT10 AH=0F: current mode.
video_hook vesa_info,          0xE1 ; INT10 AX=4F00: controller info.
video_hook vesa_mode_info,     0xE2 ; INT10 AX=4F01: enumerate mode info.
video_hook vesa_mode_fallback, 0xE3 ; INT10 AX=4F01: fallback mode info.
video_hook vesa_set_mode,      0xE4 ; INT10 AX=4F02: set mode.
video_hook vesa_pitch,         0xE5 ; INT10 AX=4F06: scanline size.
completed:
    mov [gfx_result], eax
    add esp, 0x18               ; Original main's argument cleanup.
    call 0x60F8                 ; Allegro cleanup restores text mode.
    mov al, 0xD7
    call marker
    push dword [gfx_result]
    push complete_message
    call 0xE52C                 ; Original cprintf.
    add esp, 8
%ifdef EMULATOR_TEST
    mov dx, 0x80
    mov esi, tester
.enable:
    lodsb
    out dx, al
    cmp esi, tester_end
    jb .enable
    mov dx, 0x501
    mov al, 4
    out dx, al
    inc dx
    mov al, 0x67
    cmp dword [gfx_result], 0
    je .exit
    inc al
.exit:
    out dx, al
    jmp $
tester: db '86Box',1,5
tester_end:
%else
    push dword 0
    call 0xF1C0                 ; Original CRT exit, not raw INT21.
%endif
marker:
    pushad
    out 0x80, al
    movzx eax, al
    push eax
    push stage_message
    call 0xE52C
    add esp, 8
    popad
    ret
stage_message: db 13,10,'CHRISDBG stage %02X',13,10,0
buffer_message: db 13,10,'CHRISDBG DOS transfer buffer = %08lX',13,10,0
complete_message: db 'Graphics returned %d (0 = success). Probe complete.',13,10,0
gfx_result: dd 0
