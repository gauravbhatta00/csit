"""
Seed validated Bedrock answers into the Django Question table.

Production usage from the Django project directory:

    python seed_bedrock_answers.py --dry-run
    python seed_bedrock_answers.py

If the CSV is not beside this script:

    python seed_bedrock_answers.py --csv /home/user/master_complete_bedrock_validated_answers.csv

By default this script only updates existing matched questions. Use
--create-missing only when you also want to create missing semesters,
subjects, years, sections, and questions from the CSV rows.
"""

import argparse
import csv
import os
import re
import sys
import unicodedata
from collections import Counter
from contextlib import nullcontext
from difflib import SequenceMatcher
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_CSV_NAME = "master_complete_bedrock_validated_answers.csv"
DEFAULT_INSTRUCTIONS = (
    "Candidates are required to give their answers in their own words as far as practicable.\n"
    "The figures in the margin indicate full marks."
)

ORDINAL_TO_NUMBER = {
    "first": "1",
    "second": "2",
    "third": "3",
    "fourth": "4",
    "fifth": "5",
    "sixth": "6",
    "seventh": "7",
    "eighth": "8",
}

ROMAN_TO_NUMBER = {
    "i": "1",
    "ii": "2",
    "iii": "3",
    "iv": "4",
    "v": "5",
    "vi": "6",
    "vii": "7",
    "viii": "8",
}


def set_csv_field_limit():
    limit = sys.maxsize
    while True:
        try:
            csv.field_size_limit(limit)
            return
        except OverflowError:
            limit = int(limit / 10)


def setup_django():
    sys.path.insert(0, str(BASE_DIR))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "csit_platform.settings")

    import django

    django.setup()


def clean_text(value):
    return (value or "").strip()


def compact(value):
    normalized = unicodedata.normalize("NFKC", clean_text(value)).lower()
    return "".join(character for character in normalized if character.isalnum())


def normalize_subject_name(value):
    normalized = compact(value)
    replacements = {
        "structures": "structure",
        "systems": "system",
        "algorithms": "algorithm",
        "administration": "administrator",
    }
    for old, new in replacements.items():
        normalized = normalized.replace(old, new)
    return normalized


def normalize_question_text(value):
    normalized = unicodedata.normalize("NFKC", clean_text(value)).lower()
    normalized = normalized.replace("\u00a0", " ")
    normalized = re.sub(r"[\W_]+", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def semester_number(value):
    normalized = compact(value)
    for word, number in ORDINAL_TO_NUMBER.items():
        if word in normalized:
            return number

    digit_match = re.search(r"[1-8]", normalized)
    if digit_match:
        return digit_match.group(0)

    roman_candidate = normalized.replace("semester", "")
    return ROMAN_TO_NUMBER.get(roman_candidate)


def semester_keys(value):
    keys = {compact(value)}
    number = semester_number(value)
    if number:
        keys.update({f"semester{number}", f"{number}semester"})
        for word, word_number in ORDINAL_TO_NUMBER.items():
            if word_number == number:
                keys.add(f"{word}semester")
    return keys


def canonical_semester_name(value):
    number = semester_number(value)
    return f"Semester {number}" if number else clean_text(value)


def default_csv_path():
    candidates = [
        BASE_DIR / DEFAULT_CSV_NAME,
        BASE_DIR.parent / DEFAULT_CSV_NAME,
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return BASE_DIR / DEFAULT_CSV_NAME


def read_rows(csv_path, limit=None, start_row=1):
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValueError("CSV must include a header row.")

        required = {"question_id", "semester", "subject", "year", "group", "question", "answer"}
        missing = sorted(required - set(reader.fieldnames))
        if missing:
            raise ValueError(f"CSV is missing required columns: {', '.join(missing)}")

        yielded = 0
        for row_number, row in enumerate(reader, start=2):
            data_row_number = row_number - 1
            if data_row_number < start_row:
                continue
            if limit is not None and yielded >= limit:
                break
            yielded += 1
            yield row_number, row


def resolve_semester(raw_name, create_missing=False):
    from academics.models import Semester

    target_keys = semester_keys(raw_name)
    for semester in Semester.objects.all().order_by("id"):
        if semester_keys(semester.name) & target_keys:
            return semester

    if create_missing:
        return Semester.objects.create(name=canonical_semester_name(raw_name))

    return None


def resolve_subject(raw_name, semester=None, create_missing=False):
    from academics.models import Subject

    target = normalize_subject_name(raw_name)
    queryset = Subject.objects.select_related("semester").all()

    if semester:
        semester_matches = [
            subject
            for subject in queryset.filter(semester=semester)
            if normalize_subject_name(subject.name) == target
        ]
        if len(semester_matches) == 1:
            return semester_matches[0], False
        if len(semester_matches) > 1:
            return None, True

    global_matches = [
        subject
        for subject in queryset
        if normalize_subject_name(subject.name) == target
    ]
    if len(global_matches) == 1:
        return global_matches[0], False
    if len(global_matches) > 1:
        return None, True

    if create_missing and semester:
        return Subject.objects.create(name=clean_text(raw_name), semester=semester), False

    return None, False


def resolve_year(subject, year_value, create_missing=False):
    from academics.models import Year

    if not subject or not year_value:
        return None

    year = Year.objects.filter(subject=subject, year=year_value).first()
    if year:
        return year

    if create_missing:
        return Year.objects.create(
            subject=subject,
            year=year_value,
            instructions=DEFAULT_INSTRUCTIONS,
        )

    return None


def resolve_section(year, title, create_missing=False):
    from django.db.models import Max
    from academics.models import QuestionSection

    title = clean_text(title)[:80]
    if not year or not title:
        return None

    section = QuestionSection.objects.filter(year=year, title=title).first()
    if section or not create_missing:
        return section

    current_max = (
        QuestionSection.objects.filter(year=year).aggregate(max_order=Max("order"))["max_order"]
        or 0
    )
    return QuestionSection.objects.create(year=year, title=title, order=current_max + 1)


def row_matches_question(question, row):
    csv_year = clean_text(row.get("year"))
    csv_subject = clean_text(row.get("subject"))
    csv_semester = clean_text(row.get("semester"))
    csv_question = clean_text(row.get("question"))

    if csv_year and question.year.year != csv_year:
        return False
    if csv_subject and normalize_subject_name(question.year.subject.name) != normalize_subject_name(csv_subject):
        return False
    if csv_semester and not (semester_keys(question.year.subject.semester.name) & semester_keys(csv_semester)):
        return False
    if csv_question and normalize_question_text(question.question_text) != normalize_question_text(csv_question):
        return False
    return True


def find_existing_question(row, year=None, fuzzy_threshold=0.0):
    from academics.models import Question

    question_id = clean_text(row.get("question_id"))
    question_text = clean_text(row.get("question"))
    normalized_question = normalize_question_text(question_text)

    if question_id:
        source_match = (
            Question.objects.select_related("year", "year__subject", "year__subject__semester")
            .filter(source_question_id=question_id)
            .first()
        )
        if source_match and row_matches_question(source_match, row):
            return source_match, "source_id", None

        if question_id.isdigit():
            pk_match = (
                Question.objects.select_related("year", "year__subject", "year__subject__semester")
                .filter(pk=int(question_id))
                .first()
            )
            if pk_match and row_matches_question(pk_match, row):
                return pk_match, "primary_key", None

    if not year or not normalized_question:
        return None, "missing_year", None

    candidates = list(
        Question.objects.select_related("year", "year__subject", "year__subject__semester")
        .filter(year=year)
        .only("id", "year", "question_text", "answer_text")
    )

    exact_matches = [
        question
        for question in candidates
        if normalize_question_text(question.question_text) == normalized_question
    ]
    if len(exact_matches) == 1:
        return exact_matches[0], "question_text", None
    if len(exact_matches) > 1:
        return None, "ambiguous_question_text", len(exact_matches)

    if fuzzy_threshold:
        scored = []
        for question in candidates:
            score = SequenceMatcher(
                None,
                normalized_question,
                normalize_question_text(question.question_text),
            ).ratio()
            if score >= fuzzy_threshold:
                scored.append((score, question))

        scored.sort(key=lambda item: item[0], reverse=True)
        if len(scored) == 1 or (len(scored) > 1 and scored[0][0] > scored[1][0]):
            return scored[0][1], "fuzzy_question_text", round(scored[0][0], 4)
        if scored:
            return None, "ambiguous_fuzzy_question_text", round(scored[0][0], 4)

    return None, "not_found", None


def next_question_order(year, section=None):
    from django.db.models import Max
    from academics.models import Question

    queryset = Question.objects.filter(year=year)
    if section:
        queryset = queryset.filter(section=section)
    current_max = queryset.aggregate(max_order=Max("order"))["max_order"] or 0
    return current_max + 1


def should_set_source_id(question_id):
    from academics.models import Question

    if not question_id:
        return ""
    if Question.objects.filter(source_question_id=question_id).exists():
        return ""
    return question_id


def seed(csv_path, dry_run=False, create_missing=False, only_empty=False, set_source_id=False, limit=None, start_row=1, fuzzy_threshold=0.0):
    setup_django()

    from django.db import transaction
    from academics.models import Question

    stats = Counter()
    samples = []

    context = transaction.atomic() if dry_run else nullcontext()
    with context:
        for row_number, row in read_rows(csv_path, limit=limit, start_row=start_row):
            stats["rows_read"] += 1

            answer = clean_text(row.get("answer"))
            question_text = clean_text(row.get("question"))
            year_value = clean_text(row.get("year"))

            if not answer:
                stats["skipped_empty_answer"] += 1
                continue
            if not question_text:
                stats["skipped_empty_question"] += 1
                continue

            semester = resolve_semester(row.get("semester"), create_missing=create_missing)
            if not semester:
                stats["missing_semester"] += 1
                samples.append((row_number, "missing_semester", row.get("semester")))
                continue

            subject, ambiguous_subject = resolve_subject(
                row.get("subject"),
                semester=semester,
                create_missing=create_missing,
            )
            if ambiguous_subject:
                stats["ambiguous_subject"] += 1
                samples.append((row_number, "ambiguous_subject", row.get("subject")))
                continue
            if not subject:
                stats["missing_subject"] += 1
                samples.append((row_number, "missing_subject", row.get("subject")))
                continue

            year = resolve_year(subject, year_value, create_missing=create_missing)
            if not year:
                stats["missing_year"] += 1
                samples.append((row_number, "missing_year", year_value))
                continue

            question, match_type, match_detail = find_existing_question(
                row,
                year=year,
                fuzzy_threshold=fuzzy_threshold,
            )
            stats[f"match_{match_type}"] += 1

            if not question:
                if create_missing:
                    section = resolve_section(
                        year,
                        row.get("group"),
                        create_missing=create_missing,
                    )
                    if not dry_run:
                        source_question_id = (
                            should_set_source_id(clean_text(row.get("question_id")))
                            if set_source_id
                            else ""
                        )
                        Question.objects.create(
                            year=year,
                            section=section,
                            source_question_id=source_question_id,
                            question_text=question_text,
                            answer_text=answer,
                            order=next_question_order(year, section),
                        )
                    stats["questions_created"] += 1
                    continue

                stats["missing_question"] += 1
                samples.append((row_number, match_type, match_detail or question_text[:120]))
                continue

            if only_empty and question.answer_text.strip():
                stats["skipped_existing_answer"] += 1
                continue

            if question.answer_text == answer:
                stats["questions_unchanged"] += 1
                continue

            if not dry_run:
                question.answer_text = answer
                question.save(update_fields=["answer_text"])
            stats["questions_updated"] += 1

        if dry_run:
            transaction.set_rollback(True)

    print("Dry run completed" if dry_run else "Seed completed")
    print(f"csv: {csv_path}")
    for key in sorted(stats):
        print(f"{key}: {stats[key]}")

    if samples:
        print("sample_skips:")
        for row_number, reason, detail in samples[:20]:
            print(f"- row {row_number}: {reason}: {detail}")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Seed answers from master_complete_bedrock_validated_answers.csv into existing Django questions."
    )
    parser.add_argument(
        "--csv",
        type=Path,
        default=default_csv_path(),
        help="Path to master_complete_bedrock_validated_answers.csv.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Validate matching without saving changes.")
    parser.add_argument(
        "--create-missing",
        action="store_true",
        help="Create missing semesters, subjects, years, sections, and questions.",
    )
    parser.add_argument(
        "--only-empty",
        action="store_true",
        help="Only fill questions whose answer_text is currently empty.",
    )
    parser.add_argument(
        "--set-source-id",
        action="store_true",
        help="When creating missing questions, store CSV question_id as source_question_id if it is unused.",
    )
    parser.add_argument("--limit", type=int, default=None, help="Process only the first N CSV rows.")
    parser.add_argument("--start-row", type=int, default=1, help="Start from data row N, not counting the header.")
    parser.add_argument(
        "--fuzzy-threshold",
        type=float,
        default=0.0,
        help="Optional fuzzy question-text matching threshold, for example 0.98. Default disables fuzzy matching.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    set_csv_field_limit()
    args = parse_args()

    if not args.csv.exists():
        raise SystemExit(f"CSV file not found: {args.csv}")
    if args.fuzzy_threshold and not 0.0 < args.fuzzy_threshold <= 1.0:
        raise SystemExit("--fuzzy-threshold must be between 0 and 1.")

    seed(
        csv_path=args.csv.resolve(),
        dry_run=args.dry_run,
        create_missing=args.create_missing,
        only_empty=args.only_empty,
        set_source_id=args.set_source_id,
        limit=args.limit,
        start_row=args.start_row,
        fuzzy_threshold=args.fuzzy_threshold,
    )
