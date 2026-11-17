"""Search semantics against a temporary FTS5 index, never real session data."""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from siv import search


CASES = json.loads(Path(__file__).with_name("search-cases.json").read_text())


class SearchTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        patcher = patch.object(search, "INDEX_DB", str(Path(self.temp.name) / "search.db"))
        patcher.start()
        self.addCleanup(patcher.stop)

    def insert(self, key, pos, text):
        conn = search._connect()
        try:
            with conn:
                conn.execute("INSERT INTO msg(key, pos, body) VALUES (?, ?, ?)", (key, pos, text))
        finally:
            conn.close()

    def test_boundaries_in_both_modes(self):
        for case in CASES:
            with self.subTest(case=case):
                key = str(CASES.index(case))
                self.insert(key, 0, case["text"])
                self.assertEqual(key in search.search(case["term"])["hits"], case["whole"])
                self.assertIn(key, search.search(case["term"], substring=True)["hits"])

    def test_all_terms_must_match_in_one_message(self):
        self.insert("split", 0, "ecr")
        self.insert("split", 1, "repo")
        self.insert("whole", 0, "ECR repo")
        self.insert("embedded", 0, "secret repo")
        self.assertEqual(set(search.search("ecr repo")["hits"]), {"whole"})
        self.assertEqual(set(search.search("ecr repo", substring=True)["hits"]), {"whole", "embedded"})

    def test_positions_counts_and_empty_query(self):
        self.insert("session", 0, "secret")
        self.insert("session", 1, "ECR ecr")
        self.assertEqual(search.search("ecr")["hits"]["session"], {"count": 1, "positions": [1]})
        self.assertEqual(search.search("ecr", substring=True)["hits"]["session"], {"count": 2, "positions": [0, 1]})
        self.assertEqual(search.search("")["hits"], {})

    def test_existing_quoted_phrases(self):
        self.insert("phrase", 0, "AWS ECR")
        self.insert("embedded", 0, "xAWS ECRx")
        self.assertEqual(set(search.search('"AWS ECR"')["hits"]), {"phrase"})


if __name__ == "__main__":
    unittest.main()
