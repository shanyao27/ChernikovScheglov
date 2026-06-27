# Запуск проекта

## Требования

- [Docker](https://www.docker.com/products/docker-desktop) (версия 20.10+)
- [Docker Compose](https://docs.docker.com/compose/) (входит в Docker Desktop)

---

## Запуск проекта

### 1. Клонировать репозиторий

```bash
git clone https://github.com/shanyao27/B9122-09.03.04-ChernikovScheglov
cd B9122-09.03.04-ChernikovScheglov
```

### 2. Собрать и запустить контейнеры

**Первый запуск:**

```bash
docker compose build --no-cache && docker compose up -d
```

**Перезапуск:**

```bash
docker compose up -d --build
```

При первом запуске Docker установит все зависимости (включая PyTorch), это займёт несколько минут.

### 3. Открыть приложение

После успешного запуска приложение доступно по адресу:

```
http://localhost
```

### 4. Начало работы с приложением

При первом запуске автоматически создаются учётные записи:

| Логин | Пароль | Роль |
|-------|--------|------|
| `admin` | `admin` | Глобальный администратор |
| `admin_KIP` | `admin_KIP` | Администратор КИП |
| `admin_electro` | `admin_electro` | Администратор электроучастка |
| `admin_transport` | `admin_transport` | Администратор транспортного участка |
| `admin_mech` | `admin_mech` | Администратор механического участка |
| `medic_KIP` | `medic_KIP` | Медработник КИП |
| `medic_electro` | `medic_electro` | Медработник электроучастка |
| `medic_transport` | `medic_transport` | Медработник транспортного участка |
| `medic_mech` | `medic_mech` | Медработник механического участка |
| `inspector_KIP` | `inspector_KIP` | Инспектор КИП |
| `inspector_electro` | `inspector_electro` | Инспектор электроучастка |
| `inspector_transport` | `inspector_transport` | Инспектор транспортного участка |
| `inspector_mech` | `inspector_mech` | Инспектор механического участка |

### 5. Скриншоты некоторых страниц программного решения

1. Приветственная страница
<img width="2940" height="1438" alt="image" src="https://github.com/user-attachments/assets/6a6c046b-0cc3-4963-9a39-08bf7ca285ee"/>
2. Страница входа 
<img width="1470" height="722" alt="Снимок экрана 2026-06-27 в 14 59 57" src="https://github.com/user-attachments/assets/c682b4f3-d75d-422a-ab97-29f4358608fd" />
3. Панель администратора (аналогично для инспектора и медицинского работника)
<img width="1470" height="721" alt="Снимок экрана 2026-06-27 в 15 00 47" src="https://github.com/user-attachments/assets/7ae06a0c-ec21-49e5-8d1a-d4f27a28a138" />
4. Страница регистрации
<img width="1470" height="721" alt="Снимок экрана 2026-06-27 в 15 23 30" src="https://github.com/user-attachments/assets/10c87b8f-7bed-4bdb-80a1-5ce4c37a19a1" />
5. Подтверждение регистрации пользователя
<img width="1470" height="719" alt="Снимок экрана 2026-06-27 в 15 02 47" src="https://github.com/user-attachments/assets/5637eaea-e45e-486b-ba47-65b476376ab8" />
6. Панель сотрудника
<img width="1470" height="722" alt="Снимок экрана 2026-06-27 в 15 21 30" src="https://github.com/user-attachments/assets/2bd60239-7e65-465b-88c3-ebadc321c3d1" />
