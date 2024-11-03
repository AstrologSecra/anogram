import threading
import time
import random
import logging
from pywebio import start_server
from pywebio.input import *
from pywebio.output import *
from pywebio.session import defer_call, info as session_info, run_async, run_js

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

    refresh_thread = threading.Thread(target=refresh_msg, args=(chat_id, nickname, msg_box))
    refresh_thread.start()

    while True:
        data = input_group("💭 Новое сообщение", [
            input(placeholder="Текст сообщения ...", name="msg"),
            actions(name="cmd", buttons=["Отправить", {'label': "Выйти из чата", 'type': 'cancel'}])
        ], validate = lambda m: ('msg', "Введите текст сообщения!") if m["cmd"] == "Отправить" and not m['msg'] else None)

        if data is None:
            break

        msg_box.append(put_markdown(f"`{nickname}`: {data['msg']}"))
        chat_msgs[chat_id].append((nickname, data['msg']))

    refresh_thread.join()

    toast("Вы вышли из чата!")
    msg_box.append(put_markdown(f'📢 Пользователь `{nickname}` покинул чат!'))
    chat_msgs[chat_id].append(('📢', f'Пользователь `{nickname}` покинул чат!'))

    put_buttons(['Перезайти'], onclick=lambda btn:run_js('window.location.reload()'))

def refresh_msg(chat_id, nickname, msg_box):
    global chat_msgs
    last_idx = len(chat_msgs[chat_id])

    while True:
        time.sleep(1)
        
        for m in chat_msgs[chat_id][last_idx:]:
            if m[0] != nickname: # if not a message from current user
                msg_box.append(put_markdown(f"`{m[0]}`: {m[1]}"))
        
        # remove expired
        if len(chat_msgs[chat_id]) > MAX_MESSAGES_COUNT:
            chat_msgs[chat_id] = chat_msgs[chat_id][len(chat_msgs[chat_id]) // 2:]
        
        last_idx = len(chat_msgs[chat_id])

if __name__ == "__main__":
    start_server(main, debug=True, port=8080, cdn=False)
