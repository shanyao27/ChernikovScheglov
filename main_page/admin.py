from django.contrib import admin
from django.contrib.auth.hashers import make_password
from .models import Admin, Inspector, User, Department, Position, Medic


class PublishedModelAdmin(admin.ModelAdmin):
    list_display = ('login', 'full_name', 'department')
    list_filter = ('department',)
    search_fields = ('login', 'full_name')

    fieldsets = (
        (None, {'fields': ('login', 'password')}),
        ('Персональная информация', {'fields': ('full_name', 'department')}),
    )

    def save_model(self, request, obj, form, change):
        if 'password' in form.changed_data and obj.password:
            obj.password = make_password(obj.password)
        super().save_model(request, obj, form, change)


@admin.register(Admin)
class AdminAdmin(PublishedModelAdmin):
    list_display = ('login', 'full_name', 'department', 'is_global_admin')
    list_filter = ('is_global_admin', 'department')

    fieldsets = (
        (None, {'fields': ('login', 'password')}),
        ('Персональная информация', {'fields': ('full_name', 'department')}),
        ('Права доступа', {'fields': ('is_global_admin',)}),
    )


@admin.register(Inspector)
class InspectorAdmin(PublishedModelAdmin):
    pass


@admin.register(Medic)
class MedicAdmin(PublishedModelAdmin):
    pass


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ('name', 'code')
    search_fields = ('name', 'code')


@admin.register(Position)
class PositionAdmin(admin.ModelAdmin):
    list_display = ('name', 'department')
    list_filter = ('department',)
    search_fields = ('name',)


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ('FIO', 'login', 'department', 'system_role', 'isActive', 'employment_status')
    list_filter = ('isActive', 'system_role', 'employment_status', 'department')
    search_fields = ('FIO', 'login', 'number', 'passportData')
    readonly_fields = ('password',)
    fieldsets = (
        ('Основная информация', {'fields': ('FIO', 'login', 'password', 'passportData', 'number', 'address')}),
        ('Работа', {'fields': ('department', 'position', 'role', 'manager', 'system_role')}),
        ('Статус', {'fields': ('isActive', 'employment_status', 'hire_date')}),
        ('Аттестации', {'fields': ('certifications', 'assigned_certifications')}),
        ('Документы', {'fields': ('documents',)}),
    )
