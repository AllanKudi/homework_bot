import logging
import os
import sys
import time
from http import HTTPStatus
from logging import StreamHandler

import requests
import telegram
from dotenv import load_dotenv

from exceptions import NotHomeworkError, HTTPError

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
    try:
        tockens = all([PRACTICUM_TOKEN, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID])
    except Exception as error:
        logger.critical(
            f'Отсутствуют обязательные переменные окружения! Ошибка: {error}'
        )
    return tockens


def send_message(bot, message):
    """
    Отправляет сообщение в Telegram чат.
    Принимает на вход два параметра:
    экземпляр класса Bot и строку с текстом сообщения.
    """
    try:
        bot.send_message(TELEGRAM_CHAT_ID, message)
        logger.debug('Сообщение в телеграм успешно отправлено.')
    except Exception as error:
        logger.error(
            f'Не получилось отправить сообщение. Всему виной: {error}'
        )


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
    except Exception as error:
        logger.error(f'Сбой при запросе к эндпойнту. Подробнее: {error}')
    if not homework_statuses.status_code == HTTPStatus.OK:
        raise HTTPError('Получен код, отличный от 200.')
    return homework_statuses.json()


def check_response(response):
    """
    Проверяет ответ API на соответствие документации.
    В качестве параметра функция получает ответ API,
    приведенный к типам данных Python.
    """
    if not isinstance(response, dict):
        raise TypeError('Получен иной тип данных, отличный от словаря.')
    try:
        response.get('homeworks') is not None
    except Exception as error:
        logger.error(f'Несуществующий ключ. Ошибка: {error}')
    if not isinstance(response.get('homeworks'), list):
        raise TypeError('Данные пришли не в виду списка.')
    return response.get('homeworks')


def parse_status(homework):
    """
    Извлекает из информации о домашней работе статус этой работы.
    В качестве параметра функция получает
    только один элемент из списка домашних работ.
    В случае успеха, функция возвращает
    подготовленную для отправки в Telegram строку,
    содержащую один из вердиктов словаря HOMEWORK_VERDICTS.
    """
    homework_name = ''
    homework_status = ''
    verdict = ''
    if 'homework_name' not in homework:
        raise KeyError('Отсутствует ключ названия домашки!')
    homework_name = homework.get('homework_name')
    try:
        homework_status = homework.get('status')
    except KeyError:
        logging.error('Не найден статус домашней работы!')
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
    while True:
        try:
            check_tokens()
            response = get_api_answer(timestamp)
            homework = check_response(response)
            timestamp = response.get('current_date', timestamp)
            if not homework:
                raise NotHomeworkError('Статус домашней работы не обновлен.')
            else:
                homework = homework[0]
                status = parse_status(homework)
                send_message(bot, status)
        except Exception as error:
            message = f'Сбой в работе программы: {error}'
            send_message(bot, message)
            logger.error(message)
        finally:
            time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    main()
