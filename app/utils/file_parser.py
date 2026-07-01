import csv
import json
from io import StringIO
from typing import List, Dict


def parse_json_questions(file_stream) -> List[Dict]:
    data = json.load(file_stream)
    return data.get('questions', data)


def parse_csv_questions(file_stream) -> List[Dict]:
    text = file_stream.read().decode('utf-8')
    reader = csv.DictReader(StringIO(text))
    questions = []
    for row in reader:
        questions.append({
            'text': row.get('text'),
            'type': row.get('type'),
            'difficulty': row.get('difficulty'),
            'options': [
                {'key': 'A', 'text': row.get('option_a')},
                {'key': 'B', 'text': row.get('option_b')},
                {'key': 'C', 'text': row.get('option_c')},
                {'key': 'D', 'text': row.get('option_d')},
            ],
            'correct_answer': row.get('correct_answer'),
            'explanation': row.get('explanation'),
            'marks': int(row.get('marks') or 1),
            'tags': [tag.strip() for tag in (row.get('tags') or '').split(',') if tag.strip()],
        })
    return questions
