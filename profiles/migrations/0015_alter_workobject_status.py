from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('profiles', '0014_remove_certificationtest_creator_content_type_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='workobject',
            name='status',
            field=models.CharField(
                choices=[
                    ('waiting', 'Ожидание начала'),
                    ('in_progress', 'Выполняется'),
                    ('completed', 'Завершен'),
                    ('cancelled', 'Отменен'),
                ],
                default='waiting',
                max_length=20,
                verbose_name='Статус',
            ),
        ),
    ]
