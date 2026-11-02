; Assembly-time placement only. Adapters retain complete hardware transactions.
%macro cache_phase 1
%ifidni %1,early
    BOARD_CACHE_EARLY
%elifidni %1,after_ram
    BOARD_CACHE_AFTER_RAM
%elifidni %1,finish
    BOARD_CACHE_FINISH
%else
%error "Unknown cache lifecycle phase"
%endif
%endmacro

; The complete reset owner is also used by non-keyboard reset callers.
%ifndef BOARD_CACHE_RESET
%define BOARD_CACHE_RESET warm_reset
%endif
