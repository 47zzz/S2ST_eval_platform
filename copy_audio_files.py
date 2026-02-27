#!/usr/bin/env python3
"""
Copy audio files from NonverbalTTS source directories into the speech_eval data structure.
"""
import os
import shutil
import json
import random

# Dynamically find the base project directory (one level up from speech_eval)
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.dirname(CURRENT_DIR)

DATA_DIR = os.path.join(CURRENT_DIR, "data")

# Source directories to search (in order of priority)
SEARCH_DIRS = [
    os.path.join(BASE, "NonverbalTTS-sympathetic-sad"),
    os.path.join(BASE, "NonverbalTTS-4emotions"),
    os.path.join(BASE, "NonverbalTTS"),
]

MODELS = [
    "gen_MoE_top5_attention",
    "gen_cascaded",
    "gen_expressive",
    "gen_kimi_instruct",
    "gen_seamlessm4t",
    "ChatGPT_audio",
    "gen_ours_100hr",
]

# Emotion -> list of gen filenames (with _gen suffix)
EMOTION_FILES = {
    "Laughing": [
        "0673_ex04_laughter_gen.wav",
        "0685_ex02_laughter_gen.wav",
        "ex02_laughing_00055_gen.wav",
        "ex04_laughing_00343_gen.wav",
        "id00272_OgsyLGXoyWo_00143_gen.wav",
    ],
    "Happy": [
        "ex03_laughing_00013_gen.wav",
        "ex04-ex02_happy_009-ex04_happy_css020_gen.wav",
        "ex04-ex02_nonverbal_008-ex02_nonverbal_css001_gen.wav",
        "id10611_7_ZlkxpOTsY_00092_gen.wav",
        "id00574_7139nBhNOgE_00060_gen.wav",
    ],
    "Angry": [
        "id00692_isRn-mIQiqc_00311_gen.wav",
        "id01388_vz7sd77KOlI_00024_gen.wav",
        "id06119_gwiyIHnH5Ak_00194_gen.wav",
        "ex04-ex02_angry_006-ex04_angry_css028_gen.wav",
        "ex04-ex02_nonverbal_001-ex02_nonverbal_css004_gen.wav",
    ],
    "Sad": [
        "ex03-ex01_laughing_002-ex01_laughing_css009_gen.wav",
        "ex03-ex01_sleepy_001-ex01_sleepy_css039_gen.wav",
        "ex03-ex01_sleepy_001-ex01_sleepy_css041_gen.wav",
        "ex03-ex02_sympathetic-sad_008-ex03_sympathetic_css013_gen.wav",
        "ex04-ex01_sympathetic-sad_010-ex01_sad_css040_gen.wav",
    ],
    "Crying": [
        "ex03-ex02_sympathetic-sad_008-ex02_sad_css021_gen.wav",
        "ex04-ex01_sympathetic-sad_012-ex01_sad_css020_gen.wav",
        "ex03-ex02_sympathetic-sad_015-ex02_sad_css018_gen.wav",
        "ex04-ex01_sympathetic-sad_008-ex01_sad_css017_gen.wav",
        "ex04-ex01_sympathetic-sad_011-ex01_sad_css007_gen.wav",
    ],
    "Neutral": [
        "id00020_uo0V-qY1Z24_00396_gen.wav",
        "id00928_u8YDTQMV5Ac_00088_gen.wav",
        "id03822_RSi8q8fhYXA_00142_gen.wav",
        "id04334_EZ1s12AT7tM_00118_gen.wav",
        "id04517_Fft-7TBJESE_00092_gen.wav",
    ],
}

errors = []
copied = 0


def find_source_dir(source_name):
    """Find which NonverbalTTS directory contains this source audio."""
    for d in SEARCH_DIRS:
        path = os.path.join(d, "audios", source_name)
        if os.path.isfile(path):
            return d
    return None


def copy_file(src, dst):
    global copied
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copy2(src, dst)
    copied += 1


# ── Process fixed emotions ──────────────────────────────────────────────────
for emotion, gen_files in EMOTION_FILES.items():
    for i, gen_filename in enumerate(gen_files):
        set_name = f"set_{i + 1}"
        set_dir = os.path.join(DATA_DIR, emotion, set_name)

        # Derive source filename by removing _gen
        source_name = gen_filename.replace("_gen.wav", ".wav")

        # Find which source directory has this audio
        src_dir = find_source_dir(source_name)
        if src_dir is None:
            errors.append(f"[SOURCE NOT FOUND] {emotion}/{set_name}: {source_name}")
            continue

        print(f"  {emotion}/{set_name}: found in {os.path.basename(src_dir)}")

        # Copy source audio
        src_audio = os.path.join(src_dir, "audios", source_name)
        dst_audio = os.path.join(set_dir, "source", source_name)
        copy_file(src_audio, dst_audio)
        print(f"    ✓ source: {source_name}")

        # Copy each model's generated audio
        for model in MODELS:
            if model == "gen_expressive":
                model_filename = source_name.replace(".wav", "_expressive.wav")
            else:
                model_filename = gen_filename
                
            model_gen_path = os.path.join(src_dir, model, model_filename)
            dst_model = os.path.join(set_dir, model, model_filename)
            
            if os.path.isfile(model_gen_path):
                copy_file(model_gen_path, dst_model)
                print(f"    ✓ {model}: {model_filename}")
            else:
                errors.append(f"[MODEL MISSING] {emotion}/{set_name}/{model}: {model_filename} not found in {os.path.basename(src_dir)}")




# ── Summary ──────────────────────────────────────────────────────────────────
print(f"\n{'='*60}")
print(f"✅ Total files copied: {copied}")
if errors:
    print(f"\n❌ {len(errors)} ERROR(S):")
    for e in errors:
        print(f"  {e}")
else:
    print("✅ No errors!")
