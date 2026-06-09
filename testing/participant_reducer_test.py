from oral_notes.s1_extract.doc_loader import GoogleDriveLoader
from oral_notes.s1_extract.text_extractor import TextExtractor
from oral_notes.s1_extract.startingIDs_loader import get_starting_ids
from oral_notes.s2_transform.participant_llm_reducer import ParticipantReducer
from oral_notes.s2_transform.text2json_llm_transformer import Text2JsonTransformer
from oral_notes.s3_load.json2db_loader import JSON2DBLoader
from utils.html_viewer import show
import sqlite3


DB_PATH = "../DB/oedb_baseline.db"
schema_path = "data/metadata_DB/schema.yaml"
prompt_path_text2json = "data/prompt_templates/prompt_text2json.yaml"
prompt_path_1recordT = "data/prompt_templates/prompt_1recordT.yaml"
prompt_path_ParReducer = "../data/prompt_templates/prompt_ParReducer.yaml"
service_account_file="../config/service_account_key.json"

notegroup_id = int(input("Enter notegroupID: ").strip())

with sqlite3.connect(DB_PATH) as conn:
    cursor = conn.cursor()
    cursor.execute("""
        SELECT project_name, phase, note_url_QA, note_url_PARTICIPANT
        FROM notegroups
        WHERE notegroupID = ?
    """, (notegroup_id,))
    row = cursor.fetchone()
    if row is None:
        raise ValueError(f"No notegroup found with ID {notegroup_id}")
    project_name, phase, note_url_qa, note_url_participant = row
    starting_ids = get_starting_ids(cursor, project_name, phase)

print(f"Running pipeline for project: {project_name}, phase: {phase}")

file_loader = GoogleDriveLoader(service_account_file)
extractor = TextExtractor()

all_texts = {}
all_drive_paths = {}
for label, url in [("QA", note_url_qa), ("PARTICIPANT", note_url_participant)]:
    if not url:
        print(f"\n--- Skipping {label}: no URL ---")
        continue
    print(f"\n--- Loading and extracting text from {label} ---")
    result = file_loader.load(url)
    text = extractor.extract(result)
    all_texts[label] = f"[Data source: {result['name']}]\n{text}"
    all_drive_paths[label] = result['drive_path']
combined_drive_paths = "|".join(all_drive_paths.values())
if "PARTICIPANT" in all_texts:
    print("\n--- Running participant reduction ---")
    reducer = ParticipantReducer(
        prompt_path_ParReducer=prompt_path_ParReducer,
        all_texts=all_texts,
        notegroup_id=notegroup_id,
    )
    combined_text = reducer.build_combined_text()
else:
    combined_text = all_texts["QA"]

show(combined_text, title=f"notegroup: {notegroup_id} | Combine text after participant reducing for ")