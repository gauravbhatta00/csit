from django.db import migrations


C_PROGRAM_UNITS = [
    (
        1,
        'Problem Solving with Computer',
        '2 Hrs.',
        'Problem analysis, algorithms and flowchart, coding, compilation and execution, history of C, structure of C program, debugging, testing, and documentation.',
    ),
    (
        2,
        'Elements of C',
        '4 Hrs.',
        'C standards, C character set, C tokens, escape sequence, delimiters, variables, data types, structure of a C program, executing a C program, constants, expressions, statements, and comments.',
    ),
    (
        3,
        'Input and Output',
        '2 Hrs.',
        'Conversion specification, reading a character, writing a character, I/O operations, and formatted I/O.',
    ),
    (
        4,
        'Operators and Expression',
        '4 Hrs.',
        'Arithmetic, relational, logical, assignment, ternary, bitwise, increment/decrement, conditional and special operators, expression evaluation, precedence, and associativity.',
    ),
    (
        5,
        'Control Statement',
        '4 Hrs.',
        'Conditional statements, decision making and branching, decision making and looping, exit function, break, and continue.',
    ),
    (
        6,
        'Arrays',
        '6 Hrs.',
        'Array introduction, single and multidimensional arrays, declaration, memory representation, initialization, character arrays, strings, reading and writing strings, null character, and string library functions.',
    ),
    (
        7,
        'Functions',
        '5 Hrs.',
        'Library and user-defined functions, function prototype, call and definition, nested and recursive functions, arguments and return types, passing arrays and strings, value and address passing, and variable scope, visibility, and lifetime.',
    ),
    (
        8,
        'Structure and Union',
        '5 Hrs.',
        'Structures, array of structure, passing structures and arrays of structures to functions, nested structures, union, and pointer to structure.',
    ),
    (
        9,
        'Pointers',
        '6 Hrs.',
        'Pointer introduction, address and indirection operators, pointer declaration, pointer chains, pointer arithmetic, pointers and arrays, character strings, array of pointers, function arguments, function-returned pointers, structures, and dynamic memory allocation.',
    ),
    (
        10,
        'File Handling in C',
        '4 Hrs.',
        'File concepts, opening and closing files, input/output operations in files, random access, and file error handling.',
    ),
    (
        11,
        'Introduction to Graphics',
        '3 Hrs.',
        'Graphics concepts, graphics initialization and modes, and graphics functions.',
    ),
]


def seed_c_program_syllabus(apps, schema_editor):
    Subject = apps.get_model('academics', 'Subject')
    Syllabus = apps.get_model('academics', 'Syllabus')
    SyllabusUnit = apps.get_model('academics', 'SyllabusUnit')

    subject = Subject.objects.filter(slug='c-program').first()
    if subject is None:
        return

    syllabus, _ = Syllabus.objects.get_or_create(subject=subject)
    syllabus.course_title = 'C Programming'
    syllabus.course_no = 'CSC115'
    syllabus.semester_label = 'I'
    syllabus.nature = 'Theory + Lab'
    syllabus.full_marks = '60 + 20 + 20'
    syllabus.pass_marks = '24 + 8 + 8'
    syllabus.credit_hours = '3'
    syllabus.course_description = (
        'This course covers the concepts of structured programming using C '
        'programming language.'
    )
    syllabus.course_objective = (
        'This course is designed to familiarize students with programming '
        'techniques in C.'
    )
    syllabus.laboratory_work = (
        'Students should practice creating, compiling, debugging, running, and '
        'testing C programs; using data types, operators, control statements, '
        'arrays, functions, structures, pointers, file handling, and basic '
        'graphics functions. A small integrated project is encouraged.'
    )
    syllabus.text_books = '\n'.join([
        'Byron Gottfried, Programming with C, Second Edition, McGraw Hill Education',
        'Herbert Schildt, C: The Complete Reference, Fourth Edition, Osborne/McGraw-Hill Publication',
    ])
    syllabus.reference_books = '\n'.join([
        'Paul Deitel and Harvey Deitel, C: How to Program, Eighth Edition, Pearson Publication',
        'Al Kelley and Ira Pohl, A Book on C, Fourth Edition, Pearson Education',
        'Brian W. Kernighan and Dennis M. Ritchie, The C Programming Language, Second Edition, PHI Publication',
        'Ajay Mittal, Programming in C: A Practical Approach, Pearson Publication',
        'Stephen G. Kochan, Programming in C, CBS Publishers and Distributors',
        'E. Balagurusamy, Programming in ANSI C, Third Edition, TMH Publishing',
    ])
    syllabus.save()

    for order, title, duration, content in C_PROGRAM_UNITS:
        SyllabusUnit.objects.update_or_create(
            syllabus=syllabus,
            slug=f'unit-{order}',
            defaults={
                'title': title,
                'duration': duration,
                'content': content,
                'order': order,
            },
        )


def reverse_seed_c_program_syllabus(apps, schema_editor):
    Subject = apps.get_model('academics', 'Subject')
    SyllabusUnit = apps.get_model('academics', 'SyllabusUnit')

    subject = Subject.objects.filter(slug='c-program').first()
    if subject is None:
        return

    SyllabusUnit.objects.filter(syllabus__subject=subject).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('academics', '0008_seed_iit_structured_syllabus'),
    ]

    operations = [
        migrations.RunPython(seed_c_program_syllabus, reverse_seed_c_program_syllabus),
    ]
