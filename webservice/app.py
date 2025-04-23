import os
import csv
from flask import Flask, render_template, request, jsonify
import threading
import logging

# --- Logging setup ---
logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s - %(levelname)s - %(message)s')

# --- Flask setup ---
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

# --- Paths ---
# It's often better to use environment variables or config files for paths
BASE_CSV = os.path.join(DATA_DIR, "free-text.csv")
EXT_CSV = os.path.join(DATA_DIR, "database.csv")

# --- Load DNN once ---

    # Depending on the error, you might still set _dnn_model_loaded = False

# --- Ensure Database Directory and Bootstrap new CSV ---
try:
    os.makedirs(DATA_DIR, exist_ok=True)
    if not os.path.isfile(EXT_CSV) and os.path.isfile(BASE_CSV):
        with open(BASE_CSV, newline="", encoding="utf-8") as fin, \
             open(EXT_CSV, "w", newline="", encoding="utf-8") as fout:
            reader = csv.reader(fin)
            writer = csv.writer(fout)
            try:
                header = next(reader)
                writer.writerow(header)
                logging.info(f"Created new extended CSV file: {EXT_CSV} with header from {BASE_CSV}")
            except StopIteration:
                logging.warning(f"Base CSV {BASE_CSV} is empty, cannot copy header.")
            except Exception as e:
                 logging.error(f"Error reading header from {BASE_CSV}: {e}")

    elif not os.path.isfile(EXT_CSV):
         # If base also doesn't exist, create EXT_CSV with a default header maybe?
         # Or log a warning that no data source exists.
         logging.warning(f"Extended CSV {EXT_CSV} not found and Base CSV {BASE_CSV} not found or couldn't be read. New data cannot be saved without a header.")
         # Consider creating EXT_CSV with a default header if appropriate:
         # with open(EXT_CSV, "w", newline="", encoding="utf-8") as fout:
         #    writer = csv.writer(fout)
         #    writer.writerow(["participant", "session", "key1", "key2", "feat1", "feat2", "feat3", "feat4", "feat5"]) # Example header
         #    logging.info(f"Created new extended CSV file: {EXT_CSV} with a default header.")


except Exception as e:
    logging.error(f"Error during directory/CSV setup: {e}")
    # This might prevent saving new data.

def read_all_rows():
    """
    Read both original and appended CSVs, clean headers/rows, return list of dicts.
    Handles potential FileNotFoundError and other reading errors gracefully.
    """
    rows = []
    required_keys = {"participant", "session"} # Minimum keys for a row to be useful

    for path in (BASE_CSV, EXT_CSV):
        if not os.path.isfile(path):
            logging.debug(f"CSV file not found, skipping: {path}")
            continue
        try:
            with open(path, newline="", encoding="utf-8") as f:
                # Use DictReader for easier access, handle potential empty file
                try:
                    # Need to check if file is empty before creating DictReader
                    first_char = f.read(1)
                    if not first_char:
                        logging.warning(f"CSV file is empty: {path}")
                        continue
                    f.seek(0) # Reset file pointer
                    reader = csv.DictReader(f, skipinitialspace=True)
                    header = reader.fieldnames
                    if not header:
                         logging.warning(f"CSV file has no header: {path}")
                         continue

                    for r in reader:
                        # Clean keys (strip whitespace) and drop keys that become empty
                        clean_row = {k.strip(): v for k, v in r.items() if k and k.strip()}
                        # Drop rows that don't have the essential keys or have None/empty values for them
                        if required_keys.issubset(clean_row.keys()) and \
                           all(clean_row[key] for key in required_keys):
                            rows.append(clean_row)
                        else:
                            logging.debug(f"Skipping incomplete row in {path}: {r}")
                except Exception as read_err:
                     logging.error(f"Error reading or processing CSV file {path}: {read_err}")

        except FileNotFoundError:
            # This check is redundant due to os.path.isfile above, but kept for clarity
            logging.warning(f"CSV file not found during read attempt: {path}")
        except Exception as e:
            logging.error(f"Unexpected error opening or reading CSV file {path}: {e}")

    # Deduplicate based on participant, session, and maybe other key features if necessary
    # This simple deduplication assumes row order matters (keeps first encountered)
    # For more complex scenarios, adjust the key for uniqueness.
    # Example: unique_key = lambda r: (r['participant'], r['session'], r['key1'], r['key2'], tuple(r.get(f) for f in feature_keys))
    # seen = set()
    # unique_rows = []
    # for row in rows:
    #    key = (row['participant'], row['session']) # Simple example
    #    if key not in seen:
    #        unique_rows.append(row)
    #        seen.add(key)
    # return unique_rows
    # For now, returning all rows as before:
    return rows


# --- Routes ---

@app.route("/")
def home():
    """Renders the main HTML page."""
    return render_template("biometric_test.html")

@app.route("/participants", methods=["GET"])
def list_participants():
    """Returns a sorted list of unique participant IDs."""
    try:
        all_rows = read_all_rows()
        # Use a set for uniqueness, filter out potential None or empty strings
        participants = sorted({r["participant"] for r in all_rows if r.get("participant")})
        return jsonify(data={"participants": participants})
    except Exception as e:
        logging.error(f"Error listing participants: {e}", exc_info=True)
        return jsonify(error="Failed to retrieve participant list"), 500

@app.route("/sessions", methods=["GET"])
def list_sessions():
    """Returns a sorted list of unique session IDs for a given participant."""
    participant_id = request.args.get("participant", "").strip()
    if not participant_id:
        return jsonify(error="Participant ID is required"), 400

    try:
        all_rows = read_all_rows()
        # Filter, convert to int for sorting (handle potential errors), ensure uniqueness
        sessions = set()
        for r in all_rows:
            if r.get("participant") == participant_id and r.get("session"):
                try:
                    sessions.add(int(r["session"]))
                except (ValueError, TypeError):
                    logging.warning(f"Invalid session format '{r['session']}' for participant '{participant_id}'")

        sorted_sessions = sorted(list(sessions))
        return jsonify(data={"sessions": sorted_sessions})
    except Exception as e:
        logging.error(f"Error listing sessions for participant '{participant_id}': {e}", exc_info=True)
        return jsonify(error="Failed to retrieve session list"), 500

@app.route("/history", methods=["GET"])
def view_history():
    """Returns typing history data for a specific participant and session."""
    participant_id = request.args.get("participant", "").strip()
    session_str = request.args.get("session", "").strip()

    if not participant_id:
        return jsonify(error="Participant ID is required"), 400
    if not session_str:
        return jsonify(error="Session ID is required"), 400

    try:
        session_id = int(session_str) # Validate session is an integer
    except ValueError:
        return jsonify(error="Session ID must be an integer"), 400

    try:
        all_rows = read_all_rows()
        history_data = [
            r for r in all_rows
            if r.get("participant") == participant_id and r.get("session") == session_str # Compare as string as stored in CSV
        ]
        # Ensure feature keys exist before sending, maybe rename for consistency?
        # Assuming the JS expects specific keys like "DU.key1.key1" etc.
        # If CSV headers are just feat1, feat2... map them here or adjust JS.
        # Let's assume CSV has columns: participant, session, key1, key2, DU.key1.key1, DD.key1.key2, DU.key1.key2, UD.key1.key2, UU.key1.key2
        # (Adjust if your CSV headers are different)

        return jsonify(data={"history": history_data})
    except Exception as e:
        logging.error(f"Error retrieving history for participant '{participant_id}', session '{session_str}': {e}", exc_info=True)
        return jsonify(error="Failed to retrieve history data"), 500

@app.route("/predict", methods=["POST"])
def predict():
    """Receives typing data, predicts user, saves data, returns result."""
    if not _dnn_model_loaded:
        logging.warning("Prediction attempt failed: DNN Model not loaded.")
        return jsonify(error="Prediction model is not available"), 503 # Service Unavailable

    try:
        data = request.get_json(force=True) # force=True can mask invalid JSON, consider removing
        if not data:
             return jsonify(error="Invalid JSON payload"), 400
    except Exception as e:
        logging.error(f"Failed to parse JSON payload: {e}")
        return jsonify(error="Invalid JSON payload"), 400

    app.logger.debug("RAW PREDICT PAYLOAD: %r", data)

    # --- Input Validation ---
    participant_id = data.get("participant", "").strip()
    if not participant_id:
        return jsonify(error="Participant must be a non-empty string"), 400

    try:
        session_id = int(data.get("session"))
        if session_id <= 0:
            return jsonify(error="Session must be a positive integer"), 400
    except (TypeError, ValueError, KeyError):
        return jsonify(error="Session must be provided as a positive integer"), 400

    raw_digraphs = data.get("digraphs", [])
    if not isinstance(raw_digraphs, list) or not raw_digraphs:
        return jsonify(error="Must send a non-empty list of digraphs"), 400

    valid_digraphs = []
    flat_features = []
    expected_feature_count = 5 # Should match DNN input expectation per digraph

    for i, d in enumerate(raw_digraphs):
        if not isinstance(d, dict):
             logging.warning(f"Invalid digraph format (not a dict) at index {i}: {d}")
             continue
        k1 = d.get("key1")
        k2 = d.get("key2")
        features = d.get("features")

        # More specific validation
        if (
            isinstance(k1, str) and len(k1) == 1 and # Single character keys
            isinstance(k2, str) and len(k2) == 1 and
            isinstance(features, list) and len(features) == expected_feature_count and
            all(isinstance(f, (int, float)) for f in features) and # Check feature types
            all(f is not None for f in features) # Ensure no None values
        ):
            valid_digraphs.append(d)
            flat_features.extend(features)
        else:
            logging.warning(f"Invalid digraph data at index {i}: {d}. Skipping.")

    if not valid_digraphs:
        return jsonify(error="No valid digraphs found in the provided data"), 400

    num_digraphs = len(valid_digraphs)
    num_features_per_digraph = expected_feature_count

    # --- Prediction ---
    predicted_index = None # Or some default value indicating prediction wasn't possible
    prediction_error = None
    try:
        # Make sure the dnn_wrapper.predict expects these arguments
        #predicted_index = dnn_wrapper.predict(flat_features, num_digraphs, num_features_per_digraph)
        logging.info(f"Prediction successful for '{participant_id}' session '{session_id}'. Predicted index: {predicted_index}")
        # Note: The original code returned participant_id as predicted_user.
        # This seems wrong. Prediction should return an index or ID based on the *model*,
        # not just echo the input participant. We'll return the raw index for now.
        # You might need a mapping from index to user ID later.
    except RuntimeError as e:
        logging.error(f"DNN prediction runtime error (likely input size mismatch): {e}")
        prediction_error = f"Prediction failed: Input data structure mismatch ({e})."
    except Exception as e:
        logging.exception(f"Unexpected error during prediction for '{participant_id}' session '{session_id}'") # Log full traceback
        prediction_error = "An unexpected error occurred during prediction."

    if prediction_error:
         # Decide if you want to save data even if prediction fails
         # return jsonify(error=prediction_error), 500 # Option 1: Fail fast
         pass # Option 2: Continue to save data, report prediction error later

    # --- Append to CSV ---
    # Assuming CSV header: participant, session, key1, key2, feat1, feat2, feat3, feat4, feat5
    # Adjust column order if your CSV is different
    rows_to_write = [
        [participant_id, session_id, d["key1"], d["key2"], *d["features"]]
        for d in valid_digraphs
    ]
    saved_successfully = False
    save_error = None
    try:
        # Ensure the target CSV has a header before appending
        if not os.path.isfile(EXT_CSV) or os.path.getsize(EXT_CSV) == 0:
             raise FileNotFoundError(f"Cannot append: Target CSV {EXT_CSV} is missing or empty.")

        with _csv_lock: # Acquire lock for thread safety
            with open(EXT_CSV, "a", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerows(rows_to_write)
            saved_successfully = True
            logging.info(f"Successfully appended {len(rows_to_write)} rows to {EXT_CSV} for participant '{participant_id}', session '{session_id}'")
    except FileNotFoundError as e:
        logging.error(f"File not found error while writing to CSV: {e}")
        save_error = f"Could not save typing data: Target file {EXT_CSV} not found or inaccessible."
    except IOError as e:
        logging.error(f"IOError while writing to CSV {EXT_CSV}: {e}")
        save_error = f"Could not save typing data due to a file error: {e}"
    except Exception as e:
        logging.exception(f"Unexpected error during CSV append for '{participant_id}' session '{session_id}'") # Log full traceback
        save_error = f"Could not save typing data due to an unexpected error."


    # --- Response ---
    response_data = {
        "predicted_index": predicted_index,
        # "predicted_user": participant_id, # Echoing input user seems less useful than index
        "saved": saved_successfully,
        "digraphs_processed": len(valid_digraphs),
        "digraphs_received": len(raw_digraphs),
    }
    if prediction_error:
        response_data["prediction_error"] = prediction_error
    if save_error:
         response_data["save_error"] = save_error # Add save error to response

    # If there was a critical error (like prediction or saving), maybe return 500
    if prediction_error or save_error:
         # Decide if partial success is okay (200) or if it warrants an error status (500)
         # Let's return 207 Multi-Status if some parts worked and some failed
         status_code = 207 if saved_successfully != (prediction_error is None) else (200 if saved_successfully and prediction_error is None else 500)
         if status_code == 500:
              # Ensure a top-level error message exists if returning 500
              final_error = prediction_error or save_error or "Prediction or saving failed."
              return jsonify(error=final_error, details=response_data), status_code

    # Return 200 OK if prediction succeeded and data was saved, or 207 if mixed results
    return jsonify(data=response_data), status_code if 'status_code' in locals() else 200


if __name__ == "__main__":
    # Use debug=False in production
    # Consider using a proper WSGI server like Gunicorn or Waitress
    app.run(host="127.0.0.1", port=3000, debug=True)