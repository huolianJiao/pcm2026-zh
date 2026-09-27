#!/usr/bin/env python3
"""
cdb.py — Cyanide database (.cdb) parser/patcher for PCM 2023.

File layout (zlib container):
    FF FF FF FF | u32 decompressed_size | u32 compressed_len | zlib stream

Inner format: nested marker-delimited blocks.
    Block:  AA AA AA AA | u32 size | u32 type | <header u32s + name> BB BB BB BB | <payload>
    size counts bytes after the size field itself (block spans off .. off+4+size).
    Section separators: CCCCCCCC (end of section), DDDDDDDD, EEEEEEEE (EOF).

Block types seen:
     0 root (whole file)          1 database ("cyanide database")
     2 header child
    16 table header (name)        17,22 table meta
    21 table meta (row count after BB)
    18 fields container           32 field def (name)
    33 field def copy             34 value array (u32 per row) / field attr
    35 string blob (payload size then null-terminated strings)

CONSTANT table: one field per column; string columns have BOTH a 34-array
(per-row byte length incl. NUL) and a 35-blob (concatenated NUL-terminated
strings, UTF-8).
"""
from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass, field as dc_field
from typing import Optional

AA = b"\xAA" * 4
BB = b"\xBB" * 4
CC = b"\xCC" * 4
DD = b"\xDD" * 4
EE = b"\xEE" * 4


# ---------------------------------------------------------------- container

def read_cdb(path: str) -> bytes:
    """Decompress the .cdb container, return inner bytes."""
    raw = open(path, "rb").read()
    assert raw[:4] == b"\xFF" * 4, "not a cdb container (magic)"
    dec_size, comp_len = struct.unpack_from("<II", raw, 4)
    inner = zlib.decompress(raw[12:12 + comp_len])
    assert len(inner) == dec_size, f"size mismatch {len(inner)} != {dec_size}"
    return inner


def write_cdb(path: str, inner: bytes, level: int = 9):
    """Repack inner bytes into the .cdb container (zlib, same framing)."""
    comp = zlib.compress(inner, level)
    with open(path, "wb") as f:
        f.write(b"\xFF" * 4)
        f.write(struct.pack("<II", len(inner), len(comp)))
        f.write(comp)


# ---------------------------------------------------------------- blocks

@dataclass
class Block:
    start: int          # offset of AA marker
    size: int           # value of the size field (block ends at start+4+size)
    btype: int
    name: Optional[str] # decoded ascii name if any
    hdr_vals: list = dc_field(default_factory=list)   # u32s before BB (excluding size/type/name bytes)
    payload_off: int = 0   # offset right after BB
    payload_end: int = 0   # start+4+size
    children: list = dc_field(default_factory=list)


def _looks_name(data: bytes, p: int) -> Optional[str]:
    """Try reading u32 len + ascii bytes at p; None if not plausible."""
    if p + 8 > len(data):
        return None
    ln = struct.unpack_from("<I", data, p)[0]
    if not (1 <= ln <= 64) or p + 4 + ln + 4 > len(data):
        return None
    cand = data[p + 4:p + 4 + ln]
    if cand.endswith(b"\x00"):   # name length includes the trailing NUL
        cand = cand[:-1]
    if not cand or not all(0x20 <= b <= 0x7E for b in cand):
        return None
    return cand.decode("ascii")


def parse_block(data: bytes, off: int) -> Block:
    assert data[off:off + 4] == AA, f"no AA at {off:#x}"
    size, btype = struct.unpack_from("<II", data, off + 4)
    end = off + size  # size INCLUDES the AA marker: block spans [off, off+size)
    p = off + 12
    vals, name = [], None
    while p + 4 <= end:
        v = struct.unpack_from("<I", data, p)[0]
        if v == 0xBBBBBBBB:
            p += 4
            break
        # length-prefixed name candidate: printable, padded to 4, then BB within a few u32s
        n = _looks_name(data, p)
        if n is not None:
            # name field (u32 len + bytes incl NUL) padded to 4-byte alignment
            q = (p + 4 + struct.unpack_from('<I', data, p)[0] + 3) & ~3
            ok = False
            for _ in range(3):
                if q + 4 > end:
                    break
                nv = struct.unpack_from("<I", data, q)[0]
                if nv == 0xBBBBBBBB:
                    ok = True
                    break
                q += 4
            if ok:
                name = n
                p = q  # position at BB; loop will consume it
                continue
        vals.append(v)
        p += 4
    blk = Block(off, size, btype, name, vals, p, end)
    # recurse into children found in payload
    q = p
    while q + 4 <= end:
        at_aa = data[q:q + 4] == AA
        if at_aa:
            # heuristic guard: child block must end within parent
            csize = struct.unpack_from("<I", data, q + 4)[0]
            ctype = struct.unpack_from("<I", data, q + 8)[0]
            if 0 < csize <= end - (q + 4) and ctype in (1, 2, 16, 17, 18, 21, 22, 32, 33, 34, 35, 36):
                child = parse_block(data, q)
                blk.children.append(child)
                q = child.payload_end
                continue
        # skip separator/u32 until next AA
        nxt = data.find(AA, q + 4, end) if at_aa else data.find(AA, q, end)
        if nxt < 0:
            break
        q = nxt
    return blk


def walk(blk: Block):
    yield blk
    for c in blk.children:
        yield from walk(c)


# ---------------------------------------------------------------- CONSTANT table

def find_constant_table(data: bytes) -> Block:
    """The localization table is named LOC: IDloc + CONSTANT(strID) + 14 language columns."""
    root = parse_block(data, 0)
    for b in walk(root):
        if b.btype == 16 and b.name == "LOC":
            return b
    # fallback: biggest type-16 block
    t16 = [b for b in walk(root) if b.btype == 16]
    assert t16, "no table header blocks found"
    t16.sort(key=lambda b: -b.size)
    return t16[0]


def constant_columns(data: bytes) -> list[dict]:
    """Return CONSTANT columns: [{name, lengths: [u32...], blob_off, blob_end, strings: [...]}]."""
    tbl = find_constant_table(data)
    cols = []
    # string fields: 33/32 blocks with a name, followed by sibling 34 (lengths) and 35 (blob)
    named = [b for b in walk(tbl) if b.btype in (32, 33) and b.name]
    seen_first_def = {}
    for b in named:
        if b.btype == 32:
            seen_first_def[b.name] = b
    # iterate fields in document order using the 32-def blocks
    fields = [b for b in walk(tbl) if b.btype == 32 and b.name]
    for f in fields:
        # children are nested INSIDE the 32-block: 36 (attr), 33 (def copy), 34 (lengths), 35 (blob)
        p = f.payload_off
        lengths, blob = None, None
        while p + 4 <= f.payload_end:
            if data[p:p + 4] == AA:
                c = parse_block(data, p)
                if c.btype in (36, 33):
                    p = c.payload_end
                    continue
                if c.btype == 34 and lengths is None:
                    lengths = c
                    p = c.payload_end
                    continue
                if c.btype == 35 and blob is None:
                    blob = c
                    p = c.payload_end
                    continue
                break
            # skip separators / stray u32s up to next AA inside the field
            nxt = data.find(AA, p + 1, f.payload_end)
            if nxt < 0:
                break
            p = nxt
        col = {"name": f.name, "def": f}
        if lengths is not None:
            arr_off = lengths.payload_off
            arr_len = (lengths.payload_end - arr_off) // 4
            col["lengths_off"] = arr_off
            col["lengths_end"] = lengths.payload_end
            col["lengths"] = list(struct.unpack_from(f"<{arr_len}I", data, arr_off))
            col["lengths_blk"] = lengths
        if blob is not None:
            # payload: u32 payload_size, then strings
            psz = struct.unpack_from("<I", data, blob.payload_off)[0]
            col["blob_off"] = blob.payload_off + 4
            col["blob_end"] = blob.payload_off + 4 + psz
            col["blob_blk"] = blob
            blobdata = data[col["blob_off"]:col["blob_end"]]
            col["strings"] = [s.decode("utf-8", "replace") for s in blobdata.split(b"\x00") if s]
        cols.append(col)
    return cols


if __name__ == "__main__":
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else r"E:\code\dsh-workspace\pcm-analysis\Local_dec.bin"
    data = open(path, "rb").read()
    root = parse_block(data, 0)
    print("block tree (first 3 levels):")

    def show(b, depth=0, maxdepth=3):
        print("  " * depth + f"@{b.start:08X} type={b.btype:<3} size={b.size:<9} name={b.name!r} rows={len(b.children)}")
        if depth < maxdepth:
            for c in b.children:
                show(c, depth + 1, maxdepth)

    show(root)
    cols = constant_columns(data)
    print(f"\nCONSTANT columns: {len(cols)}")
    for c in cols:
        info = f"  {c['name']:<22} lengths={len(c.get('lengths', []))}"
        if "strings" in c:
            info += f" strings={len(c['strings'])} first={c['strings'][0][:40]!r}"
        print(info)
