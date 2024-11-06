import asyncio
import random
import logging
import os
import hashlib
import base64
import json
from io import BytesIO
from PIL import Image
import shutil

from pywebio import start_server
from pywebio.input import *
from pywebio.output import *
from pywebio.session import defer_call, info as session_info, run_async, run_js

# Настройка логирования
logging.basicConfig(level=logging.DEBUG)

chat_rooms = {}
users_db = {}  # База данных пользователей (хэш -> имя)

MAX_MESSAGES_COUNT = 10

def generate_chat_id():
    return ''.join(random.choices('0123456789', k=6))

def generate_hash(name):
    random_chars = ''.join(random.choices('abcdefghijklmnopqrstuvwxyz0123456789', k=5))
    hash_input = f"{name}{random_chars}"
    hash_object = hashlib.sha256(hash_input.encode())
    return base64.b64encode(hash_object.digest()).decode()

def load_data():
    global chat_rooms, users_db
    if os.path.exists('users.json'):
        try:
            with open('users.json', 'r') as f:
                users_db = json.load(f)
        except json.JSONDecodeError:
            users_db = {}
    if os.path.exists('chats.json'):
        try:
            with open('chats.json', 'r') as f:
                chat_rooms = json.load(f)
                for chat_id in chat_rooms:
                    chat_rooms[chat_id]['users'] = set(chat_rooms[chat_id]['users'])
        except json.JSONDecodeError:
            chat_rooms = {}

def save_data():
    with open('users.json', 'w') as f:
        json.dump(users_db, f)
    with open('chats.json', 'w') as f:
        json.dump(chat_rooms, f, default=lambda x: list(x) if isinstance(x, set) else x)

def compress_image(image_data):
    img = Image.open(BytesIO(image_data))
    img.thumbnail((img.width // 5, img.height // 5), Image.LANCZOS)
    output = BytesIO()
    img.save(output, format='JPEG' if img.format == 'JPEG' else 'PNG', quality=70)
    return output.getvalue()

async def main():
    global chat_rooms, users_db
    
    load_data()
    
    # Создаем чат с ID 000000, если его еще нет
    if '000000' not in chat_rooms:
        chat_rooms['000000'] = {'msgs': [], 'users': set()}
        save_data()
    
    put_markdown("## 🧊 Добро пожаловать в онлайн чат!\nИсходный код данного чата укладывается в 100 строк кода!")

    action = await select("Выберите действие", ["Регистрация", "Вход"])

    if action == "Регистрация":
        name = await input("Введите ваше имя", required=True)
        user_hash = generate_hash(name)
        users_db[user_hash] = name
        save_data()
        toast(f"Ваш хэш для входа: {user_hash}")
        logging.info(f"Зарегистрирован новый пользователь с хэшем: {user_hash}")
        run_js(f'window.open("about:blank", "_blank").document.write("Ваш хэш для входа: {user_hash}");')
    elif action == "Вход":
        user_hash = await input("Введите ваш хэш", required=True)
        if user_hash in users_db:
            name = users_db[user_hash]
            logging.info(f"Пользователь с хэшем {user_hash} вошел в систему")
        else:
            toast("Хэш не найден!", color='error')
            logging.warning(f"Хэш {user_hash} не найден")
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

    put_markdown(f"## 🧊 Чат ID: {chat_id}")

    msg_box = output()
    put_scrollable(msg_box, height=300, keep_bottom=True)

    chat_rooms[chat_id]['users'].add(name)
    save_data()

    chat_rooms[chat_id]['msgs'].append(('📢', f'`{name}` присоединился к чату!'))
    msg_box.append(put_markdown(f'📢 `{name}` присоединился к чату'))

    refresh_task = run_async(refresh_msg(chat_id, name, msg_box))

    run_js("""
    document.addEventListener('click', function(event) {
        if (event.target.tagName === 'IMG') {
            const imgSrc = event.target.src;
            const modal = document.createElement('div');
            modal.style.position = 'fixed';
            modal.style.top = '0';
            modal.style.left = '0';
            modal.style.width = '100%';
            modal.style.height = '100%';
            modal.style.backgroundColor = 'rgba(0, 0, 0, 0.8)';
            modal.style.display = 'flex';
            modal.style.justifyContent = 'center';
            modal.style.alignItems = 'center';
            modal.style.zIndex = '1000';
            modal.onclick = function() {
                document.body.removeChild(modal);
            };
            const img = document.createElement('img');
            img.src = imgSrc;
            img.style.maxWidth = '90%';
            img.style.maxHeight = '90%';
            modal.appendChild(img);
            document.body.appendChild(modal);
        }
    });
    """)

    while True:
        data = await input_group("💭 Новое сообщение", [
            input(placeholder="Текст сообщения ...", name="msg"),
            file_upload("Загрузить файл", name="file", accept="image/*, .gif, .jpeg, .mp3"),
            actions(name="cmd", buttons=["Отправить", {'label': "Выйти из чата", 'type': 'cancel'}] + (["Консоль"] if chat_id == '000000' else []))
        ], validate = lambda m: ('msg', "Введите текст сообщения или загрузите файл!") if m["cmd"] == "Отправить" and not m['msg'] and not m['file'] else None)

        if data is None:
            break

        if data['cmd'] == "Консоль" and chat_id == '000000':
            await console(name)
            continue

        if data['file']:
            file_info = data['file']['content']
            file_type = data['file']['mime_type']
            file_name = data['file']['filename']
            try:
                if file_type.startswith('image'):
                    compressed_image_data = compress_image(file_info)
                    file_data = base64.b64encode(compressed_image_data).decode('utf-8')
                    msg_box.append(put_markdown(f"`{name}`: ![{file_name}](data:{file_type};base64,{file_data})"))
                    chat_rooms[chat_id]['msgs'].append((name, f"![{file_name}](data:{file_type};base64,{file_data})"))
                elif file_type.startswith('audio'):
                    file_data = base64.b64encode(file_info).decode('utf-8')
                    msg_box.append(put_markdown(f"`{name}`: [🎵 {file_name}](data:{file_type};base64,{file_data})"))
                    msg_box.append(put_html(f'<audio controls><source src="data:{file_type};base64,{file_data}" type="{file_type}"></audio>'))
                    chat_rooms[chat_id]['msgs'].append((name, f"[🎵 {file_name}](data:{file_type};base64,{file_data})"))
                else:
                    toast("Неподдерживаемый тип файла", color='error')
            except Exception as e:
                logging.error(f"Ошибка при обработке файла: {e}")
                toast("Ошибка при обработке файла", color='error')
        else:
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

async def console(name):
    put_markdown("## Консоль")
    command = await input("Введите команду:", required=True)
    try:
        parts = command.split()
        cmd = parts[0]
        args = parts[1:]

        if cmd == "ls":
            files = os.listdir('.')
            result = "\n".join(files)
            put_markdown(f"```\n{result}\n```")
        elif cmd == "cd":
            if len(args) == 1:
                os.chdir(args[0])
                put_markdown(f"```\nПереход в директорию: {args[0]}\n```")
            else:
                put_markdown("```\nОшибка: Неверное количество аргументов\n```")
        elif cmd == "touch":
            if len(args) == 1:
                open(args[0], 'a').close()
                put_markdown(f"```\nСоздан файл: {args[0]}\n```")
            else:
                put_markdown("```\nОшибка: Неверное количество аргументов\n```")
        elif cmd == "rm":
            if len(args) == 1:
                if os.path.isfile(args[0]):
                    os.remove(args[0])
                    put_markdown(f"```\nУдален файл: {args[0]}\n```")
                elif os.path.isdir(args[0]):
                    shutil.rmtree(args[0])
                    put_markdown(f"```\nУдалена директория: {args[0]}\n```")
                else:
                    put_markdown("```\nОшибка: Файл или директория не найдена\n```")
            else:
                put_markdown("```\nОшибка: Неверное количество аргументов\n```")
        elif cmd == "pwd":
            current_dir = os.getcwd()
            put_markdown(f"```\n{current_dir}\n```")
        else:
            put_markdown("```\nНеизвестная команда\n```")
    except Exception as e:
        put_markdown(f"```\nОшибка: {e}\n```")

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
