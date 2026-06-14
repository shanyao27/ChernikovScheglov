from django.core.management.base import BaseCommand
from main_page.models import Admin, Department, Inspector, Medic, Position
from profiles.models import Camera, ViolationType


DEPARTMENTS = [
    ('kip', 'Участок КИП', 'Контрольно-измерительные приборы и автоматика'),
    ('electro', 'Электроучасток', 'Электрика и электрооборудование'),
    ('garage', 'Транспортный участок', 'Водители и транспорт'),
    ('mechanic', 'Механический участок', 'Ремонт и обслуживание оборудования'),
]

POSITIONS = {
    'kip': [
        'Слесарь КИПиА',
        'Приборщик',
    ],
    'electro': [
        'Электромонтер',
        'Электрик',
    ],
    'garage': [
        'Водитель',
        'Механик',
    ],
    'mechanic': [
        'Слесарь-ремонтник',
        'Токарь',
        'Сварщик',
    ],
}

CAMERAS = {
    'kip': ['КИП-01 Щитовая', 'КИП-02 Насосная'],
    'electro': ['ЭЛ-01 Подстанция', 'ЭЛ-02 РУ-6кВ'],
    'garage': ['ГАР-01 Въезд', 'ГАР-02 Ремзона'],
    'safety': ['ОТ-01 Склад СИЗ', 'ОТ-02 Общая проходная'],
    'mechanic': ['МЕХ-01 Цех', 'МЕХ-02 Участок сварки'],
}

VIOLATIONS = [
    ('Пропуск утреннего медосмотра', 'medical', 'medium', 'explanation'),
    ('Не допущен по результатам осмотра', 'medical', 'high', 'suspension'),
    ('Неявка на наряд', 'work_order', 'medium', 'warning'),
    ('Просрочка закрытия наряда', 'work_order', 'medium', 'explanation'),
    ('Повторный срыв срока наряда', 'work_order', 'high', 'fine'),
    ('Отсутствие каски', 'ppe', 'high', 'fine'),
    ('Отсутствие маски', 'ppe', 'medium', 'warning'),
    ('Грубое нарушение требований СИЗ', 'ppe', 'critical', 'dismissal_notice'),
    ('Нарушение трудовой дисциплины', 'discipline', 'medium', 'warning'),
]


class Command(BaseCommand):
    help = 'Заполняет проект базовыми участками, должностями, камерами и типами нарушений.'

    def handle(self, *args, **options):
        dep_map = {}

        for code, name, description in DEPARTMENTS:
            dep, created = Department.objects.get_or_create(
                code=code,
                defaults={'name': name, 'description': description}
            )
            if not created and dep.name != name:
                dep.name = name
                dep.description = description
                dep.save()
            dep_map[code] = dep

        for code, positions in POSITIONS.items():
            dep = dep_map[code]

            for position_name in positions:
                Position.objects.get_or_create(
                    department=dep,
                    name=position_name,
                )

        for code, cameras in CAMERAS.items():
            dep = dep_map.get(code)
            if dep is None:
                continue

            for camera_name in cameras:
                zone = camera_name.split(' ', 1)[-1] if ' ' in camera_name else camera_name

                camera, created = Camera.objects.get_or_create(
                    department=dep,
                    name=camera_name,
                    defaults={
                        'zone': zone,
                        'is_active': True
                    },
                )

                changed = False
                if camera.zone != zone:
                    camera.zone = zone
                    changed = True
                if not camera.is_active:
                    camera.is_active = True
                    changed = True

                if changed:
                    camera.save()

        for name, category, severity, default_sanction in VIOLATIONS:
            violation, created = ViolationType.objects.get_or_create(
                name=name,
                defaults={
                    'category': category,
                    'severity': severity,
                    'default_sanction': default_sanction,
                    'is_active': True,
                },
            )

            changed = False
            if violation.category != category:
                violation.category = category
                changed = True
            if violation.severity != severity:
                violation.severity = severity
                changed = True
            if violation.default_sanction != default_sanction:
                violation.default_sanction = default_sanction
                changed = True
            if not violation.is_active:
                violation.is_active = True
                changed = True

            if changed:
                violation.save()

        # Глобальный админ
        if not Admin.objects.filter(login='admin').exists():
            Admin.objects.create(login='admin', password='admin', full_name='Глобальный администратор', is_global_admin=True)

        # Администраторы, медработники, инспекторы по участкам
        dept_accounts = [
            ('kip',      'KIP'),
            ('electro',  'electro'),
            ('garage',   'transport'),
            ('mechanic', 'mech'),
        ]
        for dep_code, suffix in dept_accounts:
            dep = dep_map[dep_code]

            login = f'admin_{suffix}'
            if not Admin.objects.filter(login=login).exists():
                Admin.objects.create(login=login, password=login, full_name=f'Администратор ({dep.name})', department=dep, is_global_admin=False)

            login = f'medic_{suffix}'
            if not Medic.objects.filter(login=login).exists():
                Medic.objects.create(login=login, password=login, full_name=f'Медработник ({dep.name})', department=dep)

            login = f'inspector_{suffix}'
            if not Inspector.objects.filter(login=login).exists():
                Inspector.objects.create(login=login, password=login, full_name=f'Инспектор ({dep.name})', department=dep)

        self.stdout.write(self.style.SUCCESS('Базовые справочники предприятия заполнены.'))
