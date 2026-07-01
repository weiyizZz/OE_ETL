import yaml
import json


class PromptCombiner:

    EVALUATOR_PK_EXCLUDE = {
        "participants": "participantID",
        "questions": "questionID",
        "answers": "answerID",
    }

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

    @staticmethod
    def load_prompts_system(prompt_path: str) -> str:
        with open(prompt_path) as f:
            return yaml.safe_load(f)["system"]

    # ── Schema helpers ─────────────────────────────────────────────────────────

    def extract_json_template(self, table_name: str) -> str:
        columns = self.schema["tables"][table_name]["columns"]
        return json.dumps({col: "" for col in columns}, indent=2)

    def extract_schema_metadata(self, table_name: str, exclude: str | None = None) -> str:
        columns = self.schema["tables"][table_name]["columns"]
        if exclude:
            columns = {k: v for k, v in columns.items() if k != exclude}
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

        SINGLE_RECORD_TABLES = {"1recordT"}
        single_record = table_name in SINGLE_RECORD_TABLES

        table_def = self.schema["tables"][table_name]
        columns = table_def["columns"]

        properties = {}
        required = []

        for col_name, col_def in columns.items():
            json_type = col_def.get("json_schema_type") or TYPE_MAP.get(col_def["type"], "string")
            nullable = col_def.get("nullable", True)

            type_schema = {"type": json_type}
            if json_type == "object":
                type_schema["additionalProperties"] = False
            elif json_type == "array":
                items_type = col_def.get("json_schema_items", "string")
                type_schema["items"] = {"type": items_type}

            if nullable:
                properties[col_name] = {"anyOf": [type_schema, {"type": "null"}]}
            else:
                properties[col_name] = type_schema
            required.append(col_name)

        row_schema = {
            "type": "object",
            "properties": properties,
            "required": required,
            "additionalProperties": False,
        }

        if single_record:
            schema = row_schema
        else:
            schema = {
                "type": "object",
                "properties": {
                    table_name: {
                        "type": "array",
                        "items": row_schema,
                    }
                },
                "required": [table_name],
                "additionalProperties": False,
            }

        return {
            "type": "json_schema",
            "json_schema": {
                "name": table_name,
                "strict": True,
                "schema": schema,
            },
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
        output_reduced_participants_pasttask: str,
        output_reduced_questions_pasttask: str
    ) -> str:
        if output_reduced_participants_pasttask is None:
            raise ValueError("output_reduced_participants_pasttask is required for task 'answers'")
        if output_reduced_questions_pasttask is None:
            raise ValueError("output_reduced_questions_pasttask is required for task 'answers'")

        return prompts["extra_info"]["answers"].format(
            starting_answerID_DB=starting_ids["answerID"],
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
        output_reduced_participants_pasttask: str = None,
        output_reduced_questions_pasttask: str = None,
        has_participant: bool = False
    ) -> str:

        prompts = self._load_prompts_user(prompt_path)

        if task == "participants":
            extra_info = self._extra_info_participants(prompts, starting_ids)
        elif task == "questions":
            extra_info = self._extra_info_questions(prompts, starting_ids)
        elif task == "answers":
            extra_info = self._extra_info_answers(
                prompts,
                starting_ids,
                output_reduced_participants_pasttask,
                output_reduced_questions_pasttask
            )

        if task == "participants" and not has_participant:
            extra_note = ""
        else:
            extra_note = prompts["extra_note"].get(task, "")

        return prompts["base"].format(
            text_doc=text_doc,
            task_mapped=prompts["task_mapped"][task],
            json_template_task=self.extract_json_template(task),
            extra_info_task=extra_info,
            schema_metadata_task=self.extract_schema_metadata(task),
            extra_note_task=extra_note
        )


    def build_prompt_user_1recordT(
            self,
            prompt_path: str,
            file_path_doc: str,
            text_doc: str
        ) -> str:
        prompts = self._load_prompts_user(prompt_path)
        task = "1recordT"

        return prompts["base"].format(
            text_doc=text_doc,
            file_path_doc = file_path_doc,
            json_template_task=self.extract_json_template(task),
            schema_metadata_task=self.extract_schema_metadata(task)
        )

    def build_prompt_user_evaluator(
            self,
            prompt_path: str,
            task: str,
            file_path_doc: str,
            text_doc: str,
            json_record: str
    ) -> str:
        prompts = self._load_prompts_user(prompt_path)

        extra_note_extraction_task = prompts.get("extra_note_extraction", {}).get(task, "")
        extra_note_extraction_task = extra_note_extraction_task.format(file_path_doc=file_path_doc)

        extra_note_evaluation_task = prompts.get("extra_note_evaluation", {}).get(task, "")

        return prompts["base"].format(
            text_doc=text_doc,
            extra_note_extraction_task=extra_note_extraction_task,
            json_record=json_record,
            schema_metadata_task=self.extract_schema_metadata(
                task, exclude=self.EVALUATOR_PK_EXCLUDE.get(task)
            ),
            extra_note_evaluation_task=extra_note_evaluation_task
        )

    def build_pass_placeholder(self, table_name: str) -> str:
        """
        Build a JSON object matching the schema for `table_name` (as produced
        by to_json_schema), with every field's value set to the literal
        string "pass". Used by the refiner as a machine-checkable, schema-valid
        substitute for a bare "pass" response — lets us keep strict JSON schema
        validation on the LLM call while still supporting a "nothing to change"
        signal.

        Format mirrors to_json_schema():
        - Single-record tables (e.g. "1recordT"): flat dict, e.g.
          {"date": "pass", "data_source_category": "pass"}
        - All other tables: wrapped in a list under the table name, e.g.
          {"participants": [{"participantID": "pass", ...}]}
        """
        SINGLE_RECORD_TABLES = {"1recordT"}
        single_record = table_name in SINGLE_RECORD_TABLES

        columns = self.schema["tables"][table_name]["columns"]
        row_placeholder = {col: "pass" for col in columns}

        if single_record:
            placeholder = row_placeholder
        else:
            placeholder = {table_name: [row_placeholder]}

        return json.dumps(placeholder, ensure_ascii=False)

    def build_prompt_user_refiner_1recordT(
            self,
            prompt_path: str,
            file_path_doc: str,
            text_doc: str,
            json_result_lastcall: str
    ) -> str:
        prompts = self._load_prompts_user(prompt_path)
        task = "1recordT"

        return prompts["base"].format(
            text_doc=text_doc,
            file_path_doc=file_path_doc,
            schema_metadata_task=self.extract_schema_metadata(task),
            json_result_lastcall=json_result_lastcall,
            json_pass_placeholder=self.build_pass_placeholder(task)
        )