# webservice/test.py

import os
import csv
import dnn_wrapper

# 1) Compute project root (one level up from this file)
THIS_DIR     = os.path.dirname(__file__)
PROJECT_ROOT = os.path.abspath(os.path.join(THIS_DIR, os.pardir))

# 2) Paths to the model and CSV
MODEL_PATH = os.path.join(PROJECT_ROOT, "typing.dnn")
CSV_PATH   = os.path.join(PROJECT_ROOT, "database", "free-text.csv")

assert os.path.isfile(MODEL_PATH), f"No model at {MODEL_PATH}"
assert os.path.isfile(CSV_PATH),   f"No CSV at {CSV_PATH}"

print("Loading model from:", MODEL_PATH)
dnn_wrapper.load_model(MODEL_PATH)

# 3) Read CSV into a list of cleaned dicts
with open(CSV_PATH, newline="", encoding="utf-8") as f:
    reader = csv.DictReader(f, skipinitialspace=True)
    samples = [{k.strip(): v for k, v in row.items()} for row in reader]

# 4) Build one sample: first 3 rows → 3×5 matrix flattened to length 15
timing_keys = [
    "DU.key1.key1",
    "DD.key1.key2",
    "DU.key1.key2",
    "UD.key1.key2",
    "UU.key1.key2",
]

slice3 = samples[:3]
flat = []
for row in slice3:
    for key in timing_keys:
        flat.append(float(row[key]))

# 5) Run inference
rows, cols = 3, 5
predicted_index = dnn_wrapper.predict(flat, rows, cols)
print(f"Predicted class index: {predicted_index}")

# 6) Reconstruct the participant‑to‑class mapping
participants = []
for row in samples:
    pid = row["participant"].strip()
    if pid not in participants:
        participants.append(pid)

print("Class → participant mapping:", participants)

if 0 <= predicted_index < len(participants):
    predicted_participant = participants[predicted_index]
    print(f"That means participant: {predicted_participant}")
else:
    print("Predicted index is out of range for known participants.")
