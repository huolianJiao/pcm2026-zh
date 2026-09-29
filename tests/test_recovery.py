"""Fault injection only edits a temporary copy of the installer, never game files."""
import hashlib,json,os,subprocess,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(data):return hashlib.sha256(data).hexdigest()
@unittest.skipUnless(os.name=='nt','Windows installer')
class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.game=self.root/'Game with spaces';self.payload=self.root/'payload';self.payload.mkdir()
        self.dll=self.game/'PCM/Binaries/Win64/GameCyclingDLL_Master.dll';self.dll.parent.mkdir(parents=True)
        self.pak=self.game/'PCM/Content/Paks/pakchunk99-PCM2026ZH_P.pak';self.pak.parent.mkdir(parents=True)
        self.backup=self.game/'PCM26-ZH-Backup-25503277';self.pending=self.backup/'pending.json'
        self.original=b'original DLL';self.patched=b'patched DLL';self.overlay=b'overlay data'
        self.dll.write_bytes(self.original)
        (self.payload/self.dll.name).write_bytes(self.patched);(self.payload/self.pak.name).write_bytes(self.overlay)
        self.manifest=dict(pak=self.pak.name,dll_before=sha(self.original),dll_after=sha(self.patched),sha256=sha(self.overlay))
        (self.payload/'manifest.json').write_text(json.dumps(self.manifest))
        self.script=ROOT/'Install.ps1'
    def tearDown(self):self.tmp.cleanup()
    def run_mode(self,mode,script=None):
        env=os.environ.copy();env.pop('PSModulePath',None)
        return subprocess.run(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(script or self.script),'-GamePath',str(self.game),'-PayloadPath',str(self.payload),'-Mode',mode],capture_output=True,env=env)
    def inject(self,needle,action):
        text=self.script.read_text(encoding='utf-8-sig');self.assertEqual(text.count(needle),1)
        p=self.root/'fault-installer.ps1';p.write_text(text.replace(needle,needle+'\n   '+action),encoding='utf-8-sig');return p
    def require_ok(self,mode):
        r=self.run_mode(mode);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
    def test_install_mid_write_failure_restores_original(self):
        p=self.inject("AtomicCopy (Join-Path $dir 'next.dll') $dll $after.dll $before.dll","throw 'simulated write failure'")
        r=self.run_mode('Install',p);self.assertNotEqual(r.returncode,0)
        self.assertIn(b'previous state restored',r.stderr)
        self.assertEqual(self.dll.read_bytes(),self.original);self.assertFalse(self.pak.exists());self.assertFalse(self.pending.exists())
        self.assertEqual((self.backup/'GameCyclingDLL_Master.original.dll').read_bytes(),self.original)
    def test_process_exit_then_recover_without_payload(self):
        p=self.inject("AtomicCopy (Join-Path $dir 'next.pak') $pak $after.pak $before.pak","[Environment]::Exit(86)")
        self.assertEqual(self.run_mode('Install',p).returncode,86)
        self.assertTrue(self.pending.exists());self.assertEqual(self.dll.read_bytes(),self.patched)
        self.assertNotEqual(self.run_mode('Install').returncode,0)
        self.payload.rename(self.root/'payload-away')
        self.require_ok('Recover')
        self.assertEqual(self.dll.read_bytes(),self.original);self.assertFalse(self.pak.exists());self.assertFalse(self.pending.exists())
    def test_uninstall_failure_restores_mod_and_state(self):
        self.require_ok('Install')
        state=(self.backup/'installed.json').read_bytes()
        p=self.inject("[IO.File]::Move($pak,(Join-Path $dir 'disabled-overlay.pak'))","throw 'simulated uninstall failure'")
        self.assertNotEqual(self.run_mode('Uninstall',p).returncode,0)
        self.assertEqual(self.dll.read_bytes(),self.patched);self.assertEqual(self.pak.read_bytes(),self.overlay)
        self.assertEqual((self.backup/'installed.json').read_bytes(),state);self.assertFalse(self.pending.exists())
        self.require_ok('Check')
    def test_recovery_refuses_external_changes(self):
        p=self.inject("AtomicCopy (Join-Path $dir 'next.dll') $dll $after.dll $before.dll","[Environment]::Exit(86)")
        self.assertEqual(self.run_mode('Install',p).returncode,86)
        self.dll.write_bytes(b'external Steam update')
        self.assertNotEqual(self.run_mode('Recover').returncode,0)
        self.assertEqual(self.dll.read_bytes(),b'external Steam update');self.assertTrue(self.pending.exists())
    def test_corrupt_backup_blocks_uninstall(self):
        self.require_ok('Install');(self.backup/'GameCyclingDLL_Master.original.dll').write_bytes(b'corrupt')
        self.assertNotEqual(self.run_mode('Uninstall').returncode,0)
        self.assertEqual(self.dll.read_bytes(),self.patched);self.assertEqual(self.pak.read_bytes(),self.overlay)
    def test_uninstall_without_downloaded_payload(self):
        self.require_ok('Install');self.payload.rename(self.root/'payload-away');self.require_ok('Uninstall')
        self.assertEqual(self.dll.read_bytes(),self.original);self.assertFalse(self.pak.exists())
    def test_manifest_path_traversal_rejected(self):
        self.manifest['pak']='../outside.pak';(self.payload/'manifest.json').write_text(json.dumps(self.manifest))
        self.assertNotEqual(self.run_mode('Install').returncode,0);self.assertEqual(self.dll.read_bytes(),self.original)
    def test_steam_update_repair_archives_known_overlay(self):
        legacy=b'old build overlay';self.pak.write_bytes(legacy)
        self.manifest['replaces_overlay_sha256']=[sha(legacy)]
        (self.payload/'manifest.json').write_text(json.dumps(self.manifest))
        self.require_ok('Repair');self.require_ok('Check')
        saved=list(self.backup.glob('update-*/previous-overlay.pak'))
        self.assertEqual(len(saved),1);self.assertEqual(saved[0].read_bytes(),legacy)
        self.require_ok('Uninstall');self.assertEqual(self.dll.read_bytes(),self.original)
        self.assertFalse(self.pak.exists())
    def test_steam_update_repair_refuses_unknown_overlay(self):
        self.pak.write_bytes(b'unknown mod')
        self.manifest['replaces_overlay_sha256']=[sha(b'known mod')]
        (self.payload/'manifest.json').write_text(json.dumps(self.manifest))
        self.assertNotEqual(self.run_mode('Repair').returncode,0)
        self.assertEqual(self.pak.read_bytes(),b'unknown mod');self.assertEqual(self.dll.read_bytes(),self.original)
    def test_external_overlay_created_mid_install_is_preserved(self):
        p=self.inject("AtomicCopy (Join-Path $dir 'next.dll') $dll $after.dll $before.dll", "[IO.File]::WriteAllText($pak,'external update')")
        r=self.run_mode('Install',p);self.assertNotEqual(r.returncode,0)
        self.assertEqual(self.pak.read_text(),'external update');self.assertTrue(self.pending.exists())
        self.assertIn(b'Target changed before replacement',r.stderr)
    def test_journal_cannot_mark_original_dll_absent(self):
        p=self.inject("AtomicCopy (Join-Path $dir 'next.dll') $dll $after.dll $before.dll","[Environment]::Exit(86)")
        self.assertEqual(self.run_mode('Install',p).returncode,86)
        j=json.loads(self.pending.read_text());j['before']['dll']='absent'
        self.pending.write_text(json.dumps(j))
        self.assertNotEqual(self.run_mode('Recover').returncode,0)
        self.assertEqual(self.dll.read_bytes(),self.patched);self.assertTrue(self.pending.exists())
    def test_recovery_rejects_corrupted_transaction_backup(self):
        p=self.inject("AtomicCopy (Join-Path $dir 'next.dll') $dll $after.dll $before.dll","[Environment]::Exit(86)")
        self.assertEqual(self.run_mode('Install',p).returncode,86)
        j=json.loads(self.pending.read_text());(self.backup/j['transaction']/'before.dll').write_bytes(b'bad backup')
        self.assertNotEqual(self.run_mode('Recover').returncode,0)
        self.assertEqual(self.dll.read_bytes(),self.patched);self.assertTrue(self.pending.exists())
    def test_uninstall_process_exit_can_recover(self):
        self.require_ok('Install')
        p=self.inject("[IO.File]::Move($statePath,(Join-Path $dir 'uninstalled.json'))","[Environment]::Exit(86)")
        self.assertEqual(self.run_mode('Uninstall',p).returncode,86)
        self.require_ok('Recover');self.require_ok('Check')
        self.assertEqual(self.dll.read_bytes(),self.patched);self.assertEqual(self.pak.read_bytes(),self.overlay)
    def test_cmd_preserves_launcher_failure_exit_code(self):
        folder=self.root/'cmd-test';folder.mkdir()
        (folder/'Launcher.ps1').write_text('exit 37')
        (folder/'Install.cmd').write_bytes((ROOT/'Install.cmd').read_bytes())
        env=os.environ.copy();env.pop('PSModulePath',None)
        r=subprocess.run(['cmd.exe','/d','/c','Install.cmd'],cwd=folder,input=b'\r\n',capture_output=True,env=env)
        self.assertEqual(r.returncode,37,r.stdout+r.stderr)
    def test_concurrent_installer_lock(self):
        import ctypes
        from ctypes import wintypes
        self.backup.mkdir();kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        kernel.CreateFileW.argtypes=[wintypes.LPCWSTR,wintypes.DWORD,wintypes.DWORD,ctypes.c_void_p,wintypes.DWORD,wintypes.DWORD,wintypes.HANDLE]
        kernel.CreateFileW.restype=wintypes.HANDLE;kernel.CloseHandle.argtypes=[wintypes.HANDLE]
        handle=kernel.CreateFileW(str(self.backup/'installer.lock'),0xC0000000,0,None,4,0x80,None)
        self.assertNotEqual(handle,ctypes.c_void_p(-1).value)
        try:self.assertNotEqual(self.run_mode('Install').returncode,0)
        finally:kernel.CloseHandle(handle)
        self.assertEqual(self.dll.read_bytes(),self.original)

