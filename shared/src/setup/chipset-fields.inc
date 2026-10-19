; Existing packed descriptor: label,record byte,shift,mask,count,values,help1,help2,reserved.
%define CHIP_FIELD_SIZE 14
; Values word: ordinary string-table pointer, or a board numeric formatter kind.
%define CHIP_VALUES_FAST_REGION 0
%define CHIP_VALUES_CACHE_REGION 1
%macro chipset_field 8
    dw %1
    db %2,%3,%4
    dw %5,%6,%7,%8
    db 0
%endmacro
