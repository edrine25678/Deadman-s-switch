"""
calibrate_face.py  —  Capture multiple reference faces for facial recognition

Usage:
  python calibrate_face.py                  # interactive webcam capture
  python calibrate_face.py photo1.jpg ...   # add faces from image files
  python calibrate_face.py *.jpg            # add all jpgs in folder

All encodings are saved as a list to reference_face.pkl.
Multiple runs ADD to the existing set — you never lose previous captures.
"""

import os, sys, pickle, cv2
import face_recognition

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUT_PATH = os.path.join(BASE_DIR, "reference_face.pkl")

# ── Load existing encodings ───────────────────────────────────────
encodings = []
if os.path.exists(OUT_PATH):
    try:
        with open(OUT_PATH, "rb") as f:
            existing = pickle.load(f)
        if isinstance(existing, list):
            encodings = existing
        else:
            encodings = [existing]
        print(f"  Loaded {len(encodings)} existing reference(s)")
    except Exception as e:
        print(f"  Warning: could not load existing references ({e})")

# ── Image-file mode ───────────────────────────────────────────────
if len(sys.argv) > 1:
    image_paths = [a for a in sys.argv[1:] if a.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.tiff'))]
    if not image_paths:
        print("  No valid image files found. Supported: .png .jpg .jpeg .bmp .tiff")
        sys.exit(1)
    added = 0
    for path in image_paths:
        if not os.path.exists(path):
            print(f"  Skipping (not found): {path}")
            continue
        img = face_recognition.load_image_file(path)
        new_encs = face_recognition.face_encodings(img)
        if not new_encs:
            print(f"  No face in: {os.path.basename(path)}")
            continue
        encodings.append(new_encs[0])
        added += 1
        print(f"  Added from {os.path.basename(path)}  ({len(encodings)} total)")
    with open(OUT_PATH, "wb") as f:
        pickle.dump(encodings, f)
    print(f"\n  Done. {added} face(s) added. Total: {len(encodings)} reference(s).")
    sys.exit(0)

# ── Interactive webcam mode ───────────────────────────────────────
print("""
  Instructions:
  • Press SPACE to capture your face from the current angle
  • Move your head or adjust lighting between captures
  • Captures ADD to existing references (previous ones kept)
  • Press ENTER when done to save
  • Press ESC to cancel
  Starting camera...
""")

cap = cv2.VideoCapture(0)
if not cap.isOpened():
    print("[ERROR] No webcam found")
    sys.exit(1)

while True:
    ret, frame = cap.read()
    if not ret:
        continue

    display = frame.copy()
    status = f"Stored: {len(encodings)}   SPACE: capture   ENTER: save   ESC: cancel"
    cv2.putText(display, status, (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 0), 2)

    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    face_locs = face_recognition.face_locations(rgb)
    for (top, right, bottom, left) in face_locs:
        cv2.rectangle(display, (left, top), (right, bottom), (0, 255, 0), 2)

    cv2.imshow("Face Calibration", display)
    key = cv2.waitKey(1) & 0xFF

    if key == 27:  # ESC
        print("\n  Cancelled.")
        break

    if key == 13:  # ENTER
        if len(encodings) == 0:
            print("\n  No faces captured yet.")
            continue
        with open(OUT_PATH, "wb") as f:
            pickle.dump(encodings, f)
        print(f"\n  Saved {len(encodings)} face(s) to {OUT_PATH}")
        break

    if key == 32:  # SPACE
        new_encs = face_recognition.face_encodings(rgb)
        if not new_encs:
            print("  No face detected — adjust position")
            continue
        encodings.append(new_encs[0])
        print(f"  Captured ({len(encodings)})")

cap.release()
cv2.destroyAllWindows()

if encodings:
    print(f"\n  Done. Total references: {len(encodings)}.")
else:
    sys.exit(1)
