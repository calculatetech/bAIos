"""Small artifact and layout checks; no firmware or emulator test matrix."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from shared.tools.candidates import finish, record


def failed_board_build(root):
    from unittest.mock import patch
    from contextlib import redirect_stdout
    from io import StringIO
    import runpy
    from shared.tools import rom
    spec = importlib.util.spec_from_file_location('pb430_build_fixture',ROOT/'pb430/tools/build.py')
    board = importlib.util.module_from_spec(spec);spec.loader.exec_module(board)
    port=root/'metadata';out=port/'build';out.mkdir(parents=True)
    (port/'reference').mkdir();(port/'reference/pb430-m27c1001.bin').write_bytes(bytes(32768))
    image=out/'baios-metadata.bin'
    metadata=out/'build-info.json';pointer=out/'LATEST.json'
    metadata.write_text('{"version":"0.1.0","files":[]}');pointer.write_text('{"state":"saved"}')
    before=(metadata.read_bytes(),pointer.read_bytes())
    config=dict(rom=dict(size=131072,checksum_offset=131055),identity=dict(version='0.1.1'))
    result=dict(path=str(image),size=131072,identity=config['identity'])
    def assemble(command,check):
        image.write_bytes(bytes(32768)+bytes([255])*32768+bytes(65536))
    with patch.object(board,'PORT',port), patch.object(board,'selected_vga',side_effect=ValueError('invalid VGA input')), \
         patch.object(rom,'configuration',return_value=(port,config)), patch.object(rom,'definitions',return_value=''), \
         patch.object(rom,'verify',return_value=dict(result)), patch.object(rom.subprocess,'run',side_effect=assemble), \
         patch.object(rom.shutil,'which',return_value='fixture-nasm'):
        try:board.run()
        except ValueError as error:assert str(error)=='invalid VGA input'
        else:raise AssertionError('Board validation failure was ignored')
    assert (metadata.read_bytes(),pointer.read_bytes())==before,'Failed outer build advanced candidate metadata'
    with patch.object(rom,'build',return_value=result),patch.object(sys,'argv',['build-rom.py',str(port)]),redirect_stdout(StringIO()):
        runpy.run_path(str(ROOT/'tools/build-rom.py'),run_name='__main__')
    assert json.loads(pointer.read_text())['version']=='0.1.1','Generic final CLI did not record its successful build'


def main():
    spec = importlib.util.spec_from_file_location('layout',ROOT/'tools/check-layout.py')
    layout = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(layout)
    owner = ROOT/'.agent/test-results'
    owner.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='organization-',dir=owner) as directory:
        root=Path(directory);port=root/'sample';build=port/'build'
        build.mkdir(parents=True);(port/'src').mkdir();(port/'src/bios.asm').write_text('; fixture')
        combined=build/'baios-sample.bin';low=build/'baios-sample-even.bin';high=build/'baios-sample-odd.bin'
        raw=bytes(range(256))*256
        for path,data in ((combined,raw),(low,raw[::2]),(high,raw[1::2])):path.write_bytes(data)
        stamp='2026-10-27T12:30:00+00:00'
        first=record(port,[combined,low,high],'0.1.1',stamp)
        second=record(port,[combined,low,high],'0.1.1',stamp)
        assert first==second and combined.name=='baios-sample.bin'
        (port/'src/bios.asm').write_text("%define BIOS_VERSION '0.2.0'")
        result=finish(port)
        assert result['version']=='0.1.1' and len(result['files'])==3
        for row,source in zip(result['files'],sorted((combined,low,high))):
            target=build/row['name']
            assert '-v0.1.1-20261027T123000Z.' in target.name
            assert target.read_bytes()==source.read_bytes()
        record(port,[combined,low,high],'0.1.1',stamp)
        assert [row['name'] for row in json.loads((build/'LATEST.json').read_text())['completed']['files']] == [row['name'] for row in result['files']]
        before=(build/'LATEST.json').read_bytes()
        high.write_bytes(b'changed')
        try:finish(port)
        except ValueError:pass
        else:raise AssertionError('Changed artifact accepted')
        assert (build/'LATEST.json').read_bytes()==before
        record(port,[high],'0.1.1',stamp)
        try:finish(port)
        except ValueError:pass
        else:raise AssertionError('Incompatible recorded lane accepted')
        other=root/'paired';out=other/'build';out.mkdir(parents=True)
        a=out/'baios-paired-vga50.bin';b=out/'baios-paired-vga60.bin'
        system=out/'baios-paired-system.rom';system.write_bytes(bytes(65536))
        (other/'validation.json').write_text(json.dumps(dict(artifacts=[dict(name=p.name) for p in (a,b,system)])))
        a.write_bytes(bytes(131072))
        record(other,[a,system],'0.2.0',stamp)
        before=(out/'LATEST.json').read_bytes()
        try:finish(other)
        except ValueError as error:assert 'Incomplete artifact group' in str(error)
        else:raise AssertionError('Single VGA variant accepted as a complete group')
        assert (out/'LATEST.json').read_bytes()==before
        b.write_bytes(bytes(65536)+bytes([1])*65536)
        record(other,[b],'0.2.0',stamp)
        before=(out/'LATEST.json').read_bytes()
        try:finish(other)
        except ValueError:pass
        else:raise AssertionError('Different system BIOSes accepted as a VGA pair')
        assert (out/'LATEST.json').read_bytes()==before
        b.write_bytes(bytes(131072));record(other,[b],'0.2.0',stamp)
        assert len(finish(other)['files'])==3
        system.write_bytes(bytes([1])*65536);record(other,[system],'0.2.0',stamp)
        try:finish(other)
        except ValueError as error:assert 'System ROM' in str(error)
        else:raise AssertionError('Mismatched system sidecar accepted')
        failed_board_build(root)
        assert not layout.check(root)
        foreign=build/'task-checkout';foreign.mkdir();(foreign/'.git').write_text('gitdir: fixture')
        misplaced=build/'TOOL.COM';misplaced.write_bytes(b'utility')
        errors=layout.check(root)
        assert any('repository copy' in error for error in errors)
        assert any('TOOL.COM' in error for error in errors)
        print('PASS stable iterations, recorded version/time, full lane group, stale member and VGA rejection, latest preservation, layout discrimination')


if __name__=='__main__':main()
