import hashlib,json,os,subprocess,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from pcm2026_probe import build_pak,read_overlay

def sha(b):return hashlib.sha256(b).hexdigest()
class ProjectTests(unittest.TestCase):
    def test_pak_corruption_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'test.pak';files={'PCM/Content/test.txt':b'hello'}
            build_pak(p,files);self.assertEqual(read_overlay(p),files)
            data=bytearray(p.read_bytes());data[53]^=1;p.write_bytes(data)
            with self.assertRaises(AssertionError):read_overlay(p)

    def test_catalog_rules(self):
        rows=json.loads((ROOT/'translations/zh-CN.json').read_text(encoding='utf-8'))
        self.assertEqual(len(rows),len({r['idloc'] for r in rows}))
        byid={r['idloc']:r for r in rows}
        for r in rows:
            self.assertRegex(r['source_sha256'],r'^[a-f0-9]{64}$')
            self.assertNotIn('source',r)
        for i in range(381,393):self.assertEqual(byid[i]['zh'],f'{i-380}月')
        self.assertEqual(byid[1575]['zh'],'经理模式')
        for i in (1028,1029):self.assertNotIn('\\t',byid[i]['zh'])
        self.assertIn('洲际赛历',byid[1029]['zh'])

    @unittest.skipUnless(os.name=='nt','PowerShell installer requires Windows')
    def test_install_check_restore_and_unknown_refusal(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);game=root/'Game with spaces';payload=root/'payload';payload.mkdir()
            dll=game/'PCM/Binaries/Win64/GameCyclingDLL_Master.dll';dll.parent.mkdir(parents=True)
            pak=game/'PCM/Content/Paks/pakchunk99-PCM2026ZH_P.pak';pak.parent.mkdir(parents=True)
            original=b'original test DLL';patched=b'patched test DLL';overlay=b'overlay test pak'
            dll.write_bytes(original)
            (payload/dll.name).write_bytes(patched);(payload/pak.name).write_bytes(overlay)
            m=dict(pak=pak.name,dll_before=sha(original),dll_after=sha(patched),sha256=sha(overlay))
            (payload/'manifest.json').write_text(json.dumps(m))
            def run(mode):
                env=os.environ.copy();env.pop('PSModulePath',None)
                return subprocess.run(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(ROOT/'Install.ps1'),'-GamePath',str(game),'-PayloadPath',str(payload),'-Mode',mode],capture_output=True,env=env)
            for mode in ['Install','Install','Check']:
                r=run(mode);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
            self.assertEqual(dll.read_bytes(),patched)
            self.assertEqual((game/'PCM26-ZH-Backup/GameCyclingDLL_Master.original.dll').read_bytes(),original)
            r=run('Uninstall');self.assertEqual(r.returncode,0,r.stdout+r.stderr)
            self.assertEqual(dll.read_bytes(),original);self.assertFalse(pak.exists())
            dll.write_bytes(b'unknown version')
            self.assertNotEqual(run('Install').returncode,0)
            self.assertEqual(dll.read_bytes(),b'unknown version');self.assertFalse(pak.exists())
            dll.write_bytes(original);(payload/pak.name).write_bytes(b'corrupt')
            self.assertNotEqual(run('Install').returncode,0)
            self.assertEqual(dll.read_bytes(),original)

if __name__=='__main__':unittest.main()
