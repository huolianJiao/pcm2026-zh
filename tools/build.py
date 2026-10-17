"""Build against the user's own unencrypted PCM2026 resources (Windows x64)."""
import argparse, hashlib, json, shutil, subprocess
from pathlib import Path
import pak_reader
import pcm2026_release as release
from cdb import read_cdb
from extract import table_columns

ROOT=Path(__file__).resolve().parents[1]
ORIGINAL='537cbba546b9f6e9beb2b631736632e62c8f884360642c117fe795a5df650f89'
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--game',type=Path,required=True)
    ap.add_argument('--oodle',type=Path,required=True,help='Trusted x64 DLL exporting OodleLZ_Decompress; not included')
    ap.add_argument('--original-dll',type=Path,help='Known original DLL backup, only needed when game is already patched')
    args=ap.parse_args()
    if not __debug__:raise RuntimeError('Do not use Python -O; integrity assertions are required')
    assert args.oodle.is_file(), 'Missing decompression library'
    original=args.original_dll or args.game/'PCM/Binaries/Win64/GameCyclingDLL_Master.dll'
    assert sha(original)==ORIGINAL, 'Unsupported DLL version; restore original before building'
    build=ROOT/'build'
    assert not build.exists(), 'Keep previous build intact: rename build/ before rebuilding'
    build.mkdir()
    shutil.copy2(original,build/'original.dll')
    pak_reader.OUT=build;pak_reader.OODLE=args.oodle.resolve()
    paks=sorted((args.game/'PCM/Content/Paks').glob('*.pak'))
    assert paks, 'Game paks not found'
    for pak in paks:
        if 'PCM2026ZH' in pak.name or 'PCM2026UnrealZH' in pak.name:continue
        print('Reading',pak.name,flush=True)
        info,_=pak_reader.inspect(pak)
        assert not info['encrypted_index'], 'Encrypted resources are unsupported'
    expected=json.loads((ROOT/'resources.json').read_text())
    for name,digest in expected.items():
        assert sha(build/'assets'/name)==digest, ('Unsupported game resource',name)
    cols={c['name']:c['values'] for c in table_columns(read_cdb(release.BASE/'Database/Local.cdb'),'LOC')}
    translated=json.loads((ROOT/'translations/zh-CN.json').read_text(encoding='utf-8'))
    lookup={r['idloc']:r for r in translated};assert len(lookup)==len(translated)
    catalog=[];used=set()
    for ident,key,source in zip(cols['IDloc'],cols['CONSTANT'],cols['gene_sz_english']):
        if not source:continue
        r=lookup.get(ident)
        if r:
            assert r['strid']==key and hashlib.sha256(source.encode()).hexdigest()==r['source_sha256'],key
            used.add(ident)
        catalog.append(dict(table='LOC',idloc=ident,strid=key,source=source,zh=r['zh'] if r else source,status='translated' if r else 'preserved'))
    assert used==set(lookup), 'Translation keys absent in installed game'
    (build/'catalog.json').write_text(json.dumps(catalog,ensure_ascii=False),encoding='utf-8')
    release.prepare()
    assert not json.loads((release.OUT/'pending.json').read_text()), 'Invalid translation formatting'
    subprocess.run(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(ROOT/'tools/rasterize_slot_probe.ps1'),'-OutDir',str(release.OUT),'-FontFamily','Microsoft YaHei UI','-FontScale','0.68','-FontWeight','Bold'],check=True)
    release.finish()
    manifest_path=release.OUT/'manifest.json'
    manifest=json.loads(manifest_path.read_text())
    manifest.update(version='0.6.0-preview',game_build='25827667',replaces_overlay_sha256=['a5e75f8c1775c88ab977ed501a67b04ec23c3e39965f3282295b65a86bcb569e', '669a93c634b32c027995023c1ec1c6aa8dece5dbccb4cfaf55539b94b55ccd71', '1fb5b2d3102596fd1771328eded05c4f0c88fb893d508764ea9598eee159d16e', '1a7945bc231dbb6679683613298ed62559744d896e26788bee07083f2fc64ccd', '2dba50b91f72e17732b98c59935eaed4378bd1b7eb3c3dd2b0b1629a265b6a0a'],text_language='Danish only',english_restored=True)
    manifest_path.write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    print('Build verified. Next: powershell -File .\\Install.ps1 -GamePath "'+str(args.game)+'"')
if __name__=='__main__':main()
