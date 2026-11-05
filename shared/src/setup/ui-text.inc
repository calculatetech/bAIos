; Source stays plaintext; only opted-in Setup strings use the ROM marker.
%ifndef UI_TEXT_INCLUDED
%define UI_TEXT_INCLUDED
%ifndef UI_TEXT_PAIRS
%include "setup/ui-text-pairs.inc"
%endif

%assign UI_PAIR_INDEX 0
%rep 128
    %assign UI_PAIR_LEFT %[UI_PAIR_A %+ UI_PAIR_INDEX]
    %assign UI_PAIR_RIGHT %[UI_PAIR_B %+ UI_PAIR_INDEX]
    %if UI_PAIR_LEFT < 2 || UI_PAIR_RIGHT < 2 || UI_PAIR_LEFT >= 128+UI_PAIR_INDEX || UI_PAIR_RIGHT >= 128+UI_PAIR_INDEX
        %error "Setup pair grammar must contain ASCII or earlier tokens"
    %endif
    %assign UI_PAIR_DEPTH 0
    %if UI_PAIR_LEFT >= 128
        %assign UI_PAIR_PARENT UI_PAIR_LEFT-128
        %assign UI_PAIR_DEPTH %[UI_PAIR_D %+ UI_PAIR_PARENT]
    %endif
    %if UI_PAIR_RIGHT >= 128
        %assign UI_PAIR_PARENT UI_PAIR_RIGHT-128
        %if %[UI_PAIR_D %+ UI_PAIR_PARENT] > UI_PAIR_DEPTH
            %assign UI_PAIR_DEPTH %[UI_PAIR_D %+ UI_PAIR_PARENT]
        %endif
    %endif
    %assign UI_PAIR_D%[UI_PAIR_INDEX] UI_PAIR_DEPTH+1
    %if UI_PAIR_DEPTH >= 32
        %error "Setup pair grammar exceeds32 levels"
    %endif
    %assign UI_PAIR_INDEX UI_PAIR_INDEX+1
%endrep

%macro ui_encode 1.nolist
    %strlen %%length %1
    %assign %%count %%length
    %assign %%suitable 1
    %assign %%i 0
    %rep %%length
        %substr %%char %1 (%%i+1),1
        %assign %%value %%char
        %if %%value < 2 || %%value >= 128
            %assign %%suitable 0
        %endif
        %assign %%v%[%%i] %%value
        %assign %%i %%i+1
    %endrep
    %if %%length > 0
        %if %%v0 == 1
            %error "Leading01 is reserved for compiled Setup text"
        %endif
    %endif
    %assign %%pair 0
    %if %%suitable
        %rep 128
            %assign %%a %[UI_PAIR_A %+ %%pair]
            %assign %%b %[UI_PAIR_B %+ %%pair]
            %assign %%read 0
            %assign %%write 0
            %rep %%count
                %if %%read < %%count
                    %assign %%value %%v%[%%read]
                    %assign %%next %%read+1
                    %if %%value == %%a && %%next < %%count
                        %if %%v%[%%next] == %%b
                            %assign %%value 128+%%pair
                            %assign %%read %%read+1
                        %endif
                    %endif
                    %assign %%v%[%%write] %%value
                    %assign %%write %%write+1
                    %assign %%read %%read+1
                %endif
            %endrep
            %assign %%count %%write
            %assign %%pair %%pair+1
        %endrep
    %endif
    %if %%suitable && %%count+1 < %%length
        %xdefine UI_STRING_BYTES 1
        %assign %%i 0
        %rep %%count
            %assign %%value %%v%[%%i]
            %xdefine UI_STRING_BYTES UI_STRING_BYTES,%%value
            %assign %%i %%i+1
        %endrep
        %xdefine UI_STRING_BYTES UI_STRING_BYTES,0
    %else
        %xdefine UI_STRING_BYTES %1,0
    %endif
%endmacro

%macro ui_cached 2.nolist
    %ifmacro UI_TEXT_CACHE_%1 1
        UI_TEXT_CACHE_%1 %2
    %else
        ui_encode %2
    %endif
%endmacro

; Keep real source labels and DB visible. The optional label is only a cache key.
%macro ui_string 1-2
    %if %0 == 2
        ui_cached %2,%1
    %else
        ui_encode %1
    %endif
    db UI_STRING_BYTES
%endmacro
%endif
