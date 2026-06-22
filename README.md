# Personnel Control — Запуск через Docker

## Требования

- [Docker](https://www.docker.com/products/docker-desktop) (версия 20.10+)
- [Docker Compose](https://docs.docker.com/compose/) (входит в Docker Desktop)

---

## Запуск проекта

### 1. Клонировать репозиторий

```bash
git clone https://github.com/shanyao27/ChernikovScheglov.git
cd ChernikovScheglov
```

### 2. Собрать и запустить контейнеры

**Первый запуск или при изменении зависимостей:**

```bash
docker compose build --no-cache && docker compose up -d
```

**Обычный перезапуск (изменения кода без новых пакетов):**

```bash
docker compose up -d --build
```

При первом запуске Docker установит все зависимости (включая PyTorch) — это займёт несколько минут.

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

