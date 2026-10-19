; IEEE CRC32 of DS:ESI, ECX bytes. Return EAX; preserve other registers/flags.
checksum_crc32:
    pushf
    push ebx
    push ecx
    push edx
    push esi
    mov eax,0xFFFFFFFF
    test ecx,ecx
    jz .done
.byte:
    movzx edx,byte [ds:esi]
    xor al,dl
    mov ebx,eax
    and ebx,15
    shr eax,4
    xor eax,[cs:checksum_crc32_nibbles+ebx*4]
    mov ebx,eax
    and ebx,15
    shr eax,4
    xor eax,[cs:checksum_crc32_nibbles+ebx*4]
    inc esi
    dec ecx
    jnz .byte
.done:
    not eax
    pop esi
    pop edx
    pop ecx
    pop ebx
    popf
    ret
checksum_crc32_nibbles:
    dd 0x00000000,0x1DB71064,0x3B6E20C8,0x26D930AC
    dd 0x76DC4190,0x6B6B51F4,0x4DB26158,0x5005713C
    dd 0xEDB88320,0xF00F9344,0xD6D6A3E8,0xCB61B38C
    dd 0x9B64C2B0,0x86D3D2D4,0xA00AE278,0xBDBDF21C
