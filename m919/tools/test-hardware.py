"""Explicit hardware proof dispatcher, separate from the frozen donor matrix."""
import argparse
from ram_proof import check


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case',choices=('ram-test','geometry','memory-services','cache-discovery','cache-policy','cache-settings','cpu','pci','sio'),required=True)
    args=parser.parse_args()
    if args.case=='ram-test':check(native=True)
    elif args.case=='cpu':
        from cpu_proof import run
        run()
    elif args.case=='pci':
        from pci_proof import run
        run()
    elif args.case=='sio':
        from sio_proof import run
        run()
    elif args.case.startswith('cache-'):
        from cache_proof import check as cache_check
        cache_check(args.case)
    else:
        from geometry_proof import check as hardware_check
        hardware_check(args.case)
