import logging
import os
import sys
import time
from http import HTTPStatus
from logging import StreamHandler

import requests
import telegram
from telegram.error import TelegramError
from dotenv import load_dotenv

from exceptions import HTTPError, ApiRequestError

load_dotenv()

PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

RETRY_PERIOD = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN }'}
HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
handler = StreamHandler(stream=sys.stdout)
logger.addHandler(handler)
formatter = logging.Formatter(
    '%(asctime)s - %(levelname)s - %(message)s - %(name)s'
)
handler.setFormatter(formatter)


def check_tokens():
    """
    Проверяет доступность переменных окружения.
    Если отсутствует хотя бы одна переменная окружения
    — продолжать работу бота нет смысла.
    """
    return all([PRACTICUM_TOKEN, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID])


def send_message(bot, message):
    """
    Отправляет сообщение в Telegram чат.
    Принимает на вход два параметра:
    экземпляр класса Bot и строку с текстом сообщения.
    """
    try:
        bot.send_message(TELEGRAM_CHAT_ID, message)
        logger.debug('Сообщение в телеграм успешно отправлено.')
    except TelegramError:
        logger.error('Не получилось отправить сообщение.')


def get_api_answer(timestamp):
    """
    Делает запрос к единственному эндпоинту API-сервиса.
    В качестве параметра в функцию передается временная метка.
    В случае успешного запроса должна вернуть ответ API,
    приведя его из формата JSON к типам данных Python.
    """
    payload = {'from_date': timestamp}
    try:
        homework_statuses = requests.get(
            ENDPOINT, headers=HEADERS, params=payload
        )
    except requests.RequestException as e:
        raise ApiRequestError(f'Ошибка при отправке запроса к api: {e}')
    if not homework_statuses.status_code == HTTPStatus.OK:
        raise HTTPError(
            f'Получен код, отличный от 200: {homework_statuses.status_code}. '
            f'Текст ответа: {homework_statuses.text}, '
            f'Заголовок ответа: {homework_statuses.headers}, '
        )
    return homework_statuses.json()


def check_response(response):
    """
    Проверяет ответ API на соответствие документации.
    В качестве параметра функция получает ответ API,
    приведенный к типам данных Python.
    """
    if not isinstance(response, dict):
        raise TypeError('Получен иной тип данных, отличный от словаря.')
    homeworks = response.get('homeworks')
    if not isinstance(homeworks, list):
        raise TypeError('Данные пришли не в виду списка.')
    return response.get('homeworks')


def parse_status(homeworks):
    """
    Извлекает из информации о домашней работе статус этой работы.
    В качестве параметра функция получает
    только один элемент из списка домашних работ.
    В случае успеха, функция возвращает
    подготовленную для отправки в Telegram строку,
    содержащую один из вердиктов словаря HOMEWORK_VERDICTS.
    """
    homework_name = homeworks.get('homework_name')
    if not homework_name:
        raise KeyError('Отсутствует ключ названия домашней работы!')
    homework_status = homeworks.get('status')
    if not homework_status:
        raise KeyError('Не найден ключ статуса домашней работы!')
    if homework_status not in HOMEWORK_VERDICTS.keys():
        raise KeyError('Получен неожиданный статус домашней работы!')
    verdict = HOMEWORK_VERDICTS[homework_status]
    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def main():
    """
    Основная логика работы бота.
    Сделать запрос к API.
    Проверить ответ.
    Если есть обновления — получить статус работы из обновления
    и отправить сообщение в Telegram.
    Подождать некоторое время и вернуться в пункт 1.
    """
    if not check_tokens():
        logging.critical('Переменные окружения не заданы!')
        sys.exit('Необходимо добавить переменные окружения!')
    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    timestamp = int(time.time())
    messages = ''
    while True:
        try:
            response = get_api_answer(timestamp)
            homeworks = check_response(response)
            timestamp = response.get('current_date', timestamp)
            if homeworks:
                status = parse_status(homeworks[0])
                if messages != status:
                    messages = status
                    send_message(bot, messages)
            else:
                update_message = 'Нет обновлений статуса домашней работы.'
                if messages != update_message:
                    messages = update_message
                    send_message(bot, messages)
        except Exception as error:
            message = f'Сбой в работе программы: {error}'
            if messages == message:
                logger.error(message)
            else:
                messages = message
                send_message(bot, messages)
                messages = ''
        finally:
            time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    main()
