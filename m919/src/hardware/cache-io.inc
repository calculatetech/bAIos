; Existing host PCI byte access macros; emitted hardware operations unchanged.
%ifndef M919_CACHE_IO_INCLUDED
%define M919_CACHE_IO_INCLUDED
%macro cache_write 2
    mov eax,0x80000000 | (CFG_PLATFORM_HOST_PCI_DEVICE << 11) | ((%1) & 0xFC)
    mov dx,0xCF8
    out dx,eax
    mov dx,0xCFC + ((%1) & 3)
    mov al,%2
    out dx,al
%endmacro
%macro cache_read 1
    mov eax,0x80000000 | (CFG_PLATFORM_HOST_PCI_DEVICE << 11) | ((%1) & 0xFC)
    mov dx,0xCF8
    out dx,eax
    mov dx,0xCFC + ((%1) & 3)
    in al,dx
%endmacro
%endif
