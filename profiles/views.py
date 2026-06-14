from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db.models import Q
from django.utils import timezone as dj_timezone
from django.forms.models import modelform_factory
from main_page.models import User, Admin, Inspector, Medic
from datetime import timedelta
from .models import (
    WorkObject, CertificationTest, Question, UserTestAttempt, UserBlock, Document, UserAnswer,
    DocumentSignature, ViolationSnapshot, MedicalCheck, SickLeave, Sanction, Department, VideoInspection, ViolationType
)
from .forms import (
    WorkObjectForm, CertificationTestForm, QuestionForm, DocumentForm,
    MedicalCheckForm, SickLeaveForm, SanctionForm, VideoInspectionForm,
    AdminUserProfileForm, AssignExistingTestsForm, AnswerForm,
    MedicalCheckMedicForm, SickLeaveMedicForm
)


def _get_current_admin(request):
    if request.session.get('user_role') != 'admin':
        return None
    return Admin.objects.filter(id=request.session.get('user_id')).first()


def _get_current_employee(request):
    if request.session.get('user_role') != 'user':
        return None
    return User.objects.filter(id=request.session.get('user_id')).first()


def _get_current_medic(request):
    if request.session.get('user_role') != 'medic':
        return None
    return Medic.objects.filter(id=request.session.get('user_id')).first()


def _medic_required(request):
    if request.session.get('user_role') != 'medic':
        messages.error(request, 'Доступ только для медработника')
        return False
    return True


def _inspector_required(request):
    if request.session.get('user_role') != 'inspector':
        messages.error(request, 'Доступ только для инспектора')
        return False
    return True


def _is_global_admin(admin):
    return bool(admin and admin.is_global_admin)


def _department_filtered_users(admin):
    qs = User.objects.all()
    if admin and not admin.is_global_admin and admin.department_id:
        qs = qs.filter(department_id=admin.department_id)
    return qs


def _department_filtered_work_objects(admin):
    qs = WorkObject.objects.all()
    if admin and not admin.is_global_admin and admin.department_id:
        qs = qs.filter(department_id=admin.department_id)
    return qs


def _available_tests_for_admin(admin, employee=None):
    qs = CertificationTest.objects.all().order_by('title')
    if admin and admin.is_global_admin:
        return qs
    if admin:
        qs = qs.filter(created_by_admin=admin)
    return qs


def _create_or_update_sanction_from_medical_check(check, admin_obj=None):
    if check.decision != 'unfit' or not check.sanction_reason or not check.sanction_type:
        if check.employee_id:
            Sanction.objects.filter(employee=check.employee, comment__icontains=f'[MEDCHECK:{check.id}]', status='active').update(status='cancelled')
        return
    violation_type, _ = ViolationType.objects.get_or_create(
        name=check.sanction_reason,
        defaults={'category': 'medical', 'severity': 'medium', 'default_sanction': check.sanction_type}
    )
    Sanction.objects.update_or_create(
        employee=check.employee,
        comment=f'[MEDCHECK:{check.id}] {check.comment or ""}'.strip(),
        defaults={
            'violation_type': violation_type,
            'sanction_type': check.sanction_type,
            'status': 'active',
            'created_by_admin': admin_obj,
        }
    )
    if check.sanction_type == 'suspension':
        check.employee.employment_status = 'suspended'
        check.employee.save(update_fields=['employment_status'])


def _apply_overdue_work_sanctions():
    now = dj_timezone.now()
    violation_type, _ = ViolationType.objects.get_or_create(
        name='Просрочка закрытия наряда',
        defaults={'category': 'work_order', 'severity': 'medium', 'default_sanction': 'explanation'}
    )
    for work in WorkObject.objects.exclude(status__in=['completed', 'cancelled']):
        deadline = work.planned_end_time or work.deadline
        if not deadline:
            continue
        effective_deadline = deadline + timedelta(minutes=work.close_grace_minutes or 0)
        if now > effective_deadline:
            for employee in work.employees.all():
                Sanction.objects.get_or_create(
                    employee=employee,
                    work_object=work,
                    violation_type=violation_type,
                    sanction_type='explanation',
                    defaults={'comment': f'Автоматическая санкция за просрочку закрытия наряда #{work.id}', 'status': 'active'}
                )


def _sync_reference_statuses():
    today = dj_timezone.localdate()
    now = dj_timezone.now()

    expired_sick = SickLeave.objects.filter(status='active', end_date__lt=today).select_related('employee')
    for item in expired_sick:
        item.status = 'closed'
        item.save(update_fields=['status'])
        employee = item.employee
        if employee and employee.employment_status == 'sick_leave' and employee.active_sick_leave is None:
            employee.employment_status = 'active'
            employee.save(update_fields=['employment_status'])

    expired_sanctions = Sanction.objects.filter(status='active', expires_at__isnull=False, expires_at__lt=today).select_related('employee')
    for item in expired_sanctions:
        item.status = 'expired'
        item.save(update_fields=['status'])
        employee = item.employee
        if employee and employee.employment_status == 'suspended':
            still_active = Sanction.objects.filter(employee=employee, status='active', sanction_type='suspension').exists()
            if not still_active and employee.active_sick_leave is None:
                employee.employment_status = 'active'
                employee.save(update_fields=['employment_status'])

    WorkObject.objects.filter(status='waiting', time__lte=now).update(status='in_progress')

    _apply_overdue_work_sanctions()


def admin_users_list(request):
    _sync_reference_statuses()
    admin = _get_current_admin(request)
    status_filter = request.GET.get('status', 'all')
    search = (request.GET.get('q') or '').strip()
    users = _department_filtered_users(admin).select_related('department', 'position', 'manager').order_by('FIO')

    if search:
        users = users.filter(Q(FIO__icontains=search) | Q(login__icontains=search) | Q(number__icontains=search))
    if status_filter == 'active':
        users = users.filter(isActive=True)
    elif status_filter == 'inactive':
        users = users.filter(isActive=False)
    elif status_filter == 'sick_leave':
        users = users.filter(employment_status='sick_leave')
    elif status_filter == 'suspended':
        users = users.filter(employment_status='suspended')

    return render(request, 'profiles/admin/users_list.html', {
        'users': users,
        'current_filter': status_filter,
        'search_query': search,
        'admin_obj': admin,
    })


def admin_user_detail(request, user_id):
    admin = _get_current_admin(request)
    user = get_object_or_404(_department_filtered_users(admin), id=user_id)

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'save_profile':
            form = AdminUserProfileForm(request.POST, instance=user, current_admin=admin)
            if form.is_valid():
                form.save()
                messages.success(request, 'Анкета сотрудника обновлена')
                return redirect('profiles:admin_user_detail', user_id=user.id)
        elif action == 'assign_test':
            assign_form = AssignExistingTestsForm(request.POST, current_admin=admin, employee=user)
            if assign_form.is_valid():
                test = assign_form.cleaned_data['test']
                mode = assign_form.cleaned_data['target_mode']
                targets = [user]
                if mode == 'department':
                    targets = list(_department_filtered_users(admin).filter(department_id=user.department_id, system_role='employee'))
                assigned = 0
                for target in targets:
                    if not target.assigned_certifications.filter(id=test.id).exists() and not target.certifications.filter(id=test.id).exists():
                        target.assigned_certifications.add(test)
                        assigned += 1
                messages.success(request, f'Тест назначен. Новых назначений: {assigned}')
                return redirect('profiles:admin_user_detail', user_id=user.id)
        elif action == 'call_to_admin':
            UserBlock.objects.create(user=user, expires_at=dj_timezone.now() + timedelta(days=3650), reason='Вызов к руководителю')
            messages.success(request, 'Сотрудник вызван к руководителю и временно заблокирован')
            return redirect('profiles:admin_user_detail', user_id=user.id)
        elif action == 'remove_block':
            UserBlock.objects.filter(user=user, expires_at__gt=dj_timezone.now()).update(expires_at=dj_timezone.now())
            messages.success(request, 'Блокировка сотрудника снята')
            return redirect('profiles:admin_user_detail', user_id=user.id)

    form = AdminUserProfileForm(instance=user, current_admin=admin)
    assign_form = AssignExistingTestsForm(current_admin=admin, employee=user)
    sanctions = user.sanctions.select_related('violation_type', 'work_object').order_by('-created_at')[:20]

    return render(request, 'profiles/admin/user_detail.html', {
        'user': user,
        'form': form,
        'assign_form': assign_form,
        'admin_obj': admin,
        'sanctions': sanctions,
    })


def admin_user_confirm(request, user_id):
    admin = _get_current_admin(request)
    user = get_object_or_404(_department_filtered_users(admin), id=user_id)
    user.isActive = True
    user.employment_status = 'active'
    if not user.hire_date:
        user.hire_date = dj_timezone.localdate()

    assigned_count = 0
    for test in _available_tests_for_admin(admin, user):
        if not user.assigned_certifications.filter(id=test.id).exists() and not user.certifications.filter(id=test.id).exists():
            user.assigned_certifications.add(test)
            assigned_count += 1
    user.save()

    messages.success(request, f'Пользователь {user.FIO} подтвержден. Назначено тестов: {assigned_count}')
    return redirect('profiles:admin_users_list')


def confirm_users(request):
    if request.method == 'POST':
        admin = _get_current_admin(request)
        user_ids = request.POST.getlist('selected_users')
        users = _department_filtered_users(admin).filter(id__in=user_ids)
        total_assigned = 0

        for user in users:
            user.isActive = True
            user.employment_status = 'active'
            if not user.hire_date:
                user.hire_date = dj_timezone.localdate()
            for test in _available_tests_for_admin(admin, user):
                if not user.assigned_certifications.filter(id=test.id).exists() and not user.certifications.filter(id=test.id).exists():
                    user.assigned_certifications.add(test)
                    total_assigned += 1
            user.save()

        messages.success(request, f'Подтверждено пользователей: {users.count()}, назначено тестов: {total_assigned}')
    return redirect('profiles:admin_users_list')


def admin_workobjects_list(request):
    _sync_reference_statuses()
    if request.session.get('user_role') != 'admin':
        return redirect('main_page:login')

    admin_id = request.session.get('user_id')
    current_admin = get_object_or_404(Admin, id=admin_id)

    work_objects = WorkObject.objects.all().order_by('-time')

    if not current_admin.is_global_admin and current_admin.department:
        work_objects = work_objects.filter(department=current_admin.department)

    status_filter = request.GET.get('status', 'all')

    if status_filter == 'waiting':
        work_objects = work_objects.filter(status='waiting')
    elif status_filter == 'in_progress':
        work_objects = work_objects.filter(status='in_progress')
    elif status_filter == 'completed':
        work_objects = work_objects.filter(status='completed')
    elif status_filter == 'cancelled':
        work_objects = work_objects.filter(status='cancelled')

    return render(request, 'profiles/admin/workobjects_list.html', {
        'work_objects': work_objects,
        'now': dj_timezone.now(),
        'current_status': status_filter,
    })


def admin_workobject_create(request):
    if request.session.get('user_role') != 'admin':
        return redirect('main_page:login')

    admin = _get_current_admin(request)
    available_employees = _get_available_employees_for_work(admin)

    if request.method == 'POST':
        form = WorkObjectForm(request.POST, current_admin=admin)
        form.fields['employees'].queryset = available_employees.exclude(role='lead')
        form.fields['leadEmployee'].queryset = available_employees.filter(role='lead')
        if form.is_valid():
            obj = form.save(commit=False)
            obj.created_by_admin = admin
            if admin and not admin.is_global_admin:
                obj.responsible_admin = admin
            obj.save()
            form.save_m2m()
            obj.update_status()
            messages.success(request, 'Наряд создан')
            return redirect('profiles:admin_workobjects_list')
    else:
        form = WorkObjectForm(current_admin=admin)
        form.fields['employees'].queryset = available_employees.exclude(role='lead')
        form.fields['leadEmployee'].queryset = available_employees.filter(role='lead')

    return render(request, 'profiles/admin/workobject_form.html', {
        'form': form,
        'title': 'Создание наряда',
        'admin_obj': admin,
        'available_employees': available_employees,
    })


def admin_workobject_edit(request, pk):
    if request.session.get('user_role') != 'admin':
        messages.error(request, 'Доступ запрещён')
        return redirect('main_page:main_page')

    admin = _get_current_admin(request)
    work_object = get_object_or_404(_department_filtered_work_objects(admin), id=pk)

    if work_object.status == 'cancelled':
        messages.error(request, f'Наряд #{work_object.id} отменён и не может быть отредактирован')
        return redirect('profiles:admin_workobjects_list')

    available_employees = _get_available_employees_for_work(admin)

    assigned_ids = list(work_object.employees.values_list('id', flat=True))
    assigned_lead_id = work_object.leadEmployee_id

    edit_employees_qs = User.objects.filter(
        Q(id__in=available_employees.exclude(role='lead').values_list('id', flat=True)) |
        Q(id__in=assigned_ids)
    ).select_related('position', 'department').order_by('position__name', 'FIO')

    lead_ids = list(available_employees.filter(role='lead').values_list('id', flat=True))
    if assigned_lead_id:
        lead_ids.append(assigned_lead_id)
    edit_leads_qs = User.objects.filter(id__in=lead_ids).select_related('position', 'department').order_by('FIO')

    if request.method == 'POST':
        form = WorkObjectForm(request.POST, instance=work_object, current_admin=admin)
        form.fields['employees'].queryset = edit_employees_qs
        form.fields['leadEmployee'].queryset = edit_leads_qs
        if form.is_valid():
            obj = form.save(commit=False)
            if admin and not admin.is_global_admin:
                obj.responsible_admin = admin
            obj.save()
            form.save_m2m()
            obj.update_status()
            messages.success(request, f'Наряд #{work_object.id} обновлен')
            return redirect('profiles:admin_workobjects_list')
    else:
        form = WorkObjectForm(instance=work_object, current_admin=admin)
        form.fields['employees'].queryset = edit_employees_qs
        form.fields['leadEmployee'].queryset = edit_leads_qs

    return render(request, 'profiles/admin/workobject_form.html', {
        'form': form,
        'title': f'Редактирование заказ-наряда от {work_object.time.strftime("%d.%m.%Y %H:%M")}',
        'admin_obj': admin,
        'work_object': work_object,
        'available_employees': edit_employees_qs,
    })


def admin_workobject_delete(request, pk):
    if request.session.get('user_role') != 'admin':
        messages.error(request, 'Доступ запрещён')
        return redirect('main_page:main_page')

    admin = _get_current_admin(request)
    work_object = get_object_or_404(_department_filtered_work_objects(admin), id=pk)

    if request.method == 'POST':
        if work_object.status == 'cancelled':
            messages.warning(request, f'Наряд #{work_object.id} уже отменён')
        else:
            work_object.status = 'cancelled'
            work_object.save(update_fields=['status'])
            messages.success(request, f'Наряд #{work_object.id} отменён')

    return redirect('profiles:admin_workobjects_list')


def admin_workobject_assign_lead(request, pk):
    if request.session.get('user_role') != 'admin':
        messages.error(request, 'Доступ запрещён')
        return redirect('main_page:main_page')

    admin = _get_current_admin(request)
    work = get_object_or_404(_department_filtered_work_objects(admin), id=pk)
    work.update_status()

    if request.method == 'POST':
        employee_id = request.POST.get('employee_id')
        try:
            available_employees = _get_available_employees_for_work(admin)
            employee = available_employees.filter(id=employee_id, role='lead').first()

            if not employee:
                messages.error(request, 'Сотрудник не может быть назначен старшим')
                return redirect('profiles:admin_workobjects_list')

            work.leadEmployee = employee
            work.save(update_fields=['leadEmployee'])
            messages.success(request, f'Старший назначен: {employee.FIO}')
        except User.DoesNotExist:
            messages.error(request, 'Сотрудник не найден')

    return redirect('profiles:admin_workobjects_list')


def admin_test_list(request):
    user_role = request.session.get('user_role')

    if user_role not in ['admin', 'inspector']:
        messages.error(request, 'Доступ запрещён')
        return redirect('main_page:main_page')

    tests = CertificationTest.objects.all().order_by('-created_at')

    if user_role == 'admin':
        admin = _get_current_admin(request)
        if admin and admin.is_global_admin:
            tests = tests.all()
        else:
            tests = tests.filter(created_by_admin=admin)
    elif user_role == 'inspector':
        inspector = Inspector.objects.get(id=request.session.get('user_id'))
        tests = tests.filter(Q(department_id=inspector.department_id) | Q(department__isnull=True))

    for test in tests:
        passed_ids = set(
            UserTestAttempt.objects.filter(test=test, passed=True, completed_at__isnull=False)
            .values_list('user_id', flat=True).distinct()
        )
        assigned_ids = set(
            User.objects.filter(assigned_certifications=test).values_list('id', flat=True)
        )
        failed_ids = set(
            UserTestAttempt.objects.filter(test=test, passed=False, completed_at__isnull=False)
            .values_list('user_id', flat=True).distinct()
        )
        test.passed_count = len(passed_ids)
        test.not_passed_count = len((assigned_ids | failed_ids) - passed_ids)

    return render(request, 'profiles/admin/test_list.html', {'tests': tests, 'user_role': user_role})


def admin_test_create(request):
    user_role = request.session.get('user_role')
    user_id = request.session.get('user_id')

    if user_role not in ['admin', 'inspector']:
        messages.error(request, 'Доступ запрещён')
        return redirect('main_page:main_page')

    test = CertificationTest(title='Новая аттестация')

    if user_role == 'admin':
        admin = Admin.objects.get(id=user_id)
        test.created_by_admin = admin
        test.department = admin.department
    else:
        inspector = Inspector.objects.get(id=user_id)
        test.department_id = inspector.department_id

    test.save()
    return redirect('profiles:admin_test_edit', test_id=test.id)


def admin_test_edit(request, test_id):
    user_role = request.session.get('user_role')

    if user_role not in ['admin', 'inspector']:
        messages.error(request, 'Доступ запрещён')
        return redirect('main_page:main_page')

    test = get_object_or_404(CertificationTest, id=test_id)
    questions = test.questions.all()

    if user_role == 'admin':
        admin = _get_current_admin(request)
        if not admin.is_global_admin and test.created_by_admin != admin:
            messages.error(request, 'У вас нет прав для редактирования этого теста')
            return redirect('profiles:admin_test_list')
    elif user_role == 'inspector':
        inspector = Inspector.objects.get(id=request.session.get('user_id'))
        if test.department_id and test.department_id != inspector.department_id:
            messages.error(request, 'У вас нет прав для редактирования этого теста')
            return redirect('profiles:admin_test_list')

    current_admin = _get_current_admin(request) if user_role == 'admin' else None

    if request.method == 'POST':
        if 'add_question' in request.POST:
            form = QuestionForm(request.POST)
            info_form = CertificationTestForm(instance=test, current_admin=current_admin)
            if form.is_valid():
                question = form.save(commit=False)
                question.test = test
                question.save()
                messages.success(request, 'Вопрос добавлен')
                return redirect('profiles:admin_test_edit', test_id=test.id)
        elif 'edit_question' in request.POST:
            question_id = request.POST.get('question_id')
            question = get_object_or_404(Question, id=question_id, test=test)
            q_form = QuestionForm(request.POST, instance=question)
            if q_form.is_valid():
                q_form.save()
                messages.success(request, 'Вопрос обновлён')
                return redirect('profiles:admin_test_edit', test_id=test.id)
            form = QuestionForm()
            info_form = CertificationTestForm(instance=test, current_admin=current_admin)
        elif 'delete_question' in request.POST:
            question_id = request.POST.get('question_id')
            question = get_object_or_404(Question, id=question_id, test=test)
            question.delete()
            messages.success(request, 'Вопрос удалён')
            return redirect('profiles:admin_test_edit', test_id=test.id)
        elif 'save_info' in request.POST:
            info_form = CertificationTestForm(request.POST, instance=test, current_admin=current_admin)
            form = QuestionForm()
            if info_form.is_valid():
                info_form.save()
                messages.success(request, 'Информация об аттестации обновлена')
                return redirect('profiles:admin_test_edit', test_id=test.id)
        elif 'finish' in request.POST:
            if questions.count() == 0:
                messages.error(request, 'Нельзя сохранить тест без вопросов! Добавьте хотя бы один вопрос.')
                return redirect('profiles:admin_test_edit', test_id=test.id)
            else:
                messages.success(request, f'Тест "{test.title}" успешно сохранен с {questions.count()} вопросами')
                return redirect('profiles:admin_test_list')
        else:
            form = QuestionForm()
            info_form = CertificationTestForm(instance=test, current_admin=current_admin)
    else:
        form = QuestionForm()
        info_form = CertificationTestForm(instance=test, current_admin=current_admin)

    return render(request, 'profiles/admin/test_edit.html', {
        'test': test,
        'questions': questions,
        'form': form,
        'info_form': info_form,
        'user_role': user_role
    })


def admin_test_delete(request, test_id):
    user_role = request.session.get('user_role')

    if user_role not in ['admin', 'inspector']:
        messages.error(request, 'Доступ запрещён')
        return redirect('main_page:main_page')

    test = get_object_or_404(CertificationTest, id=test_id)

    if user_role == 'admin':
        admin = _get_current_admin(request)
        if not admin.is_global_admin and test.created_by_admin != admin:
            messages.error(request, 'У вас нет прав для удаления этого теста')
            return redirect('profiles:admin_test_list')
    elif user_role == 'inspector':
        inspector = Inspector.objects.get(id=request.session.get('user_id'))
        if test.department_id and test.department_id != inspector.department_id:
            messages.error(request, 'У вас нет прав для удаления этого теста')
            return redirect('profiles:admin_test_list')

    if request.method == 'POST':
        test.delete()
        messages.success(request, 'Тест удалён')
        return redirect('profiles:admin_test_list')

    return render(request, 'profiles/admin/test_confirm_delete.html', {'test': test})


def admin_test_results(request, test_id):
    user_role = request.session.get('user_role')

    if user_role not in ['admin', 'inspector']:
        messages.error(request, 'Доступ запрещён')
        return redirect('main_page:main_page')

    test = get_object_or_404(CertificationTest, id=test_id)
    attempts = UserTestAttempt.objects.filter(test=test).order_by('-completed_at')

    return render(request, 'profiles/admin/test_results.html', {
        'test': test,
        'attempts': attempts
    })


def admin_assign_all_tests_to_all_users(request):
    admin = _get_current_admin(request)

    if request.session.get('user_role') != 'admin':
        messages.error(request, 'Доступ запрещён')
        return redirect('main_page:main_page')

    users = _department_filtered_users(admin).filter(system_role='employee')
    tests = list(_available_tests_for_admin(admin))
    total_assigned = 0

    for user in users:
        for test in tests:
            if not user.assigned_certifications.filter(id=test.id).exists() and not user.certifications.filter(id=test.id).exists():
                user.assigned_certifications.add(test)
                total_assigned += 1

    messages.success(request, f'Тесты назначены сотрудникам. Новых назначений: {total_assigned}')
    return redirect('profiles:admin_users_list')


def admin_test_assign_to_all(request, test_id):
    admin = _get_current_admin(request)

    if not admin:
        messages.error(request, 'Доступ запрещён')
        return redirect('profiles:admin_test_list')

    test = get_object_or_404(CertificationTest, id=test_id)

    if not admin.is_global_admin and test.created_by_admin != admin:
        messages.error(request, 'У вас нет прав для назначения этого теста')
        return redirect('profiles:admin_test_list')

    users = _department_filtered_users(admin).filter(system_role='employee')

    assigned_count = 0
    for user in users:
        if not user.assigned_certifications.filter(id=test.id).exists() and not user.certifications.filter(id=test.id).exists():
            user.assigned_certifications.add(test)
            assigned_count += 1

    messages.success(request, f'Тест "{test.title}" назначен {assigned_count} сотрудникам')
    return redirect('profiles:admin_test_list')


def admin_medical_checks_list(request):
    admin = _get_current_admin(request)
    _sync_reference_statuses()
    q = (request.GET.get('q') or '').strip()
    department_id = request.GET.get('department')

    checks = MedicalCheck.objects.select_related('employee', 'employee__department', 'medic').order_by('-checked_at')

    if admin and not admin.is_global_admin and admin.department_id:
        checks = checks.filter(employee__department_id=admin.department_id)
    if q:
        checks = checks.filter(employee__FIO__icontains=q)
    if department_id:
        checks = checks.filter(employee__department_id=department_id)

    return render(request, 'profiles/admin/medical_checks_list.html', {
        'checks': checks[:200],
        'departments': Department.objects.filter(),
        'search_query': q,
        'department_id': str(department_id or ''),
        'admin_obj': admin,
    })


def admin_medical_check_create(request):
    admin = _get_current_admin(request)

    if request.method == 'POST':
        form = MedicalCheckForm(request.POST, current_admin=admin)
        if form.is_valid():
            check = form.save(commit=False)
            check.check_date = dj_timezone.localtime(check.checked_at).date()
            check.save()
            _create_or_update_sanction_from_medical_check(check, admin)
            messages.success(request, 'Медосмотр сохранен')
            return redirect('profiles:admin_medical_checks_list')
    else:
        form = MedicalCheckForm(current_admin=admin)

    return render(request, 'profiles/admin/medical_check_form.html', {'form': form, 'title': 'Создание медосмотра', 'admin_obj': admin})


def admin_sick_leaves_list(request):
    admin = _get_current_admin(request)
    q = (request.GET.get('q') or '').strip()
    department_id = request.GET.get('department')

    items = SickLeave.objects.select_related('employee', 'employee__department').order_by('-start_date')

    if admin and not admin.is_global_admin and admin.department_id:
        items = items.filter(employee__department_id=admin.department_id)
    if q:
        items = items.filter(employee__FIO__icontains=q)
    if department_id:
        items = items.filter(employee__department_id=department_id)

    return render(request, 'profiles/admin/sick_leaves_list.html', {
        'sick_leaves': items,
        'departments': Department.objects.filter(),
        'search_query': q,
        'department_id': str(department_id or ''),
        'admin_obj': admin,
    })


def admin_sick_leave_create(request):
    admin = _get_current_admin(request)

    if request.method == 'POST':
        form = SickLeaveForm(request.POST, current_admin=admin)
        if form.is_valid():
            sick_leave = form.save(commit=False)
            sick_leave.save()
            sick_leave.employee.employment_status = 'sick_leave'
            sick_leave.employee.save(update_fields=['employment_status'])
            messages.success(request, 'Больничный сохранен')
            return redirect('profiles:admin_sick_leaves_list')
    else:
        form = SickLeaveForm(current_admin=admin)

    return render(request, 'profiles/admin/sick_leave_form.html', {'form': form, 'title': 'Новый больничный', 'admin_obj': admin})


def admin_sick_leave_edit(request, pk):
    admin = _get_current_admin(request)
    sick_leave = get_object_or_404(SickLeave, id=pk)

    if request.method == 'POST':
        form = SickLeaveForm(request.POST, instance=sick_leave, current_admin=admin)
        if form.is_valid():
            form.save()
            messages.success(request, 'Больничный обновлён')
            return redirect('profiles:admin_sick_leaves_list')
    else:
        form = SickLeaveForm(instance=sick_leave, current_admin=admin)

    return render(request, 'profiles/admin/sick_leave_form.html', {
        'form': form,
        'title': f'Редактирование больничного — {sick_leave.employee.FIO}',
        'admin_obj': admin,
    })


def admin_sanctions_list(request):
    admin = _get_current_admin(request)
    _sync_reference_statuses()

    sanctions = Sanction.objects.select_related('employee', 'violation_type', 'work_object').order_by('-created_at')

    if admin and not admin.is_global_admin and admin.department_id:
        sanctions = sanctions.filter(employee__department_id=admin.department_id)

    return render(request, 'profiles/admin/sanctions_list.html', {'sanctions': sanctions, 'admin_obj': admin})


def admin_sanction_create(request):
    admin = _get_current_admin(request)

    if request.method == 'POST':
        form = SanctionForm(request.POST, current_admin=admin)
        if form.is_valid():
            sanction = form.save(commit=False)
            sanction.created_by_admin = admin
            sanction.save()
            if sanction.sanction_type == 'suspension':
                sanction.employee.employment_status = 'suspended'
                sanction.employee.save(update_fields=['employment_status'])
            messages.success(request, 'Санкция назначена')
            return redirect('profiles:admin_sanctions_list')
    else:
        form = SanctionForm(current_admin=admin)

    return render(request, 'profiles/admin/sanction_form.html', {'form': form, 'title': 'Новая санкция', 'admin_obj': admin})


def admin_document_list(request):
    if request.session.get('user_role') != 'admin':
        messages.error(request, 'Доступ запрещён')
        return redirect('main_page:main_page')

    admin = _get_current_admin(request)

    if admin and admin.is_global_admin:
        documents = Document.objects.all().order_by('-created_at')
    else:
        documents = Document.objects.filter(created_by=admin).order_by('-created_at')

    total_users = _department_filtered_users(admin).count()

    for doc in documents:
        doc.signed_count = doc.signatures.count()
        doc.pending_count = total_users - doc.signed_count

    return render(request, 'profiles/admin/document_list.html', {
        'documents': documents,
        'total_users': total_users,
        'admin_obj': admin,
    })


def admin_document_create(request):
    user_role = request.session.get('user_role')
    user_id = request.session.get('user_id')
    admin = _get_current_admin(request)

    if user_role != 'admin':
        messages.error(request, 'Доступ запрещён')
        return redirect('main_page:main_page')

    if request.method == 'POST':
        form = DocumentForm(request.POST, request.FILES)
        if form.is_valid():
            document = form.save(commit=False)
            document.created_by = Admin.objects.get(id=user_id)
            document.save()

            users = _department_filtered_users(admin)
            for user in users:
                user.documents.add(document)

            messages.success(request, f'Документ "{document.title}" создан и разослан {users.count()} пользователям')
            return redirect('profiles:admin_document_list')
    else:
        form = DocumentForm()

    return render(request, 'profiles/admin/document_form.html', {
        'form': form,
        'title': 'Загрузка нового документа',
        'admin_obj': admin,
    })


def medic_employees_list(request):
    if not _medic_required(request):
        return redirect('profiles:dashboard')

    medic_user = _get_current_medic(request)

    employees = User.objects.filter(
        system_role='employee'
    ).select_related('department', 'position', 'manager').order_by('FIO')

    if medic_user and medic_user.department:
        employees = employees.filter(department=medic_user.department)

    search = request.GET.get('q', '').strip()
    department_id = request.GET.get('department')

    if search:
        employees = employees.filter(FIO__icontains=search)
    if department_id:
        employees = employees.filter(department_id=department_id)

    departments = User.objects.filter(
        system_role='employee',
        department__isnull=False
    ).values_list('department__id', 'department__name').distinct()

    return render(request, 'profiles/medic/employees_list.html', {
        'employees': employees,
        'departments': departments,
        'search': search,
        'selected_department': department_id,
        'medic_obj': medic_user,
    })


def medic_medical_checks_list(request):
    if not _medic_required(request):
        return redirect('profiles:dashboard')

    medic_user = _get_current_medic(request)
    _sync_reference_statuses()
    q = (request.GET.get('q') or '').strip()
    department_id = request.GET.get('department')
    today = dj_timezone.localdate()

    checks = MedicalCheck.objects.select_related(
        'employee', 'employee__department', 'medic'
    ).order_by('-checked_at')

    if medic_user and medic_user.department:
        checks = checks.filter(employee__department=medic_user.department)

    if q:
        checks = checks.filter(employee__FIO__icontains=q)
    if department_id:
        checks = checks.filter(employee__department_id=department_id)

    employees = User.objects.filter(system_role='employee', isActive=True)
    if medic_user and medic_user.department:
        employees = employees.filter(department=medic_user.department)

    morning_passed = checks.filter(check_date=today, check_type='morning').values('employee_id').distinct().count()
    evening_passed = checks.filter(check_date=today, check_type='evening').values('employee_id').distinct().count()

    return render(request, 'profiles/medic/medical_checks_list.html', {
        'checks': checks[:200],
        'departments': Department.objects.filter(),
        'search_query': q,
        'department_id': str(department_id or ''),
        'today': today,
        'morning_total': employees.count(),
        'morning_passed': morning_passed,
        'morning_missed': employees.count() - morning_passed,
        'evening_total': employees.count(),
        'evening_passed': evening_passed,
        'evening_missed': employees.count() - evening_passed,
        'medic_obj': medic_user,
    })


def medic_medical_check_detail(request, check_id):
    if not _medic_required(request):
        return redirect('profiles:dashboard')

    check = get_object_or_404(
        MedicalCheck.objects.select_related('employee', 'employee__department', 'employee__position', 'medic'),
        id=check_id
    )

    return render(request, 'profiles/medic/medical_check_detail.html', {'check': check})


def medic_medical_check_create(request):
    if not _medic_required(request):
        return redirect('profiles:dashboard')

    medic_user = _get_current_medic(request)

    if request.method == 'POST':
        form = MedicalCheckForm(request.POST)
        if form.is_valid():
            check = form.save(commit=False)
            check.check_date = dj_timezone.localtime(check.checked_at).date()
            check.medic = medic_user
            check.sanction_reason = form.cleaned_data.get('sanction_reason', '')
            check.sanction_type = form.cleaned_data.get('sanction_type', '')
            check.save()
            _create_or_update_sanction_from_medical_check(check)
            messages.success(request, 'Медосмотр сохранен')
            return redirect('profiles:medic_medical_checks_list')
    else:
        form = MedicalCheckForm()

    return render(request, 'profiles/medic/medical_check_form.html', {'form': form, 'title': 'Новый медосмотр'})


def medic_medical_check_create_for_employee(request, employee_id):
    if not _medic_required(request):
        return redirect('profiles:dashboard')

    medic_user = _get_current_medic(request)
    employee = get_object_or_404(User, id=employee_id, system_role='employee')

    if request.method == 'POST':
        form = MedicalCheckMedicForm(request.POST)
        if form.is_valid():
            check = form.save(commit=False)
            check.employee = employee
            check.medic = medic_user
            check.check_date = dj_timezone.localtime(check.checked_at).date()
            check.save()
            _create_or_update_sanction_from_medical_check(check)
            messages.success(request, f'Медосмотр для {employee.FIO} сохранен')
            return redirect('profiles:medic_medical_checks_list')
    else:
        form = MedicalCheckMedicForm(initial={'checked_at': dj_timezone.now()})

    return render(request, 'profiles/medic/medical_check_form.html', {
        'form': form,
        'title': f'Медосмотр: {employee.FIO}',
        'employee_obj': employee,
    })


def medic_sick_leaves_list(request):
    if not _medic_required(request):
        return redirect('profiles:dashboard')

    medic_user = _get_current_medic(request)
    q = (request.GET.get('q') or '').strip()
    department_id = request.GET.get('department')

    items = SickLeave.objects.select_related('employee', 'employee__department').order_by('-start_date')

    if medic_user and medic_user.department:
        items = items.filter(employee__department=medic_user.department)

    if q:
        items = items.filter(employee__FIO__icontains=q)
    if department_id:
        items = items.filter(employee__department_id=department_id)

    return render(request, 'profiles/medic/sick_leaves_list.html', {
        'sick_leaves': items,
        'departments': Department.objects.filter(),
        'search_query': q,
        'department_id': str(department_id or ''),
        'medic_obj': medic_user,
    })


def medic_sick_leave_create(request):
    if not _medic_required(request):
        return redirect('profiles:dashboard')

    medic_user = _get_current_medic(request)

    if request.method == 'POST':
        form = SickLeaveForm(request.POST)
        if form.is_valid():
            sick_leave = form.save(commit=False)
            sick_leave.issued_by = medic_user
            sick_leave.save()
            sick_leave.employee.employment_status = 'sick_leave'
            sick_leave.employee.save(update_fields=['employment_status'])
            messages.success(request, 'Больничный сохранен')
            return redirect('profiles:medic_sick_leaves_list')
    else:
        form = SickLeaveForm()

    return render(request, 'profiles/medic/sick_leave_form.html', {'form': form, 'title': 'Новый больничный'})


def medic_sick_leave_edit(request, pk):
    if not _medic_required(request):
        return redirect('profiles:dashboard')

    sick_leave = get_object_or_404(SickLeave, id=pk)

    if request.method == 'POST':
        form = SickLeaveForm(request.POST, instance=sick_leave)
        if form.is_valid():
            form.save()
            messages.success(request, 'Больничный обновлён')
            return redirect('profiles:medic_sick_leaves_list')
    else:
        form = SickLeaveForm(instance=sick_leave)

    return render(request, 'profiles/medic/sick_leave_form.html', {
        'form': form,
        'title': f'Редактирование больничного — {sick_leave.employee.FIO}',
    })


def medic_sick_leave_create_for_employee(request, employee_id):
    if not _medic_required(request):
        return redirect('profiles:dashboard')

    medic_user = _get_current_medic(request)
    employee = get_object_or_404(User, id=employee_id, system_role='employee')

    if request.method == 'POST':
        form = SickLeaveMedicForm(request.POST)
        if form.is_valid():
            sick_leave = form.save(commit=False)
            sick_leave.employee = employee
            sick_leave.issued_by = medic_user
            sick_leave.save()
            employee.employment_status = 'sick_leave'
            employee.save()
            messages.success(request, f'Больничный для {employee.FIO} сохранен')
            return redirect('profiles:medic_sick_leaves_list')
    else:
        form = SickLeaveMedicForm()

    return render(request, 'profiles/medic/sick_leave_form.html', {
        'form': form,
        'title': f'Больничный: {employee.FIO}',
        'employee_obj': employee,
    })


def inspector_video_inspections(request):
    if not _inspector_required(request):
        return redirect('profiles:dashboard')

    inspector = Inspector.objects.filter(id=request.session.get('user_id')).select_related('department').first()
    inspections = VideoInspection.objects.all().order_by('-created_at')

    if inspector and inspector.department_id:
        inspections = inspections.filter(work_object__department_id=inspector.department_id)

    return render(request, 'profiles/inspector/video_inspections_list.html', {
        'inspections': inspections,
        'inspector_obj': inspector,
    })


def inspector_video_inspection_create(request):
    if not _inspector_required(request):
        return redirect('profiles:dashboard')

    inspector = get_object_or_404(Inspector, id=request.session.get('user_id'))

    if request.method == 'POST':
        form = VideoInspectionForm(request.POST, request.FILES, inspector=inspector)
        if form.is_valid():
            inspection = form.save(commit=False)
            inspection.inspector = inspector
            if inspection.work_object:
                inspection.object_number = inspection.work_object.zone or inspection.work_object.address or ''
            inspection.status = 'queued'
            inspection.save()
            messages.success(request, 'Видео загружено. Проверка поставлена в очередь.')
            return redirect('profiles:inspector_video_inspection_detail', pk=inspection.id)
    else:
        form = VideoInspectionForm(inspector=inspector)

    return render(request, 'profiles/inspector/video_inspection_create.html', {'form': form})


def inspector_video_inspection_detail(request, pk: int):
    if not _inspector_required(request):
        return redirect('profiles:dashboard')

    inspector = Inspector.objects.filter(id=request.session.get('user_id')).select_related('department').first()
    inspections_qs = VideoInspection.objects.all()

    if inspector and inspector.department_id:
        inspections_qs = inspections_qs.filter(work_object__department_id=inspector.department_id)

    inspection = get_object_or_404(inspections_qs, id=pk)
    violations = inspection.violations.all().order_by('-created_at')
    employees = inspection.work_object.employees.all() if inspection.work_object else []

    return render(request, 'profiles/inspector/video_inspection_detail.html', {
        'inspection': inspection,
        'violations': violations,
        'employees': employees
    })


def inspector_violation_decision(request, pk: int, violation_id: int):
    if not _inspector_required(request):
        return redirect('profiles:dashboard')

    inspection = get_object_or_404(VideoInspection, pk=pk)
    violation = get_object_or_404(ViolationSnapshot, pk=violation_id, inspection=inspection)

    if request.method != 'POST':
        return redirect('profiles:inspector_video_inspection_detail', pk=pk)

    decision = request.POST.get('decision')
    violation.comment = request.POST.get('comment', '')
    violation.reviewed_at = dj_timezone.now()

    if decision == 'yes':
        violation.confirmed = True
        violation.save(update_fields=['comment', 'reviewed_at', 'confirmed'])

        employee_id = request.POST.get('employee_id')

        if not employee_id:
            messages.error(request, 'Необходимо выбрать сотрудника для назначения нарушения')
            return redirect('profiles:inspector_video_inspection_detail', pk=pk)

        try:
            if inspection.work_object:
                employee = inspection.work_object.employees.filter(id=employee_id).first()
            else:
                employee = User.objects.filter(id=employee_id).first()

            if not employee:
                messages.error(request, 'Выбранный сотрудник не найден или не работает на этом наряде')
                return redirect('profiles:inspector_video_inspection_detail', pk=pk)
        except User.DoesNotExist:
            messages.error(request, 'Сотрудник не найден')
            return redirect('profiles:inspector_video_inspection_detail', pk=pk)

        reason = request.POST.get('sanction_reason') or ('Отсутствие каски' if violation.violation_type == 'no_helmet' else 'Отсутствие маски')
        sanction_type = request.POST.get('sanction_type') or 'fine'
        violation_type, _ = ViolationType.objects.get_or_create(
            name=reason,
            defaults={'category': 'ppe', 'severity': 'medium', 'default_sanction': sanction_type}
        )

        Sanction.objects.create(
            employee=employee,
            violation_type=violation_type,
            work_object=inspection.work_object,
            sanction_type=sanction_type,
            comment=f'[VIDEO:{violation.id}] Нарушение на наряде #{inspection.work_object.id if inspection.work_object else "?"}. {violation.comment}'.strip(),
            status='active',
        )

        violation.employee = employee
        violation.save(update_fields=['employee'])

        messages.success(request, f'Нарушение подтверждено. Санкция назначена сотруднику {employee.FIO}')

    else:
        violation.confirmed = False
        violation.save(update_fields=['comment', 'reviewed_at', 'confirmed'])
        messages.info(request, 'Отмечено как ложное срабатывание')

    return redirect('profiles:inspector_video_inspection_detail', pk=pk)


def user_dashboard(request):
    user_id = request.session.get('user_id')
    user_login = request.session.get('user_login')

    if not user_id:
        return redirect('login')

    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        return redirect('main_page:login')

    if not user.isActive:
        return render(request, 'profiles/user/pending_approval.html', {'user_login': user_login})

    pending_tests = user.assigned_certifications.all()

    if user.has_pending_certifications:
        messages.warning(request, f'У вас есть непройденные аттестации: {", ".join([t.title for t in pending_tests])}')

    return render(request, 'profiles/user/dashboard.html', {
        'user_login': user_login,
        'user': user,
        'pending_tests': pending_tests,
        'today_medical': user.todays_medical_check,
        'active_sick_leave': user.active_sick_leave,
        'allowed_to_work_today': user.AllowedToWork,
    })


def user_test_list(request):
    user_id = request.session.get('user_id')
    user_role = request.session.get('user_role')

    if user_role != 'user' or not user_id:
        messages.error(request, 'Доступ запрещён')
        return redirect('main_page:main_page')

    user = get_object_or_404(User, id=user_id)

    if not user.isActive:
        messages.warning(request, 'Ваша учетная запись еще не подтверждена администратором')
        return redirect('profiles:dashboard')

    active_block = UserBlock.objects.filter(user=user, expires_at__gt=dj_timezone.now()).first()
    if active_block:
        days_left = (active_block.expires_at - dj_timezone.now()).days + 1
        messages.error(request, f'Вы заблокированы на {days_left} дн. Причина: {active_block.reason}')
        return redirect('profiles:dashboard')

    assigned_tests = user.assigned_certifications.all()
    passed_tests = user.certifications.all()

    return render(request, 'profiles/user/test_list.html', {
        'tests': assigned_tests,
        'passed_tests': passed_tests,
        'user': user
    })


def user_take_test(request, test_id):
    user_id = request.session.get('user_id')
    user_role = request.session.get('user_role')

    if user_role != 'user' or not user_id:
        messages.error(request, 'Доступ запрещён')
        return redirect('main_page:main_page')

    user = get_object_or_404(User, id=user_id)

    if not user.isActive:
        messages.warning(request, 'Ваша учетная запись еще не подтверждена администратором')
        return redirect('profiles:dashboard')

    active_block = UserBlock.objects.filter(user=user, expires_at__gt=dj_timezone.now()).first()
    if active_block:
        hours_left = int((active_block.expires_at - dj_timezone.now()).total_seconds() / 3600) + 1
        messages.error(request, f'Вы заблокированы на {hours_left} ч. Причина: {active_block.reason}')
        return redirect('profiles:user_test_list')

    test = get_object_or_404(CertificationTest, id=test_id)

    if not user.assigned_certifications.filter(id=test.id).exists():
        messages.error(request, 'Этот тест не назначен вам для прохождения')
        return redirect('profiles:user_test_list')

    if user.certifications.filter(id=test.id).exists():
        messages.error(request, 'Вы уже прошли этот тест')
        return redirect('profiles:user_test_list')

    questions = list(test.questions.all())
    if not questions:
        messages.error(request, 'В этом тесте нет вопросов')
        return redirect('profiles:user_test_list')

    attempt_key = f"take_test_attempt_{test_id}"
    idx_key = f"take_test_qidx_{test_id}"

    attempt_id = request.session.get(attempt_key)
    attempt = None

    if attempt_id:
        attempt = UserTestAttempt.objects.filter(id=attempt_id, user=user, test=test).first()
        if attempt and attempt.completed_at:
            attempt = None
            request.session.pop(attempt_key, None)
            request.session.pop(idx_key, None)

    if attempt is None:
        attempt = UserTestAttempt.objects.create(user=user, test=test)
        request.session[attempt_key] = attempt.id
        request.session[idx_key] = 0

    qidx = int(request.session.get(idx_key, 0))
    if qidx >= len(questions):
        qidx = 0
        request.session[idx_key] = 0

    question = questions[qidx]
    total = len(questions)
    question_num = qidx + 1
    progress = int((qidx / total) * 100)

    if request.method == 'POST':
        form = AnswerForm(request.POST)
        if form.is_valid():
            ans = int(form.cleaned_data['answer'])
            is_correct = (ans == question.correct_answer)
            option_text = {1: question.option1, 2: question.option2, 3: question.option3}.get(ans, '')

            UserAnswer.objects.create(
                attempt=attempt,
                question=question,
                answer_text=option_text if option_text else f"Вариант {ans}",
                is_correct=is_correct
            )

            qidx += 1
            request.session[idx_key] = qidx

            if qidx >= total:
                correct_count = UserAnswer.objects.filter(attempt=attempt, is_correct=True).count()
                percent_correct = (correct_count / total) * 100

                if percent_correct >= 60:
                    attempt.passed = True
                    attempt.completed_at = dj_timezone.now()
                    attempt.save(update_fields=['passed', 'completed_at'])
                    user.assigned_certifications.remove(test)
                    user.certifications.add(test)
                    messages.success(request, f'Тест пройден! Результат: {percent_correct:.0f}% правильных ответов (нужно ≥60%).')
                else:
                    attempt.passed = False
                    attempt.completed_at = dj_timezone.now()
                    attempt.save(update_fields=['passed', 'completed_at'])
                    UserBlock.objects.create(
                        user=user,
                        expires_at=dj_timezone.now() + timedelta(hours=12),
                        reason=f'Проваленная аттестация (результат: {percent_correct:.0f}%)'
                    )
                    user.assigned_certifications.remove(test)
                    messages.error(request, f'Тест не сдан. Результат: {percent_correct:.0f}% (нужно ≥60%). Вы заблокированы на 12 часов.')

                request.session.pop(attempt_key, None)
                request.session.pop(idx_key, None)
                return redirect('profiles:user_test_list')

            return redirect('profiles:user_take_test', test_id=test.id)
    else:
        form = AnswerForm()

    return render(request, 'profiles/user/take_test.html', {
        'test': test,
        'question': question,
        'question_num': question_num,
        'total': total,
        'progress': progress,
        'form': form,
        'user': user
    })


def user_test_history(request):
    user_id = request.session.get('user_id')
    user_role = request.session.get('user_role')

    if user_role != 'user' or not user_id:
        messages.error(request, 'Доступ запрещён')
        return redirect('main_page:main_page')

    user = get_object_or_404(User, id=user_id)

    if not user.isActive:
        messages.warning(request, 'Ваша учетная запись еще не подтверждена администратором')
        return redirect('profiles:dashboard')

    attempts = UserTestAttempt.objects.filter(user=user).order_by('-started_at')

    date_from = request.GET.get('date_from')
    if date_from:
        attempts = attempts.filter(started_at__date__gte=date_from)

    date_to = request.GET.get('date_to')
    if date_to:
        attempts = attempts.filter(started_at__date__lte=date_to)

    completed_from = request.GET.get('completed_from')
    if completed_from:
        attempts = attempts.filter(completed_at__date__gte=completed_from)

    completed_to = request.GET.get('completed_to')
    if completed_to:
        attempts = attempts.filter(completed_at__date__lte=completed_to)

    result = request.GET.get('result')
    if result == 'passed':
        attempts = attempts.filter(passed=True, completed_at__isnull=False)
    elif result == 'failed':
        attempts = attempts.filter(passed=False, completed_at__isnull=False)
    elif result == 'in_progress':
        attempts = attempts.filter(completed_at__isnull=True)

    return render(request, 'profiles/user/test_history.html', {
        'attempts': attempts,
        'user': user
    })


def user_test_attempt_detail(request, attempt_id):
    user_id = request.session.get('user_id')
    user_role = request.session.get('user_role')

    if user_role != 'user' or not user_id:
        messages.error(request, 'Доступ запрещён')
        return redirect('main_page:main_page')

    user = get_object_or_404(User, id=user_id)
    attempt = get_object_or_404(
        UserTestAttempt.objects.select_related('test', 'user'),
        id=attempt_id,
        user=user
    )

    answers = UserAnswer.objects.filter(attempt=attempt).select_related('question')

    questions_data = []
    correct_count = 0

    for answer in answers:
        is_correct = answer.is_correct
        if is_correct:
            correct_count += 1

        correct_answer_num = answer.question.correct_answer
        if correct_answer_num == 1:
            correct_answer_text = answer.question.option1
        elif correct_answer_num == 2:
            correct_answer_text = answer.question.option2
        else:
            correct_answer_text = answer.question.option3

        questions_data.append({
            'question_text': answer.question.text,
            'user_answer': answer.answer_text,
            'correct_answer': correct_answer_text,
            'option1': answer.question.option1,
            'option2': answer.question.option2,
            'option3': answer.question.option3,
            'is_correct': is_correct,
        })

    total_questions = len(answers)
    percent_correct = (correct_count / total_questions * 100) if total_questions > 0 else 0

    context = {
        'attempt': attempt,
        'questions_data': questions_data,
        'total_questions': total_questions,
        'correct_count': correct_count,
        'percent_correct': percent_correct,
        'user': user,
    }

    return render(request, 'profiles/user/test_attempt_detail.html', context)


def user_current_works(request):
    user_id = request.session.get('user_id')
    if not user_id:
        return redirect('main_page:login')

    _sync_reference_statuses()

    user = get_object_or_404(User, id=user_id)

    if request.method == 'POST':
        work_id = request.POST.get('work_id')
        work = get_object_or_404(
            WorkObject.objects.filter(Q(employees=user) | Q(leadEmployee=user)),
            id=work_id,
        )
        if request.POST.get('action') == 'complete' and work.leadEmployee_id == user.id:
            work.status = 'completed'
            work.actual_end_time = dj_timezone.now()
            work.save(update_fields=['status', 'actual_end_time'])
            messages.success(request, f'Наряд #{work.id} завершен')
            return redirect('profiles:user_current_works')

    my_works = WorkObject.objects.filter(
        Q(employees=user) | Q(leadEmployee=user)
    ).distinct().order_by('-time')
    status_filter = request.GET.get('status', 'all')

    if status_filter == 'waiting':
        my_works = my_works.filter(status='waiting')
    elif status_filter == 'in_progress':
        my_works = my_works.filter(status='in_progress')
    elif status_filter == 'completed':
        my_works = my_works.filter(status='completed')
    elif status_filter == 'cancelled':
        my_works = my_works.filter(status='cancelled')

    return render(request, 'profiles/user/current_works.html', {'my_works': my_works, 'user': user, 'now': dj_timezone.now()})


def user_available_works(request):
    user_id = request.session.get('user_id')
    if not user_id:
        return redirect('main_page:login')

    user = get_object_or_404(User, id=user_id)

    if user.role == 'lead':
        messages.info(request, 'Старшие сотрудники не могут записываться на наряды')
        return redirect('profiles:dashboard')

    if not user.isActive:
        messages.warning(request, 'Ваша учетная запись еще не подтверждена администратором')
        return redirect('profiles:dashboard')

    if not user.AllowedToWork:
        if user.has_pending_certifications:
            pending = user.assigned_certifications.all()
            test_names = ", ".join([t.title for t in pending])
            messages.warning(request, f'Для записи на наряды необходимо пройти аттестации: {test_names}')
        elif not user.noDocuments:
            messages.warning(request, 'Для записи на наряды необходимо подписать все документы')
        return redirect('profiles:dashboard')

    available_works = WorkObject.objects.filter(employeesReady=False, status='waiting')
    if user.department_id:
        available_works = available_works.filter(department_id=user.department_id)
    available_works = available_works.exclude(employees=user).order_by('time')

    return render(request, 'profiles/user/available_works.html', {'available_works': available_works, 'user': user})


def user_signup_work(request, work_id):
    user_id = request.session.get('user_id')
    if not user_id:
        return redirect('main_page:login')

    try:
        user = User.objects.get(id=user_id)
        work = WorkObject.objects.get(id=work_id)
        work.update_status()
    except (User.DoesNotExist, WorkObject.DoesNotExist):
        messages.error(request, 'Ошибка при записи на наряд')
        return redirect('profiles:user_available_works')

    if not user.isActive:
        messages.warning(request, 'Ваша учетная запись не активна')
        return redirect('profiles:user_available_works')
    if not user.AllowedToWork:
        messages.warning(request, 'Вы не допущены к работам')
        return redirect('profiles:user_available_works')
    if work.is_completed:
        messages.warning(request, 'Этот наряд уже завершен')
        return redirect('profiles:user_available_works')
    if work.employeesReady:
        messages.warning(request, 'Этот наряд уже укомплектован')
        return redirect('profiles:user_available_works')
    if user in work.employees.all():
        messages.warning(request, 'Вы уже записаны на этот наряд')
        return redirect('profiles:user_available_works')

    active_works = user.works.filter(status='waiting')
    if active_works.exists():
        active_work = active_works.first()
        messages.warning(request, f'Вы уже записаны на наряд #{active_work.id} ({active_work.address}). Отпишитесь от него, чтобы записаться на новый.')
        return redirect('profiles:user_current_works')

    work.employees.add(user)
    work.last_signup_time = dj_timezone.now()
    work.save()

    if work.employees.count() >= work.employeesNeeded:
        work.employeesReady = True
        work.status = 'waiting'
        work.save()

    messages.success(request, f'Вы успешно записаны на наряд #{work.id}')
    return redirect('profiles:user_current_works')


def user_work_detail(request, work_id):
    user_id = request.session.get('user_id')
    if not user_id:
        return redirect('main_page:login')

    user = get_object_or_404(User, id=user_id)
    work = get_object_or_404(
        WorkObject.objects.filter(Q(employees=user) | Q(leadEmployee=user)).distinct(),
        id=work_id,
    )

    return render(request, 'profiles/user/work_detail.html', {'work': work, 'user': user})


def user_unsubscribe_work(request, work_id):
    user_id = request.session.get('user_id')
    if not user_id:
        return redirect('main_page:login')

    try:
        user = User.objects.get(id=user_id)
        work = WorkObject.objects.get(id=work_id)
        work.update_status()
    except (User.DoesNotExist, WorkObject.DoesNotExist):
        messages.error(request, 'Ошибка при отписке от наряда')
        return redirect('profiles:user_current_works')

    if work.is_completed:
        messages.warning(request, 'Нельзя отписаться от завершенного наряда')
        return redirect('profiles:user_current_works')

    if user not in work.employees.all():
        messages.warning(request, 'Вы не записаны на этот наряд')
    else:
        if work.leadEmployee == user:
            messages.warning(request, 'Старший сотрудник не может отписаться от наряда')
            return redirect('profiles:user_current_works')

        work.employees.remove(user)
        if work.employeesReady:
            work.employeesReady = False
            work.status = 'waiting'
            work.save()
        messages.success(request, f'Вы отписались от наряда #{work.id}')

    return redirect('profiles:user_current_works')


def user_documents(request):
    user_id = request.session.get('user_id')
    if not user_id:
        return redirect('main_page:login')

    user = get_object_or_404(User, id=user_id)
    signed_doc_ids = DocumentSignature.objects.filter(user=user).values_list('document_id', flat=True)
    all_assigned_docs = user.documents.filter(is_active=True).order_by('-created_at')
    pending_docs = all_assigned_docs.exclude(id__in=signed_doc_ids)
    signed_docs = all_assigned_docs.filter(id__in=signed_doc_ids)

    return render(request, 'profiles/user/documents.html', {
        'pending_docs': pending_docs,
        'signed_docs': signed_docs,
        'user': user,
        'pending_count': pending_docs.count()
    })


def view_document(request, doc_id):
    user_id = request.session.get('user_id')
    if not user_id:
        return redirect('main_page:login')

    document = get_object_or_404(Document, id=doc_id)
    from django.http import FileResponse
    response = FileResponse(document.file, content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="{document.file.name.split("/")[-1]}"'
    return response


def sign_document(request, doc_id):
    user_id = request.session.get('user_id')
    if not user_id:
        return redirect('main_page:login')

    user = get_object_or_404(User, id=user_id)
    document = get_object_or_404(Document, id=doc_id)

    if not user.documents.filter(id=document.id).exists():
        messages.error(request, 'Этот документ не назначен вам')
        return redirect('profiles:user_documents')

    if DocumentSignature.objects.filter(user=user, document=document).exists():
        messages.warning(request, 'Вы уже подписали этот документ')
        return redirect('profiles:user_documents')

    if request.method == 'POST':
        DocumentSignature.objects.create(user=user, document=document, ip_address=request.META.get('REMOTE_ADDR'))
        messages.success(request, f'Документ "{document.title}" подписан')
        return redirect('profiles:user_documents')

    return render(request, 'profiles/user/sign_confirm.html', {'document': document, 'user': user})


def user_violations(request):
    user_id = request.session.get('user_id')
    if not user_id:
        return redirect('main_page:login')
    if request.session.get('user_role') != 'user':
        return redirect('profiles:dashboard')

    user = get_object_or_404(User, id=user_id)
    sanctions = user.sanctions.select_related('violation_type', 'work_object').order_by('-created_at')
    return render(request, 'profiles/user/violations.html', {'sanctions': sanctions, 'user': user})


def user_ppe_violations(request):
    if request.session.get('user_role') != 'user':
        return redirect('profiles:dashboard')

    user_id = request.session.get('user_id')
    user = get_object_or_404(User, id=user_id)
    violations = ViolationSnapshot.objects.filter(employee=user, confirmed=True).select_related('inspection', 'inspection__work_object').order_by('-created_at')

    return render(request, 'profiles/user/ppe_violations.html', {'violations': violations})


def _get_available_employees_for_work(admin):
    qs = User.objects.filter(
        isActive=True,
        system_role='employee',
        employment_status='active',
    ).select_related('position', 'department').order_by('position__name', 'FIO')

    if admin and not admin.is_global_admin and admin.department_id:
        qs = qs.filter(department_id=admin.department_id)

    allowed_ids = [u.id for u in qs if u.AllowedToWork]
    return User.objects.filter(id__in=allowed_ids).select_related('position', 'department').order_by('position__name', 'FIO')


def dashboard(request):
    _sync_reference_statuses()
    user_id = request.session.get('user_id')
    user_login = request.session.get('user_login')
    user_role = request.session.get('user_role')

    if not user_id or not user_role:
        return redirect('main_page:login')

    context = {'user_login': user_login, 'user_role': user_role}

    if user_role == 'user':
        user = get_object_or_404(User, id=user_id)
        context['user'] = user
        context['today_medical'] = user.todays_medical_check
        context['active_sick_leave'] = user.active_sick_leave
        context['allowed_to_work_today'] = user.AllowedToWork

        deny_reasons = []
        if not user.isActive:
            deny_reasons.append('Пользователь не активирован.')
        if not user.noCertifications:
            deny_reasons.append('Есть непройденные аттестации.')
        if not user.noDocuments:
            deny_reasons.append('Есть неподписанные документы.')
        if user.active_sick_leave:
            deny_reasons.append(f'Сотрудник находится на больничном до {user.active_sick_leave.end_date.strftime("%d.%m.%Y")}.')
        elif user.todays_medical_check and user.todays_medical_check.decision == 'unfit':
            deny_reasons.append('По результатам сегодняшнего медосмотра сотрудник не допущен к работе.')
        elif not user.todays_medical_check:
            deny_reasons.append('Сегодня не пройден обязательный медосмотр.')
        context['deny_reasons'] = deny_reasons
        return render(request, 'profiles/dashboard.html', context)

    elif user_role == 'medic':
        medic = Medic.objects.filter(id=user_id).first()
        if not medic:
            return redirect('main_page:login')
        today = dj_timezone.localdate()
        today_checks = MedicalCheck.objects.filter(check_date=today)
        context['medic'] = medic
        context['medic_stats'] = {
            'checks_total': today_checks.count(),
            'fit_total': today_checks.filter(decision='fit').count(),
            'unfit_total': today_checks.filter(decision='unfit').count(),
            'sick_total': SickLeave.objects.filter(status='active', start_date__lte=today, end_date__gte=today).count()
        }
        return render(request, 'profiles/dashboard.html', context)

    elif user_role == 'admin':
        admin = Admin.objects.filter(id=user_id).select_related('department').first()
        context['admin_obj'] = admin
        context['dashboard_stats'] = {
            'users_total': _department_filtered_users(admin).count(),
            'users_pending': _department_filtered_users(admin).filter(isActive=False).count(),
            'work_open': _department_filtered_work_objects(admin).filter(status__in=['waiting', 'in_progress']).count(),
        }
        return render(request, 'profiles/dashboard.html', context)

    elif user_role == 'inspector':
        inspector = Inspector.objects.filter(id=user_id).select_related('department').first()
        context['inspector_obj'] = inspector
        return render(request, 'profiles/dashboard.html', context)

    return redirect('main_page:login')


def logout(request):
    request.session.flush()
    return redirect('main_page:main_page')
