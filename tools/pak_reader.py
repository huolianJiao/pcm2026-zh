import ctypes, hashlib, io, re, struct, zlib
from pathlib import Path
OUT=Path("build")
OODLE=None
def decode_oodle(blob, size):
    lib = ctypes.CDLL(str(OODLE))
    fn = lib.OodleLZ_Decompress
    fn.restype = ctypes.c_ssize_t
    fn.argtypes = [ctypes.c_void_p, ctypes.c_ssize_t, ctypes.c_void_p, ctypes.c_ssize_t,
                   ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_void_p,
                   ctypes.c_ssize_t, ctypes.c_void_p, ctypes.c_void_p,
                   ctypes.c_void_p, ctypes.c_ssize_t, ctypes.c_int]
    src = ctypes.create_string_buffer(blob)
    dst = ctypes.create_string_buffer(size + 64)
    result = fn(src, len(blob), dst, size, 1, 0, 0, None, 0, None, None, None, 0, 3)
    assert result == size, ('Oodle decode failed', result, size)
    return dst.raw[:size]

def unpack(f, fmt):
    return struct.unpack('<' + fmt, f.read(struct.calcsize('<' + fmt)))

def string(f):
    n, = unpack(f, 'i')
    assert abs(n) < 1000000
    return f.read(n if n >= 0 else -2*n).decode('utf-8' if n >= 0 else 'utf-16le').rstrip('\0')

def inspect(p):
    with p.open('rb') as f:
        f.seek(-221, 2)
        footer = f.read(221)
        magic, version, offset, size = struct.unpack_from('<IIqq', footer, 17)
        assert magic == 0x5a6f12e1 and version == 11, (p, hex(magic), version)
        info = dict(pak=p.name, version=version, encrypted_index=bool(footer[16]), index_size=size)
        methods = ['None'] + [footer[i:i+32].split(b'\0')[0].decode() for i in range(61,221,32)]
        info['compression_methods'] = methods
        if info['encrypted_index']:
            return info, []
        f.seek(offset)
        data = f.read(size)
        assert hashlib.sha1(data).digest() == footer[41:61]
        s = io.BytesIO(data)
        mount = string(s)
        count, seed = unpack(s, 'iQ')
        indices = []
        for _ in range(2):
            has, = unpack(s, 'I')
            indices.append(unpack(s, 'qq20s') if has else None)
        n, = unpack(s, 'i')
        encoded = s.read(n)
        info.update(mount=mount, entries=count, nonencoded=unpack(s,'i')[0])
        assert indices[1]
        off, sz, digest = indices[1]
        f.seek(off)
        directory = f.read(sz)
        assert hashlib.sha1(directory).digest() == digest
        d = io.BytesIO(directory)
        files = []
        for _ in range(unpack(d, 'i')[0]):
            folder = string(d)
            for _ in range(unpack(d, 'i')[0]):
                name = string(d)
                location, = unpack(d, 'i')
                path = (mount + folder + name).removeprefix('../../../')
                if location < 0 or location == 0x7fffffff:
                    continue
                e = io.BytesIO(encoded)
                e.seek(location)
                bits, = unpack(e, 'I')
                if bits & 63 == 63:
                    unpack(e, 'I')
                pos, = unpack(e, 'I' if bits & (1<<31) else 'Q')
                rawsize, = unpack(e, 'I' if bits & (1<<30) else 'Q')
                method = (bits >> 23) & 63
                entry = dict(path=path, offset=pos, size=rawsize, method=methods[method], encrypted=bool(bits & (1<<22)))
                files.append(entry)
                wanted = path in ['PCM/Content/Database/Local.cdb','PCM/Content/Database/OfficialLocal.cdb'] or bool(re.fullmatch(r'PCM/Content/Gui/fonts_(?:nor|big|sma|4k)\.(?:xml|uasset|uexp)',path))
                if not wanted or entry['encrypted']:
                    continue
                f.seek(pos)
                ignored, stored, uncompressed, compression, digest = unpack(f,'qqqI20s')
                blocks = [unpack(f,'qq') for _ in range(unpack(f,'i')[0])] if compression else []
                flags, blocksize = unpack(f,'BI')
                assert not flags & 1
                if not compression:
                    blob = f.read(stored)
                elif methods[compression] in ('Zlib','Oodle'):
                    chunks = []
                    packed = []
                    for a,b in blocks:
                        f.seek(pos+a)
                        block = f.read(b-a)
                        packed.append(block)
                        expected = min(blocksize, rawsize-sum(map(len,chunks)))
                        try:
                            chunks.append(zlib.decompress(block) if methods[compression]=='Zlib' else decode_oodle(block,expected))
                        except AssertionError as error:
                            entry['extract_error'] = str(error)
                            entry['first_block_header'] = block[:16].hex()
                            break
                    if 'extract_error' in entry:
                        continue
                    assert hashlib.sha1(b''.join(packed)).digest() == digest
                    blob = b''.join(chunks)
                else:
                    entry['extract_error'] = 'Unsupported compression: ' + methods[compression]
                    continue
                assert len(blob) == uncompressed == rawsize
                if not compression:
                    assert hashlib.sha1(blob).digest() == digest
                dest = (OUT / 'assets' / path).resolve()
                assert dest.is_relative_to((OUT/'assets').resolve())
                dest.parent.mkdir(parents=True,exist_ok=True)
                dest.write_bytes(blob)
                entry['extracted_sha256'] = hashlib.sha256(blob).hexdigest()
        info['files_indexed'] = len(files)
        return info, files
