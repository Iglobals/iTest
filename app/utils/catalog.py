"""Exam catalog for exams sold through the iGlobal e-library.

Each catalog exam has a stable `catalog_key` (e.g. 'jupeb-mathematics').
The e-library's purchase webhook grants access by these keys, never by
exam _id, so the admin can rebuild an exam without breaking book mappings.
The same key strings live in iGlobal_edu (book.exam_keys) - keep in sync.

ensure_catalog_exams() creates any missing ones with placeholder questions
(published, per the product decision); the admin then edits them in the
normal question builder.
"""
import uuid
from datetime import datetime

from app.utils.mongo import get_collection

# (key, subject, [(question, [options...], index_of_correct), ...])
JUPEB_SUBJECTS = [
    ('jupeb-mathematics', 'Mathematics', [
        ('If 2x + 3 = 11, what is x?', ['4', '3', '5', '7'], 0),
        ('What is the derivative of x^3 with respect to x?', ['3x^2', 'x^2', '3x', 'x^4/4'], 0),
        ('What is the sum of the interior angles of a triangle?', ['90°', '180°', '270°', '360°'], 1),
        ('What is log₁₀(1000)?', ['2', '3', '10', '100'], 1),
        ('What is the value of 5! (5 factorial)?', ['25', '60', '120', '720'], 2),
    ]),
    ('jupeb-physics', 'Physics', [
        ('What is the SI unit of force?', ['Joule', 'Watt', 'Newton', 'Pascal'], 2),
        ('Acceleration due to gravity near the Earth’s surface is approximately:', ['9.8 m/s²', '1.6 m/s²', '98 m/s²', '0.98 m/s²'], 0),
        ('Which of these is a vector quantity?', ['Speed', 'Mass', 'Velocity', 'Energy'], 2),
        ('According to Ohm’s law, V equals:', ['I/R', 'IR', 'R/I', 'I²R'], 1),
        ('The speed of light in a vacuum is approximately:', ['3.0 × 10⁸ m/s', '3.0 × 10⁶ m/s', '3.4 × 10² m/s', '1.5 × 10⁸ m/s'], 0),
    ]),
    ('jupeb-chemistry', 'Chemistry', [
        ('What is the atomic number of carbon?', ['4', '6', '8', '12'], 1),
        ('What is the chemical formula of water?', ['H₂O', 'HO₂', 'H₂O₂', 'OH'], 0),
        ('The pH of pure water at 25°C is:', ['0', '5', '7', '14'], 2),
        ('Which gas is produced when zinc reacts with dilute hydrochloric acid?', ['Oxygen', 'Chlorine', 'Carbon dioxide', 'Hydrogen'], 3),
        ('Which is the most electronegative element?', ['Oxygen', 'Fluorine', 'Chlorine', 'Nitrogen'], 1),
    ]),
    ('jupeb-biology', 'Biology', [
        ('Which organelle is known as the powerhouse of the cell?', ['Nucleus', 'Ribosome', 'Mitochondrion', 'Golgi body'], 2),
        ('The process by which green plants make their food is called:', ['Respiration', 'Photosynthesis', 'Transpiration', 'Digestion'], 1),
        ('The basic unit of heredity is the:', ['Cell', 'Gene', 'Tissue', 'Organ'], 1),
        ('Which blood cells mainly fight infection?', ['Red blood cells', 'Platelets', 'White blood cells', 'Plasma'], 2),
        ('How many chambers does the human heart have?', ['2', '3', '4', '5'], 2),
    ]),
    ('jupeb-government', 'Government', [
        ('Nigeria’s current constitution came into force in:', ['1963', '1979', '1989', '1999'], 3),
        ('Which arm of government interprets the law?', ['Legislature', 'Executive', 'Judiciary', 'Civil service'], 2),
        ('Dividing government powers among three arms is known as:', ['Federalism', 'Separation of powers', 'Rule of law', 'Delegated legislation'], 1),
        ('What is the minimum voting age in Nigeria?', ['16', '18', '21', '25'], 1),
        ('A system where power is shared between a central government and component units is:', ['Unitary', 'Confederal', 'Federal', 'Monarchical'], 2),
    ]),
    ('jupeb-literature-in-english', 'Literature-in-English', [
        ('Who wrote “Things Fall Apart”?', ['Wole Soyinka', 'Chinua Achebe', 'Ngugi wa Thiong’o', 'Buchi Emecheta'], 1),
        ('A poem of fourteen lines is called a:', ['Haiku', 'Ode', 'Sonnet', 'Limerick'], 2),
        ('A comparison using “like” or “as” is a:', ['Metaphor', 'Simile', 'Hyperbole', 'Personification'], 1),
        ('The main character in a story is the:', ['Antagonist', 'Narrator', 'Protagonist', 'Foil'], 2),
        ('Wole Soyinka won the Nobel Prize in Literature in:', ['1976', '1986', '1996', '2006'], 1),
    ]),
    ('jupeb-economics', 'Economics', [
        ('By the law of demand, when price rises (other things equal), quantity demanded:', ['Rises', 'Falls', 'Stays the same', 'Doubles'], 1),
        ('The basic economic problem arises from:', ['Scarcity', 'Inflation', 'Taxation', 'Unemployment'], 0),
        ('A market with a single seller is a:', ['Monopoly', 'Oligopoly', 'Perfect competition', 'Duopoly'], 0),
        ('GDP stands for:', ['General Domestic Price', 'Gross Domestic Product', 'Gross Demand Projection', 'Government Development Plan'], 1),
        ('Opportunity cost is:', ['The money price of a good', 'The next best alternative forgone', 'The cost of production', 'A tax on imports'], 1),
    ]),
    ('jupeb-crs', 'Christian Religious Studies', [
        ('What is the first book of the Bible?', ['Exodus', 'Genesis', 'Leviticus', 'Matthew'], 1),
        ('Who led the Israelites out of Egypt?', ['Abraham', 'Joshua', 'Moses', 'David'], 2),
        ('How many disciples did Jesus choose?', ['7', '10', '12', '70'], 2),
        ('Where was Jesus born?', ['Nazareth', 'Jerusalem', 'Bethlehem', 'Capernaum'], 2),
        ('Who betrayed Jesus?', ['Peter', 'Thomas', 'Judas Iscariot', 'John'], 2),
    ]),
    ('jupeb-accounting', 'Accounting', [
        ('The accounting equation is: Assets =', ['Liabilities − Capital', 'Liabilities + Capital', 'Capital − Liabilities', 'Revenue − Expenses'], 1),
        ('Credit purchases of goods are first recorded in the:', ['Sales day book', 'Purchases day book', 'Cash book', 'Journal proper'], 1),
        ('Depreciation is best described as:', ['An increase in asset value', 'The fall in value of a non-current asset over time', 'A cash payment', 'A type of liability'], 1),
        ('A trial balance is mainly prepared to:', ['Calculate profit', 'Check the arithmetical accuracy of the ledger', 'Record sales', 'Pay suppliers'], 1),
        ('Under double entry, every transaction has:', ['Only a debit entry', 'Only a credit entry', 'Equal debit and credit entries', 'Two credit entries'], 2),
    ]),
    ('jupeb-business-studies', 'Business Studies', [
        ('A business owned and run by one person is a:', ['Partnership', 'Sole proprietorship', 'Cooperative', 'Public company'], 1),
        ('The document a buyer sends to order goods is a:', ['Invoice', 'Receipt', 'Purchase order', 'Credit note'], 2),
        ('The main aim of most private businesses is to make:', ['Profit', 'Laws', 'Taxes', 'Loans'], 0),
        ('The “four Ps” of marketing are Product, Price, Place and:', ['People', 'Promotion', 'Profit', 'Planning'], 1),
        ('The insurance principle requiring full disclosure of facts is:', ['Indemnity', 'Subrogation', 'Utmost good faith', 'Contribution'], 2),
    ]),
]

CATALOG_KEYS = {key for key, _, _ in JUPEB_SUBJECTS}


def _questions(items):
    questions = []
    for text, options, correct in items:
        opts = [{'id': f'opt_{uuid.uuid4().hex[:9]}', 'text': o, 'is_correct': i == correct}
                for i, o in enumerate(options)]
        questions.append({
            '_id': str(uuid.uuid4()), 'type': 'mcq', 'text': f'<p>{text}</p>', 'image_url': '',
            'marks': 1, 'options': opts, 'correct_answer': opts[correct]['id'],
            'placeholder': True,  # replace via the question builder
        })
    return questions


def ensure_catalog_exams(admin_user, org):
    """Create any catalog exam that doesn't exist yet (idempotent - existing
    ones, including ones the admin already edited, are never touched).
    Returns the list of keys created."""
    from app.exams.routes import generate_unique_slug
    exams = get_collection('exams')
    created = []
    now = datetime.utcnow()
    for key, subject, items in JUPEB_SUBJECTS:
        if exams.find_one({'catalog_key': key, 'status': {'$ne': 'deleted'}}):
            continue
        title = f'JUPEB {subject}'
        questions = _questions(items)
        exams.insert_one({
            'title': title,
            'slug': generate_unique_slug(title, exams),
            'description': f'JUPEB {subject} practice exam - included with the matching iGlobal e-library book + exam package.',
            'cover_image_url': '',
            'created_by': admin_user['_id'],
            'created_by_type': 'platform_admin',
            'exam_type': 'private',          # access only via email grants from the e-library
            'grading_mode': 'objective',
            'catalog_key': key,
            'catalog_source': 'igs-elibrary',
            'visibility': {'type': 'email', 'class_ids': [], 'student_ids': [], 'excluded_student_ids': []},
            'subject_tag_id': subject,
            'organization_id': org['_id'] if org else None,
            'instructions': '',
            'settings': {
                'duration_minutes': 60, 'allow_retake': True, 'max_attempts': 3,
                'randomize_questions': True, 'randomize_options': True, 'pass_mark_percent': 50,
                'show_result_immediately': True, 'proctoring_enabled': False, 'ai_proctoring_enabled': False,
            },
            'schedule': {'available_from': None, 'available_until': None, 'is_published': True},
            'status': 'published',
            'questions': questions,
            'total_questions': len(questions),
            'total_marks': float(len(questions)),
            'statistics': {'total_attempts': 0, 'avg_score_percent': 0, 'pass_rate_percent': 0},
            'created_at': now, 'updated_at': now,
        })
        created.append(key)
    return created
