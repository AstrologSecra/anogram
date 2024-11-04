import asyncio
import random
import logging
import os
import hashlib
import base64
import json

from pywebio import start_server
from pywebio.input import *
from pywebio.output import *
from pywebio.session import defer_call, info as session_info, run_async, run_js

# Настройка логирования
logging.basicConfig(level=logging.DEBUG)

chat_rooms = {}
users_db = {}  # База данных пользователей (хэш -> имя)

MAX_MESSAGES_COUNT = 100

def generate_chat_id():
    return ''.join(random.choices('0123456789', k=6))

def generate_hash(name):
    # Генерируем случайные символы для добавления в хэш
    random_chars = ''.join(random.choices('abcdefghijklmnopqrstuvwxyz0123456789', k=5))
    # Создаем строку для хеширования
    hash_input = f"{name}{random_chars}"
    # Хешируем строку с использованием SHA-256
    hash_object = hashlib.sha256(hash_input.encode())
    # Возвращаем хэш в виде base64 строки
    return base64.b64encode(hash_object.digest()).decode()

def load_data():
    global chat_rooms, users_db
    if os.path.exists('users.json'):
        with open('users.json', 'r') as f:
            users_db = json.load(f)
    if os.path.exists('chats.json'):
        with open('chats.json', 'r') as f:
            chat_rooms = json.load(f)
            for chat_id in chat_rooms:
                chat_rooms[chat_id]['users'] = set(chat_rooms[chat_id]['users'])

def save_data():
    with open('users.json', 'w') as f:
        json.dump(users_db, f)
    with open('chats.json', 'w') as f:
        json.dump(chat_rooms, f, default=lambda x: list(x) if isinstance(x, set) else x)

async def main():
    global chat_rooms, users_db
    
    load_data()
    
    put_markdown("## 🧊 Добро пожаловать в онлайн чат!\nИсходный код данного чата укладывается в 100 строк кода! Автор не несёт ответственности за действия на этом сайте!")

    action = await select("Выберите действие", ["Регистрация", "Вход", "Удалить аккаунт"])

    if action == "Регистрация":
        while True:
            name = await input("Введите ваше имя", required=True)
            if name in users_db.values():
                toast("Этот ник уже занят! Пожалуйста, выберите другой.", color='error')
            else:
                break
        user_hash = generate_hash(name)
        users_db[user_hash] = name
        save_data()
        toast(f"Ваш хэш для входа: {user_hash}")
        logging.info(f"Зарегистрирован новый пользователь с именем: {name}")
        # Открываем новое окно с хэшем пользователя
        run_js(f'window.open("about:blank", "_blank").document.write("Ваш хэш для входа: {user_hash}");')
    elif action == "Вход":
        user_hash = await input("Введите ваш хэш", required=True)
        if user_hash in users_db:
            name = users_db[user_hash]
            logging.info(f"Пользователь с именем {name} вошел в систему")
        else:
            toast("Хэш не найден!", color='error')
            logging.warning(f"Хэш не найден")
            return

    elif action == "Удалить аккаунт":
        user_hash = await input("Введите ваш хэш", required=True)
        if user_hash in users_db:
            name = users_db[user_hash]
            del users_db[user_hash]
            save_data()
            toast(f"Аккаунт пользователя {name} удален!")
            logging.info(f"Аккаунт пользователя {name} удален")
            # Удаляем пользователя из всех чатов
            for chat_id in chat_rooms:
                if name in chat_rooms[chat_id]['users']:
                    chat_rooms[chat_id]['users'].remove(name)
                    chat_rooms[chat_id]['msgs'].append(('📢', f'Акаунт`{name}` удалён его владельцем!'))
            save_data()
            # Перенаправляем на страницу регистрации
            run_js('window.location.reload()')
            return
        else:
            toast("Хэш не найден!", color='error')
            logging.warning(f"Хэш не найден")
            return

    chat_id = await input("Введите ID чата (оставьте пустым для создания нового)", required=False, placeholder="6-значный ID")
    
    if not chat_id:
        chat_id = generate_chat_id()
        chat_rooms[chat_id] = {'msgs': [], 'users': set()}
        save_data()
        toast(f"Создан новый чат с ID: {chat_id}")
        logging.info(f"Создан новый чат с ID: {chat_id}")
    elif chat_id not in chat_rooms:
        toast("Чат с таким ID не найден!", color='error')
        logging.warning(f"Чат с ID {chat_id} не найден")
        return
    else:
        logging.info(f"Присоединение к существующему чату с ID: {chat_id}")

    # Проверка на уникальность ника в чате
    if name in chat_rooms[chat_id]['users']:
        toast("Этот ник уже используется в этом чате!", color='error')
        return

    # Отображение ID чата в заголовке
    put_markdown(f"## 🧊 Чат ID: {chat_id}")

    msg_box = output()
    put_scrollable(msg_box, height=300, keep_bottom=True)

    chat_rooms[chat_id]['users'].add(name)
    save_data()

    chat_rooms[chat_id]['msgs'].append(('📢', f'`{name}` присоединился к чату!'))
    msg_box.append(put_markdown(f'📢 `{name}` присоединился к чату'))

    refresh_task = run_async(refresh_msg(chat_id, name, msg_box))

    while True:
        data = await input_group("💭 Новое сообщение", [
            input(placeholder="Текст сообщения ...", name="msg"),
            actions(name="cmd", buttons=["Отправить", {'label': "Выйти из чата", 'type': 'cancel'}])
        ], validate = lambda m: ('msg', "Введите текст сообщения!") if m["cmd"] == "Отправить" and not m['msg'] else None)

        if data is None:
            break

        msg_box.append(put_markdown(f"`{name}`: {data['msg']}"))
        chat_rooms[chat_id]['msgs'].append((name, data['msg']))
        save_data()

    refresh_task.close()

    chat_rooms[chat_id]['users'].remove(name)
    save_data()
    toast("Вы вышли из чата!")
    msg_box.append(put_markdown(f'📢 Пользователь `{name}` покинул чат!'))
    chat_rooms[chat_id]['msgs'].append(('📢', f'Пользователь `{name}` покинул чат!'))
    save_data()

    put_buttons(['Перезайти'], onclick=lambda btn:run_js('window.location.reload()'))

async def refresh_msg(chat_id, nickname, msg_box):
    last_idx = len(chat_rooms[chat_id]['msgs'])

    while True:
        await asyncio.sleep(1)
        
        for m in chat_rooms[chat_id]['msgs'][last_idx:]:
            if m[0] != nickname: # if not a message from current user
                msg_box.append(put_markdown(f"`{m[0]}`: {m[1]}"))
        
        # remove expired
        if len(chat_rooms[chat_id]['msgs']) > MAX_MESSAGES_COUNT:
            chat_rooms[chat_id]['msgs'] = chat_rooms[chat_id]['msgs'][len(chat_rooms[chat_id]['msgs']) // 2:]
            save_data()
        
        last_idx = len(chat_rooms[chat_id]['msgs'])

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    start_server(main, debug=True, port=port, cdn=False)
