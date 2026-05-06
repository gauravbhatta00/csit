from django.core.management.base import BaseCommand

from academics.models import Question, QuestionSection, Semester, Subject, Year


QUESTION_SETS = {
    "2080": {
        "course_code": "STA169",
        "full_marks": "60 + 20 + 20",
        "pass_marks": "24 + 8 + 8",
        "sections": [
            {
                "title": "Section A",
                "instruction": "Attempt any two questions.",
                "order": 1,
                "marks": "10",
                "questions": [
                    (
                        "Define statistics. Explain its scope and limitations in scientific study.",
                        "Statistics is the science of collecting, organizing, presenting, analyzing, and interpreting numerical data. Its scope includes summarizing large datasets, supporting decision making, forecasting trends, and testing assumptions. Its limitations are that it deals with aggregates, depends on data quality, and can be misused if context and methods are ignored.",
                    ),
                    (
                        "What is standard deviation? Why is it preferred over range as a measure of dispersion?",
                        "Standard deviation measures the average spread of observations from the mean. It is preferred over range because it uses every observation, while range depends only on the largest and smallest values.",
                    ),
                    (
                        "Explain the concept of correlation and write the interpretation of positive, negative, and zero correlation.",
                        "Correlation measures the direction and strength of relationship between two variables. Positive correlation means both variables move in the same direction. Negative correlation means one rises as the other falls. Zero correlation means no linear relationship is observed.",
                    ),
                ],
            },
            {
                "title": "Section B",
                "instruction": "Attempt any eight questions.",
                "order": 2,
                "marks": "5",
                "questions": [
                    (
                        "Calculate the arithmetic mean, median, and mode for the data: 4, 6, 8, 8, 10, 12.",
                        "Mean = (4 + 6 + 8 + 8 + 10 + 12) / 6 = 8. Median = average of the 3rd and 4th values = (8 + 8) / 2 = 8. Mode = 8 because it occurs most frequently.",
                    ),
                    (
                        "Distinguish between discrete and continuous variables with examples.",
                        "A discrete variable takes countable values such as number of students or number of books. A continuous variable can take any value within an interval such as height, weight, or time.",
                    ),
                ],
            },
        ],
    },
    "2079": {
        "course_code": "STA169",
        "full_marks": "60",
        "pass_marks": "24",
        "sections": [
            {
                "title": "Section A",
                "instruction": "Attempt any two questions.",
                "order": 1,
                "marks": "10",
                "questions": [
                    (
                        "Describe the steps involved in a statistical investigation.",
                        "The main steps are defining the problem, planning the enquiry, collecting data, organizing and presenting data, analyzing data, interpreting results, and preparing conclusions or recommendations.",
                    ),
                    (
                        "What is probability? State the addition rule for two events.",
                        "Probability is a numerical measure of the chance that an event will occur. For two events A and B, P(A or B) = P(A) + P(B) - P(A and B). If the events are mutually exclusive, P(A and B) = 0.",
                    ),
                    (
                        "Explain simple random sampling and mention one advantage and one disadvantage.",
                        "Simple random sampling gives every unit of the population an equal chance of selection. Its advantage is that it reduces selection bias. Its disadvantage is that it can be difficult to apply when a complete population list is unavailable.",
                    ),
                ],
            },
            {
                "title": "Section B",
                "instruction": "Attempt any six questions.",
                "order": 2,
                "marks": "5",
                "questions": [
                    (
                        "Find the range and coefficient of range for the observations: 12, 18, 20, 25, 30.",
                        "Largest value = 30 and smallest value = 12. Range = 30 - 12 = 18. Coefficient of range = (30 - 12) / (30 + 12) = 18 / 42 = 0.429 approximately.",
                    ),
                    (
                        "Differentiate between primary data and secondary data.",
                        "Primary data is collected first-hand for a specific purpose, for example through surveys or experiments. Secondary data has already been collected by others, for example from books, reports, or official records.",
                    ),
                ],
            },
        ],
    },
}


class Command(BaseCommand):
    help = "Seed sample Stat1 question sets for two exam years."

    def handle(self, *args, **options):
        semester, _ = Semester.objects.get_or_create(
            slug="second",
            defaults={"name": "Second"},
        )
        subject, _ = Subject.objects.get_or_create(
            slug="stat1",
            defaults={"semester": semester, "name": "Stat1"},
        )

        created_count = 0
        updated_count = 0

        for exam_year, paper in QUESTION_SETS.items():
            year, _ = Year.objects.update_or_create(
                subject=subject,
                year=exam_year,
                defaults={
                    "institution": "Tribhuvan University",
                    "institute": "Institute of Science and Technology",
                    "level": "Bachelor Level / second-semester / Science",
                    "course_code": paper["course_code"],
                    "full_marks": paper["full_marks"],
                    "pass_marks": paper["pass_marks"],
                    "time": "3 Hours",
                },
            )

            question_number = 1
            for section_data in paper["sections"]:
                section, _ = QuestionSection.objects.update_or_create(
                    year=year,
                    title=section_data["title"],
                    defaults={
                        "instruction": section_data["instruction"],
                        "order": section_data["order"],
                    },
                )

                for question_text, answer_text in section_data["questions"]:
                    _, created = Question.objects.update_or_create(
                        year=year,
                        question_text=question_text,
                        defaults={
                            "section": section,
                            "answer_text": answer_text,
                            "marks": section_data["marks"],
                            "order": question_number,
                        },
                    )
                    if created:
                        created_count += 1
                    else:
                        updated_count += 1
                    question_number += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Seeded Stat1 questions: {created_count} created, {updated_count} updated."
            )
        )
