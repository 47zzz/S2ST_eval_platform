from flask import Flask, request, send_from_directory, jsonify, abort
import os
import json
import time
import uuid
import re

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__, static_folder=os.path.join(BASE_DIR, 'static'), static_url_path='')

# [資安] 限制請求大小為 10 MB，防止惡意使用者傳送超大 JSON 塞爆硬碟
app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024  # 10 MB

SAVE_DIR = os.path.join(BASE_DIR, 'saved')
DATA_DIR = os.path.join(BASE_DIR, 'data')
CONFIG_PATH = os.path.join(BASE_DIR, 'config.json')
PASSWORD = "123456"

# [資安] 限制每次存檔最多接受的 record 數量，防止單次大量寫入
MAX_RECORDS_PER_SAVE = 500

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
    # [資安防護] 過濾不安全的字元，防止使用者輸入含有 ../ 等路徑穿越的字串
    subject_id = re.sub(r'[^a-zA-Z0-9_\-]', '', subject_id)
    phase = re.sub(r'[^a-zA-Z0-9_\-]', '', phase)
    
    timestamp = int(time.time() * 1000)
    unique_id = uuid.uuid4().hex[:6]
    base = os.path.join(SAVE_DIR, f"{subject_id}_{phase}_{timestamp}_{unique_id}")
    return base + ".jsonl"


@app.route('/save', methods=['POST'])
def save():
    try:
        data = request.get_json()
        if not data:
            return jsonify({'ok': False, 'error': 'Invalid JSON'}), 400

        subject_id = (data.get('subject_id') or '').strip()
        phase = (data.get('phase') or '').strip()   # 'mos' | 'ab'
        records = data.get('records')

        if not subject_id or not phase or not records:
            return jsonify({'ok': False, 'error': 'Missing fields'}), 400

        # [資安] phase 只允許 'mos' 或 'ab'
        if phase not in ('mos', 'ab'):
            return jsonify({'ok': False, 'error': 'Invalid phase'}), 400

        # [資安] 限制 records 必須是 list 且數量不能過多
        if not isinstance(records, list) or len(records) > MAX_RECORDS_PER_SAVE:
            return jsonify({'ok': False, 'error': f'Too many records (max {MAX_RECORDS_PER_SAVE})'}), 400

        filepath = _find_save_path(subject_id, phase)
        with open(filepath, 'w', encoding='utf-8') as f:
            for rec in records:
                f.write(json.dumps(rec, ensure_ascii=False) + '\n')

        print(f"[INFO] Saved {len(records)} records → {filepath}")
        return jsonify({'ok': True, 'file': os.path.basename(filepath)})
    except Exception as e:
        print(f"[ERROR] {e}")
        # [資安] 不要把內部錯誤訊息暴露給外部使用者
        return jsonify({'ok': False, 'error': 'Internal server error'}), 500


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
    # [資安] 只回傳前端需要的設定，不洩漏其他資訊
    config = json.load(open(CONFIG_PATH, encoding='utf-8'))
    safe_config = {
        'ab_test': config.get('ab_test', {}),
        'emotions': config.get('emotions', []),
        'sets_per_emotion': config.get('sets_per_emotion', 0),
        'models_per_set': config.get('models_per_set', 0)
    }
    return jsonify(safe_config)


# ── Audio files ───────────────────────────────────────────────────────────────

@app.route('/audio/<path:filepath>')
def serve_audio(filepath):
    # [資安防護] 直接將 DATA_DIR 交給 send_from_directory，Flask 內部會自動阻擋所有嘗試跑到 DATA_DIR 外面 (../) 的請求
    return send_from_directory(DATA_DIR, filepath)


@app.route('/data/<path:filepath>')
def serve_data(filepath):
    # [資安防護] 同上，交由 Flask 安全地提供檔案
    return send_from_directory(DATA_DIR, filepath)


# ── Static frontend ───────────────────────────────────────────────────────────

# [資安] 只允許存取的靜態檔案副檔名白名單
ALLOWED_STATIC_EXT = {'.html', '.css', '.js', '.json', '.png', '.jpg', '.jpeg', '.gif', '.svg', '.ico', '.woff', '.woff2', '.ttf'}

@app.route('/')
def index():
    return app.send_static_file('login.html')


@app.route('/<path:filename>')
def static_files(filename):
    # [資安] 阻擋存取 .py、.gitignore 等敏感檔案
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_STATIC_EXT:
        abort(404)
    return app.send_static_file(filename)


if __name__ == '__main__':
    # [資安] 正式部署時請關閉 debug 模式！debug=True 會讓任何人透過瀏覽器執行任意 Python 程式碼
    app.run(host='0.0.0.0', port=8000, debug=False)
