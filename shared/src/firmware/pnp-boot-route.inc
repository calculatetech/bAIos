pnp_boot_route:
    mov dword [0x60],(0xF000 << 16)+(int18-$$)
    mov dword [0x64],(0xF000 << 16)+(int19-$$)
    ret
