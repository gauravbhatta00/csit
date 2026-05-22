from django.db import migrations


IIT_UNITS = [
    (
        1,
        'Introduction to Computer',
        '3 Hrs.',
        'Introduction; digital and analog computers; characteristics, history, generations, and classification of computers; computer system; applications of computers.',
    ),
    (
        2,
        'The Computer System Hardware',
        '3 Hrs.',
        'Central processing unit, memory unit, instruction format, instruction set, instruction cycle, microprocessor, interconnecting computer units, and inside a computer cabinet.',
    ),
    (
        3,
        'Computer Memory',
        '4 Hrs.',
        'Memory representation and hierarchy, CPU registers, cache, primary and secondary memory, storage access types, magnetic tape and disk, optical disk, magneto-optical disk, and memory use.',
    ),
    (
        4,
        'Input and Output Devices',
        '4 Hrs.',
        'Input-output unit, input devices, human data entry devices, source data entry devices, output devices, I/O port, and working of I/O systems.',
    ),
    (
        5,
        'Data Representation',
        '6 Hrs.',
        'Number systems and conversions, binary arithmetic, signed and unsigned numbers, binary data representation, binary coding schemes, and logic gates.',
    ),
    (
        6,
        'Computer Software',
        '6 Hrs.',
        'Types of software, system and application software, software acquisition, and operating system concepts including process, memory, file, device, protection, security, and user-interface management.',
    ),
    (
        7,
        'Data Communication and Computer Network',
        '5 Hrs.',
        'Networking importance, transmission media, data transmission and networking, network types, topology, communication protocol, network devices, and wireless networking.',
    ),
    (
        8,
        'The Internet and Internet Services',
        '4 Hrs.',
        'Internet history, internetworking protocols, architecture and management, connectivity, internet addresses and services, IoT, wearable and cloud computing, e-commerce, e-governance, smart city, and GIS.',
    ),
    (
        9,
        'Fundamentals of Database',
        '4 Hrs.',
        'Database concepts, database systems, DBMS, database system architectures, applications, data warehousing, data mining, and big data.',
    ),
    (
        10,
        'Multimedia',
        '3 Hrs.',
        'Multimedia definition, characteristics, elements, and applications.',
    ),
    (
        11,
        'Computer Security',
        '3 Hrs.',
        'Security threats and attacks, malicious software, security services and mechanisms, cryptography, digital signature, firewall, user identification and authentication, intrusion detection systems, security awareness, and security policy.',
    ),
]


def seed_iit_syllabus(apps, schema_editor):
    Subject = apps.get_model('academics', 'Subject')
    Syllabus = apps.get_model('academics', 'Syllabus')
    SyllabusUnit = apps.get_model('academics', 'SyllabusUnit')

    subject = Subject.objects.filter(slug='iit').first()
    if subject is None:
        return

    syllabus, _ = Syllabus.objects.get_or_create(subject=subject)
    syllabus.course_title = 'Introduction to Information Technology'
    syllabus.course_no = 'CSC114'
    syllabus.semester_label = 'I'
    syllabus.nature = 'Theory + Lab'
    syllabus.full_marks = '60 + 20 + 20'
    syllabus.pass_marks = '24 + 8 + 8'
    syllabus.credit_hours = '3'
    syllabus.course_description = (
        'This course covers basic concepts of computers and information technology, '
        'including hardware, software, memory, input/output, data representation, '
        'database, networking, internet services, multimedia, and computer security.'
    )
    syllabus.course_objective = (
        'To provide students with foundational knowledge of computer and information '
        'technology concepts.'
    )
    syllabus.laboratory_work = (
        'Students should gain practical knowledge of computer hardware components, '
        'operating systems, word processors, spreadsheets, presentation graphics, '
        'management systems, and internet services.'
    )
    syllabus.text_books = 'Computer Fundamentals, Anita Goel, Pearson Education India'
    syllabus.reference_books = '\n'.join([
        'Introduction to Computers, Peter Norton, 7th Edition, McGraw Hill Education',
        'Computer Fundamentals, Pradeep K. Sinha and Priti Sinha',
        'Data Mining Concepts and Techniques, Third Edition, Jiawei Han, Micheline Kamber and Jian Pei',
        'Cloud Computing Bible, Barrie Sosinsky, Wiley',
    ])
    syllabus.save()

    for order, title, duration, content in IIT_UNITS:
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


def reverse_seed_iit_syllabus(apps, schema_editor):
    Subject = apps.get_model('academics', 'Subject')
    SyllabusUnit = apps.get_model('academics', 'SyllabusUnit')

    subject = Subject.objects.filter(slug='iit').first()
    if subject is None:
        return

    SyllabusUnit.objects.filter(syllabus__subject=subject).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('academics', '0007_syllabus_course_description_syllabus_course_no_and_more'),
    ]

    operations = [
        migrations.RunPython(seed_iit_syllabus, reverse_seed_iit_syllabus),
    ]
