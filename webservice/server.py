import os
import csv
from flask import Flask, render_template, request, jsonify
import dnn_wrapper
import threading
import logging

# ——— Logging setup ———
logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s - %(levelname)s - %(message)s')

# ——— Flask setup ———
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_DIR = os.path.join(BASE_DIR, "templates")
STATIC_DIR = os.path.join(BASE_DIR, "static")
DATA_DIR = os.path.join(BASE_DIR, "database")

app = Flask(
    __name__,
    template_folder=TEMPLATE_DIR,
    static_folder=STATIC_DIR
)
_csv_lock = threading.Lock()

# ——— Paths ———
MODEL_PATH = os.path.abspath(os.path.join(BASE_DIR, os.pardir, "typing.dnn"))
BASE_CSV = os.path.join(DATA_DIR, "free-text.csv")
EXT_CSV = os.path.join(DATA_DIR, "free-text-new.csv")

# ——— Load DNN once ———
try:
    if not os.path.isfile(MODEL_PATH):
        raise FileNotFoundError(f"Cannot find model at {MODEL_PATH}")
    dnn_wrapper.load_model(MODEL_PATH)
    logging.info(f"DNN model loaded successfully from {MODEL_PATH}")
except FileNotFoundError as e:
    logging.error(f"Error loading DNN model: {e}")
    # In a production setting, you might want to disable prediction
    # functionality or exit the application.
    # For now, we'll let the app start but prediction will fail.
except Exception as e:
    logging.error(f"An unexpected error occurred during DNN model loading: {e}")
    # Same consideration as above for production.

# ——— Bootstrap new CSV header if missing ———
if not os.path.isfile(EXT_CSV):
    try:
        os.makedirs(DATA_DIR, exist_ok=True)  # Ensure directory exists before creating file
        with open(BASE_CSV, newline="", encoding="utf-8") as fin, \
             open(EXT_CSV, "w", newline="", encoding="utf-8") as fout:
            writer = csv.writer(fout)
            writer.writerow(next(csv.reader(fin)))  # copy header
        logging.info(f"Created new extended CSV file: {EXT_CSV} with header from {BASE_CSV}")
    except Exception as e:
        logging.error(f"Error bootstrapping extended CSV file: {e}")
        # Non-critical error, the application can still function for history viewing.
        pass

def read_all_rows():
    """
    Read both original and appended CSVs,
    strip whitespace from header names, drop blank keys,
    and return list of clean dicts.
    """
    rows = []
    for path in (BASE_CSV, EXT_CSV):
        try:
            with open(path, newline="", encoding="utf-8") as f:
                raw = csv.DictReader(f, skipinitialspace=True)
                for r in raw:
                    # clean keys and drop empties
                    clean = {k.strip(): v for k, v in r.items() if k and k.strip()}
                    # only consider rows that actually have a participant and session
                    if "participant" in clean and "session" in clean:
                        rows.append(clean)
        except FileNotFoundError:
            logging.warning(f"CSV file not found: {path}")
            # If one CSV is missing, we can still try to read the other.
        except Exception as e:
            logging.error(f"Error reading CSV file {path}: {e}")
    return rows

# ——— Routes ———

@app.route("/")
def home():
    return render_template("biometric_test.html")

@app.route("/participants", methods=["GET"])
def list_participants():
    try:
        parts = sorted({r["participant"] for r in read_all_rows()})
        return jsonify(participants=parts)
    except Exception as e:
        logging.error(f"Error listing participants: {e}")
        return jsonify(error="Failed to retrieve participants"), 500

@app.route("/sessions", methods=["GET"])
def list_sessions():
    part = request.args.get("participant", "")
    try:
        sess = sorted({
            r["session"]
            for r in read_all_rows()
            if r["participant"] == part
        })
        return jsonify(sessions=sess)
    except Exception as e:
        logging.error(f"Error listing sessions for participant '{part}': {e}")
        return jsonify(error="Failed to retrieve sessions"), 500

@app.route("/history", methods=["GET"])
def view_history():
    part = request.args.get("participant", "")
    sess = request.args.get("session", "")
    try:
        hist = [
            r for r in read_all_rows()
            if r["participant"] == part and r["session"] == sess
        ]
        return jsonify(history=hist)
    except Exception as e:
        logging.error(f"Error viewing history for participant '{part}', session '{sess}': {e}")
        return jsonify(error="Failed to retrieve history"), 500

# ——— right after your other imports, before anything else ———
# ensure the database directory exists (moved here for clarity)
os.makedirs(DATA_DIR, exist_ok=True)

@app.route("/predict", methods=["POST"])
def predict():
    data = request.get_json(force=True)
    app.logger.debug("RAW PREDICT PAYLOAD: %r", data)

    # Input validation and sanitization
    part = data.get("participant", "").strip()
    if not part:
        return jsonify(error="Participant must be a non-empty string"), 400

    try:
        sess = int(data.get("session"))
        if sess <= 0:
            return jsonify(error="Session must be a positive integer"), 400
    except (TypeError, ValueError):
        return jsonify(error="Session must be an integer"), 400

    raw = data.get("digraphs", [])
    if not isinstance(raw, list) or not raw:
        return jsonify(error="Must send at least one digraph"), 400

    flat, digs = [], []
    for i, d in enumerate(raw):
        k1 = d.get("key1")
        k2 = d.get("key2")
        feats = d.get("features")
        if (
            isinstance(k1, str) and len(k1) == 1 and
            isinstance(k2, str) and len(k2) == 1 and
            isinstance(feats, list) and len(feats) == 5 and
            all(isinstance(f, (int, float)) for f in feats) # Validate feature types
        ):
            digs.append(d)
            flat.extend(feats)
        else:
            logging.warning(f"Invalid digraph at index {i}: {d}")

    if not digs:
        return jsonify(error="No valid character digraphs to process"), 400

    # Prediction with explicit error handling for the DNN
    predicted_index = None
    try:
        predicted_index = dnn_wrapper.predict(flat, len(digs), 5)
    except RuntimeError as e:
        logging.error(f"DNN prediction error (likely input size mismatch): {e}")
        return jsonify(error=f"Prediction failed due to input size mismatch: {e}"), 400
    except Exception as e:
        logging.error(f"Unexpected error during prediction: {e}")
        return jsonify(error="An unexpected error occurred during prediction"), 500

    # Append to CSV with better error handling
    rows_to_write = [
        [part, sess, d["key1"], d["key2"], *d["features"]]
        for d in digs
    ]
    saved = False
    try:
        with _csv_lock:
            with open(EXT_CSV, "a", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerows(rows_to_write)
            saved = True
            logging.info(f"Successfully appended {len(rows_to_write)} rows to {EXT_CSV} for participant '{part}', session '{sess}'")
    except IOError as e:
        logging.error(f"IOError while writing to CSV: {e}")
        return jsonify(error=f"Could not save typing data due to a file error: {e}"), 500
    except Exception as e:
        logging.exception("Unexpected error during CSV append")
        return jsonify(error=f"Could not save typing data due to an unexpected error: {e}"), 500

    return jsonify(
        predicted_index=predicted_index,
        predicted_user=part,
        saved=saved
    )

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=3000, debug=True)