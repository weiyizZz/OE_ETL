"""
measure_combined_text_length.py
--------------------------------
Measures the character length of the combined text for each notegroup (1–23),
mimicking the pipeline logic but WITHOUT calling the ParticipantReducer LLM.

For notegroups that have a PARTICIPANT file: the combined text is
    QA_text + "\n\n" + PARTICIPANT_text  (raw, pre-reduction)
For notegroups with only a QA file: the combined text is just QA_text.

Outputs: combined_text_lengths.csv
"""

import sqlite3
import csv
import sys
import os

# ── Adjust these paths to match your project layout ──────────────────────────
DB_PATH = "../DB/oedb_baseline_v3.db"
SERVICE_ACCOUNT_FILE = "../config/service_account_key.json"
OUTPUT_CSV = "combined_text_lengths.csv"
# ─────────────────────────────────────────────────────────────────────────────

from oral_notes.s1_extract.doc_loader import GoogleDriveLoader
from oral_notes.s1_extract.text_extractor import TextExtractor


def main():
    file_loader = GoogleDriveLoader(SERVICE_ACCOUNT_FILE)
    extractor = TextExtractor()

    rows = []

    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()

        for notegroup_id in range(1, 24):
            cursor.execute("""
                SELECT project_name, phase, note_url_QA, note_url_PARTICIPANT
                FROM notegroups
                WHERE notegroupID = ?
            """, (notegroup_id,))
            row = cursor.fetchone()

            project_name, phase, note_url_qa, note_url_participant = row
            print(f"\n[{notegroup_id}] {project_name} / phase {phase}")

            all_texts = {}
            char_lens = {}
            error_msg = None

            for label, url in [("QA", note_url_qa), ("PARTICIPANT", note_url_participant)]:
                if not url:
                    print(f"  Skipping {label}: no URL")
                    continue
                try:
                    result = file_loader.load(url)
                    text = extractor.extract(result)
                    full_text = f"[Data source: {result['name']}]\n{text}"
                    all_texts[label] = full_text
                    char_lens[label] = len(full_text)
                    print(f"  {label}: {char_lens[label]:,} chars")
                except Exception as e:
                    print(f"  {label} failed: {e}")
                    error_msg = str(e)

            # Replicate pipeline logic: combine texts (without LLM reduction)
            if "QA" in all_texts and "PARTICIPANT" in all_texts:
                combined = all_texts["QA"] + "\n\n" + all_texts["PARTICIPANT"]
            elif "QA" in all_texts:
                combined = all_texts["QA"]
            elif "PARTICIPANT" in all_texts:
                combined = all_texts["PARTICIPANT"]
            else:
                combined = ""

            combined_len = len(combined) if combined else None
            print(f"  → Combined: {combined_len:,} chars" if combined_len else "  → Combined: N/A")

            rows.append({
                "notegroupID": notegroup_id,
                "project_name": project_name,
                "phase": phase,
                "has_QA": "QA" in all_texts,
                "has_PARTICIPANT": "PARTICIPANT" in all_texts,
                "char_len_QA": char_lens.get("QA"),
                "char_len_PARTICIPANT": char_lens.get("PARTICIPANT"),
                "char_len_combined": combined_len,
                "error": error_msg,
            })

    # Write CSV
    fieldnames = [
        "notegroupID", "project_name", "phase",
        "has_QA", "has_PARTICIPANT",
        "char_len_QA", "char_len_PARTICIPANT", "char_len_combined",
        "error",
    ]
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"\n✓ Done. Results saved to: {OUTPUT_CSV}")


if __name__ == "__main__":
    main()