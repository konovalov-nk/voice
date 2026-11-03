#!/usr/bin/env python3
"""
Extract dialogue subtitles from Skyrim.esm + .ILSTRINGS/.DLSTRINGS/.STRINGS.
Matches INFO response text to voice filenames by FormID + response_index.

Subrecord order matters: TRDT starts a new response block, NAM1 gives the string ID.
"""

import json
import struct
import sys
from pathlib import Path


# ── String table loader ────────────────────────────────────────────────────
def _decode_str(raw: bytes) -> str:
    for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            pass
    return raw.decode("latin-1", errors="replace")


def read_strings_file(path: Path) -> dict[int, str]:
    data = path.read_bytes()
    count, data_size = struct.unpack_from("<II", data, 0)
    entries_start = 8
    data_start = entries_start + count * 8
    result = {}

    for i in range(count):
        string_id, offset = struct.unpack_from("<II", data, entries_start + i * 8)
        pos = data_start + offset

        if path.suffix.lower() in (".ilstrings", ".dlstrings"):
            if pos + 4 <= len(data):
                length = struct.unpack_from("<I", data, pos)[0]
                start = pos + 4
                end = start + length
                if end <= len(data):
                    raw = data[start:end]
                else:
                    end = data.find(b"\x00", pos)
                    raw = data[pos : end if end != -1 else len(data)]
            else:
                raw = b""
        else:
            end = data.find(b"\x00", pos)
            raw = data[pos : end if end != -1 else len(data)]

        result[string_id] = _decode_str(raw)

    return result


def load_string_tables(strings_dir: Path, prefix: str = "skyrim_english") -> dict[int, str]:
    merged = {}
    for ext in ("ilstrings", "dlstrings", "strings"):
        p = strings_dir / f"{prefix}.{ext}"
        if p.exists():
            table = read_strings_file(p)
            print(f"  {p.name}: {len(table)} entries")
            merged.update(table)
    return merged


# ── ESM binary helpers ──────────────────────────────────────────────────────
def _u32(data, off):
    return struct.unpack_from("<I", data, off)[0]


def _u16(data, off):
    return struct.unpack_from("<H", data, off)[0]


def _fmt_hex(val):
    return f"{val:08x}"


# ── Ordered subrecord parser ────────────────────────────────────────────────
def _parse_subrecords_ordered(data, start, end):
    """Parse subrecords as ordered list of (type, raw_bytes)."""
    result = []
    pos = start
    while pos + 6 <= end:
        stype = data[pos : pos + 4].decode("ascii", errors="replace")
        ssize = _u16(data, pos + 4)
        pos += 6
        if pos + ssize > end:
            break
        result.append((stype, data[pos : pos + ssize]))
        pos += ssize
    return result


# ── Main extraction ─────────────────────────────────────────────────────────
def extract_dialogue(esm_path: Path, strings_dir: Path, string_prefixes: list[str]):
    data = esm_path.read_bytes()
    filesize = len(data)

    # Skip TES4 header
    tsize = _u32(data, 4)
    pos = 8 + tsize

    # ── Find DIAL top-level GRUP ──
    dial_start = dial_end = None
    while pos + 24 <= filesize:
        if data[pos : pos + 4] != b"GRUP":
            pos += 4
            continue
        gsize = _u32(data, pos + 4)
        gtype = _u32(data, pos + 12)
        label = data[pos + 8 : pos + 12]
        try:
            label_str = label.decode("ascii")
        except:
            label_str = ""
        if label_str == "DIAL" and gtype == 0:
            dial_start = pos + 24
            dial_end = pos + gsize
            break
        pos += gsize

    if dial_start is None:
        print("ERROR: DIAL group not found in ESM")
        return []

    print(f"DIAL group: 0x{dial_start - 24:x} — 0x{dial_end:x} ({dial_end - dial_start} bytes)")

    # ── Scan DIAL records and INFO child groups ──
    pos = dial_start
    current_dial = {}
    results = []

    while pos + 24 <= dial_end:
        tag = data[pos : pos + 4]

        if tag == b"GRUP":
            gsize = _u32(data, pos + 4)
            gtype = _u32(data, pos + 12)
            glabel = _u32(data, pos + 8)

            if gtype == 7:
                # INFO child group: extract response blocks with ordered subrecords
                inner = pos + 24
                inner_end = pos + gsize
                while inner + 24 <= inner_end:
                    if data[inner : inner + 4] != b"INFO":
                        inner += 1
                        continue
                    isize = _u32(data, inner + 4)
                    iformid = _u32(data, inner + 12)
                    subrecs = _parse_subrecords_ordered(data, inner + 24, inner + 24 + isize)

                    # Walk TRDT/NAM1 pairs to build response_index
                    response_index = 0
                    for stype, sdata in subrecs:
                        if stype == "TRDT":
                            response_index += 1
                        elif stype == "NAM1" and response_index > 0 and len(sdata) == 4:
                            string_id = _u32(sdata, 0)
                            results.append(
                                {
                                    "dial_formid": _fmt_hex(current_dial.get("formid", glabel)),
                                    "dial_edid": current_dial.get("edid", ""),
                                    "quest_formid": _fmt_hex(current_dial.get("quest_formid", 0)),
                                    "info_formid": _fmt_hex(iformid),
                                    "response_index": response_index,
                                    "string_id": string_id,
                                }
                            )

                    inner += 24 + isize

            pos += gsize

        elif tag == b"DIAL":
            dsize = _u32(data, pos + 4)
            dformid = _u32(data, pos + 12)
            subrecs = _parse_subrecords_ordered(data, pos + 24, pos + 24 + dsize)

            edid = ""
            quest_fid = 0
            for stype, sdata in subrecs:
                if stype == "EDID":
                    edid = sdata.rstrip(b"\x00").decode("latin-1", errors="replace")
                elif stype == "QSTI" and len(sdata) >= 4:
                    quest_fid = _u32(sdata, 0)

            current_dial = {"formid": dformid, "edid": edid, "quest_formid": quest_fid}
            pos += 24 + dsize

        else:
            pos += 1

    return results


def main():
    if len(sys.argv) < 3:
        print("Usage: esm2subtitles.py <Skyrim.esm> <strings_dir> [out.jsonl]")
        sys.exit(1)

    esm_path = Path(sys.argv[1])
    strings_dir = Path(sys.argv[2])
    out_path = Path(sys.argv[3]) if len(sys.argv) > 3 else Path("dialogue.jsonl")

    # Load base game string tables first (they have priority)
    prefixes = ["skyrim_english", "update_english"]
    for extra in sys.argv[4:]:
        if extra not in prefixes:
            prefixes.append(extra)

    # DLC tables loaded as fallback only — don't overwrite base game entries
    dlc_prefixes = []
    for dlc in ["dawnguard_english", "dragonborn_english", "hearthfires_english"]:
        if (strings_dir / f"{dlc}.ilstrings").exists():
            dlc_prefixes.append(dlc)

    print("Loading string tables...")
    strings = {}
    # Base game first (wins)
    for prefix in prefixes:
        table = {}
        for ext in ("ilstrings", "dlstrings", "strings"):
            p = strings_dir / f"{prefix}.{ext}"
            if p.exists():
                table.update(read_strings_file(p))
        strings.update(table)
        print(f"  {prefix}: {len(table)} entries")

    # DLC as fallback (only fill missing)
    for prefix in dlc_prefixes:
        table = {}
        for ext in ("ilstrings", "dlstrings", "strings"):
            p = strings_dir / f"{prefix}.{ext}"
            if p.exists():
                table.update(read_strings_file(p))
        new = sum(1 for k in table if k not in strings)
        for k, v in table.items():
            if k not in strings:
                strings[k] = v
        print(f"  {prefix}: {new} new entries (fallback, no overwrites)")
    print(f"Total strings: {len(strings)}")

    # Extract INFO records
    print(f"\nParsing {esm_path.name} ...")
    results = extract_dialogue(esm_path, strings_dir, prefixes)

    # Resolve string IDs and write output
    resolved = 0
    unresolved = 0
    with open(out_path, "w", encoding="utf-8") as f:
        for r in results:
            text = strings.get(r["string_id"], "")
            if text:
                resolved += 1
            else:
                unresolved += 1
            r["text"] = text
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"\nExtracted {len(results)} response entries")
    print(f"  resolved:  {resolved}")
    print(f"  unresolved: {unresolved}")
    print(f"  output:    {out_path}")

    # Sanity check
    for r in results:
        if "arrow" in r["text"].lower() and "knee" in r["text"].lower():
            print(f"\nSANITY CHECK: {r['info_formid']}_idx{r['response_index']}: {r['text']}")
            break
    else:
        # Arrow to the knee is guard dialogue, might use male guard voice type
        print("\nSANITY CHECK: 'arrow in the knee' - searching string table directly...")
        for sid, text in strings.items():
            if "arrow" in text.lower() and "knee" in text.lower():
                print(f"  string_id={sid} ({_fmt_hex(sid)}): {text[:150]}")
                break
        else:
            print("  NOT FOUND in string tables")


if __name__ == "__main__":
    main()
