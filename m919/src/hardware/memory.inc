; HB52/53/61 geometry from the UMC reference. No RAM stack until mapping.
; SS=candidate/upper record, FS=first/lower record, ES=physical pair selection.
flat_addressing:
    lgdt [cs:ram_gdtr]
    mov eax,cr0
    or al,1
    mov cr0,eax
    jmp 0x08:.protected
.protected:
    mov ax,0x10
    mov gs,ax
    mov eax,cr0
    and al,0xFE
    mov cr0,eax
    jmp CFG_ROM_CODE_SEGMENT:ram_initialize

; Independent words, including change-one/read-the-other and exact restoration.
; ECX/EDI addresses; EAX/EBX/EDX scratch; CF indicates an alias or bad data.
%macro umc_ram_pair 0
    mov eax,[gs:ecx]
    mov ebx,[gs:edi]
    mov dword [gs:ecx],0x13579BDF
    mov dword [gs:edi],0xECA86420
    cmp dword [gs:ecx],0x13579BDF
    jne %%bad
    cmp dword [gs:edi],0xECA86420
    jne %%bad
    mov dword [gs:ecx],0xECA86420
    cmp dword [gs:ecx],0xECA86420
    jne %%bad
    cmp dword [gs:edi],0xECA86420
    jne %%bad
    xor edx,edx
    jmp %%restore
%%bad:
    mov edx,1
%%restore:
    mov [gs:edi],ebx
    mov [gs:ecx],eax
    test edx,edx
    jz %%ok
    stc
    jmp %%done
%%ok:
    clc
%%done:
%endmacro
ram_initialize:
    and esp,0xFFFF
    ; Only revision 04 has documented asymmetric DRAM addressing.
    mov eax,0x80000008 | (CFG_PLATFORM_HOST_PCI_DEVICE << 11)
    mov dx,0xCF8
    out dx,eax
    mov dx,0xCFC
    in al,dx
    xor ah,ah
    mov ds,ax
    xor ax,ax
    mov es,ax
    mov fs,ax
.pair:
    xor ebp,ebp
    xor si,si
.organization:
    mov bh,[cs:ram_organizations+si]
    mov bl,0x53
    early_chipset_write CFG_PLATFORM_HOST_PCI_DEVICE
    mov bh,[cs:ram_modes+si]
    mov bl,0x61
    early_chipset_write CFG_PLATFORM_HOST_PCI_DEVICE
    mov ax,1
    mov ss,ax
.capacity:
    mov ax,ss
    mov cx,bp
    cmp al,cl
    jbe .next_capacity
    mov bh,al
    mov ax,es
    or bh,al
    mov bl,0x52
    early_chipset_write CFG_PLATFORM_HOST_PCI_DEVICE
    ; Every decoded address bit must identify an independent writable word.
    mov ecx,0x8000
    mov edi,4
.address:
    xor edi,ecx
    umc_ram_pair
    jc .next_capacity
    xor edi,ecx
    shl edi,1
    mov cx,ss
    mov eax,0x100000
    shl eax,cl
    mov ecx,0x8000
    cmp edi,eax
    jb .address
    lea edi,[eax-4]
    umc_ram_pair
    jc .next_capacity
    mov ax,ss
    mov bp,si
    shl bp,8
    or bp,ax
.next_capacity:
    mov ax,ss
    inc ax
    mov ss,ax
    cmp ax,7
    jbe .capacity
    inc si
    cmp si,6
    jne .next_organization
    mov ax,ds
    cmp ax,4
    jne .pair_done
.next_organization:
    cmp si,12
    jb .organization
.pair_done:
    mov ax,es
    test ax,ax
    jnz .measured
    mov fs,bp
    mov ax,8
    mov es,ax
    jmp .pair
.measured:
    mov ax,fs
    mov cx,bp
    cmp al,cl
    jae .first_lower
    mov ss,ax
    mov fs,bp
    mov ax,8
    jmp .assign
.first_lower:
    mov ss,bp
    xor ax,ax
.assign:
    mov es,ax
.final_map:
    mov ax,fs
    test al,al
    jz .missing
    movzx si,ah
    mov bh,[cs:ram_organizations+si]
    mov ax,ss
    test al,al
    jz .population
    movzx si,ah
    mov al,[cs:ram_organizations+si]
    mov ah,al
    and al,3
    shl al,2
    and ah,0x10
    shl ah,1
    or bh,al
    or bh,ah
.population:
    mov bl,0x53
    early_chipset_write CFG_PLATFORM_HOST_PCI_DEVICE
    mov ax,fs
    movzx si,ah
    mov bh,[cs:ram_modes+si]
    mov ax,ss
    test al,al
    jz .address_mode
    movzx si,ah
    mov al,[cs:ram_modes+si]
    shl al,1
    or bh,al
.address_mode:
    mov bl,0x61
    early_chipset_write CFG_PLATFORM_HOST_PCI_DEVICE
    mov ax,fs
    mov bh,al
    mov ax,ss
    shl al,4
    or bh,al
    mov ax,es
    or bh,al
    mov bl,0x52
    early_chipset_write CFG_PLATFORM_HOST_PCI_DEVICE
    mov cx,fs
    mov ebp,0x100000
    shl ebp,cl
    mov ax,ss
    test al,al
    jz .workspace
    lea edi,[ebp+0x8000]
    mov ecx,0x8000
    umc_ram_pair
    jnc .upper_independent
    xor ax,ax
    mov ss,ax
    jmp .final_map
.upper_independent:
    mov cx,ss
    mov eax,0x100000
    shl eax,cl
    add ebp,eax
.workspace:
    ; Prove both owners before creating the conventional stack and EBDA.
    mov ecx,0x6FF0
    mov edi,CFG_PLATFORM_STATE_SEG << 4
    umc_ram_pair
    jc .failed
    xor ax,ax
    mov ds,ax
    mov eax,0x80000050 | (CFG_PLATFORM_HOST_PCI_DEVICE << 11)
    mov dx,0xCF8
    out dx,eax
    mov dx,0xCFE
    in al,dx
    mov [0x509],al
    inc dx
    in al,dx
    mov [0x504],al
    mov eax,0x80000060 | (CFG_PLATFORM_HOST_PCI_DEVICE << 11)
    mov dx,0xCF8
    out dx,eax
    mov dx,0xCFD
    in al,dx
    mov [0x505],al
    ; Convert the two region populations to physical slot bits.
    mov al,[0x504]
    mov bl,1
    test al,0x10
    jz .lower
    mov bl,2
.lower:
    test al,1
    jz .upper
    mov bl,3
.upper:
    mov cx,ss
    test cl,cl
    jz .slots
    mov bh,4
    test al,0x20
    jz .upper_population
    mov bh,8
.upper_population:
    test al,4
    jz .combine
    mov bh,12
.combine:
    or bl,bh
.slots:
    test byte [0x509],8
    jz .publish
    mov al,bl
    shl bl,2
    shr al,2
    or bl,al
    and bl,15
.publish:
    mov [0x506],bl
    jmp startup.ram_ready
.missing:
    post_code_early 0xE2
    jmp hard_halt
.failed:
    post_code_early 0xE3
    jmp hard_halt

; One/both slots, one/two sides and the single-slot swap, then 12-row modes.
ram_organizations db 0,2,0x10,0x12,1,3,0,2,0x10,0x12,1,3
ram_modes db 0,0,0,0,0,0,0x10,0x10,0x10,0x10,0x10,0x10
align 8
ram_gdt:
    dq 0
    dw 0xFFFF,(CFG_ROM_CODE_SEGMENT << 4) & 0xFFFF
    db ((CFG_ROM_CODE_SEGMENT << 4) >> 16) & 0xFF,0x9B,0,0
    dq 0x00CF93000000FFFF
    ; Documented FFFF0000 ROM alias; 16-bit code and a full 64 KiB limit.
    dw 0xFFFF,0
    db 0xFF,0x9B,0,0xFF
ram_gdtr:
    dw $-ram_gdt-1
    dd (CFG_ROM_CODE_SEGMENT << 4)+ram_gdt
