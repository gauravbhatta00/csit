import csv
import re
from collections import defaultdict
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.utils.text import slugify

from academics.models import Semester, Subject, Syllabus, SyllabusSection, SyllabusUnit


ROMAN_SEMESTERS = {
    'I': 1,
    'II': 2,
    'III': 3,
    'IV': 4,
    'V': 5,
    'VI': 6,
    'VII': 7,
    'VIII': 8,
}

FIELD_SECTIONS = {
    'course description': 'course_description',
    'course objective': 'course_objective',
    'course objectives': 'course_objective',
    'laboratory works': 'laboratory_work',
    'laboratory work': 'laboratory_work',
    'laboratory works': 'laboratory_work',
    'text books': 'text_books',
    'text book': 'text_books',
    'reference books': 'reference_books',
    'reference book': 'reference_books',
}


def compact(value):
    return re.sub(r'[^a-z0-9]+', '', (value or '').lower())


def normalize_subject_name(value):
    normalized = compact(value)
    replacements = {
        'structures': 'structure',
        'systems': 'system',
        'algorithms': 'algorithm',
        'administration': 'administrator',
    }
    for old, new in replacements.items():
        normalized = normalized.replace(old, new)
    return normalized


def clean(value):
    return (value or '').strip()


def append_text(current, value):
    value = clean(value)
    if not value:
        return current
    current = clean(current)
    return f'{current}\n{value}' if current else value


def unique_unit_slug(syllabus, title, used_slugs):
    max_length = SyllabusUnit._meta.get_field('slug').max_length or 50
    base = (slugify(title) or 'unit')[:max_length].rstrip('-') or 'unit'
    slug = base
    index = 2
    while slug in used_slugs or SyllabusUnit.objects.filter(syllabus=syllabus, slug=slug).exists():
        suffix = f'-{index}'
        slug_base = base[:max_length - len(suffix)].rstrip('-') or 'unit'
        slug = f'{slug_base}{suffix}'
        index += 1
    used_slugs.add(slug)
    return slug


class Command(BaseCommand):
    help = 'Import structured syllabus CSV rows into Syllabus, SyllabusUnit, and SyllabusSection.'

    def add_arguments(self, parser):
        parser.add_argument(
            'csv_path',
            nargs='?',
            default='../syllabus_csv_by_semester/syllabus_csv_by_semester/all_subjects_syllabus.csv',
            help='Path to all_subjects_syllabus.csv.',
        )

    def handle(self, *args, **options):
        csv_path = Path(options['csv_path']).resolve()
        if not csv_path.exists():
            raise CommandError(f'Syllabus CSV not found: {csv_path}')

        with csv_path.open(newline='', encoding='utf-8-sig') as handle:
            rows = list(csv.DictReader(handle))

        grouped_rows = defaultdict(list)
        for row in rows:
            key = (
                clean(row.get('semester')),
                clean(row.get('course_code')),
                clean(row.get('course_title')),
            )
            grouped_rows[key].append(row)

        imported_subjects = 0
        imported_units = 0
        imported_sections = 0

        for (semester_label, course_code, course_title), subject_rows in grouped_rows.items():
            semester_number = ROMAN_SEMESTERS.get(semester_label)
            if not semester_number:
                self.stdout.write(self.style.WARNING(f'Skipped unknown semester {semester_label}: {course_title}'))
                continue

            semester, _ = Semester.objects.get_or_create(
                name=f'Semester {semester_number}',
                defaults={'slug': f'semester-{semester_number}'},
            )
            subject = self.get_or_create_subject(semester, course_title)
            first_row = subject_rows[0]

            syllabus, _ = Syllabus.objects.get_or_create(subject=subject)
            syllabus.course_title = course_title
            syllabus.course_no = course_code
            syllabus.semester_label = semester_label
            syllabus.nature = clean(first_row.get('nature'))
            syllabus.full_marks = clean(first_row.get('full_marks'))
            syllabus.pass_marks = clean(first_row.get('pass_marks'))
            syllabus.credit_hours = clean(first_row.get('credit_hrs'))
            syllabus.course_description = ''
            syllabus.course_objective = ''
            syllabus.laboratory_work = ''
            syllabus.text_books = ''
            syllabus.reference_books = ''
            syllabus.save()

            syllabus.units.all().delete()
            syllabus.sections.all().delete()

            section_order = 1
            used_slugs = set()
            for row in subject_rows:
                section = clean(row.get('section'))
                section_key = section.lower()
                content = clean(row.get('content'))

                if section_key == 'course contents':
                    unit_no = clean(row.get('unit_no'))
                    unit_title = clean(row.get('unit_title')) or f'Unit {unit_no}'
                    if not unit_no:
                        continue

                    unit = SyllabusUnit.objects.create(
                        syllabus=syllabus,
                        title=unit_title,
                        slug=unique_unit_slug(syllabus, unit_title, used_slugs),
                        duration=clean(row.get('hours')),
                        content=content,
                        order=self.parse_order(unit_no),
                    )
                    imported_units += 1
                    used_slugs.add(unit.slug)
                    continue

                field_name = FIELD_SECTIONS.get(section_key)
                if field_name:
                    setattr(syllabus, field_name, append_text(getattr(syllabus, field_name), content))
                    continue

                if content:
                    SyllabusSection.objects.create(
                        syllabus=syllabus,
                        title=section,
                        content=content,
                        order=section_order,
                    )
                    imported_sections += 1
                    section_order += 1

            syllabus.save()
            imported_subjects += 1

        self.stdout.write(
            self.style.SUCCESS(
                f'Imported {imported_subjects} syllabi, {imported_units} units, and {imported_sections} extra sections.'
            )
        )

    def get_or_create_subject(self, semester, course_title):
        target = normalize_subject_name(course_title)
        for subject in Subject.objects.filter(semester=semester):
            if normalize_subject_name(subject.name) == target:
                return subject

        slug_base = slugify(course_title) or 'subject'
        slug = slug_base
        index = 2
        while Subject.objects.filter(slug=slug).exists():
            slug = f'{slug_base}-{index}'
            index += 1

        return Subject.objects.create(semester=semester, name=course_title, slug=slug)

    def parse_order(self, value):
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return 0
