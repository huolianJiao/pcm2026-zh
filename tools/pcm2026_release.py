"""Reproducible exact-source migration and four-scale texture expansion; staging only."""
import argparse,json,re,shutil,struct
from collections import Counter
import xml.etree.ElementTree as ET
from pathlib import Path
from build_phase1 import TOKEN
from cdb import read_cdb,write_cdb
from extract import table_columns
from repack import apply_patches,build_patch
from pcm2026_probe import build_pak,read_overlay
import pcm2026_cjk as engine
ROOT=Path(__file__).resolve().parents[1]
BASE=engine.BASE
OUT=ROOT/'build/payload'
CATALOG=ROOT/'build/catalog.json'
def save(name,obj): (OUT/name).write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding='utf-8')
def prepare():
    assert not OUT.exists(),'Preserve existing stage'
    OUT.mkdir()
    old=json.loads(CATALOG.read_text(encoding='utf-8'))
    lookup={}
    for r in old:
        if r['table']=='LOC':
            k=(r['strid'],r['source'])
            assert k not in lookup or lookup[k]['zh']==r['zh']
            lookup[k]=r
    cols={c['name']:c['values'] for c in table_columns(read_cdb(BASE/'Database/Local.cdb'),'LOC')}
    accepted=[];pending=[]
    for ident,key,src in zip(cols['IDloc'],cols['CONSTANT'],cols['gene_sz_english']):
        if not src: continue
        r=lookup.get((key,src)); row=dict(idloc=ident,strid=key,source=src)
        if r:
            zh=r['zh']
            token_source=src.replace('\\t','') if key in ('RacesCyaWorldTourDesc','RacesContinentalDesc') else src
            valid=r['status'] in ('translated','preserved') and zh.strip() and '\0' not in zh and '\ufffd' not in zh and Counter(TOKEN.findall(token_source))==Counter(TOKEN.findall(zh)) and src.count('\n')==zh.count('\n')
            if valid:
                accepted.append(dict(row,zh=zh,status=r['status'],review=r.get('review','exact-source migration; 2026 context pending')));continue
        pending.append(dict(row,reason='format validation failed' if r else 'changed or new source'))
    save('catalog.json',accepted);save('pending.json',pending)
    chars=sorted({c for r in accepted for c in r['zh'] if ord(c)>255})
    assert chars and max(map(ord,chars))<65536
    plans={};jobs={}
    for scale in ['sma','nor','big','4k']:
        name='fonts_'+scale;tree=ET.parse(BASE/f'Gui/{name}.xml').getroot()
        ow,oh=int(tree.get('imageWidth')),int(tree.get('imageHeight'))
        fonts={n.get('name').rsplit('-',1)[0]:int(n.get('height')) for n in tree if n.get('name').endswith('-0032')}
        width=max(ow,4096);x=0;y=oh+2;rowheight=0;packed={}
        for size in sorted(set(fonts.values()),reverse=True):
            for ch in chars:
                if x+size+2>width:x=0;y+=rowheight;rowheight=0
                key=f'{ord(ch):04x}-{size}';packed[key]=dict(x=x+1,y=y+1,size=size)
                jobs[key]=dict(key=key,char=ch,size=size)
                x+=size+2;rowheight=max(rowheight,size+2)
        height=1<<(y+rowheight-1).bit_length();assert height<=16384
        plans[name]=dict(width=width,height=height,old_width=ow,old_height=oh,fonts=fonts,packed=packed)
    save('plan.json',dict(chars=chars,mapping={c:256+i for i,c in enumerate(chars)},atlases=plans,jobs=list(jobs.values())))
    shutil.copy2(ROOT/'build/original.dll',OUT/'GameCyclingDLL_Master.original.dll')
    print(json.dumps(dict(accepted=len(accepted),pending=len(pending),chars=len(chars),glyph_variants=len(jobs),dimensions={k:[v['width'],v['height']] for k,v in plans.items()})))
def unique(data,needle):
    pos=data.find(needle);assert pos>=0 and data.find(needle,pos+1)<0,(len(needle),pos);return pos
def texture(name,p,pixels):
    asset=bytearray((BASE/f'Gui/{name}.uasset').read_bytes());exp=(BASE/f'Gui/{name}.uexp').read_bytes()
    ow,oh=p['old_width'],p['old_height'];w,h=p['width'],p['height'];oldsize=ow*oh*4;newsize=w*h*4;delta=newsize-oldsize
    assert len(exp)==oldsize+500 and exp[448:460]==b'PF_B8G8R8A8\0'
    head=bytearray(exp[:472]);tail=bytearray(exp[-28:])
    # ImportedSize property, platform dimensions, and mip dimensions.
    dims=struct.pack('<II',ow,oh)
    imported=unique(head[:400],dims);head[imported:imported+8]=struct.pack('<II',w,h)
    assert head[432:440]==dims and tail[:8]==dims
    struct.pack_into('<II',head,432,w,h);struct.pack_into('<II',tail,0,w,h)
    assert struct.unpack_from('<Q',head,408)[0]==oldsize+80
    struct.pack_into('<Q',head,408,newsize+80)
    serial=unique(asset,struct.pack('<QQ',len(exp)-4,len(asset)))
    struct.pack_into('<Q',asset,serial,len(exp)-4+delta)
    bulkstart=unique(asset,struct.pack('<Q',len(asset)+len(exp)-4))
    struct.pack_into('<Q',asset,bulkstart,len(asset)+len(exp)-4+delta)
    # One inline data resource: serial offset 472, duplicate offset -1,
    # serialized and raw sizes, legacy flags 1, cooked flags 0x48.
    resource=struct.pack('<QqQQII',472,-1,oldsize,oldsize,1,0x48)
    rp=unique(asset,resource);assert rp+len(resource)==len(asset)
    struct.pack_into('<QQ',asset,rp+16,newsize,newsize)
    return bytes(asset),bytes(head)+pixels+bytes(tail)
def finish():
    assert not (OUT/'manifest.json').exists()
    p=json.loads((OUT/'plan.json').read_text(encoding='utf-8'));chars=p['chars'];files={}
    for name,a in p['atlases'].items():
        w,h=a['width'],a['height'];ow,oh=a['old_width'],a['old_height'];pixels=bytearray(w*h*4)
        orig=(BASE/f'Gui/{name}.uexp').read_bytes()[472:-28]
        for y in range(oh):pixels[y*w*4:y*w*4+ow*4]=orig[y*ow*4:(y+1)*ow*4]
        bounds={}
        for key,pos in a['packed'].items():
            size=pos['size'];g=(OUT/'glyphs'/f'{key}.bgra').read_bytes();assert len(g)==size*size*4
            xs=[x for x in range(size) if any(g[(y*size+x)*4+3] for y in range(size))]
            assert xs,('empty glyph',key)
            bounds[key]=(xs[0],min(size,xs[-1]+2)-xs[0])
            for y in range(size):
                at=((pos['y']+y)*w+pos['x'])*4;pixels[at:at+size*4]=g[y*size*4:(y+1)*size*4]
        for y in range(oh):assert pixels[y*w*4:y*w*4+ow*4]==orig[y*ow*4:(y+1)*ow*4]
        tree=ET.parse(BASE/f'Gui/{name}.xml').getroot();tree.set('imageWidth',str(w));tree.set('imageHeight',str(h))
        for font,size in a['fonts'].items():
            assert sum(n.get('name').startswith(font+'-') for n in tree)==224
            for i in range(256,288):ET.SubElement(tree,'SubTexture',dict(name=f'{font}-{i:04d}',x='0',y=str(oh),width='1',height='1'))
            for i,ch in enumerate(chars):
                key=f'{ord(ch):04x}-{size}';pos=a['packed'][key];left,width=bounds[key]
                ET.SubElement(tree,'SubTexture',dict(name=f'{font}-0{288+i:03d}',x=str(pos['x']+left),y=str(pos['y']),width=str(width),height=str(size)))
        tree[:]=sorted(tree,key=lambda n:(n.get('name').rsplit('-',1)[0],int(n.get('name').rsplit('-',1)[1])))
        asset,exp=texture(name,a,bytes(pixels))
        for ext,blob in [('xml',ET.tostring(tree,encoding='utf-8')),('uasset',asset),('uexp',exp)]:files[f'PCM/Content/Gui/{name}.{ext}']=blob
        print('Built',name,w,h,flush=True)
    catalog=json.loads((OUT/'catalog.json').read_text(encoding='utf-8'));lookup={(r['strid'],r['source']):r['zh'] for r in catalog}
    for db in ['Local.cdb','OfficialLocal.cdb']:
        raw=read_cdb(BASE/'Database'/db);cols={c['name']:c['values'] for c in table_columns(raw,'LOC')}
        vals=[lookup.get((key,src),src) for key,src in zip(cols['CONSTANT'],cols['gene_sz_english'])]
        raw=bytes(apply_patches(raw,build_patch(raw,'LOC','gene_sz_danish',vals)))
        write_cdb(OUT/db,raw);assert read_cdb(OUT/db)==raw
        verify={c['name']:c['values'] for c in table_columns(raw,'LOC')}
        for key in cols:assert verify[key]==(vals if key=='gene_sz_danish' else cols[key]),key
        files['PCM/Content/Database/'+db]=(OUT/db).read_bytes()
    pak=OUT/'pakchunk99-PCM2026ZH_P.pak';digest=build_pak(pak,files);assert read_overlay(pak)==files
    engine.OUT=OUT;dll=engine.build_dll(p['mapping']);(OUT/'GameCyclingDLL_Master.dll').write_bytes(dll)
    save('manifest.json',dict(pak=pak.name,sha256=digest,dll_before=engine.sha((OUT/'GameCyclingDLL_Master.original.dll').read_bytes()),dll_after=engine.sha(dll),characters=len(chars),catalog_rows=len(catalog),translated_rows=sum(r.get('status')=='translated' for r in catalog),preserved_rows=sum(r.get('status')=='preserved' for r in catalog),original_sprite_pixels_preserved=True,status='runtime validation pending'))
    print('PASS: CDB round trip, unchanged columns, original pixels, pak entry hashes, DLL preconditions')
