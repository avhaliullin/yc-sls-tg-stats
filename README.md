# Пререквизиты
1. Развернутый кластер managed clickhouse с публичным доступом
2. Python 3.11 на ноутбуке

# Notes
Здесь показано использование CH с публичным доступом. При наличии на облаке [флага](https://cloud.yandex.ru/docs/functions/concepts/networking#polzovatelskaya-set) для запуска функций в VPC - можно все провернуть без публичного доступа, но мы сталкиваемся с ограничениями tf для функций.
В итоге можно развернуть функцию tf-рецептом, а потом воткнуть ее в VPC уже через web ui.

В этом рецепте предполагается, что все действие происходит в одном фолдере - в том же самом, в котором развернут кликхаус. Это не какое-то принципиальное ограничение, просто так проще писать рецепт.

# Готовим БД
1. Создаем БД в кластере CH (или используем существующую)
2. Заводим в CH пользователя с правами на нашу БД
3. Креды пользователя (логин и пароль) складываем в lockbox-секрет в ключи `user` и `pass`
4. Создаем в БД таблички по `schema.sql`

# Разбираемся с телегой
1. Создаем telegram app по [инструкции](https://core.telegram.org/api/obtaining_api_id#obtaining-api-id) - нам нужны api_id и api_hash
2. Устанавливаем питонячьи зависимости на ноут: `pip install -r ./src/requirements.txt`
3. Запускаем логин: `python src/login.py` с флагами:
   - `--tg-api-id` и `--tg-api-hash` - получаем от телеги в шаге 1
   - `--yc-folder-id` - id фолдера
   - `--yc-oauth` - [OAuth-токен](https://cloud.yandex.ru/docs/iam/concepts/authorization/oauth-token) к облаку
   
   На этом этапе клиент телеги пытается в ней авторизоваться. Он интерактивно попросит все, что ему нужно - номер телефона (вводить через +7 для рф), код подтверждения, пароль (если настроена 2fa).
   В случае успеха скрипт напечатает `secret id` - идентификатор свежесозданного секрета в lockbox, в котором лежит все для авторизации в телеге
4. Выбираем группы, для которых хотим собирать статистику. Для этого запускаем `python ./src/list_groups.py` с флагами:
   - `--yc-oauth` - OAuth-токен к облаку
   - `--tg-secret-id` - id секрета, полученного на предыдущем шаге
   
    Скрипт печатает названия доступных групп и их числовые идентификаторы. Чтобы "рассказать" функции, какие группы нам нужно анализировать - нужно собрать числовые идентификаторы в строчку через запятые (без пробелов).
5. Инициализируем tf-проект: `terraform init`
6. Строим план `terraform plan -out plan.out`, с флагами:
   -  `-var folder-id=<ID фолдера>`
   -  `-var yc-token=<OAuth-токен облака>`
   -  `-var ch-host=<FQDN хоста CH с публичным доступом>`
   -  `-var ch-db-name=<Имя БД из шага 1 раздела "готовим БД">`
   -  `-var dialog-ids=<Список id групп из шага 4>`
   -  `-var tg-secret-id=<ID секрета из шага 3>`
   -  `-var ch-secret-id=<ID секрета из шага 3 раздела "готовим БД">`
   
    Смотрим план глазами, убеждаемся, что все ок (например, что tf не собирается ничего удалять)
7. Применяем план `terraform apply plan.out`

При успешном развертывании данные начнут наливаться через 5-10 минут, и будут обновляться каждые 5 минут