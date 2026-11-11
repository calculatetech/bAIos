@echo off
echo Before Windows: > KBSTATE.TXT
KBSTATE >> KBSTATE.TXT
WIN
echo After Windows: >> KBSTATE.TXT
KBSTATE >> KBSTATE.TXT
type KBSTATE.TXT
