# Backend TechTrendSearcher

Python-пакет `radar` реализует поиск, загрузку HTML/PDF, извлечение технологий, проверку цитат и сборку карточек. FastAPI предоставляет HTTP API и раздаёт собранный интерфейс.

- [Запуск приложения](../../README.md)
- [Настройки модели и разработка](../../DOCUMENTATION.md)
- [Архитектура](../architecture-2026-09-29.md)
- [Методика и ограничения](../submission-methodology-2026-09-28.md)

Из корня репозитория, после установки Python-зависимостей:

```bash
PYTHONPATH=hackathon python -m uvicorn radar.public:app --host 127.0.0.1 --port 8000
python -m pytest hackathon/radar/tests -q
PYTHONPATH=hackathon python -m radar run --direction "Защита ИИ" --mode fixtures
```

Перед запуском сервиса скопируйте `.env.example` в корневой `.env`: там включён деморежим. Команда `fixtures` использует подготовленные ответы, не вызывает платные API и сохраняет результат в рабочий каталог.

Команды `reference`, `evaluate` и параметр `--area` предназначены для отдельной оценки покрытия по закрытому эталону. Сам эталон не включён в репозиторий и для работы приложения не требуется. `smoke` выполняет реальные API-запросы; для проверки установки он не нужен.
