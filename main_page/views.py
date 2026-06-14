from django.shortcuts import render, redirect
from django.contrib import messages
from .forms import LoginForm, UserRegistrationForm
from .models import User, Admin, Inspector, Medic, Position
from django.http import JsonResponse


def main_page(request):
    return render(request, 'main_page/main_page.html', {'hide_footer': False, 'hide_menu': True})


def about(request):
    return render(request, 'main_page/about.html', {'hide_footer': True, 'hide_menu': True})


def login(request):
    if request.method == 'POST':
        form = LoginForm(request.POST)

        if form.is_valid():
            username = form.cleaned_data['username']
            password = form.cleaned_data['password']

            try:
                admin = Admin.objects.get(login=username)
                if admin.check_password(password):
                    request.session['user_id'] = admin.id
                    request.session['user_login'] = admin.login
                    request.session['user_role'] = 'admin'
                    return redirect('profiles:dashboard')
            except Admin.DoesNotExist:
                pass

            try:
                inspector = Inspector.objects.get(login=username)
                if inspector.check_password(password):
                    request.session['user_id'] = inspector.id
                    request.session['user_login'] = inspector.login
                    request.session['user_role'] = 'inspector'
                    return redirect('profiles:dashboard')
            except Inspector.DoesNotExist:
                pass

            try:
                medic = Medic.objects.get(login=username)
                if medic.check_password(password):
                    request.session['user_id'] = medic.id
                    request.session['user_login'] = medic.login
                    request.session['user_role'] = 'medic'
                    return redirect('profiles:dashboard')
            except Medic.DoesNotExist:
                pass

            try:
                user = User.objects.get(login=username)
                if user.check_password(password) and user.isActive:
                    request.session['user_id'] = user.id
                    request.session['user_login'] = user.login
                    request.session['user_role'] = 'user'
                    return redirect('profiles:dashboard')
                elif user.check_password(password) and not user.isActive:
                    messages.error(request, 'Ваша учетная запись еще не подтверждена администратором')
                    return redirect('main_page:login')
            except User.DoesNotExist:
                pass

            return render(request, 'main_page/login.html', {
                'form': form,
                'error': 'Неверный логин или пароль',
                'hide_footer': True,
                'hide_menu': True
            })
    else:
        form = LoginForm()

    return render(request, 'main_page/login.html', {'form': form, 'hide_footer': True, 'hide_menu': True})


def registration(request):
    if request.method == 'POST':
        form = UserRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()

            messages.success(
                request,
                f'Регистрация успешна! Ваш логин для авторизации: {user.login}'
            )

            messages.success(
                request,
                'Дождитесь подтверждения администратора'
            )

            return redirect('main_page:login')
    else:
        form = UserRegistrationForm()

    return render(request, 'main_page/registration.html', {'form': form, 'hide_footer': True, 'hide_menu': True})


def get_positions_by_department(request):
    department_id = request.GET.get('department_id')
    if department_id:
        positions = Position.objects.filter(
            department_id=department_id
        ).values('id', 'name').order_by('name')
        return JsonResponse(list(positions), safe=False)
    return JsonResponse([], safe=False)
