import logging
import os
import random
import sqlite3

import telegram.error
from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, Bot
from telegram.ext import (ApplicationBuilder,
                          CommandHandler,
                          CallbackContext,
                          CallbackQueryHandler,
                          filters,
                          MessageHandler)

load_dotenv()

logger = logging.getLogger(__name__)

TRIP_THEME = 'Поездка в Дагестан'
DATA_DIR = os.path.join(os.path.dirname(__file__), 'data')
os.makedirs(DATA_DIR, exist_ok=True)
DB_NAME = os.path.join(DATA_DIR, 'secret_santa.db')
LOG_NAME = os.path.join(DATA_DIR, 'secret_santa.log')

TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
ADMIN_CHAT_ID = int(os.getenv('ADMIN_CHAT_ID'))

bot = Bot(token=TELEGRAM_TOKEN)
application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()


def get_admin_keybord() -> InlineKeyboardMarkup:
    button_join = InlineKeyboardButton(
        'Участвовать',
        callback_data='join',
    )
    button_edit_name = InlineKeyboardButton(
        'Изменить имя',
        callback_data='edit',
    )
    button_user_list = InlineKeyboardButton(
        'Список участников',
        callback_data='user_list',
    )
    button_delete_user = InlineKeyboardButton(
        'Удалить участника',
        callback_data='delete_user',
    )
    button_roll = InlineKeyboardButton(
        'Розыгрыш и рассылка',
        callback_data='x_moment',
    )
    keyboard = InlineKeyboardMarkup(
        [[button_join, button_edit_name],
         [button_user_list, button_delete_user],
         [button_roll]]
    )
    return keyboard


def get_keybord() -> InlineKeyboardMarkup:
    button_join = InlineKeyboardButton(
        'Участвовать',
        callback_data='join',
    )
    button_edit_name = InlineKeyboardButton(
        'Изменить имя',
        callback_data='edit',
    )
    button_user_list = InlineKeyboardButton(
        'Список участников',
        callback_data='user_list',
    )
    keyboard = InlineKeyboardMarkup(
        [[button_join, button_edit_name],
         [button_user_list]]
    )
    return keyboard


def is_admin(user_id: int) -> bool:
    return user_id == ADMIN_CHAT_ID


# Обработчик команды /start
async def start(update: Update, context: CallbackContext) -> None:
    """
    Обработка команды "/start".
    """
    user = update.message.from_user
    try:
        if is_admin(user.id):
            await update.message.reply_text(
                f'Привет, {user.first_name}! {TRIP_THEME}. Выбери кнопку:',
                reply_markup=get_admin_keybord()
            )
        else:
            await update.message.reply_text(
                f'Привет, {user.first_name}! {TRIP_THEME}. Выбери кнопку:',
                reply_markup=get_keybord()
            )
    except telegram.error.TelegramError as error:
        logger.critical(f'Что-то пошло не так: {error}')


# Обработчик кнопки "Участвовать"
async def join(update: Update, context: CallbackContext) -> None:
    """
    Обработка кнопки "Участвовать".
    """
    query = update.callback_query
    chat_id = update.effective_user.id
    try:
        await query.answer()
        await query.edit_message_text(
            text=f'{update.effective_chat.first_name}, чтобы '
            'присоединиться к розыгрышу, напиши своё имя.')
        context.user_data['waiting_for_name'] = True
        context.user_data['is_edit'] = False
    except telegram.error.TelegramError as error:
        logger.critical(f'Что-то пошло не так: {error}')


# Обработчик кнопки "Изменить имя"
async def edit(update: Update, context: CallbackContext) -> None:
    """
    Обработка кнопки "Изменить имя".
    """
    query = update.callback_query
    try:
        await query.answer()
        await query.edit_message_text(text='Введи новое имя:')
        context.user_data['waiting_for_name'] = True
        context.user_data['is_edit'] = True
    except telegram.error.TelegramError as error:
        logger.critical(f'Что-то пошло не так: {error}')


# Обработчик кнопки "Удалить участника"
async def delete(update: Update, context: CallbackContext) -> None:
    """
    Обработка кнопки "Удалить участника" (доступно только админу).
    """
    query = update.callback_query
    user_id = update.effective_user.id
    try:
        await query.answer()
        if not is_admin(user_id):
            await query.edit_message_text(
                text='Эта функция доступна только организатору.')
            return
        context.user_data['waiting_for_delete_chat_id'] = True
        await query.edit_message_text(
            text='Введи chat_id участника, которого нужно удалить.')
    except telegram.error.TelegramError as error:
        logger.critical(f'Что-то пошло не так: {error}')


async def participant_user_input(update: Update,
                                 context: CallbackContext) -> None:
    """
    Разбирает текстовые сообщения пользователя в зависимости от того,
    какого ввода бот ожидает в данный момент.
    """
    user_input = update.effective_message.text.strip()

    if context.user_data.get('waiting_for_delete_chat_id', False):
        context.user_data['waiting_for_delete_chat_id'] = False
        return await delete_from_db(update, context, user_input)

    if context.user_data.get('waiting_for_name', False):
        context.user_data['waiting_for_name'] = False
        is_edit = context.user_data.pop('is_edit', False)
        if is_edit:
            return await update_name_in_db(update, context, user_input)
        return await write_name_to_db(update, context, user_input)


async def write_name_to_db(update: Update,
                           context: CallbackContext,
                           full_name: str) -> None:
    """
    Записываем нового участника в БД.
    """
    user_name = update.effective_chat.first_name
    chat_id = update.effective_user.id

    try:
        with sqlite3.connect(DB_NAME) as connection:
            cursor = connection.cursor()
            cursor.execute('''
                INSERT INTO users (chat_id, full_name)
                VALUES (?, ?)
            ''', (chat_id, full_name))
            connection.commit()
        await update.message.reply_text(
            f'Всё отлично, {user_name}, ты стал участником!'
        )
        await update.message.reply_text(
            'Выбери кнопку:', reply_markup=get_keybord()
        )
    except sqlite3.Error as error:
        logger.error(f'Проблема с записью данных в БД: {error}')
        if str(error).startswith('UNIQUE constraint failed'):
            await update.message.reply_text(
                'Дважды стать участником не получится.'
            )
        else:
            await update.message.reply_text(
                'Что-то пошло не так, попробуй еще раз.'
            )
    except telegram.error.TelegramError as tg_error:
        logger.critical(f'Что-то пошло не так: {tg_error}')


async def update_name_in_db(update: Update,
                            context: CallbackContext,
                            full_name: str) -> None:
    """
    Обновляем имя участника в БД.
    """
    user_name = update.effective_chat.first_name
    chat_id = update.effective_user.id

    try:
        with sqlite3.connect(DB_NAME) as connection:
            cursor = connection.cursor()
            cursor.execute('''
                UPDATE users SET full_name = ? WHERE chat_id = ?
            ''', (full_name, chat_id))
            connection.commit()
        await update.message.reply_text(
            f'Готово, {user_name}, имя обновлено!'
        )
        await update.message.reply_text(
            'Выбери кнопку:', reply_markup=get_keybord()
        )
    except sqlite3.Error as error:
        logger.error(f'Проблема с записью данных в БД: {error}')
        await update.message.reply_text(
            'Что-то пошло не так, попробуй еще раз.'
        )
    except telegram.error.TelegramError as tg_error:
        logger.critical(f'Что-то пошло не так: {tg_error}')


async def delete_from_db(update: Update,
                         context: CallbackContext,
                         chat_id_for_delete: str) -> None:
    """
    Удаляем участника из БД по chat_id.
    """
    try:
        with sqlite3.connect(DB_NAME) as connection:
            cursor = connection.cursor()
            cursor.execute(
                'DELETE FROM users WHERE chat_id = ?',
                (chat_id_for_delete,)
            )
            connection.commit()
        await update.message.reply_text('Участник удален.')
    except sqlite3.Error as error:
        logger.error(f'Проблема с удалением данных из БД: {error}')
        await update.message.reply_text(
            'Что-то пошло не так, попробуй еще раз.'
        )
    except telegram.error.TelegramError as tg_error:
        logger.critical(f'Что-то пошло не так: {tg_error}')


# Обработчик кнопки "Список участников"
async def users_count_first_ten_users(update: Update,
                                      context: CallbackContext) -> None:
    """
    Обработка кнопки "Список участников".
    Выводит общее количество и первые 10 имен участников.
    """
    button_view_all_users = InlineKeyboardButton(
        'Посмотреть всех',
        callback_data='all_participants',
    )
    keyboard = InlineKeyboardMarkup(
        [[button_view_all_users]]
    )
    chat_id = update.effective_message.chat_id
    query = update.callback_query
    try:
        await query.answer()
        total_users = get_total_users()
        users_list = get_users_list()
        message_text = '\n'.join(users_list[:10])
        await bot.send_message(
            chat_id=chat_id,
            text=f'Общее количество участников: {total_users}'
        )
        await bot.send_message(
            chat_id=chat_id,
            text=('Список участников (будут показаны первые 10):'
                  f'\n{message_text}'),
            reply_markup=keyboard
        )
    except telegram.error.TelegramError as tg_error:
        logger.critical(f'Что-то пошло не так: {tg_error}')


async def get_participants_list(update: Update,
                                context: CallbackContext) -> None:
    """
    Обработка кнопки "Посмотреть всех".
    """
    chat_id = update.effective_message.chat_id
    users_list = get_users_list()
    message_text = '\n'.join(users_list)
    try:
        await bot.send_message(
            chat_id=chat_id,
            text=f'Список всех участников:\n{message_text}'
        )
    except telegram.error.TelegramError as tg_error:
        logger.critical(f'Что-то пошло не так: {tg_error}')


def get_total_users() -> int:
    """
    Метод для подсчета количества участников.
    """
    with sqlite3.connect(DB_NAME) as connection:
        cursor = connection.cursor()
        query = cursor.execute('select count(*) from users;')
        total_users = query.fetchone()[0]
    return total_users


def get_users_list() -> list:
    """
    Метод для вывода списка участников.
    """
    with sqlite3.connect(DB_NAME) as connection:
        cursor = connection.cursor()
        query = cursor.execute('select full_name from users;')
        user_list = [user[0] for user in query.fetchall()]
    return user_list


# Обработчик кнопки "Розыгрыш и рассылка"
async def x_moment(update: Update, context: CallbackContext) -> None:
    """
    Обработка кнопки "Розыгрыш и рассылка" (доступно только админу).
    Распределяет участников по парам и рассылает каждому личное сообщение.
    """
    query = update.callback_query
    user_id = update.effective_user.id
    try:
        await query.answer()
        if not is_admin(user_id):
            await query.edit_message_text(
                text='Эта функция доступна только организатору.')
            return
        await query.edit_message_text(text='Провожу розыгрыш...')
    except telegram.error.TelegramError as error:
        logger.critical(f'Что-то пошло не так: {error}')
        return

    assign_gift_receivers()
    await send_assignment_messages()


def assign_gift_receivers() -> None:
    """
    Распределяет участников по парам и сохраняет результат в БД.
    """
    with sqlite3.connect(DB_NAME) as connection:
        cursor = connection.cursor()
        query = cursor.execute('select chat_id from users;')
        participants = [user[0] for user in query.fetchall()]

    if len(participants) < 2:
        logger.error('Недостаточно участников для розыгрыша.')
        return

    pairs = secret_santa_algorithm(participants)
    write_pairs_to_db(pairs)


def secret_santa_algorithm(participants: list) -> dict:
    """
    Тасует участников и строит кольцо "santa -> receiver" так, чтобы никто
    не дарил подарок сам себе.
    """
    shuffled = participants[:]
    random.shuffle(shuffled)
    return {
        shuffled[i]: shuffled[(i + 1) % len(shuffled)]
        for i in range(len(shuffled))
    }


def write_pairs_to_db(pairs: dict) -> None:
    """
    Сохраняет результат розыгрыша (кому дарить подарок) в БД.
    """
    try:
        with sqlite3.connect(DB_NAME) as connection:
            cursor = connection.cursor()
            for santa_chat_id, receiver_chat_id in pairs.items():
                query = cursor.execute(
                    'select full_name from users where chat_id = ?',
                    (receiver_chat_id,)
                )
                receiver_full_name = query.fetchone()[0]
                cursor.execute('''
                    UPDATE users
                    SET gift_receiver_chat_id = ?,
                        gift_receiver_full_name = ?
                    WHERE chat_id = ?
                ''', (receiver_chat_id, receiver_full_name, santa_chat_id))
            connection.commit()
    except sqlite3.Error as error:
        logger.error(f'Проблема с записью результатов розыгрыша: {error}')


async def send_assignment_messages() -> None:
    """
    Рассылает каждому участнику личное сообщение с тем, кому он дарит
    подарок.
    """
    try:
        with sqlite3.connect(DB_NAME) as connection:
            cursor = connection.cursor()
            query = cursor.execute('''
                select chat_id, gift_receiver_full_name
                from users
                where gift_receiver_chat_id is not null;
            ''')
            assignments = query.fetchall()
    except sqlite3.Error as error:
        logger.error(f'Проблема с получением данных из БД: {error}')
        return

    for chat_id, receiver_full_name in assignments:
        try:
            await bot.send_message(
                chat_id=chat_id,
                text=(
                    f'🏔 Розыгрыш перед поездкой в Дагестан завершен!\n\n'
                    f'Ты даришь подарок — {receiver_full_name}.\n\n'
                    'Пусть сюрприз будет тёплым и по-кавказски щедрым! 🎁'
                )
            )
        except telegram.error.TelegramError as tg_error:
            logger.critical(
                f'Не удалось отправить сообщение {chat_id}: {tg_error}'
            )


# Инициализация бота
def main() -> None:

    # Регистрация обработчиков команд
    application.add_handlers(
        handlers=(
            CommandHandler('start', start),
            CallbackQueryHandler(join, 'join'),
            CallbackQueryHandler(edit, 'edit'),
            CallbackQueryHandler(delete, 'delete_user'),
            CallbackQueryHandler(users_count_first_ten_users, 'user_list'),
            CallbackQueryHandler(get_participants_list, 'all_participants'),
            CallbackQueryHandler(x_moment, 'x_moment'),
            MessageHandler(filters.TEXT, callback=participant_user_input),
        )
    )

    # Запуск бота
    try:
        application.run_polling()
    except telegram.error.TelegramError as error:
        logger.critical(f'Что-то пошло не так: {error}')


if __name__ == '__main__':
    # настраиваем логгер
    logging.basicConfig(
        level=logging.INFO,
        filename=LOG_NAME,
        format='%(asctime)s, %(levelname)s, %(message)s, %(funcName)s',
        encoding='utf-8'
    )

    main()
