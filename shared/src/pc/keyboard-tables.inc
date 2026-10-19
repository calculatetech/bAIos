keyboard_normal:
    db 0, 0x1B, '1','2','3','4','5','6','7','8','9','0','-','=',0x08,0x09
    db 'q','w','e','r','t','y','u','i','o','p','[',']',0x0D,0
    db 'a','s','d','f','g','h','j','k','l',';',0x27,0x60,0,0x5C
    db 'z','x','c','v','b','n','m',',','.','/',0,'*',0,' ',0
    times 0x59 - ($ - keyboard_normal) db 0

keyboard_shift:
    db 0, 0x1B, '!','@','#','$','%','^','&','*','(',')','_','+',0x08,0x09
    db 'Q','W','E','R','T','Y','U','I','O','P','{','}',0x0D,0
    db 'A','S','D','F','G','H','J','K','L',':',0x22,'~',0,'|'
    db 'Z','X','C','V','B','N','M','<','>','?',0,'*',0,' ',0
    times 0x59 - ($ - keyboard_shift) db 0

keyboard_keypad:
    db '7','8','9','-','4','5','6','+','1','2','3','0','.'
keyboard_keypad_control:
    db 0x77,0x8D,0x84,0x8E,0x73,0x8F,0x74,0x90,0x75,0x91,0x76,0x92,0x93

; Offsets from each plain function-key code: plain, Shift, Ctrl, Alt.
keyboard_function_legacy db 0,0x19,0x23,0x2D
keyboard_function_enhanced db 0,2,4,6
