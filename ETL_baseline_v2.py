from oral_notes.s1_extract.doc_loader import GoogleDriveLoader
from oral_notes.s1_extract.text_extractor import TextExtractor
from oral_notes.s1_extract.startingIDs_loader import get_starting_ids
from oral_notes.s2_transform.participant_llm_reducer import ParticipantReducer
from oral_notes.s2_transform.text2json_llm_transformer import Text2JsonTransformer
from oral_notes.s3_load.json2db_loader import JSON2DBLoader
from utils.html_viewer import show
import sqlite3


pipeline_type="baseline_v2"
DB_PATH = "DB/oedb_baseline_v2.db"
schema_path = "data/metadata_DB/schema_v2.yaml"
prompt_path_text2json = "data/prompt_templates/prompt_text2json-v2.yaml"
prompt_path_1recordT = "data/prompt_templates/prompt_1recordT.yaml"
prompt_path_ParReducer = "data/prompt_templates/prompt_ParReducer.yaml"
service_account_file="config/service_account_key.json"

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

has_participant = "PARTICIPANT" in all_texts
if has_participant:
    print("\n--- Running participant reduction ---")
    reducer = ParticipantReducer(
        pipeline_type=pipeline_type,
        prompt_path_ParReducer=prompt_path_ParReducer,
        all_texts=all_texts,
        notegroup_id=notegroup_id,
    )
    combined_text = reducer.build_combined_text()
else:
    combined_text = all_texts["QA"]

print("""\n--- Transforming the document into structured jsons, with tasks: "participants", "questions", "answers", "1recordT" ---""")
transformer_2json = Text2JsonTransformer(prompt_path_text2json=prompt_path_text2json,
                                         prompt_path_1recordT=prompt_path_1recordT,
                                         schema_path=schema_path, combined_text=combined_text,
                                         starting_ids=starting_ids, file_path_doc=combined_drive_paths,
                                         notegroup_id=notegroup_id, has_participant=has_participant,
                                         pipeline_type=pipeline_type)
transformed_results = transformer_2json.transform_4tasks()

print("""\n--- Loading each json into the database: oedb_baseline.db ---""")
loader = JSON2DBLoader(db_path=DB_PATH, project_id=starting_ids['projectID'], notegroup_id=notegroup_id)
for task in ["participants", "questions", "answers", "1recordT"]:
    loader.load(transformed_results[task], task)

