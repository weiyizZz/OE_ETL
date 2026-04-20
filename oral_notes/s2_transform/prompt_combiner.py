import yaml
import json


class PromptCombiner:

    VALID_TASKS = ("participants", "questions", "answers")

    def __init__(self, schema_path: str):
        self.schema_path = schema_path
        self.schema = self._load_schema()

    # ── Private loaders ────────────────────────────────────────────────────────

    def _load_schema(self) -> dict:
        with open(self.schema_path) as f:
            return yaml.safe_load(f)

    @staticmethod
    def _load_prompts_user(prompt_path: str) -> dict:
        with open(prompt_path) as f:
            return yaml.safe_load(f)["user"]

    # ── Public loaders ────────────────────────────────────────────────────────

    @staticmethod
    def load_prompts_system(prompt_path: str) -> str:
        with open(prompt_path) as f:
            return yaml.safe_load(f)["system"]

    # ── Schema helpers ─────────────────────────────────────────────────────────

    def extract_json_template(self, table_name: str) -> str:
        columns = self.schema["tables"][table_name]["columns"]
        return json.dumps({col: "" for col in columns}, indent=2)

    def extract_schema_metadata(self, table_name: str) -> str:
        columns = self.schema["tables"][table_name]["columns"]
        # render with indent but compact any list values
        def compact_lists(obj):
            if isinstance(obj, dict):
                return {k: compact_lists(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                # render list as single line
                return json.dumps(obj, ensure_ascii=False)
            return obj
        compacted = compact_lists(columns)
        return json.dumps(compacted, ensure_ascii=False)

    def to_json_schema(self, table_name: str) -> dict:
        """
        Convert a table definition from self.schema (loaded YAML) into
        an OpenAI-compatible JSON Schema object, wrapped in response_format.
        """
        TYPE_MAP = {
            "INTEGER": "integer",
            "Text": "string",
            "JSONB": "object",
            "Date": "string",
        }

        table_def = self.schema["tables"][table_name]
        columns = table_def["columns"]

        properties = {}
        required = []

        for col_name, col_def in columns.items():
            json_type = col_def.get("json_schema_type") or TYPE_MAP.get(col_def["type"], "string")
            nullable = col_def.get("nullable", True)

            # object types require additionalProperties: false in strict mode
            type_schema = {"type": json_type}
            if json_type == "object":
                type_schema["additionalProperties"] = False
            elif json_type == "array":
                items_type = col_def.get("json_schema_items", "string")  # default to string
                type_schema["items"] = {"type": items_type}

            if nullable:
                properties[col_name] = {
                    "anyOf": [
                        type_schema,
                        {"type": "null"}
                    ]
                }
            else:
                properties[col_name] = type_schema
            required.append(col_name)

        schema = {
            "type": "object",
            "properties": {
                table_name: {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": properties,
                        "required": required,
                        "additionalProperties": False
                    }
                }
            },
            "required": [table_name],
            "additionalProperties": False
        }

        return {
            "type": "json_schema",
            "json_schema": {
                "name": table_name,
                "strict": True,
                "schema": schema
            }
        }

    # ── Extra info resolvers ───────────────────────────────────────────────────

    def _extra_info_participants(self, prompts: dict, starting_ids: dict) -> str:
        return prompts["extra_info"]["participants"].format(
            starting_participantID_DB=starting_ids["participantID"]
        )

    def _extra_info_questions(self, prompts: dict, starting_ids: dict) -> str:
        return prompts["extra_info"]["questions"].format(
            starting_questionID_DB=starting_ids["questionID"]
        )

    def _extra_info_answers(
        self,
        prompts: dict,
        starting_ids: dict,
        file_path_doc: str,
        output_reduced_participants_pasttask: str,
        output_reduced_questions_pasttask: str
    ) -> str:
        if file_path_doc is None:
            raise ValueError("file_path_doc is required for task 'answers'")
        if output_reduced_participants_pasttask is None:
            raise ValueError("output_reduced_participants_pasttask is required for task 'answers'")
        if output_reduced_questions_pasttask is None:
            raise ValueError("output_reduced_questions_pasttask is required for task 'answers'")

        return prompts["extra_info"]["answers"].format(
            starting_answerID_DB=starting_ids["answerID"],
            file_path_doc=file_path_doc,
            output_reduced_participants_pasttask=output_reduced_participants_pasttask,
            output_reduced_questions_pasttask=output_reduced_questions_pasttask
        )

    # ── Main methods ────────────────────────────────────────────────────────────

    def build_prompt_user_text2json(
        self,
        prompt_path: str,
        task: str,
        text_doc: str,
        starting_ids: dict,
        file_path_doc: str = None,
        output_reduced_participants_pasttask: str = None,
        output_reduced_questions_pasttask: str = None
    ) -> str:

        prompts = self._load_prompts_user(prompt_path)

        if task not in self.VALID_TASKS:
            raise ValueError(f"task must be one of {self.VALID_TASKS}, got '{task}'")

        if task == "participants":
            extra_info = self._extra_info_participants(prompts, starting_ids)
        elif task == "questions":
            extra_info = self._extra_info_questions(prompts, starting_ids)
        elif task == "answers":
            extra_info = self._extra_info_answers(
                prompts,
                starting_ids,
                file_path_doc,
                output_reduced_participants_pasttask,
                output_reduced_questions_pasttask
            )

        extra_note = prompts["extra_note"].get(task, "")

        return prompts["base"].format(
            text_doc=text_doc,
            task=task,
            json_template_task=self.extract_json_template(task),
            extra_info_task=extra_info,
            schema_metadata_task=self.extract_schema_metadata(task),
            extra_note_task=extra_note
        )

