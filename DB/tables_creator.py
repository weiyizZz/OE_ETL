import sqlite3

def create_tables(db_path: str = "oedb_baseline.db"):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("PRAGMA foreign_keys = ON")

    cursor.execute("""
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
            targeted_participant_group  TEXT -- JSONB: [group1, group2]
        )
    """)

    cursor.execute("""
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
            other_information   TEXT    -- JSONB: {"field": "value"}
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS questions (
            questionID          INTEGER PRIMARY KEY NOT NULL,
            question_content    TEXT    NOT NULL,
            main_indicator      TEXT,    -- main_indicator IN (
                                    -- 'work', 'education', 'housing', 'health',
                                    -- 'leisure', 'bonds', 'bridges', 'links',
                                    -- 'language', 'culture', 'digital skills',
                                    -- 'safety', 'stability', 'rights and responsibilities'
                               -- )
            followed_questionID INTEGER,
            following_trigger   TEXT,
            question_type       TEXT,    -- question_type IN ('polar', 'wh', 'alternative')
            FOREIGN KEY (followed_questionID)
                REFERENCES questions(questionID)
                ON DELETE RESTRICT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS answers (
            answerID                INTEGER PRIMARY KEY NOT NULL,
            projectID               INTEGER,
            questionID              INTEGER,
            participantID           INTEGER,
            answer_content_oriLAN   TEXT    NOT NULL,
            answer_content_EN       TEXT,
            answer_extraction_LLM   TEXT,
            sentiment_score_LLM     INTEGER,
            date                    DATE,
            data_source_category    TEXT,    --data_source_category IN ('expertpool', 'survey', 'focus group','diepteinterview', 'other'),
            data_source             TEXT,
            FOREIGN KEY (projectID)     REFERENCES projects(projectID)      ON DELETE RESTRICT,
            FOREIGN KEY (questionID)    REFERENCES questions(questionID)     ON DELETE SET NULL,
            FOREIGN KEY (participantID) REFERENCES participants(participantID) ON DELETE SET NULL
        )
    """)

    conn.commit()
    conn.close()
    print("All tables created successfully.")


if __name__ == "__main__":
    create_tables()