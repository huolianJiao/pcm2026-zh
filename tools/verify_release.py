"""Audit a built ZIP; optionally install its real payload in an isolated fake game."""
import argparse,hashlib,json,os,subprocess,tempfile,zipfile
from pathlib import Path,PurePosixPath
from pcm2026_probe import read_overlay
from cdb import read_cdb
from extract import table_columns
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    ap=argparse.ArgumentParser();ap.add_argument('zip',type=Path)
    ap.add_argument('--original-dll',type=Path);ap.add_argument('--assets',type=Path)
    args=ap.parse_args()
    with tempfile.TemporaryDirectory(prefix='pcm26-release-audit-') as folder:
        tmp=Path(folder)
        with zipfile.ZipFile(args.zip) as z:
            names=z.namelist();assert len(names)==len(set(names)),'Duplicate ZIP entries'
            for name in names:
                path=PurePosixPath(name.replace('\\','/'))
                assert not path.is_absolute() and '..' not in path.parts and ':' not in name,name
                assert (tmp/name).resolve().is_relative_to(tmp.resolve()),name
            assert z.testzip() is None,'ZIP checksum failure'
            z.extractall(tmp)
        roots=list(tmp.glob('*/payload/manifest.json'));assert len(roots)==1
        package=roots[0].parents[1];payload=package/'payload'
        m=json.loads(roots[0].read_text(encoding='utf-8-sig'))
        assert m['pak']=='pakchunk99-PCM2026ZH_P.pak'
        assert sha(payload/'GameCyclingDLL_Master.dll')==m['dll_after']
        assert sha(payload/m['pak'])==m['sha256']
        for name in ('Install.ps1','Launcher.ps1','Install.cmd','Check.cmd','Uninstall.cmd','Recover.cmd','Repair.cmd'):
            assert (package/name).read_bytes()==(ROOT/name).read_bytes(),('Script/source mismatch',name)
        files=read_overlay(payload/m['pak'])
        expected={f'PCM/Content/Gui/fonts_{s}.{e}' for s in ('sma','nor','big','4k') for e in ('xml','uasset','uexp')}
        expected|={'PCM/Content/Database/Local.cdb','PCM/Content/Database/OfficialLocal.cdb'}
        assert set(files)==expected,'Unexpected overlay entries'
        if args.assets:
            rows=json.loads((ROOT/'translations/zh-CN.json').read_text(encoding='utf-8'))
            lookup={(r['strid'],r['source_sha256']):r['zh'] for r in rows}
            for db in ('Local.cdb','OfficialLocal.cdb'):
                output=tmp/db;output.write_bytes(files['PCM/Content/Database/'+db])
                old={c['name']:c['values'] for c in table_columns(read_cdb(args.assets/'Database'/db),'LOC')}
                new={c['name']:c['values'] for c in table_columns(read_cdb(output),'LOC')}
                for key in old:
                    if key!='gene_sz_danish':assert old[key]==new[key],(db,key)
                values=[lookup.get((k,hashlib.sha256(s.encode()).hexdigest()),s) for k,s in zip(old['CONSTANT'],old['gene_sz_english'])]
                assert new['gene_sz_danish']==values,db
            print('PASS: both databases; Danish translations exact, all other LOC columns original',flush=True)
        if args.original_dll:
            assert os.name=='nt';assert sha(args.original_dll)==m['dll_before']
            game=tmp/'isolated game'
            dll=game/'PCM/Binaries/Win64/GameCyclingDLL_Master.dll';dll.parent.mkdir(parents=True)
            (game/'PCM/Content/Paks').mkdir(parents=True)
            dll.write_bytes(args.original_dll.read_bytes())
            env=os.environ.copy();env.pop('PSModulePath',None)
            for mode in ('Install','Check','Install','Uninstall'):
                result=subprocess.run(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(package/'Install.ps1'),'-GamePath',str(game),'-PayloadPath',str(payload),'-Mode',mode],env=env,capture_output=True)
                assert result.returncode==0,(mode,result.stdout,result.stderr)
                print('PASS: actual release payload '+mode,flush=True)
            assert sha(dll)==m['dll_before']
            assert not (game/'PCM/Content/Paks'/m['pak']).exists()
            assert sha(game/'PCM26-ZH-Backup-25827667/GameCyclingDLL_Master.original.dll')==m['dll_before']
        print('PASS: ZIP, scripts, payload hashes and all pak entries',flush=True)
if __name__=='__main__':main()
