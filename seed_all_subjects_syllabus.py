"""
Seed structured CSIT syllabi from all_subjects_syllabus.csv.

Production usage from the Django project directory:

    python seed_all_subjects_syllabus.py --dry-run
    python seed_all_subjects_syllabus.py

If the CSV is elsewhere:

    python seed_all_subjects_syllabus.py --csv /home/user/all_subjects_syllabus.csv

The script matches existing semesters/subjects created by earlier question or
answer imports. It understands semester labels like I, II, First Semester, and
Semester 1, and it normalizes common singular/plural subject-name differences.
"""

import argparse
import csv
import os
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from contextlib import nullcontext
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_CSV_NAME = "all_subjects_syllabus.csv"

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

FIELD_SECTIONS = {
    "course description": "course_description",
    "course objective": "course_objective",
    "course objectives": "course_objective",
    "laboratory works": "laboratory_work",
    "laboratory work": "laboratory_work",
    "text books": "text_books",
    "text book": "text_books",
    "reference books": "reference_books",
    "reference book": "reference_books",
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
    return (value or "").strip()


def compact(value):
    normalized = unicodedata.normalize("NFKC", clean(value)).lower()
    return "".join(character for character in normalized if character.isalnum())


def normalize_subject_name(value):
    normalized = compact(value)
    replacements = {
        "structures": "structure",
        "systems": "system",
        "algorithms": "algorithm",
        "administration": "administrator",
        "applications": "application",
        "technologies": "technology",
        "principles": "principle",
    }
    for old, new in replacements.items():
        normalized = normalized.replace(old, new)
    return normalized


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


def parse_order(value):
    try:
        return int(float(clean(value)))
    except (TypeError, ValueError):
        return 0


def append_text(current, value):
    value = clean(value)
    if not value:
        return current
    current = clean(current)
    return f"{current}\n{value}" if current else value


def default_csv_path():
    candidates = [
        BASE_DIR / DEFAULT_CSV_NAME,
        BASE_DIR.parent / "syllabus_csv_by_semester" / "syllabus_csv_by_semester" / DEFAULT_CSV_NAME,
        BASE_DIR.parent / DEFAULT_CSV_NAME,
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return BASE_DIR / DEFAULT_CSV_NAME


def read_grouped_rows(csv_path):
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValueError("CSV must include a header row.")

        required = {
            "semester",
            "course_code",
            "course_title",
            "credit_hrs",
            "full_marks",
            "pass_marks",
            "nature",
            "section",
            "unit_no",
            "unit_title",
            "hours",
            "content",
        }
        missing = sorted(required - set(reader.fieldnames))
        if missing:
            raise ValueError(f"CSV is missing required columns: {', '.join(missing)}")

        grouped = defaultdict(list)
        for row in reader:
            key = (
                clean(row.get("semester")),
                clean(row.get("course_code")),
                clean(row.get("course_title")),
            )
            if all(key):
                grouped[key].append(row)
        return grouped


def resolve_semester(raw_label, create_missing=True):
    from academics.models import Semester

    target_keys = semester_keys(raw_label)
    for semester in Semester.objects.all().order_by("id"):
        if semester_keys(semester.name) & target_keys:
            return semester, False

    if create_missing:
        return Semester.objects.create(name=canonical_semester_name(raw_label)), True

    return None, False


def resolve_subject(semester, course_title, course_code, create_missing=True):
    from academics.models import Subject

    course_code_key = compact(course_code)
    if course_code_key:
        code_match = (
            Subject.objects.select_related("semester")
            .filter(semester=semester, syllabus__course_no__iexact=course_code)
            .first()
        )
        if code_match:
            return code_match, False, "course_code"

    target = normalize_subject_name(course_title)
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
        for subject in Subject.objects.all().order_by("id")
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

    subject = Subject.objects.create(semester=semester, name=clean(course_title))
    return subject, True, "created_subject"


def unique_unit_slug(syllabus, title, used_slugs):
    from django.utils.text import slugify
    from academics.models import SyllabusUnit

    max_length = SyllabusUnit._meta.get_field("slug").max_length or 50
    base = (slugify(title) or "unit")[:max_length].rstrip("-") or "unit"
    slug = base
    index = 2
    while slug in used_slugs or SyllabusUnit.objects.filter(syllabus=syllabus, slug=slug).exists():
        suffix = f"-{index}"
        slug_base = base[: max_length - len(suffix)].rstrip("-") or "unit"
        slug = f"{slug_base}{suffix}"
        index += 1
    used_slugs.add(slug)
    return slug


def import_subject_syllabus(subject, subject_rows, replace=True):
    from academics.models import Syllabus, SyllabusSection, SyllabusUnit

    first_row = subject_rows[0]
    syllabus, created = Syllabus.objects.get_or_create(subject=subject)

    syllabus.course_title = clean(first_row.get("course_title")) or subject.name
    syllabus.course_no = clean(first_row.get("course_code"))
    syllabus.semester_label = clean(first_row.get("semester"))
    syllabus.nature = clean(first_row.get("nature"))
    syllabus.full_marks = clean(first_row.get("full_marks"))
    syllabus.pass_marks = clean(first_row.get("pass_marks"))
    syllabus.credit_hours = clean(first_row.get("credit_hrs"))
    syllabus.course_description = ""
    syllabus.course_objective = ""
    syllabus.laboratory_work = ""
    syllabus.text_books = ""
    syllabus.reference_books = ""
    syllabus.save()

    if replace:
        syllabus.units.all().delete()
        syllabus.sections.all().delete()

    imported_units = 0
    imported_sections = 0
    section_order = 1
    used_slugs = set()

    for row in subject_rows:
        section = clean(row.get("section"))
        section_key = section.lower()
        content = clean(row.get("content"))

        if section_key == "course contents":
            unit_no = clean(row.get("unit_no"))
            if not unit_no:
                continue

            unit_title = clean(row.get("unit_title")) or f"Unit {unit_no}"
            SyllabusUnit.objects.create(
                syllabus=syllabus,
                title=unit_title,
                slug=unique_unit_slug(syllabus, unit_title, used_slugs),
                duration=clean(row.get("hours")),
                content=content,
                order=parse_order(unit_no),
            )
            imported_units += 1
            continue

        field_name = FIELD_SECTIONS.get(section_key)
        if field_name:
            setattr(syllabus, field_name, append_text(getattr(syllabus, field_name), content))
            continue

        if content:
            SyllabusSection.objects.create(
                syllabus=syllabus,
                title=section[:160],
                content=content,
                order=section_order,
            )
            imported_sections += 1
            section_order += 1

    syllabus.save()
    return created, imported_units, imported_sections


def seed(csv_path, dry_run=False, create_missing=True, replace=True):
    setup_django()

    from django.db import transaction

    grouped_rows = read_grouped_rows(csv_path)
    stats = Counter()
    samples = []

    context = transaction.atomic() if dry_run else nullcontext()
    with context:
        for (semester_label, course_code, course_title), subject_rows in grouped_rows.items():
            stats["syllabi_seen"] += 1

            semester, semester_created = resolve_semester(
                semester_label,
                create_missing=create_missing,
            )
            if not semester:
                stats["missing_semester"] += 1
                samples.append((course_title, "missing_semester", semester_label))
                continue
            stats["semesters_created" if semester_created else "semesters_matched"] += 1

            subject, subject_created, match_type = resolve_subject(
                semester,
                course_title,
                course_code,
                create_missing=create_missing,
            )
            stats[f"subject_{match_type}"] += 1
            if not subject:
                stats["skipped_subject"] += 1
                samples.append((course_title, match_type, semester.name))
                continue
            if subject_created:
                stats["subjects_created"] += 1

            syllabus_created, unit_count, section_count = import_subject_syllabus(
                subject,
                subject_rows,
                replace=replace,
            )
            stats["syllabi_created" if syllabus_created else "syllabi_updated"] += 1
            stats["units_imported"] += unit_count
            stats["sections_imported"] += section_count

        if dry_run:
            transaction.set_rollback(True)

    print("Dry run completed" if dry_run else "Seed completed")
    print(f"csv: {csv_path}")
    for key in sorted(stats):
        print(f"{key}: {stats[key]}")

    if samples:
        print("sample_skips:")
        for course_title, reason, detail in samples[:20]:
            print(f"- {course_title}: {reason}: {detail}")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Seed structured syllabi from all_subjects_syllabus.csv."
    )
    parser.add_argument(
        "--csv",
        type=Path,
        default=default_csv_path(),
        help="Path to all_subjects_syllabus.csv.",
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
        help="Append units/sections instead of replacing current syllabus units and sections.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    set_csv_field_limit()
    args = parse_args()
    if not args.csv.exists():
        raise SystemExit(f"CSV file not found: {args.csv}")

    seed(
        csv_path=args.csv.resolve(),
        dry_run=args.dry_run,
        create_missing=not args.update_existing_only,
        replace=not args.append,
    )
