; Native OEM23FC..2412 board-control helpers.
oem_cache_23FC:
    cli
oem_cache_23FD:
    out 0x5a, al
oem_cache_23FF:
    jmp short oem_cache_2401
oem_cache_2401:
    in al, 0x5b
oem_cache_2403:
    jmp short oem_cache_2405
oem_cache_2405:
    jmp bp
oem_cache_2407:
    cli
oem_cache_2408:
    out 0x5a, al
oem_cache_240A:
    jmp short oem_cache_240C
oem_cache_240C:
    mov al, ah
oem_cache_240E:
    out 0x5b, al
oem_cache_2410:
    jmp short oem_cache_2412
oem_cache_2412:
    jmp bp
