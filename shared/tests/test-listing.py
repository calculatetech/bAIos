"""Keep scoped NASM label lookup equivalent without rescanning instruction rows."""
from pathlib import Path
import re
import sys
import tempfile

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from shared.tools.ram_proof import Listing


def check():
    lines = [
        '  1 <1> first:',
        '  2 00000000 E80100 call .wait',
        '  3 <2> .wait:',
        '  4 00000003 90 nop',
        '  5 <1> second:',
        '  6 00000004 90 nop ; first: is a reference',
        '  7 <3> .wait:   ',
        '  8 00000005 90 nop',
        '  9 <1> second.wait:',
        ' 10 <1> dollar$label:',
        ' 11 <1> first:',
    ]
    with tempfile.NamedTemporaryFile(mode='w',suffix='.lst',delete=False) as output:
        output.write('\n'.join(lines))
        path = Path(output.name)
    try:
        listing = Listing(path)
        for name in ('first','second','.wait','second.wait','dollar$label','missing',''):
            for start in (-1,0,1,3,5,7,len(lines),len(lines)+1):
                expected = next((i for i in range(start,len(lines))
                    if re.search(r'(?<![\w.])'+re.escape(name)+r':\s*$',lines[i])),None)
                try:
                    actual = listing.row(name,start)
                except StopIteration:
                    actual = None
                assert actual == expected,(name,start,actual,expected)
        assert listing.symbol('.wait','first') == 3
        assert listing.symbol('.wait','second') == 5
        path.write_text('replacement:\n 1 000000AA 90 nop\n')
        assert listing.symbol('.wait','first') == 3
        assert Listing(path).symbol('replacement') == 0xAA
    finally:
        path.unlink()
    print('PASS listing scopes, literal names, missing labels and candidate-local caches')


if __name__ == '__main__':
    check()
