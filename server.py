from flask import Flask, request, send_from_directory, jsonify
from flask_cors import CORS
import os
import json
import time
import uuid

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__, static_folder=os.path.join(BASE_DIR, 'static'), static_url_path='')
CORS(app, resources={r"/*": {"origins": "*"}})

SAVE_DIR = os.path.join(BASE_DIR, 'saved')
DATA_DIR = os.path.join(BASE_DIR, 'data')
CONFIG_PATH = os.path.join(BASE_DIR, 'config.json')
PASSWORD = "123456"

os.makedirs(SAVE_DIR, exist_ok=True)


@app.before_request
def log_request():
    print(f"[LOG] {request.method} {request.path}")


# ── Auth ──────────────────────────────────────────────────────────────────────

@app.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    subject_id = (data.get('subject_id') or '').strip()
    password = (data.get('password') or '').strip()

    if not subject_id:
        return jsonify({'ok': False, 'error': 'Missing subject ID'}), 400
    if password != PASSWORD:
        return jsonify({'ok': False, 'error': 'Invalid password'}), 401

    return jsonify({'ok': True})


# ── Save results ──────────────────────────────────────────────────────────────

def _find_save_path(subject_id, phase):
    """Return a unique filepath for this (subject, phase)."""
    timestamp = int(time.time() * 1000)
    unique_id = uuid.uuid4().hex[:6]
    base = os.path.join(SAVE_DIR, f"{subject_id}_{phase}_{timestamp}_{unique_id}")
    return base + ".jsonl"


@app.route('/save', methods=['POST'])
def save():
    try:
        data = request.get_json()
        subject_id = (data.get('subject_id') or '').strip()
        phase = (data.get('phase') or '').strip()   # 'mos' | 'ab'
        records = data.get('records')

        if not subject_id or not phase or not records:
            return jsonify({'ok': False, 'error': 'Missing fields'}), 400

        filepath = _find_save_path(subject_id, phase)
        with open(filepath, 'w', encoding='utf-8') as f:
            for rec in records:
                f.write(json.dumps(rec, ensure_ascii=False) + '\n')

        print(f"[INFO] Saved {len(records)} records → {filepath}")
        return jsonify({'ok': True, 'file': os.path.basename(filepath)})
    except Exception as e:
        print(f"[ERROR] {e}")
        return jsonify({'ok': False, 'error': str(e)}), 500


# ── Data listing ──────────────────────────────────────────────────────────────

@app.route('/api/sets')
def list_sets():
    """Return list of all (emotion, set) pairs with their model folders."""
    config = json.load(open(CONFIG_PATH))
    result = []
    for emotion in sorted(os.listdir(DATA_DIR)):
        emo_path = os.path.join(DATA_DIR, emotion)
        if not os.path.isdir(emo_path) or emotion.startswith('.'):
            continue
        for set_name in sorted(os.listdir(emo_path)):
            set_path = os.path.join(emo_path, set_name)
            if not os.path.isdir(set_path) or set_name.startswith('.'):
                continue
            # Find source audio
            source_path = os.path.join(set_path, 'source')
            source_file = None
            if os.path.isdir(source_path):
                for f in os.listdir(source_path):
                    if not f.startswith('.'):
                        source_file = f"/audio/{emotion}/{set_name}/source/{f}"
                        break
            # Find model folders (everything except 'source')
            models = {}
            for fname in sorted(os.listdir(set_path)):
                fpath = os.path.join(set_path, fname)
                if os.path.isdir(fpath) and fname != 'source' and not fname.startswith('.'):
                    for af in os.listdir(fpath):
                        if not af.startswith('.'):
                            models[fname] = f"/audio/{emotion}/{set_name}/{fname}/{af}"
                            break
            result.append({
                'emotion': emotion,
                'set': set_name,
                'source': source_file,
                'models': models   # { folder_name: url }
            })
    return jsonify(result)


@app.route('/api/config')
def get_config():
    return send_from_directory(BASE_DIR, 'config.json')


# ── Audio files ───────────────────────────────────────────────────────────────

@app.route('/audio/<path:filepath>')
def serve_audio(filepath):
    directory, filename = os.path.split(os.path.join(DATA_DIR, filepath))
    return send_from_directory(directory, filename)


@app.route('/data/<path:filepath>')
def serve_data(filepath):
    directory, filename = os.path.split(os.path.join(DATA_DIR, filepath))
    return send_from_directory(directory, filename)


# ── Static frontend ───────────────────────────────────────────────────────────

@app.route('/')
def index():
    return app.send_static_file('login.html')


@app.route('/<path:filename>')
def static_files(filename):
    return app.send_static_file(filename)


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000, debug=True)
