#!/usr/bin/env python3
"""
generate_manifest.py
Run this script once after placing your audio files into data/.
It will scan data/ and produce static/data_manifest.json which the
offline evaluation site reads to find all audio files.

Usage:
    python generate_manifest.py
"""

import os
import json

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')
OUT_PATH = os.path.join(BASE_DIR, 'static', 'data_manifest.json')

AUDIO_EXT = {'.wav', '.mp3', '.ogg', '.flac', '.m4a'}


def first_audio(folder):
    """Return the first audio filename found in folder, or None."""
    if not os.path.isdir(folder):
        return None
    for f in sorted(os.listdir(folder)):
        if os.path.splitext(f)[1].lower() in AUDIO_EXT:
            return f
    return None


sets = []

for emotion in sorted(os.listdir(DATA_DIR)):
    emo_path = os.path.join(DATA_DIR, emotion)
    if not os.path.isdir(emo_path) or emotion.startswith('.'):
        continue

    for set_name in sorted(os.listdir(emo_path)):
        set_path = os.path.join(emo_path, set_name)
        if not os.path.isdir(set_path) or set_name.startswith('.'):
            continue

        # Source audio
        src_folder = os.path.join(set_path, 'source')
        src_file = first_audio(src_folder)
        source_path = f"../data/{emotion}/{set_name}/source/{src_file}" if src_file else None

        # Model folders (everything except 'source')
        models = {}
        for fname in sorted(os.listdir(set_path)):
            fpath = os.path.join(set_path, fname)
            if os.path.isdir(fpath) and fname != 'source' and not fname.startswith('.'):
                af = first_audio(fpath)
                if af:
                    models[fname] = f"../data/{emotion}/{set_name}/{fname}/{af}"

        if not models:
            print(f"  [WARN] No model audio found in {set_path}")
            continue

        sets.append({
            "emotion":  emotion,
            "set":      set_name,
            "source":   source_path,
            "models":   models
        })

manifest = {"sets": sets}

with open(OUT_PATH, 'w', encoding='utf-8') as f:
    json.dump(manifest, f, ensure_ascii=False, indent=2)

print(f"✅  Manifest written to {OUT_PATH}")
print(f"    {len(sets)} sets found across {len({s['emotion'] for s in sets})} emotions.")
