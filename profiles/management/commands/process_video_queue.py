import time

from django.core.management.base import BaseCommand
from django.utils import timezone

from profiles.models import VideoInspection


class Command(BaseCommand):
    help = 'Обрабатывает очередь видео-проверок СИЗ'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Video worker started'))

        # Сбрасываем зависшие проверки после прошлых падений/перезапусков
        VideoInspection.objects.filter(
            status='processing',
            finished_at__isnull=True
        ).update(
            status='queued',
            error='',
            started_at=None,
            finished_at=None
        )

        while True:
            inspection = (
                VideoInspection.objects
                .filter(status='queued')
                .order_by('created_at')
                .first()
            )

            if not inspection:
                time.sleep(2)
                continue

            # Сразу показываем в интерфейсе, что проверка уже взята в работу
            VideoInspection.objects.filter(id=inspection.id, status='queued').update(
                status='processing',
                started_at=timezone.now(),
                error=''
            )

            self.stdout.write(f'Processing video inspection #{inspection.id}')

            try:
                from profiles.ppe_video import run_inspection

                run_inspection(inspection.id)
                self.stdout.write(self.style.SUCCESS(f'Inspection #{inspection.id} done'))

            except Exception as e:
                VideoInspection.objects.filter(id=inspection.id).update(
                    status='failed',
                    finished_at=timezone.now(),
                    error=str(e)
                )
                self.stdout.write(self.style.ERROR(f'Inspection #{inspection.id} failed: {e}'))
