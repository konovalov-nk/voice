#!/usr/bin/env python3
"""Join WAV files with dialogue subtitles into a single manifest."""

import json
import re
import sys
from pathlib import Path


def main():
    dialogue_path = Path(sys.argv[1])
    wav_dir = Path(sys.argv[2])
    out_path = Path(sys.argv[3]) if len(sys.argv) > 3 else Path("voice_manifest.jsonl")

    # Load dialogue
    dial_by_key = {}
    with open(dialogue_path) as f:
        for line in f:
            r = json.loads(line)
            r["text"] = r["text"].rstrip("\x00").strip()
            if r["text"]:
                key = (r["info_formid"], r["response_index"])
                dial_by_key[key] = r

    # Match with WAVs
    voice_re = re.compile(r"_([0-9a-fA-F]{8})_(\d+)\.wav$")
    matched = 0
    unmatched = 0

    with open(out_path, "w", encoding="utf-8") as out:
        for wav in sorted(wav_dir.rglob("*.wav")):
            m = voice_re.search(wav.name)
            if not m:
                continue

            formid = m.group(1).lower()
            resp_idx = int(m.group(2))
            key = (formid, resp_idx)
            rel = wav.relative_to(wav_dir)
            voice_type = rel.parent.name
            plugin = rel.parent.parent.name if rel.parent.parent != rel.parent else ""

            entry = {
                "wav": str(rel),
                "plugin": plugin,
                "voice_type": voice_type,
                "info_formid": formid,
                "response_index": resp_idx,
            }

            if key in dial_by_key:
                d = dial_by_key[key]
                entry["text"] = d["text"]
                entry["dial_edid"] = d.get("dial_edid", "")
                matched += 1
            else:
                entry["text"] = None
                unmatched += 1

            out.write(json.dumps(entry, ensure_ascii=False) + "\n")

    total = matched + unmatched
    print(f"Total WAVs: {total}")
    print(f"With subtitles: {matched} ({matched/total*100:.1f}%)")
    print(f"Without subtitles: {unmatched}")
    print(f"Manifest: {out_path}")


if __name__ == "__main__":
    main()
