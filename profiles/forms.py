from django import forms
from datetime import timedelta
from django.db.models import Q
from .models import (
    WorkObject,
    CertificationTest,
    Question,
    Document,
    VideoInspection,
    MedicalCheck,
    SickLeave,
    Sanction,
)
from main_page.models import Department, User, Admin, Position


class WorkObjectForm(forms.ModelForm):
    class Meta:
        model = WorkObject
        fields = [
            'department', 'zone', 'work_type', 'description', 'employeesNeeded', 'employees',
            'leadEmployee', 'responsible_admin', 'payment', 'time', 'duration', 'close_grace_minutes'
        ]
        widgets = {
            'department': forms.Select(attrs={'class': 'form-control'}),
            'zone': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Зона выполнения работ'}),
            'work_type': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Вид работ'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 4}),
            'employeesNeeded': forms.NumberInput(attrs={'class': 'form-control', 'min': 1}),
            'employees': forms.SelectMultiple(attrs={'class': 'form-control'}),
            'leadEmployee': forms.Select(attrs={'class': 'form-control'}),
            'responsible_admin': forms.Select(attrs={'class': 'form-control'}),
            'payment': forms.NumberInput(attrs={'class': 'form-control', 'min': 0}),
            'time': forms.DateTimeInput(attrs={'class': 'form-control', 'type': 'datetime-local'}),
            'duration': forms.NumberInput(attrs={'class': 'form-control', 'min': 1}),
            'close_grace_minutes': forms.NumberInput(attrs={'class': 'form-control', 'min': 1}),
        }

    def __init__(self, *args, **kwargs):
        current_admin = kwargs.pop('current_admin', None)
        super().__init__(*args, **kwargs)

        for field_name in ['zone', 'work_type', 'employeesNeeded', 'payment', 'time', 'duration', 'close_grace_minutes']:
            if field_name in self.fields:
                self.fields[field_name].required = True

        self.fields['leadEmployee'].required = False
        self.fields['leadEmployee'].empty_label = "Не выбран"

        if current_admin and current_admin.department_id:
            self.fields['department'].queryset = Department.objects.filter(id=current_admin.department_id)
            self.fields['department'].initial = current_admin.department_id
            self.fields['department'].disabled = True
            self.fields['department'].required = True

            self.fields['responsible_admin'].queryset = Admin.objects.filter(
                Q(id=current_admin.id) | Q(is_global_admin=True)
            )
            self.fields['responsible_admin'].initial = current_admin.id
            self.fields['responsible_admin'].disabled = True
            self.fields['responsible_admin'].required = True
        else:
            self.fields['department'].queryset = Department.objects.filter(is_active=True)
            self.fields['responsible_admin'].queryset = Admin.objects.all()
            self.fields['department'].required = True
            self.fields['responsible_admin'].required = True

        if current_admin and current_admin.department_id:
            base_employees = User.objects.filter(
                department_id=current_admin.department_id,
                isActive=True,
            ).exclude(role='lead').exclude(
                employment_status__in=['sick_leave', 'suspended', 'dismissed']
            ).select_related('position', 'department').order_by('position__name', 'FIO')

            lead_employees = User.objects.filter(
                department_id=current_admin.department_id,
                isActive=True,
                role='lead'
            ).exclude(employment_status__in=['sick_leave', 'suspended', 'dismissed']).order_by('FIO')

            self.fields['employees'].queryset = base_employees
            self.fields['leadEmployee'].queryset = lead_employees
        else:
            self.fields['employees'].queryset = User.objects.filter(
                isActive=True
            ).exclude(role='lead').exclude(
                employment_status__in=['sick_leave', 'suspended', 'dismissed']
            ).select_related('position', 'department').order_by('position__name', 'FIO')

            self.fields['leadEmployee'].queryset = User.objects.filter(
                isActive=True,
                role='lead'
            ).exclude(employment_status__in=['sick_leave', 'suspended', 'dismissed']).order_by('FIO')

        if self.instance and self.instance.pk:
            if self.instance.department:
                dept_users = User.objects.filter(
                    department=self.instance.department,
                    isActive=True,
                ).exclude(role='lead').exclude(
                    employment_status__in=['sick_leave', 'suspended', 'dismissed']
                ).order_by('position__name', 'FIO')

                lead_users = User.objects.filter(
                    department=self.instance.department,
                    isActive=True,
                    role='lead'
                ).exclude(employment_status__in=['sick_leave', 'suspended', 'dismissed']).order_by('FIO')

                self.fields['employees'].queryset = dept_users
                self.fields['leadEmployee'].queryset = lead_users

    def clean_time(self):
        from django.utils import timezone as dj_timezone
        from datetime import timedelta

        work_time = self.cleaned_data.get('time')
        if work_time:
            min_allowed_time = dj_timezone.now() + timedelta(days=1)
            if work_time < min_allowed_time:
                raise forms.ValidationError('Время проведения наряда должно быть больше текущего времени минимум на 1 день.')
        return work_time

    def clean(self):
        cleaned_data = super().clean()
        employees = cleaned_data.get('employees', [])
        employees_needed = cleaned_data.get('employeesNeeded')

        if employees_needed is not None and len(employees) < employees_needed:
            self.add_error(
                'employees',
                f'Выбрано сотрудников: {len(employees)}, требуется: {employees_needed}. '
                f'Добавьте ещё {employees_needed - len(employees)} чел.'
            )

        return cleaned_data

    def save(self, commit=True):
        obj = super().save(commit=False)
        obj.address = obj.zone or ''
        if commit:
            obj.save()
            self.save_m2m()
        return obj


class MedicalCheckForm(forms.ModelForm):
    sanction_reason = forms.ChoiceField(
        required=False,
        label='Основание',
        choices=[
            ('', '---------'),
            ('Не допущен по результатам осмотра', 'Не допущен по результатам осмотра'),
            ('Нарушение трудовой дисциплины', 'Нарушение трудовой дисциплины'),
            ('Пропуск утреннего осмотра', 'Пропуск утреннего осмотра'),
            ('Пропуск вечернего осмотра', 'Пропуск вечернего осмотра'),
        ],
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    sanction_type = forms.ChoiceField(
        required=False,
        label='Вид санкции',
        choices=[('', '---------')] + list(Sanction.SANCTION_CHOICES),
        widget=forms.Select(attrs={'class': 'form-control'})
    )

    class Meta:
        model = MedicalCheck
        fields = [
            'employee', 'check_type', 'checked_at', 'decision', 'sanction_reason', 'sanction_type',
            'blood_pressure', 'temperature', 'pulse', 'complaints', 'alcohol_free', 'comment'
        ]
        widgets = {
            'employee': forms.Select(attrs={'class': 'form-control'}),
            'check_type': forms.Select(attrs={'class': 'form-control'}),
            'checked_at': forms.DateTimeInput(attrs={'class': 'form-control', 'type': 'datetime-local'}),
            'decision': forms.Select(attrs={'class': 'form-control'}),
            'blood_pressure': forms.TextInput(attrs={'class': 'form-control'}),
            'temperature': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.1'}),
            'pulse': forms.NumberInput(attrs={'class': 'form-control', 'min': 0}),
            'complaints': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'alcohol_free': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'comment': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        current_admin = kwargs.pop('current_admin', None)
        super().__init__(*args, **kwargs)
        qs = User.objects.filter(isActive=True, system_role='employee').order_by('FIO')
        if current_admin and not current_admin.is_global_admin and current_admin.department_id:
            qs = qs.filter(department_id=current_admin.department_id)
        self.fields['employee'].queryset = qs
        if self.instance and self.instance.pk:
            self.fields['sanction_reason'].initial = self.instance.sanction_reason
            self.fields['sanction_type'].initial = self.instance.sanction_type

    def clean(self):
        cleaned = super().clean()
        if cleaned.get('decision') == 'unfit' and (not cleaned.get('sanction_reason') or not cleaned.get('sanction_type')):
            raise forms.ValidationError('Если сотрудник не допущен, нужно указать основание и вид санкции.')
        return cleaned


class MedicalCheckMedicForm(forms.ModelForm):
    class Meta:
        model = MedicalCheck
        fields = ['check_type', 'checked_at', 'decision',
                  'blood_pressure', 'temperature', 'pulse',
                  'complaints', 'alcohol_free', 'comment']
        widgets = {
            'check_type': forms.Select(attrs={'class': 'form-control'}),
            'checked_at': forms.DateTimeInput(attrs={'class': 'form-control', 'type': 'datetime-local'}),
            'decision': forms.Select(attrs={'class': 'form-control'}),
            'blood_pressure': forms.TextInput(attrs={'class': 'form-control'}),
            'temperature': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.1'}),
            'pulse': forms.NumberInput(attrs={'class': 'form-control', 'min': 0}),
            'complaints': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'alcohol_free': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'comment': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        employee = kwargs.pop('employee', None)
        medic = kwargs.pop('medic', None)
        super().__init__(*args, **kwargs)

        if employee:
            self.instance.employee = employee
        if medic:
            self.instance.medic = medic


class SickLeaveMedicForm(forms.ModelForm):
    class Meta:
        model = SickLeave
        fields = ['start_date', 'end_date', 'reason', 'comment', 'status']
        widgets = {
            'start_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'end_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'reason': forms.TextInput(attrs={'class': 'form-control'}),
            'comment': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'status': forms.Select(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        employee = kwargs.pop('employee', None)
        medic = kwargs.pop('medic', None)
        super().__init__(*args, **kwargs)

        if employee:
            self.instance.employee = employee
        if medic:
            self.instance.issued_by = medic


class SickLeaveForm(forms.ModelForm):
    class Meta:
        model = SickLeave
        fields = ['employee', 'start_date', 'end_date', 'reason', 'comment', 'status']
        widgets = {
            'employee': forms.Select(attrs={'class': 'form-control'}),
            'start_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'end_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'reason': forms.TextInput(attrs={'class': 'form-control'}),
            'comment': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'status': forms.Select(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        current_admin = kwargs.pop('current_admin', None)
        super().__init__(*args, **kwargs)
        qs = User.objects.filter(isActive=True, system_role='employee').order_by('FIO')
        if current_admin and not current_admin.is_global_admin and current_admin.department_id:
            qs = qs.filter(department_id=current_admin.department_id)
        self.fields['employee'].queryset = qs


class SanctionForm(forms.ModelForm):
    class Meta:
        model = Sanction
        fields = ['employee', 'violation_type', 'work_object', 'sanction_type', 'amount', 'comment', 'status', 'expires_at']
        widgets = {
            'employee': forms.Select(attrs={'class': 'form-control'}),
            'violation_type': forms.Select(attrs={'class': 'form-control'}),
            'work_object': forms.Select(attrs={'class': 'form-control'}),
            'sanction_type': forms.Select(attrs={'class': 'form-control'}),
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'min': 0}),
            'comment': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'status': forms.Select(attrs={'class': 'form-control'}),
            'expires_at': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
        }

        labels = {
            'amount': 'Сумма удержания',
            'expires_at': 'Действует до',
        }

    def __init__(self, *args, **kwargs):
        current_admin = kwargs.pop('current_admin', None)
        super().__init__(*args, **kwargs)
        employee_qs = User.objects.filter(isActive=True).order_by('FIO')
        work_qs = WorkObject.objects.order_by('-time')
        if current_admin and not current_admin.is_global_admin and current_admin.department_id:
            employee_qs = employee_qs.filter(department_id=current_admin.department_id)
            work_qs = work_qs.filter(department_id=current_admin.department_id)
        self.fields['employee'].queryset = employee_qs
        self.fields['work_object'].queryset = work_qs


class QuestionForm(forms.ModelForm):
    class Meta:
        model = Question
        fields = ['text', 'option1', 'option2', 'option3', 'correct_answer']
        widgets = {
            'text': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Введите текст вопроса'}),
            'option1': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Первый вариант ответа'}),
            'option2': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Второй вариант ответа'}),
            'option3': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Третий вариант ответа'}),
            'correct_answer': forms.Select(attrs={'class': 'form-control'}),
        }
        labels = {
            'text': 'Текст вопроса',
            'option1': 'Вариант ответа 1',
            'option2': 'Вариант ответа 2',
            'option3': 'Вариант ответа 3',
            'correct_answer': 'Правильный ответ'
        }


class AnswerForm(forms.Form):
    ANSWER_CHOICES = [
        (1, 'Вариант 1'),
        (2, 'Вариант 2'),
        (3, 'Вариант 3'),
    ]

    answer = forms.ChoiceField(
        label='Выберите ответ',
        choices=ANSWER_CHOICES,
        widget=forms.RadioSelect(attrs={'class': 'form-check-input'}),
        required=True
    )


class CertificationTestForm(forms.ModelForm):
    class Meta:
        model = CertificationTest
        fields = ['title', 'department', 'description']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Название аттестации'}),
            'department': forms.Select(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Описание (необязательно)'}),
        }

    def __init__(self, *args, **kwargs):
        current_admin = kwargs.pop('current_admin', None)
        super().__init__(*args, **kwargs)
        qs = Department.objects.order_by('name')
        if current_admin and not current_admin.is_global_admin and current_admin.department_id:
            qs = qs.filter(id=current_admin.department_id)
            self.fields['department'].initial = current_admin.department_id
        self.fields['department'].queryset = qs
        self.fields['department'].required = False


class DocumentForm(forms.ModelForm):
    class Meta:
        model = Document
        fields = ['title', 'description', 'category', 'file']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Например: Инструкция по охране труда'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Краткое описание документа'}),
            'category': forms.Select(attrs={'class': 'form-control'}),
            'file': forms.FileInput(attrs={'class': 'form-control', 'accept': '.pdf'}),
        }
        labels = {
            'title': 'Название документа',
            'description': 'Описание',
            'category': 'Категория',
            'file': 'PDF файл',
        }


class VideoInspectionForm(forms.ModelForm):
    work_object = forms.ModelChoiceField(
        queryset=WorkObject.objects.all().order_by('-time'),
        required=False,
        label='Заказ-наряд',
        widget=forms.Select(attrs={'class': 'form-control'})
    )

    class Meta:
        model = VideoInspection
        fields = ['work_object', 'object_number', 'video', 'check_helmet', 'check_mask', 'violation_seconds', 'frame_stride']
        widgets = {
            'object_number': forms.TextInput(attrs={'class': 'form-control', 'readonly': 'readonly'}),
            'video': forms.ClearableFileInput(attrs={'class': 'form-control'}),
            'check_helmet': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'check_mask': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'violation_seconds': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.5', 'min': 1}),
            'frame_stride': forms.NumberInput(attrs={'class': 'form-control', 'min': 1, 'max': 10}),
        }
        labels = {
            'object_number': 'Зона выполнения работ',
            'video': 'Видео для проверки',
            'check_helmet': 'Проверять каски',
            'check_mask': 'Проверять маски',
            'violation_seconds': 'Порог нарушения (сек)',
            'frame_stride': 'Шаг по кадрам (1 = каждый кадр)',
        }

    def __init__(self, *args, **kwargs):
        inspector = kwargs.pop('inspector', None)
        super().__init__(*args, **kwargs)
        qs = WorkObject.objects.order_by('-time')
        if inspector and inspector.department_id:
            qs = qs.filter(department_id=inspector.department_id)
        self.fields['work_object'].queryset = qs
        selected = self.data.get('work_object') or getattr(self.instance, 'work_object_id', None)
        if selected:
            try:
                wo = qs.get(id=selected)
                self.fields['object_number'].initial = wo.zone
            except Exception:
                pass
        elif self.instance and self.instance.work_object:
            self.fields['object_number'].initial = self.instance.work_object.zone

    def clean(self):
        cleaned = super().clean()
        if not cleaned.get('check_helmet') and not cleaned.get('check_mask'):
            raise forms.ValidationError('Выбери хотя бы один параметр проверки: каски или маски.')
        work_object = cleaned.get('work_object')
        if work_object:
            cleaned['object_number'] = work_object.zone or work_object.address or ''
        return cleaned


class AdminUserProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ['FIO', 'number', 'address', 'department', 'position', 'role', 'employment_status']
        widgets = {
            'FIO': forms.TextInput(attrs={'class': 'form-control'}),
            'number': forms.TextInput(attrs={'class': 'form-control'}),
            'address': forms.TextInput(attrs={'class': 'form-control'}),
            'department': forms.Select(attrs={'class': 'form-control'}),
            'position': forms.Select(attrs={'class': 'form-control'}),
            'role': forms.Select(attrs={'class': 'form-control'}),
            'employment_status': forms.Select(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        current_admin = kwargs.pop('current_admin', None)
        super().__init__(*args, **kwargs)
        departments = Department.objects.all().order_by('name')
        if current_admin and not current_admin.is_global_admin and current_admin.department_id:
            departments = departments.filter(id=current_admin.department_id)
        self.fields['department'].queryset = departments
        self.fields['position'].queryset = Position.objects.order_by('name')
        department = self.data.get('department') or getattr(self.instance, 'department_id', None)
        if department:
            self.fields['position'].queryset = self.fields['position'].queryset.filter(department_id=department)


class AssignExistingTestsForm(forms.Form):
    test = forms.ModelChoiceField(queryset=CertificationTest.objects.none(), label='Тест', widget=forms.Select(attrs={'class': 'form-control'}))
    target_mode = forms.ChoiceField(
        choices=[('single', 'Конкретному сотруднику'), ('department', 'Всем сотрудникам участка')],
        label='Кому назначить',
        widget=forms.Select(attrs={'class': 'form-control'})
    )

    def __init__(self, *args, **kwargs):
        current_admin = kwargs.pop('current_admin', None)
        employee = kwargs.pop('employee', None)
        super().__init__(*args, **kwargs)
        qs = CertificationTest.objects.all().order_by('title')
        if current_admin and not current_admin.is_global_admin and current_admin.department_id:
            qs = qs.filter(Q(department_id=current_admin.department_id) | Q(department__isnull=True))
            self.fields['target_mode'].choices = [('single', 'Конкретному сотруднику'), ('department', 'Всем сотрудникам участка')]
        self.fields['test'].queryset = qs
        if employee is None:
            self.fields['target_mode'].initial = 'department'
