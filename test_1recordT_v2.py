import json
import sqlite3
from utils.logger import get_logger
from oral_notes.s1_extract.doc_loader import GoogleDriveLoader
from oral_notes.s1_extract.text_extractor import TextExtractor
from oral_notes.s1_extract.startingIDs_loader import get_starting_ids
from oral_notes.s2_transform.participant_llm_reducer import ParticipantReducer
from oral_notes.s2_transform.text2json_llm_transformer import Text2JsonTransformer
from oral_notes.s3_load.json2db_loader import JSON2DBLoader

pipeline_type = "baseline_v2_1recordT_test"
DB_PATH = "DB/oedb_baseline_v2.db"
schema_path = "data/metadata_DB/schema_v2.yaml"
prompt_path_text2json = "data/prompt_templates/prompt_text2json_v2.yaml"
prompt_path_1recordT = "data/prompt_templates/prompt_1recordT_v2_3.yaml"
prompt_path_ParReducer = "data/prompt_templates/prompt_ParReducer.yaml"
service_account_file = "config/service_account_key.json"

logger = get_logger(__name__)

TARGET_NOTEGROUPS = list(range(1, 24))  # 1 to 23 inclusive

file_loader = GoogleDriveLoader(service_account_file)
extractor = TextExtractor()

for notegroup_id in TARGET_NOTEGROUPS:
    print(f"\n{'='*60}")
    print(f"notegroupID: {notegroup_id}")
    print('='*60)

    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT project_name, phase, note_url_QA, note_url_PARTICIPANT
            FROM notegroups
            WHERE notegroupID = ?
        """, (notegroup_id,))
        row = cursor.fetchone()
        if row is None:
            print(f"  [SKIP] No notegroup found with ID {notegroup_id}")
            continue
        project_name, phase, note_url_qa, note_url_participant = row
        starting_ids = get_starting_ids(cursor, project_name, phase)

    # --- Extract ---
    all_texts = {}
    all_drive_paths = {}
    for label, url in [("QA", note_url_qa), ("PARTICIPANT", note_url_participant)]:
        if not url:
            continue
        result = file_loader.load(url)
        text = extractor.extract(result)
        all_texts[label] = f"[Data source: {result['name']}]\n{text}"
        all_drive_paths[label] = result['drive_path']
    combined_drive_paths = "|".join(all_drive_paths.values())

    # --- Participant reduction ---
    has_participant = "PARTICIPANT" in all_texts
    if has_participant:
        reducer = ParticipantReducer(
            pipeline_type=pipeline_type,
            prompt_path_ParReducer=prompt_path_ParReducer,
            all_texts=all_texts,
            notegroup_id=notegroup_id,
        )
        combined_text = reducer.build_combined_text()
    else:
        combined_text = all_texts["QA"]

    # --- Transform: 1recordT only ---
    transformer = Text2JsonTransformer(
        prompt_path_text2json=prompt_path_text2json,
        prompt_path_1recordT=prompt_path_1recordT,
        schema_path=schema_path,
        combined_text=combined_text,
        starting_ids=starting_ids,
        file_path_doc=combined_drive_paths,
        notegroup_id=notegroup_id,
        has_participant=has_participant,
        pipeline_type=pipeline_type,
    )
    result_1recordT = transformer.transform_1task(task="1recordT")
    logger.info("=== Result: 1recordT (from %s) ===\n%s", notegroup_id, result_1recordT)

    # --- Load into notegroups_test ---
    loader = JSON2DBLoader(db_path=DB_PATH, project_id=starting_ids['projectID'], notegroup_id=notegroup_id)
    loader.load(result_1recordT, task="1recordT")

print("\nDone. Inspect results in notegroups.")