"""JSONL file reading."""

import json


def read_records(path):
    """Every JSON record in a JSONL file; undecodable lines are skipped.

    Files are read whole: usage sums and tool counts need every record.
    """
    with open(path, "rb") as f:
        return decode_records(f.read().decode("utf-8", "replace").splitlines())


def decode_records(lines):
    records = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except ValueError:
            continue
    return records
