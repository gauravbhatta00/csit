from django.core.management.base import BaseCommand

from academics.models import MockTest, MockTestQuestion, Subject


class Command(BaseCommand):
    help = 'Seed a sample mock test for the STAT subject.'

    def handle(self, *args, **options):
        subject = Subject.objects.filter(slug='stat1').first()

        if not subject:
            self.stdout.write(self.style.WARNING('Subject with slug stat1 not found.'))
            return

        mock_test, _ = MockTest.objects.get_or_create(
            subject=subject,
            title='STAT Quick Practice Test',
            defaults={
                'duration_minutes': 15,
                'total_marks': 5,
                'is_active': True,
            },
        )

        questions = [
            {
                'question_text': 'Which measure is most affected by extreme values?',
                'option_a': 'Median',
                'option_b': 'Mode',
                'option_c': 'Mean',
                'option_d': 'Quartile deviation',
                'correct_option': 'C',
            },
            {
                'question_text': 'If all observations are identical, the standard deviation is:',
                'option_a': '0',
                'option_b': '1',
                'option_c': 'Undefined',
                'option_d': 'Equal to the mean',
                'correct_option': 'A',
            },
            {
                'question_text': 'The probability of an impossible event is:',
                'option_a': '1',
                'option_b': '0',
                'option_c': '0.5',
                'option_d': 'Greater than 1',
                'correct_option': 'B',
            },
            {
                'question_text': 'For a normal distribution, mean, median, and mode are:',
                'option_a': 'All different',
                'option_b': 'Equal',
                'option_c': 'Always negative',
                'option_d': 'Not defined',
                'correct_option': 'B',
            },
            {
                'question_text': 'Correlation coefficient lies between:',
                'option_a': '0 and 1',
                'option_b': '-1 and 1',
                'option_c': '-10 and 10',
                'option_d': '1 and 100',
                'correct_option': 'B',
            },
        ]

        for question in questions:
            MockTestQuestion.objects.get_or_create(
                mock_test=mock_test,
                question_text=question['question_text'],
                defaults={
                    'option_a': question['option_a'],
                    'option_b': question['option_b'],
                    'option_c': question['option_c'],
                    'option_d': question['option_d'],
                    'correct_option': question['correct_option'],
                    'marks': 1,
                },
            )

        mock_test.total_marks = mock_test.questions.count()
        mock_test.save(update_fields=['total_marks'])

        self.stdout.write(
            self.style.SUCCESS(
                f'Seeded {mock_test.title} with {mock_test.questions.count()} questions.'
            )
        )
