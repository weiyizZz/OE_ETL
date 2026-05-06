from oral_notes.s1_extract.doc_loader import GoogleDriveLoader
from oral_notes.s1_extract.text_extractor import TextExtractor
from oral_notes.s1_extract.startingIDs_loader import get_starting_ids
from oral_notes.s2_transform.text2json_llm_transformer import Text2JsonTransformer
from oral_notes.s3_load.json2db_loader import JSON2DBLoader
from utils.html_viewer import show
import sqlite3


project_name = input("Enter project name: ").strip()
if not project_name:
    raise ValueError("Project name cannot be empty")
project_starting_date = input("Enter the starting date of the project: ").strip()
print(f"Running pipeline for project: {project_name}")
print("Enter Google Drive URLs (one per line, empty line to finish):")
urls = []
while True:
    url = input().strip()
    if not url:
        break
    urls.append(url)
"""
# for current test
project_name = "Helmond de Peel (2025)"
project_starting_date ="2025-01-01"
urls = ["https://docs.google.com/document/d/1jgVRKPK4bEfU0ARhlYNbiMmDTszwjBQloOhjBUWmJwI/edit?tab=t.0",
        "https://docs.google.com/document/d/1IMC2OpswPRnubdLWqNJStHWEjb9JTGhL/edit"]
"""
DB_PATH = "DB/oedb_baseline.db"
schema_path = "data/metadata_DB/schema.yaml"
prompt_path_text2json = "data/prompt_templates/prompt_text2json.yaml"
service_account_file="config/service_account_key.json"

file_loader = GoogleDriveLoader(service_account_file)
extractor = TextExtractor()

all_texts = []
all_drive_paths = []

for i, url in enumerate(urls):
    print(f"\n--- Loading and extracting text from file {i + 1} of {len(urls)} ---")
    result = file_loader.load(url)
    text = extractor.extract(result)
    all_texts.append(f"[Data source: {result['name']}]\n{text}")
    all_drive_paths.append(result['drive_path'])

combined_text = "\n\n---\n\n".join(all_texts)
combined_drive_paths = "|".join(all_drive_paths)
# Opens combined text in browser
show(combined_text, title="Extracted Text from Google Drive urls")
print("\n=== The combined text is shown in browser ===")

print("\n--- Loading IDs and calculating starting IDs from the database ---")
with sqlite3.connect(DB_PATH) as conn:
    cursor = conn.cursor()
    starting_ids = get_starting_ids(cursor, project_name, project_starting_date)
print("""\n--- Transforming the document into structured jsons, with tasks: "participants", "questions", "answers" ---""")
transformer_2json = Text2JsonTransformer(prompt_path=prompt_path_text2json, schema_path=schema_path,
                                   combined_text=combined_text, starting_ids=starting_ids, file_path_doc=combined_drive_paths,
                                         urls=urls)
transformed_results = transformer_2json.transform_3tasks()

print("""\n--- Loading each json into the database: oedb_baseline.db ---""")
loader = JSON2DBLoader(db_path=DB_PATH, project_id=starting_ids['projectID'], data_source=urls)
for task in ["participants", "questions", "answers"]:
    loader.load(transformed_results[task], task)

