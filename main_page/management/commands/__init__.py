from django.core.management.base import BaseCommand
from main_page.models import Department, Position
from profiles.models import Camera, ViolationType


DEPARTMENTS = [
    ('kip', 'Участок КИП', 'Контрольно-измерительные приборы и автоматика'),
    ('electro', 'Электроучасток', 'Электрика и электрооборудование'),
    ('garage', 'Транспортный участок', 'Водители и транспорт'),
    ('mechanic', 'Механический участок', 'Ремонт и обслуживание оборудования'),
]

POSITIONS = {
    'kip': ['Слесарь КИПиА', 'Приборщик'],
    'electro': ['Электромонтер', 'Электрик'],
    'garage': ['Водитель', 'Механик'],
    'mechanic': ['Слесарь-ремонтник', 'Токарь', 'Сварщик'],
}

CAMERAS = {
    'kip': ['КИП-01 Щитовая', 'КИП-02 Насосная'],
    'electro': ['ЭЛ-01 Подстанция', 'ЭЛ-02 РУ-6кВ'],
    'garage': ['ГАР-01 Въезд', 'ГАР-02 Ремзона'],
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

        # Создаем участки
        for code, name, description in DEPARTMENTS:
            dep, created = Department.objects.get_or_create(
                code=code,
                defaults={
                    'name': name,
                    'description': description,
                    'is_active': True
                }
            )
            if not created:
                dep.name = name
                dep.description = description
                dep.is_active = True
                dep.save()
            dep_map[code] = dep
            self.stdout.write(f"Участок: {dep.name} (код: {dep.code})")

        # Создаем должности
        for code, positions in POSITIONS.items():
            dep = dep_map[code]
            for position_name in positions:
                position, created = Position.objects.get_or_create(
                    department=dep,
                    name=position_name,
                    defaults={
                        'is_managerial': False,
                        'requires_medical_check': True,
                        'is_active': True
                    }
                )
                if not created and not position.is_active:
                    position.is_active = True
                    position.save()
                self.stdout.write(f"  Должность: {position_name} ({dep.name})")

        # Создаем камеры
        for code, cameras in CAMERAS.items():
            dep = dep_map.get(code)
            if not dep:
                continue
            for camera_name in cameras:
                zone = camera_name.split(' ', 1)[-1] if ' ' in camera_name else camera_name
                camera, created = Camera.objects.get_or_create(
                    department=dep,
                    name=camera_name,
                    defaults={
                        'zone': zone,
                        'is_active': True
                    }
                )
                if not created and not camera.is_active:
                    camera.is_active = True
                    camera.save()
                self.stdout.write(f"  Камера: {camera_name} ({dep.name})")

        # Создаем типы нарушений
        for name, category, severity, default_sanction in VIOLATIONS:
            violation, created = ViolationType.objects.get_or_create(
                name=name,
                defaults={
                    'category': category,
                    'severity': severity,
                    'default_sanction': default_sanction,
                    'is_active': True,
                }
            )
            if not created:
                violation.category = category
                violation.severity = severity
                violation.default_sanction = default_sanction
                violation.is_active = True
                violation.save()
            self.stdout.write(f"  Нарушение: {name}")

        self.stdout.write(self.style.SUCCESS('Предопределенные данные заполнены'))