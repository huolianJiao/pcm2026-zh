#!/usr/bin/env python3
"""repack.py — patch a localization column of Local.cdb from a translated CSV.

Usage:
    python repack.py <original.cdb> <csv_dir> --from <src_col> --to <dst_lang_col> -o <out.cdb>

    <csv_dir> contains LOC.csv / LOC_GUIDE.csv as produced by extract.py.
    --from names the CSV column holding the new text (e.g. "chinese",
             or "gene_sz_hungarian" for an identity round-trip test).
    --to   names the in-game language column to overwrite
             (e.g. "gene_sz_hungarian").

Strategy: byte surgery on the decompressed database.
  * the 34-block length array is rewritten in place (same slot count, sentinel
    slots keep their original 0xCCCC.. u32) -> zero size change
  * the 35-block string blob is replaced; its payload-size u32, its block size,
    and the sizes of every enclosing block are adjusted by the byte delta
  * row count, schema, all other bytes untouched
"""
import argparse
import csv
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cdb import read_cdb, write_cdb, parse_block, walk, AA

SENTINEL_MIN = 0x1000000


def collect_column(data: bytes, table_name: str, col_name: str):
    """Locate a string column; return (blk34, blk35, lengths tuple)."""
    root = parse_block(data, 0)
    tbl = None
    for b in walk(root):
        if b.btype == 16 and b.name == table_name:
            tbl = b
            break
    if tbl is None:
        return None
    for f in [b for b in walk(tbl) if b.btype == 32 and b.name == col_name]:
        p, lengths, blob = f.payload_off, None, None
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
            nxt = data.find(AA, p + 1, f.payload_end)
            if nxt < 0:
                break
            p = nxt
        if lengths is not None and blob is not None:
            n = (lengths.payload_end - lengths.payload_off) // 4
            return lengths, blob, struct.unpack_from(f"<{n}I", data, lengths.payload_off)
    return None


def build_patch(inner: bytes, table_name: str, col_name: str, new_strings: list) -> list:
    """Return list of (offset, old_len, new_bytes) patches for one column."""
    got = collect_column(inner, table_name, col_name)
    if got is None:
        raise SystemExit(f"column {col_name} not found in {table_name}")
    blk34, blk35, lens = got
    if len(lens) != len(new_strings):
        raise SystemExit(f"{table_name}.{col_name}: {len(lens)} slots vs {len(new_strings)} csv rows")

    # --- build new blob + new length array (preserve original trailing padding)
    new_lens, blob_parts = [], []
    for i, s in enumerate(new_strings):
        if lens[i] >= SENTINEL_MIN:          # sentinel slot: no string, keep u32
            new_lens.append(lens[i])
            continue
        b = s.encode("utf-8") + b"\x00"
        new_lens.append(len(b))
        blob_parts.append(b)
    sum_old = sum(v for v in lens if v < SENTINEL_MIN)
    psz_off = blk35.payload_off
    psz_old = struct.unpack_from("<I", inner, psz_off)[0]
    blob_start = psz_off + 4
    padding = inner[blob_start + sum_old: blob_start + psz_old]  # keep byte-for-byte
    core = b"".join(blob_parts)
    # the format keeps every block on a 4-byte grid: pad so the size delta % 4 == 0
    k = (-(len(core) + len(padding) - psz_old)) % 4
    new_blob = core + padding + b"\x00" * k

    patches = []
    # 1. length array: in-place overwrite (same byte size)
    arr_start, arr_end = blk34.payload_off, blk34.payload_end
    new_arr = struct.pack(f"<{len(new_lens)}I", *new_lens)
    assert len(new_arr) == arr_end - arr_start, "length array size changed?!"
    patches.append((arr_start, arr_end - arr_start, new_arr))

    # 2. string blob: replace [payload_off+4, payload_off+4+psz_old)
    patches.append((blob_start, psz_old, new_blob))
    # 3. payload-size u32
    patches.append((psz_off, 4, struct.pack("<I", len(new_blob))))
    # 4. 35-block size field: grow/shrink by the same delta, preserving any tail layout
    delta = len(new_blob) - psz_old
    patches.append((blk35.start + 4, 4, struct.pack("<I", blk35.size + delta)))

    # 5. every enclosing block (on original coordinates) grows/shrinks by delta
    if delta != 0:
        root = parse_block(inner, 0)
        old_end35 = blk35.start + blk35.size
        for b in walk(root):
            if b is blk35 or b.start >= blk35.start or b.start + b.size < old_end35:
                continue
            if b.btype in (0, 1, 2, 16, 17, 18, 21, 22, 32, 33, 34, 35, 36):
                patches.append((b.start + 4, 4, struct.pack("<I", b.size + delta)))
    return patches


def apply_patches(inner: bytes, patches: list) -> bytearray:
    patches = sorted(patches, key=lambda t: -t[0])
    for i in range(1, len(patches)):
        a, b = patches[i - 1], patches[i]
        assert a[0] >= b[0] + b[1] or a[0] + a[1] <= b[0], f"overlapping patches at {a[0]:#x}/{b[0]:#x}"
    out = bytearray(inner)
    for off, old_len, new_bytes in patches:
        out[off:off + old_len] = new_bytes
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cdb")
    ap.add_argument("csv_dir")
    ap.add_argument("--from", dest="src", required=True)
    ap.add_argument("--to", dest="dst", required=True)
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--tables", nargs="+", default=["LOC", "LOC_GUIDE"])
    args = ap.parse_args()

    inner = read_cdb(args.cdb)
    print(f"original inner: {len(inner)} bytes")

    all_patches = []
    for tname in args.tables:
        csv_path = os.path.join(args.csv_dir, tname + ".csv")
        if not os.path.exists(csv_path):
            print(f"{tname}: no csv, skipped")
            continue
        with open(csv_path, encoding="utf-8-sig") as f:
            rows = list(csv.reader(f))
        header = rows[0]
        if args.src not in header:
            print(f"{tname}: csv has no column {args.src!r} -> skipped")
            continue
        si = header.index(args.src)
        new_strings = [r[si] for r in rows[1:]]
        n_empty = sum(1 for s in new_strings if not s.strip())
        print(f"{tname}: {len(new_strings)} rows from csv ({n_empty} empty -> keep original)")
        # empty translation -> keep the ORIGINAL column value (read dst column of same csv)
        di = header.index(args.dst)
        orig = [r[di] for r in rows[1:]]
        new_strings = [s if s.strip() else orig[i] for i, s in enumerate(new_strings)]

        all_patches += build_patch(inner, tname, args.dst, new_strings)

    out = apply_patches(inner, all_patches)
    print(f"patched inner: {len(out)} bytes ({len(out) - len(inner):+d})")
    write_cdb(args.out, bytes(out))
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
