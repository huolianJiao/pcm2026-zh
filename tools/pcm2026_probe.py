import hashlib, io, struct
from pathlib import Path
def fstring(text):
    b=text.encode('utf-8')+b'\0'
    return struct.pack('<i',len(b))+b

def entry(offset,blob):
    return struct.pack('<qqqI20sBI',offset,len(blob),len(blob),0,hashlib.sha1(blob).digest(),0,0)

def build_pak(path,files):
    data=bytearray(); records=[]
    for name,blob in sorted(files.items()):
        offset=len(data)
        record=entry(offset,blob)
        data.extend(entry(0,blob));data.extend(blob)
        records.append(fstring(name)+record)
    index=fstring('../../../')+struct.pack('<i',len(records))+b''.join(records)
    offset=len(data);data.extend(index)
    data.extend(b'\0'*17+struct.pack('<IIqq',0x5a6f12e1,8,offset,len(index))+hashlib.sha1(index).digest()+b'\0'*160)
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_bytes(data)
    assert data[-221+17:-221+21]==struct.pack('<I',0x5a6f12e1)
    assert hashlib.sha1(data[offset:offset+len(index)]).digest()==data[-180:-160]
    return hashlib.sha256(data).hexdigest()

def read_overlay(path):
    """Validate and read this tool's uncompressed v8 overlay format."""
    data=path.read_bytes();footer=data[-221:]
    magic,version,index_off,index_size=struct.unpack_from('<IIqq',footer,17)
    assert magic==0x5a6f12e1 and version==8 and footer[16]==0
    index=data[index_off:index_off+index_size]
    assert hashlib.sha1(index).digest()==footer[41:61]
    f=io.BytesIO(index)
    def text():
        n=struct.unpack('<i',f.read(4))[0];assert 0<n<4096
        return f.read(n)[:-1].decode()
    assert text()=='../../../'
    count=struct.unpack('<i',f.read(4))[0];files={}
    for _ in range(count):
        name=text();off,size,usize,compression,digest,flags,block=struct.unpack('<qqqI20sBI',f.read(53))
        assert compression==0 and flags==0 and size==usize
        blob=data[off+53:off+53+size]
        assert hashlib.sha1(blob).digest()==digest
        assert data[off:off+53]==entry(0,blob)
        files[name]=blob
    assert f.tell()==len(index)
    return files
