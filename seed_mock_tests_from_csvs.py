"""
Seed subject mock tests from a directory of MCQ CSV files.

Expected CSV columns:
Semester, Subject, Unit, Question, Option A, Option B, Option C, Option D,
Correct Answer, Difficulty

Production usage from the Django project directory:

    python seed_mock_tests_from_csvs.py --dry-run
    python seed_mock_tests_from_csvs.py

If the CSV folder is elsewhere:

    python seed_mock_tests_from_csvs.py --dir /home/user/fuckmock/bmc --dry-run
    python seed_mock_tests_from_csvs.py --dir /home/user/fuckmock/bmc

The script matches existing semesters/subjects from previous question, answer,
and syllabus seeds. Duplicate files such as "copy" files are merged into the
same subject mock test and duplicate question text is imported only once.
"""

import argparse
import csv
import math
import os
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from contextlib import nullcontext
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_TITLE_TEMPLATE = "{subject} Mock Test"

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


def clean(value):
    if value is None:
        return ""
    if isinstance(value, list):
        return " ".join(clean(item) for item in value if clean(item)).strip()
    return str(value).strip()


def compact(value):
    normalized = unicodedata.normalize("NFKC", clean(value)).lower()
    return "".join(character for character in normalized if character.isalnum())


def normalize_subject_name(value):
    normalized = compact(value)
    replacements = {
        "structures": "structure",
        "systems": "system",
        "algorithms": "algorithm",
        "applications": "application",
        "technologies": "technology",
        "principles": "principle",
        "administration": "administrator",
        "and": "",
    }
    for old, new in replacements.items():
        normalized = normalized.replace(old, new)
    return normalized


def normalize_question_text(value):
    normalized = unicodedata.normalize("NFKC", clean(value)).lower()
    normalized = normalized.replace("\u00a0", " ")
    normalized = re.sub(r"[\W_]+", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def semester_number(value):
    normalized = compact(value)
    if normalized in ROMAN_TO_NUMBER:
        return ROMAN_TO_NUMBER[normalized]

    roman_candidate = normalized.replace("semester", "")
    if roman_candidate in ROMAN_TO_NUMBER:
        return ROMAN_TO_NUMBER[roman_candidate]

    for word, number in ORDINAL_TO_NUMBER.items():
        if word in normalized:
            return number

    match = re.search(r"[1-8]", normalized)
    return match.group(0) if match else ""


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
    return f"Semester {number}" if number else clean(value)


def default_dir():
    candidates = [
        BASE_DIR / "bmc",
        BASE_DIR.parent / "fuckmock" / "bmc",
        BASE_DIR.parent / "fuckmock",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return BASE_DIR / "bmc"


def csv_value(row, *keys):
    normalized = {
        compact(key): clean(value)
        for key, value in row.items()
        if key is not None
    }
    for key in keys:
        value = normalized.get(compact(key))
        if value:
            return value
    return ""


def read_csv_groups(input_dir):
    csv_files = sorted(Path(input_dir).rglob("*.csv"))
    if not csv_files:
        raise ValueError(f"No CSV files found under {input_dir}")

    groups = defaultdict(list)
    stats = Counter()

    for csv_path in csv_files:
        with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle, skipinitialspace=True)
            if not reader.fieldnames:
                stats["files_without_header"] += 1
                continue

            for row_number, row in enumerate(reader, start=2):
                semester = csv_value(row, "semester")
                subject = csv_value(row, "subject")
                if not semester or not subject:
                    stats["rows_missing_subject_or_semester"] += 1
                    continue

                key = (semester_number(semester) or semester, normalize_subject_name(subject), subject)
                groups[key].append((csv_path, row_number, row))
                stats["rows_read"] += 1

    stats["files_read"] = len(csv_files)
    stats["subject_groups"] = len(groups)
    return groups, stats


def resolve_semester(raw_label, create_missing=True):
    from academics.models import Semester

    target_keys = semester_keys(raw_label)
    for semester in Semester.objects.all().order_by("id"):
        if semester_keys(semester.name) & target_keys:
            return semester, False

    if create_missing:
        return Semester.objects.create(name=canonical_semester_name(raw_label)), True

    return None, False


def unique_slug(model, value):
    from django.utils.text import slugify

    max_length = model._meta.get_field("slug").max_length or 50
    base = (slugify(value) or "item")[:max_length].rstrip("-") or "item"
    slug = base
    index = 2
    while model.objects.filter(slug=slug).exists():
        suffix = f"-{index}"
        slug_base = base[: max_length - len(suffix)].rstrip("-") or "item"
        slug = f"{slug_base}{suffix}"
        index += 1
    return slug


def resolve_subject(semester, raw_name, create_missing=True):
    from academics.models import Subject

    target = normalize_subject_name(raw_name)
    semester_matches = [
        subject
        for subject in Subject.objects.filter(semester=semester).order_by("id")
        if normalize_subject_name(subject.name) == target
    ]
    if len(semester_matches) == 1:
        return semester_matches[0], False, "semester_subject_name"
    if len(semester_matches) > 1:
        return None, False, "ambiguous_semester_subject_name"

    global_matches = [
        subject
        for subject in Subject.objects.select_related("semester").all().order_by("id")
        if normalize_subject_name(subject.name) == target
    ]
    if len(global_matches) == 1:
        return global_matches[0], False, "global_subject_name"
    if len(global_matches) > 1:
        same_semester = [
            subject
            for subject in global_matches
            if semester_keys(subject.semester.name) & semester_keys(semester.name)
        ]
        if len(same_semester) == 1:
            return same_semester[0], False, "global_subject_name_semester"
        return None, False, "ambiguous_global_subject_name"

    if not create_missing:
        return None, False, "missing_subject"

    name = clean(raw_name)[: Subject._meta.get_field("name").max_length]
    subject = Subject.objects.create(
        semester=semester,
        name=name,
        slug=unique_slug(Subject, f"{semester.name}-{name}"),
    )
    return subject, True, "created_subject"


def trim_to_field(model, field_name, value):
    max_length = model._meta.get_field(field_name).max_length
    value = clean(value)
    if max_length and len(value) > max_length:
        return value[:max_length], True
    return value, False


def build_questions(group_rows):
    from academics.models import MockTestQuestion

    questions = []
    seen = set()
    stats = Counter()
    samples = []

    for csv_path, row_number, row in group_rows:
        question_text = csv_value(row, "question", "question_text", "prompt")
        option_a = csv_value(row, "option a", "option_a", "a")
        option_b = csv_value(row, "option b", "option_b", "b")
        option_c = csv_value(row, "option c", "option_c", "c")
        option_d = csv_value(row, "option d", "option_d", "d")
        correct_option = csv_value(row, "correct answer", "correct_option", "correct", "answer")[:1].upper()

        if not all([question_text, option_a, option_b, option_c, option_d]):
            stats["rows_missing_question_or_options"] += 1
            samples.append((csv_path.name, row_number, "missing question/options"))
            continue
        if correct_option not in {"A", "B", "C", "D"}:
            stats["rows_invalid_correct_option"] += 1
            samples.append((csv_path.name, row_number, f"invalid correct answer {correct_option!r}"))
            continue

        question_key = normalize_question_text(question_text)
        if question_key in seen:
            stats["duplicate_questions_skipped"] += 1
            continue
        seen.add(question_key)

        option_a, truncated_a = trim_to_field(MockTestQuestion, "option_a", option_a)
        option_b, truncated_b = trim_to_field(MockTestQuestion, "option_b", option_b)
        option_c, truncated_c = trim_to_field(MockTestQuestion, "option_c", option_c)
        option_d, truncated_d = trim_to_field(MockTestQuestion, "option_d", option_d)
        if any([truncated_a, truncated_b, truncated_c, truncated_d]):
            stats["options_truncated"] += 1

        questions.append(
            MockTestQuestion(
                question_text=question_text,
                option_a=option_a,
                option_b=option_b,
                option_c=option_c,
                option_d=option_d,
                correct_option=correct_option,
                marks=1,
            )
        )
        stats["questions_valid"] += 1

    return questions, stats, samples


def seed(input_dir, dry_run=False, create_missing=True, replace=True, title_template=DEFAULT_TITLE_TEMPLATE):
    setup_django()

    from django.db import transaction
    from academics.models import MockTest, MockTestQuestion

    groups, stats = read_csv_groups(input_dir)
    samples = []

    context = transaction.atomic() if dry_run else nullcontext()
    with context:
        for (semester_label, _subject_key, raw_subject_name), group_rows in sorted(groups.items()):
            semester, semester_created = resolve_semester(
                semester_label,
                create_missing=create_missing,
            )
            if not semester:
                stats["missing_semester"] += 1
                samples.append((raw_subject_name, "missing_semester", semester_label))
                continue
            stats["semesters_created" if semester_created else "semesters_matched"] += 1

            subject, subject_created, match_type = resolve_subject(
                semester,
                raw_subject_name,
                create_missing=create_missing,
            )
            stats[f"subject_{match_type}"] += 1
            if not subject:
                stats["skipped_subject_groups"] += 1
                samples.append((raw_subject_name, match_type, semester.name))
                continue
            if subject_created:
                stats["subjects_created"] += 1

            questions, question_stats, question_samples = build_questions(group_rows)
            stats.update(question_stats)
            samples.extend((raw_subject_name, reason, f"{file_name}:{row_number}") for file_name, row_number, reason in question_samples)

            if not questions:
                stats["mock_tests_skipped_empty"] += 1
                continue

            title = title_template.format(subject=subject.name, semester=semester.name)
            title = title[: MockTest._meta.get_field("title").max_length]
            mock_test, created = MockTest.objects.get_or_create(
                subject=subject,
                title=title,
                defaults={
                    "duration_minutes": max(1, math.ceil(len(questions) * 1.5)),
                    "total_marks": len(questions),
                    "is_active": True,
                },
            )
            stats["mock_tests_created" if created else "mock_tests_updated"] += 1

            if replace:
                mock_test.questions.all().delete()

            for question in questions:
                question.mock_test = mock_test
            MockTestQuestion.objects.bulk_create(questions)

            mock_test.duration_minutes = max(1, math.ceil(len(questions) * 1.5))
            mock_test.total_marks = mock_test.questions.count()
            mock_test.is_active = True
            mock_test.save(update_fields=["duration_minutes", "total_marks", "is_active"])

        if dry_run:
            transaction.set_rollback(True)

    print("Dry run completed" if dry_run else "Seed completed")
    print(f"dir: {input_dir}")
    for key in sorted(stats):
        print(f"{key}: {stats[key]}")

    if samples:
        print("sample_skips:")
        for subject, reason, detail in samples[:25]:
            print(f"- {subject}: {reason}: {detail}")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Seed mock tests from a directory of MCQ CSV files."
    )
    parser.add_argument(
        "--dir",
        type=Path,
        default=default_dir(),
        help="Directory containing mock-test CSV files.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Validate import without saving changes.")
    parser.add_argument(
        "--update-existing-only",
        action="store_true",
        help="Do not create missing semesters or subjects.",
    )
    parser.add_argument(
        "--append",
        action="store_true",
        help="Append questions to existing mock tests instead of replacing them.",
    )
    parser.add_argument(
        "--title-template",
        default=DEFAULT_TITLE_TEMPLATE,
        help="Mock test title template. Available fields: {subject}, {semester}.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    set_csv_field_limit()
    args = parse_args()

    if not args.dir.exists():
        raise SystemExit(f"Directory not found: {args.dir}")

    seed(
        input_dir=args.dir.resolve(),
        dry_run=args.dry_run,
        create_missing=not args.update_existing_only,
        replace=not args.append,
        title_template=args.title_template,
    )
