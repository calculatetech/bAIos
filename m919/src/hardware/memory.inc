; No return frame or RAM state survives a geometry change. FS's visible
; selector holds the best code/index; SS holds the current capacity code.
; GS retains its flat hidden descriptor for real physical address probes.
flat_addressing:
    cli
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
    jmp CFG_ROM_CODE_SEGMENT:.real
.real:
    jmp ram_initialize

; All geometry state remains in registers while the map changes.
%macro ram_independent 0
    mov eax,[gs:ecx]
    mov edx,[gs:edi]
    mov dword [gs:ecx],0x1265ABCD
    mov dword [gs:edi],0xED9A5432
    cmp dword [gs:ecx],0x1265ABCD
    jne %%alias
    cmp dword [gs:edi],0xED9A5432
    jne %%alias
    mov dword [gs:edi],0x1265ABCD
    cmp dword [gs:edi],0x1265ABCD
    jne %%alias
    mov dword [gs:ecx],0xED9A5432
    cmp dword [gs:edi],0x1265ABCD
    jne %%alias
    mov [gs:edi],edx
    mov [gs:ecx],eax
    clc
    jmp %%done
%%alias:
    mov [gs:edi],edx
    mov [gs:ecx],eax
    stc
%%done:
%endmacro

; Interleaving puts bit 2 in the bank select, so check each bank's own aliases.
%macro ram_inside 1
    mov ecx,0x10000
%%bank:
    mov edi,4
%%address:
    mov ebx,edi
    xor edi,ecx
    ram_independent
    mov edi,ebx
    jc %1
    shl edi,1
    cmp edi,ebp
    jb %%address
    lea edi,[ebp-4]
    ram_independent
    jc %1
    test cl,4
    jnz %%done
    add ecx,4
    jmp %%bank
%%done:
%endmacro

ram_initialize:
    ; Preserve unrelated HB53/HB61 controls in DS's visible selector.
    mov eax,0x80000060 | (CFG_PLATFORM_HOST_PCI_DEVICE << 11)
    mov dx,0xCF8
    out dx,eax
    mov dx,0xCFD
    in al,dx
    and ax,0x00CF
    mov di,ax
    mov eax,0x80000050 | (CFG_PLATFORM_HOST_PCI_DEVICE << 11)
    mov dx,0xCF8
    out dx,eax
    mov dx,0xCFF
    in al,dx
    and ax,0x00C0
    shl ax,8
    or ax,di
    mov ds,ax
    ; AMI and the documented silicon expose asymmetric addressing on rev 04.
    mov eax,0x80000008 | (CFG_PLATFORM_HOST_PCI_DEVICE << 11)
    mov dx,0xCF8
    out dx,eax
    mov dx,0xCFC
    in al,dx
    cmp al,4
    jne .revision_ready
    mov ax,ds
    or al,0x10                 ; Register-only permission flag, never written.
    mov ds,ax
.revision_ready:
    and esp,0xFFFF             ; Reset CPU signature remains in the low word.
    xor ax,ax
    mov es,ax                 ; Isolate physical pair 0, then pair 1.
.pair:
    xor ax,ax
    mov fs,ax
    xor si,si
.organization:
    mov ax,ds
    mov bh,ah
    or bh,[cs:ram_organizations+si]
    mov bl,0x53
    early_chipset_write CFG_PLATFORM_HOST_PCI_DEVICE
    mov ax,ds
    mov bh,al
    and bh,0xCF
    or bh,[cs:ram_modes+si]
    mov bl,0x61
    early_chipset_write CFG_PLATFORM_HOST_PCI_DEVICE
    mov ax,1
    mov ss,ax
.capacity:
    mov ax,ss
    mov bh,al
    mov ax,es
    or bh,al
    mov bl,0x52
    early_chipset_write CFG_PLATFORM_HOST_PCI_DEVICE
    wbinvd
    mov cx,ss
    mov ebp,0x100000
    shl ebp,cl
    ram_inside .reject
    mov ax,fs
    mov cx,ss
    cmp cl,al
    jbe .reject
    mov ax,si
    shl ax,8
    or ax,cx
    mov fs,ax
.reject:
    mov ax,ss
    inc ax
    mov ss,ax
    cmp ax,7
    jbe .capacity
    inc si
    cmp si,6
    jne .more_organizations
    mov ax,ds
    test al,0x10
    jz .pair_complete
.more_organizations:
    cmp si,ram_organizations_end-ram_organizations
    jb .organization
.pair_complete:
    mov ax,es
    test ax,ax
    jnz .both_measured
    mov ax,fs
    movzx eax,ax
    shl eax,16
    or esp,eax
    mov ax,8
    mov es,ax
    jmp .pair
.both_measured:
    mov eax,esp
    shr eax,16
    mov ss,ax                 ; SS = pair 0, FS = pair 1.
    and esp,0xFFFF
    mov cx,fs
    cmp al,cl
    jae .pair0_lower
    mov ss,cx
    mov fs,ax
    mov ax,8
    jmp .assignment
.pair0_lower:
    xor ax,ax
.assignment:
    mov es,ax                 ; HB52.08 chooses the physical lower pair.
.final_map:
    mov ax,ss
    test al,al
    jz .no_geometry
    movzx si,ah
    mov bh,[cs:ram_organizations+si]
    mov ax,ds
    or bh,ah
    mov ax,fs
    test al,al
    jz .organization_ready
    movzx si,ah
    mov al,[cs:ram_organizations+si]
    mov ah,al
    and al,3
    shl al,2
    and ah,0x10
    shl ah,1
    or al,ah
    or bh,al
.organization_ready:
    mov bl,0x53
    early_chipset_write CFG_PLATFORM_HOST_PCI_DEVICE
    mov ax,ss
    movzx si,ah
    mov ax,ds
    mov bh,al
    and bh,0xCF
    or bh,[cs:ram_modes+si]
    mov ax,fs
    test al,al
    jz .mode_ready
    movzx si,ah
    mov al,[cs:ram_modes+si]
    shl al,1
    or bh,al
.mode_ready:
    mov bl,0x61
    early_chipset_write CFG_PLATFORM_HOST_PCI_DEVICE
    mov ax,ss
    mov bh,al
    mov ax,fs
    shl al,4
    or bh,al
    mov ax,es
    or bh,al
    mov bl,0x52
    early_chipset_write CFG_PLATFORM_HOST_PCI_DEVICE
    wbinvd
    mov cx,ss
    mov ebp,0x100000
    shl ebp,cl
    mov ax,fs
    test al,al
    jz .total
    mov cl,al
    mov edi,0x100000
    shl edi,cl
    add ebp,edi
.total:
    ram_inside .reduce
    ; Match the low anchor so an outside wrap is distinguishable from more RAM.
    lea edi,[ebp+0x10000]
    mov ecx,0x10000
    ram_independent
    jnc .reduce
    ; The upper region must be independent of its matching lower offset.
    mov ax,fs
    test al,al
    jz .mapped
    mov cx,ss
    mov edi,0x100000
    shl edi,cl
    add edi,0x10000
    mov ecx,0x10000
    ram_independent
    jc .reduce
    jmp .mapped
.reduce:
    ; Stored-register-only hardware can expose the same RAM for both pairs.
    ; Publish only a continuous map that the actual data probes can prove.
    mov ax,fs
    test al,al
    jz .reduce_lower
    dec al
    mov fs,ax
    jmp .final_map
.reduce_lower:
    mov ax,ss
    dec al
    mov ss,ax
    jmp .final_map
.mapped:
    xor ax,ax
    mov ds,ax
    ; Capture the applied register map only after RAM has been validated.
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
    ; Physical bank numbers follow region assignment, population and swap.
    mov al,[0x504]
    mov bl,1
    test al,0x10
    jz .lower_first
    mov bl,2
.lower_first:
    test al,1
    jz .upper_banks
    mov bl,3
.upper_banks:
    mov ax,fs
    test al,al
    jz .bank_assignment
    mov al,[0x504]
    mov bh,4
    test al,0x20
    jz .upper_first
    mov bh,8
.upper_first:
    test al,4
    jz .combine_banks
    mov bh,12
.combine_banks:
    or bl,bh
.bank_assignment:
    test byte [0x509],8
    jz .bank_store
    mov al,bl
    shl bl,2
    shr al,2
    or bl,al
    and bl,15
.bank_store:
    mov [0x506],bl
    ; Opposing data at every usable 4 KiB page precedes any RAM stack.
    mov edi,0x20000
.test:
    cmp edi,0xA0000
    jne .ordinary
    mov edi,0x100000
.ordinary:
    cmp edi,ebp
    jae .done
    mov edx,[gs:edi]
    mov dword [gs:edi],0x55AA33CC
    cmp dword [gs:edi],0x55AA33CC
    jne .failed
    mov dword [gs:edi],0xAA55CC33
    cmp dword [gs:edi],0xAA55CC33
    jne .failed
    mov [gs:edi],edx
    add edi,0x1000
    jmp .test
.failed:
    mov [gs:edi],edx
    mov al,0xE3
    out POST_PORT,al
    jmp hard_halt
.no_geometry:
    mov al,0xE2
    out POST_PORT,al
    jmp hard_halt
.done:
    jmp startup.ram_ready

ram_organizations: db 0,2,0x10,0x12,1,3,0,2,0x10,0x12,1,3
ram_organizations_end:
ram_modes: db 0,0,0,0,0,0,0x10,0x10,0x10,0x10,0x10,0x10
align 8
ram_gdt:
    dq 0
    dw 0xFFFF,(CFG_ROM_CODE_SEGMENT << 4) & 0xFFFF
    db ((CFG_ROM_CODE_SEGMENT << 4) >> 16) & 0xFF,0x9B,0,0
    dq 0x00CF93000000FFFF
ram_gdtr:
    dw $-ram_gdt-1
    dd (CFG_ROM_CODE_SEGMENT << 4)+ram_gdt
