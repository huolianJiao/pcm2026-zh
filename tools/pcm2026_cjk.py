import hashlib, json, struct
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/"build/assets/PCM/Content"
OUT=ROOT/"build/payload"
def sha(blob):return hashlib.sha256(blob).hexdigest()

def align(n,a):return (n+a-1)//a*a

def build_dll(mapping,diagnostic=False):
    data=bytearray((OUT/'GameCyclingDLL_Master.original.dll').read_bytes())
    assert sha(data)=='ef5ce7b20912b317db77c549f844206844b25d9ffb0a0f7e0e990744fcaac8d4'
    pe=struct.unpack_from('<I',data,60)[0];opt=pe+24
    count=struct.unpack_from('<H',data,pe+6)[0];st=opt+struct.unpack_from('<H',data,pe+20)[0]
    sa,fa=struct.unpack_from('<II',data,opt+32)
    sections=[struct.unpack_from('<IIII',data,st+i*40+8) for i in range(count)]
    def off(rva):return next(ro+rva-va for vs,va,rs,ro in sections if va<=rva<va+rs)
    assert st+(count+1)*40<=min(s[3] for s in sections if s[3])
    base=align(max(va+max(vs,rs) for vs,va,rs,ro in sections),sa);raw=align(len(data),fa)
    code=bytearray();labels={};fix=[]
    def emit(s):code.extend(bytes.fromhex(s))
    def label(s):labels[s]=base+len(code)
    def jump(op,target):emit(op);fix.append((len(code),target));code.extend(b'\0'*4)
    label('map');emit('81FAFFFF0000');jump('0F87','fallback')
    emit('488D05');fix.append((len(code),'table'));code.extend(b'\0'*4)
    emit('8B0490 85C0');jump('0F84','fallback')
    if diagnostic:
        emit('498B8730020000 8B805C150000 4489C9 83E103 83F103 C1E102 D3E8 83E00F 83F80A')
        jump('0F82','digit');emit('83C007');label('digit');emit('83C030 89C2');jump('E9',0x6c4597)
    else:
        emit('498B8D38020000');jump('E9',0x6c45c1)
    label('fallback');emit('81FA13200000');jump('E9',0x6c4470)
    label('guard');emit('4181FC00010000');jump('0F83',0x67d7ca)
    emit('410FB6CC488D41544803C0890CC3');jump('E9',0x67d7ca)
    label('advance');emit('81FA00010000');jump('0F82',0x67dc1f)
    emit('3B915C150000');jump('0F83',0x67dc0b)
    emit('488B8140150000 4863D2 488B04D0 F30F104020 4883C438 C3')
    endcode=len(code);code.extend(b'\0'*(align(len(code),16)-len(code)));label('table')
    table=bytearray(65536*4)
    for ch,index in mapping.items():struct.pack_into('<I',table,ord(ch)*4,index)
    code.extend(table)
    for pos,target in fix:struct.pack_into('<i',code,pos,(labels[target] if isinstance(target,str) else target)-(base+pos+4))
    patches=[]
    def patch(rva,old,new):
        before=bytes.fromhex(old);where=off(rva)
        assert data[where:where+len(before)]==before,(hex(rva),data[where:where+len(before)].hex(),old)
        assert len(new)<=len(before)
        after=new+b'\x90'*(len(before)-len(new));data[where:where+len(before)]=after
        patches.append(dict(rva=hex(rva),before=old,after=after.hex()))
    def branch(src,dest):return b'\xe9'+struct.pack('<i',dest-src-5)
    patch(0x6c421e,'0F851D010000',branch(0x6c421e,0x6c424a))
    patch(0x6c446a,'81FA13200000',branch(0x6c446a,labels['map']))
    patch(0x67d4a9,'7569',bytes.fromhex('7269'))
    patch(0x67d7bc,'410FB6CC488D41544803C0890CC3',branch(0x67d7bc,labels['guard']))
    patch(0x67dc17,'81FA000100007DEC',branch(0x67dc17,labels['advance']))
    hdr=bytearray(40);hdr[:8]=b'.cjkext\0'
    struct.pack_into('<IIII',hdr,8,len(code),base,align(len(code),fa),raw);struct.pack_into('<I',hdr,36,0x60000020)
    data[st+count*40:st+(count+1)*40]=hdr
    struct.pack_into('<H',data,pe+6,count+1);struct.pack_into('<I',data,opt+56,align(base+len(code),sa));struct.pack_into('<I',data,opt+64,0)
    data.extend(b'\0'*(raw-len(data)));data.extend(code);data.extend(b'\0'*(align(len(data),fa)-len(data)))
    import capstone
    md=capstone.Cs(capstone.CS_ARCH_X86,capstone.CS_MODE_64)
    decoded=list(md.disasm(code[:endcode],base));assert sum(i.size for i in decoded)==endcode
    (OUT/'patch-disassembly.txt').write_text('\n'.join(f'{i.address:08x}: {i.mnemonic} {i.op_str}' for i in decoded))
    (OUT/'patches.json').write_text(json.dumps(patches,indent=2))
    return bytes(data)
