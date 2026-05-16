def get_starting_ids(cursor, project_name: str, phase: int) -> dict:
    """Loads the last primary keys in the tables from the database, to learn the starting IDs of the new records.
    Also ensures the project exists and returns its projectID."""

    # Insert project if it doesn't exist
    print("\n--- Loading IDs and calculating starting IDs from the database ---")
    cursor.execute("SELECT projectID FROM projects WHERE project_name = ? AND phase = ?", (project_name, phase))
    existing = cursor.fetchone()

    if existing:
        project_id = existing[0]
    else:
        cursor.execute(
            "INSERT INTO projects (project_name, phase) VALUES (?, ?)",
            (project_name, phase)
        )
        project_id = cursor.lastrowid

    cursor.execute("SELECT MAX(CAST(participantID AS INTEGER)) FROM participants")
    last_participant = cursor.fetchone()[0]
    cursor.execute("SELECT MAX(CAST(questionID AS INTEGER)) FROM questions")
    last_question = cursor.fetchone()[0]
    cursor.execute("SELECT MAX(CAST(answerID AS INTEGER)) FROM answers")
    last_answer = cursor.fetchone()[0]

    starting_ids = {
        "projectID":     project_id,
        "participantID": int(last_participant) + 1 if last_participant else 1,
        "questionID":    int(last_question)    + 1 if last_question    else 1,
        "answerID":      int(last_answer)      + 1 if last_answer      else 1,
    }

    print(f"projectID     : {starting_ids['projectID']}")
    print(f"Starting IDs:")
    print(f"  participantID : {starting_ids['participantID']}")
    print(f"  questionID    : {starting_ids['questionID']}")
    print(f"  answerID      : {starting_ids['answerID']}")

    return starting_ids