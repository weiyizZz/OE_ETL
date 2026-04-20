import yaml
import json

_schema_path = "../data/metadata_DB/schema.yaml"


def extract_json_template(schema_path: str, table_name: str) -> str:
    with open(schema_path) as f:
        schema = yaml.safe_load(f)
    columns = schema["tables"][table_name]["columns"]
    return json.dumps({col: "" for col in columns}, indent=2)
template = extract_json_template(_schema_path, "participants")
print(template)