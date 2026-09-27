#!/usr/bin/env python3
"""extract.py — export LOC (and LOC_GUIDE) localization tables from Local.cdb to CSV.

Usage: python extract.py <Local.cdb> <outdir>
Writes: <outdir>/<table>.csv with columns: idloc, strid, <lang...>
"""
import csv
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cdb import read_cdb, parse_block, walk


def table_columns(data: bytes, table_name: str):
    """Return (fieldnames, per-column row values) for the named localization table."""
    root = parse_block(data, 0)
    tbl = None
    for b in walk(root):
        if b.btype == 16 and b.name == table_name:
            tbl = b
            break
    if tbl is None:
        raise SystemExit(f"table {table_name} not found")

    fields = [b for b in walk(tbl) if b.btype == 32 and b.name]
    cols = []  # list of dicts: name, kind, values
    for f in fields:
        p = f.payload_off
        lengths = blob = None
        while p + 4 <= f.payload_end:
            if data[p:p + 4] == b"\xAA" * 4:
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
            nxt = data.find(b"\xAA" * 4, p + 1, f.payload_end)
            if nxt < 0:
                break
            p = nxt

        col = {"name": f.name, "blk32": f}
        if lengths is not None and blob is not None:
            # string column: lengths[] (bytes incl NUL) + blob.
            # Trailing slots hold 0xCCCC.. padding sentinels (value >= 0x1000000) - keep them.
            n = (lengths.payload_end - lengths.payload_off) // 4
            lens = struct.unpack_from(f"<{n}I", data, lengths.payload_off)
            psz = struct.unpack_from("<I", data, blob.payload_off)[0]
            blob_data = data[blob.payload_off + 4: blob.payload_off + 4 + psz]
            real = [v for v in lens if v < 0x1000000]
            assert sum(real) <= len(blob_data), \
                f"{f.name}: sum(lengths)={sum(real)} > blob={len(blob_data)}"
            used = sum(real)  # trailing bytes beyond this are padding
            vals, q = [], 0
            for ln in lens:
                if ln >= 0x1000000:      # sentinel slot: no string
                    vals.append("")
                    continue
                vals.append(blob_data[q:q + ln - 1].decode("utf-8", "replace"))  # strip NUL
                q += ln
            col.update(kind="str", lengths=lens, values=vals, blk34=lengths, blk35=blob)
        elif lengths is not None:
            n = (lengths.payload_end - lengths.payload_off) // 4
            vals = list(struct.unpack_from(f"<{n}I", data, lengths.payload_off))
            col.update(kind="int", values=vals, blk34=lengths)
        cols.append(col)
    return cols


LANG_COLS = ["gene_sz_english", "gene_sz_french", "gene_sz_spanish", "gene_sz_italian",
             "gene_sz_dutch", "gene_sz_german", "gene_sz_danish", "gene_sz_norvegian",
             "gene_sz_polish", "gene_sz_russian", "gene_sz_portuguese", "gene_sz_czech",
             "gene_sz_japanese", "gene_sz_hungarian"]


def export_table(data: bytes, table_name: str, out_csv: str):
    cols = table_columns(data, table_name)
    names = [c["name"] for c in cols]
    rows_n = len(cols[0]["values"])
    for c in cols:
        assert len(c["values"]) == rows_n, f"row count mismatch in {c['name']}"
    print(f"{table_name}: {rows_n} rows, columns: {names}")
    byname = {c["name"]: c for c in cols}
    sz_cols = [n for n in names if n.startswith("gene_sz_")]
    header = ["idloc", "strid"] + sz_cols
    with open(out_csv, "w", newline="", encoding="utf-8-sig") as fp:
        w = csv.writer(fp)
        w.writerow(header)
        for i in range(rows_n):
            w.writerow([byname["IDloc"]["values"][i], byname["CONSTANT"]["values"][i]]
                       + [byname[n]["values"][i] for n in sz_cols])
    print(f"  -> {out_csv}")


if __name__ == "__main__":
    cdb_path = sys.argv[1] if len(sys.argv) > 1 else r"E:\SteamLibrary\steamapps\common\Pro Cycling Manager 2023\Database\Local.cdb"
    outdir = sys.argv[2] if len(sys.argv) > 2 else r"E:\code\dsh-workspace\pcm-l10n\work"
    os.makedirs(outdir, exist_ok=True)
    data = read_cdb(cdb_path)
    print(f"decompressed: {len(data)} bytes")
    export_table(data, "LOC", os.path.join(outdir, "LOC.csv"))
    try:
        export_table(data, "LOC_GUIDE", os.path.join(outdir, "LOC_GUIDE.csv"))
    except SystemExit:
        print("LOC_GUIDE not present, skipped")
