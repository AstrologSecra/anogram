from flask import Flask, request, jsonify
from flask_socketio import SocketIO, emit
from pywebio.platform.flask import webio_view
from pywebio import STATIC_PATH
from pywebio.input import *
from pywebio.output import *
from pywebio.session import defer_call, info as session_info, run_async, run_js
import random
import logging
import threading
import time
import os

app = Flask(__name__)
socketio = SocketIO(app)

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Словарь для хранения сообщений каждого чата
chat_msgs = {}

# Словарь для хранения существующих идентификаторов чатов
existing_chat_ids = set()

MAX_MESSAGES_COUNT = 100

def generate_chat_id():
    while True:
        chat_id = f"{random.randint(0, 999999):06d}"
        if chat_id not in existing_chat_ids:
            existing_chat_ids.add(chat_id)
            return chat_id

def main():
    put_markdown("## 🧊 Добро пожаловать в личный чат!")

    # Выбор действия: создать новый чат или присоединиться к существующему
    action = actions("Выберите действие", ["Создать новый чат", "Присоединиться к существующему чату"])

    if action == "Создать новый чат":
        chat_id = generate_chat_id()
        logger.info(f"Создан новый чат с ID: {chat_id}")
        put_markdown(f"## Ваш ID: {chat_id}")
        put_button("Скопировать ID", onclick=lambda: run_js(f"navigator.clipboard.writeText('{chat_id}')"))
        chat(chat_id)
    elif action == "Присоединиться к существующему чату":
        chat_id = input("Введите ID чата", required=True, placeholder="ID чата")
        if chat_id not in existing_chat_ids:
            toast("Чат с таким ID не найден!", color='error')
            logger.warning(f"Попытка присоединиться к несуществующему чату с ID: {chat_id}")
            return
        logger.info(f"Присоединение к существующему чату с ID: {chat_id}")
        chat(chat_id)

def chat(chat_id):
    global chat_msgs
    
    if chat_id not in chat_msgs:
        chat_msgs[chat_id] = []
    
    msg_box = output()
    put_scrollable(msg_box, height=300, keep_bottom=True)

    nickname = input("Войти в чат", required=True, placeholder="Ваше имя")

    chat_msgs[chat_id].append(('📢', f'`{nickname}` присоединился к чату!'))
    msg_box.append(put_markdown(f'📢 `{nickname}` присоединился к чату'))

    socketio.emit('chat_message', {'nickname': '📢', 'message': f'`{nickname}` присоединился к чату!'}, room=chat_id)

    while True:
        data = input_group("💭 Новое сообщение", [
            input(placeholder="Текст сообщения ...", name="msg"),
            actions(name="cmd", buttons=["Отправить", {'label': "Выйти из чата", 'type': 'cancel'}])
        ], validate = lambda m: ('msg', "Введите текст сообщения!") if m["cmd"] == "Отправить" and not m['msg'] else None)

        if data is None:
            break

        msg_box.append(put_markdown(f"`{nickname}`: {data['msg']}"))
        chat_msgs[chat_id].append((nickname, data['msg']))

        socketio.emit('chat_message', {'nickname': nickname, 'message': data['msg']}, room=chat_id)

    toast("Вы вышли из чата!")
    msg_box.append(put_markdown(f'📢 Пользователь `{nickname}` покинул чат!'))
    chat_msgs[chat_id].append(('📢', f'Пользователь `{nickname}` покинул чат!'))

    socketio.emit('chat_message', {'nickname': '📢', 'message': f'Пользователь `{nickname}` покинул чат!'}, room=chat_id)

    put_buttons(['Перезайти'], onclick=lambda btn:run_js('window.location.reload()'))

@socketio.on('connect')
def handle_connect():
    logger.info('Client connected')

@socketio.on('disconnect')
def handle_disconnect():
    logger.info('Client disconnected')

app.add_url_rule('/', 'webio_view', webio_view(main), methods=['GET', 'POST', 'OPTIONS'])

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    socketio.run(app, host='0.0.0.0', port=port)
