import sqlite3
import csv

def create_tables(conn):
    cur = conn.cursor()
    cur.execute("PRAGMA foreign_keys = ON")

    cur.execute("""
        CREATE TABLE IF NOT EXISTS projects (
            projectID                   INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
            project_name                TEXT,
            phase                       INTEGER,
            start_date                  DATE,
            end_date                    DATE,
            data_sources                TEXT, -- JSONB: {"expertpool":{url1, url2}}
            reports                     TEXT, -- JSONB: [url1, url2]
            city                        TEXT,
            municipality                TEXT,
            province                    TEXT,
            country                     TEXT,
            targeted_participant_group  TEXT  -- JSONB: [group1, group2]
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS notegroups (
            notegroupID          INTEGER PRIMARY KEY,
            projectID            INTEGER REFERENCES projects(projectID) ON DELETE SET NULL,
            project_name         TEXT,
            phase                INTEGER,
            remark               TEXT,
            note_url_QA          TEXT,
            note_url_PARTICIPANT TEXT,
            date                 DATE,
            data_source_category TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS participants (
            participantID       INTEGER PRIMARY KEY NOT NULL,
            initials            TEXT,
            gender              TEXT,
            projectID_age       TEXT,   -- JSONB: {projectID: age}
            learning_route      TEXT,
            participant_group   TEXT,
            status              TEXT,
            place_of_origin     TEXT,
            language_group      TEXT,   -- JSONB: ["lang1", "lang2"]
            country_staying_in  TEXT,
            first_arrival_date  DATE,
            municipality        TEXT,
            labor_market_region TEXT,
            other_information   TEXT,   -- JSONB: {"field": "value"}
            notegroupID         INTEGER REFERENCES notegroups(notegroupID) ON DELETE SET NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS questions (
            questionID          INTEGER PRIMARY KEY NOT NULL,
            question_content    TEXT    NOT NULL,
            main_indicator      TEXT,   -- main_indicator IN (
                                        -- 'work', 'education', 'housing', 'health',
                                        -- 'leisure', 'bonds', 'bridges', 'links',
                                        -- 'language', 'culture', 'digital skills',
                                        -- 'safety', 'stability', 'rights and responsibilities'
                                        -- )
            followed_questionID INTEGER,
            following_trigger   TEXT,
            question_type       TEXT,   -- question_type IN ('polar', 'wh', 'alternative')
            notegroupID         INTEGER REFERENCES notegroups(notegroupID) ON DELETE SET NULL,
            FOREIGN KEY (followed_questionID)
                REFERENCES questions(questionID)
                ON DELETE RESTRICT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS answers (
            answerID                INTEGER PRIMARY KEY NOT NULL,
            projectID               INTEGER,
            questionID              INTEGER,
            participantID           INTEGER,
            notegroupID             INTEGER REFERENCES notegroups(notegroupID) ON DELETE SET NULL,
            answer_content_oriLAN   TEXT    NOT NULL,
            answer_content_EN       TEXT,
            answer_extraction_LLM   TEXT,
            sentiment_score_LLM     INTEGER,
            
            FOREIGN KEY (projectID)       REFERENCES projects(projectID)        ON DELETE SET NULL,
            FOREIGN KEY (questionID)      REFERENCES questions(questionID)       ON DELETE SET NULL,
            FOREIGN KEY (participantID)   REFERENCES participants(participantID) ON DELETE SET NULL
        )
    """)

    conn.commit()
    print("All tables created successfully.")


def load_notegroups(conn, csv_path: str):
    cur = conn.cursor()

    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            cur.execute("""
                INSERT OR IGNORE INTO notegroups
                    (notegroupID, project_name, phase, remark, note_url_QA, note_url_PARTICIPANT)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                int(row["notegroupID"]),
                row["project_name"],
                int(row["phase"]) if row["phase"].strip() else None,
                row["remark"] if row["remark"].strip() else None,
                row["note_url_QA"] if row["note_url_QA"].strip() else None,
                row["note_url_PARTICIPANT"] if row["note_url_PARTICIPANT"].strip() else None
            ))

    conn.commit()
    print(f"Notegroups loaded: {cur.rowcount} rows inserted.")


if __name__ == "__main__":
    db_path  = "oedb_baseline.db"
    csv_path = "../data/input_data/notegroups.csv"

    conn = sqlite3.connect(db_path)
    create_tables(conn)
    load_notegroups(conn, csv_path)
    conn.close()