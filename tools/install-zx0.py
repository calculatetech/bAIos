"""Install or check the pinned optional ZX0 Windows build dependency."""
import argparse
import hashlib
from pathlib import Path
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
COMMIT='ecde3a2ae05061fe06469ed46df81a33b7de7d86'
FILES={'zx0.exe':'e6aec5cdfc3535b808610cb54412ce375b5b13e17b59f2bc878a54a00a8acbac',
       'dzx0.exe':'b232d119fea7be2f671b9d62953bea3e08a5db731eb6cff910ae6c81b78bdb83'}


def install(check=False):
    folder=ROOT/'tools/deps/zx0'
    for name,expected in FILES.items():
        target=folder/name
        if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest()==expected:
            print('PASS pinned '+name);continue
        if check:raise SystemExit('Missing or changed '+str(target)+'. Run python -B tools/install-zx0.py.')
        url='https://raw.githubusercontent.com/einar-saukas/ZX0/'+COMMIT+'/win/'+name
        with urllib.request.urlopen(url,timeout=30) as response:data=response.read(1024*1024)
        if hashlib.sha256(data).hexdigest()!=expected:raise RuntimeError('Downloaded ZX0 identity differs: '+name)
        folder.mkdir(parents=True,exist_ok=True)
        temporary=target.with_suffix('.tmp');temporary.write_bytes(data);temporary.replace(target)
        print('Installed pinned '+name)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--check',action='store_true');args=p.parse_args();install(args.check)
