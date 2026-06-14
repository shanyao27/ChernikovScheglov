import re
from django import forms
from .models import User, Department, Position
from django.contrib.auth.hashers import make_password


class LoginForm(forms.Form):
    username = forms.CharField(
        label="Логин",
        max_length=50,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Введите логин'})
    )
    password = forms.CharField(
        label="Пароль",
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Введите пароль'})
    )


class UserRegistrationForm(forms.ModelForm):
    password = forms.CharField(
        label="Пароль",
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Введите пароль'})
    )
    password2 = forms.CharField(
        label="Подтверждение пароля",
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Повторите пароль'})
    )

    class Meta:
        model = User
        fields = ['FIO', 'passportData', 'number', 'address', 'department', 'position', 'role']
        widgets = {
            'FIO': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Иванов Иван Иванович'}),
            'passportData': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '1234 567890'}),
            'number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '+79991234567'}),
            'address': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'г. Москва, ул. Ленина, д. 1'}),
            'department': forms.Select(attrs={'class': 'form-control', 'id': 'id_department'}),
            'position': forms.Select(attrs={'class': 'form-control', 'id': 'id_position'}),
            'role': forms.Select(attrs={'class': 'form-control'}),
        }
        labels = {
            'FIO': 'ФИО',
            'passportData': 'Паспорт',
            'number': 'Телефон',
            'address': 'Адрес',
            'department': 'Участок',
            'position': 'Штатная должность',
            'role': 'Роль в наряде',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields['FIO'].required = True
        self.fields['passportData'].required = True
        self.fields['number'].required = True
        self.fields['address'].required = True
        self.fields['role'].required = True
        self.fields['department'].required = True
        self.fields['position'].required = True

        self.fields['department'].queryset = Department.objects.order_by('name')

        department_id = None
        if self.data.get('department'):
            department_id = self.data.get('department')
        elif self.instance and self.instance.department_id:
            department_id = self.instance.department_id

        if department_id:
            self.fields['position'].queryset = Position.objects.filter(
                department_id=department_id
            ).order_by('name')

            if self.data.get('position'):
                try:
                    selected_pos = Position.objects.get(id=self.data.get('position'))
                    if selected_pos not in self.fields['position'].queryset:
                        self.fields['position'].queryset = self.fields['position'].queryset | Position.objects.filter(id=selected_pos.id)
                except Position.DoesNotExist:
                    pass
        else:
            self.fields['position'].queryset = Position.objects.none()

    def clean_department(self):
        department = self.cleaned_data.get('department')
        if not department:
            raise forms.ValidationError('Участок обязателен для выбора')
        return department

    def clean_position(self):
        department = self.cleaned_data.get('department')
        position = self.cleaned_data.get('position')

        if not position:
            raise forms.ValidationError('Должность обязательна для выбора')

        if isinstance(position, (int, str)) and str(position).isdigit():
            try:
                position_obj = Position.objects.get(id=int(position))
            except Position.DoesNotExist:
                raise forms.ValidationError('Выбранная должность не найдена')
        else:
            position_obj = position

        if department and position_obj.department_id != department.id:
            raise forms.ValidationError(f'Должность "{position_obj.name}" не принадлежит выбранному участку "{department.name}"')

        return position_obj

    def clean_password2(self):
        password = self.cleaned_data.get('password')
        password2 = self.cleaned_data.get('password2')

        if password and password2 and password != password2:
            raise forms.ValidationError('Пароли не совпадают')
        return password2

    def clean_FIO(self):
        fio = self.cleaned_data.get('FIO')
        if not fio or not fio.strip():
            raise forms.ValidationError('ФИО обязательно для заполнения')

        parts = fio.strip().split()
        if len(parts) < 2:
            raise forms.ValidationError('ФИО должно содержать как минимум фамилию и имя')

        return fio

    def clean_passportData(self):
        passport = self.cleaned_data.get('passportData')
        if not passport:
            raise forms.ValidationError('Паспорт обязателен для заполнения')

        passport_clean = passport.replace(' ', '')

        if User.objects.filter(passportData__icontains=passport_clean).exists():
            raise forms.ValidationError('Пользователь с таким паспортом уже зарегистрирован')
        return passport

    def clean_number(self):
        number = self.cleaned_data.get('number')
        if not number:
            raise forms.ValidationError('Номер телефона обязателен для заполнения')

        number_clean = re.sub(r'[^\d]', '', number)
        if len(number_clean) < 10:
            raise forms.ValidationError('Введите корректный номер телефона')

        if User.objects.filter(number__icontains=number_clean).exists():
            raise forms.ValidationError('Пользователь с таким номером телефона уже зарегистрирован')
        return number

    def clean_address(self):
        address = self.cleaned_data.get('address')
        if not address:
            raise forms.ValidationError('Адрес обязателен для заполнения')
        return address

    def clean_role(self):
        role = self.cleaned_data.get('role')
        if not role:
            raise forms.ValidationError('Роль обязательна для выбора')
        return role

    def _translit(self, text):
        translit_dict = {
            'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'e',
            'ж': 'zh', 'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm',
            'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u',
            'ф': 'f', 'х': 'kh', 'ц': 'ts', 'ч': 'ch', 'ш': 'sh', 'щ': 'shch',
            'ъ': '', 'ы': 'y', 'ь': '', 'э': 'e', 'ю': 'yu', 'я': 'ya'
        }
        result = ''
        for char in text.lower():
            result += translit_dict.get(char, char)
        return result

    def generate_login(self, fio):
        if not fio or not fio.strip():
            raise forms.ValidationError('ФИО не может быть пустым')

        parts = fio.strip().split()
        if len(parts) < 2:
            raise forms.ValidationError('ФИО должно содержать фамилию и имя')

        last_name = parts[0]
        first_name = parts[1]
        middle_name = parts[2] if len(parts) > 2 else ''

        translit_last = self._translit(last_name).capitalize()
        first_initial = self._translit(first_name[0]).upper() if first_name else ''
        middle_initial = self._translit(middle_name[0]).upper() if middle_name else ''

        if first_initial and middle_initial:
            base_login = f"{translit_last}.{first_initial}{middle_initial}"
        elif first_initial:
            base_login = f"{translit_last}.{first_initial}"
        else:
            base_login = translit_last

        login = base_login
        counter = 1

        while User.objects.filter(login=login).exists():
            login = f"{base_login}{counter}"
            counter += 1

        return login

    def save(self, commit=True):
        user = super().save(commit=False)
        user.login = self.generate_login(self.cleaned_data['FIO'])
        user.password = make_password(self.cleaned_data['password'])
        user.isActive = False

        if commit:
            user.save()

            from profiles.models import Document
            all_docs = Document.objects.all()
            if all_docs.exists():
                user.documents.set(all_docs)

        return user
