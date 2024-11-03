import asyncio
import random

from pywebio import start_server
from pywebio.input import *
from pywebio.output import *
from pywebio.session import defer_call, info as session_info, run_async, run_js

chat_rooms = {}

MAX_MESSAGES_COUNT = 100

def generate_chat_id():
    return ''.join(random.choices('0123456789', k=6))

async def main():
    global chat_rooms
    
    put_markdown("## 🧊 Добро пожаловать в онлайн чат!\nИсходный код данного чата укладывается в 100 строк кода!")

    chat_id = await input("Введите ID чата (оставьте пустым для создания нового)", required=False, placeholder="6-значный ID")
    
    if not chat_id:
        chat_id = generate_chat_id()
        chat_rooms[chat_id] = {'msgs': [], 'users': set()}
        toast(f"Создан новый чат с ID: {chat_id}")
    elif chat_id not in chat_rooms:
        toast("Чат с таким ID не найден!", color='error')
        return

    # Отображение ID чата в заголовке
    put_markdown(f"## 🧊 Чат ID: {chat_id}")

    msg_box = output()
    put_scrollable(msg_box, height=300, keep_bottom=True)

    nickname = await input("Войти в чат", required=True, placeholder="Ваше имя", validate=lambda n: "Такой ник уже используется!" if n in chat_rooms[chat_id]['users'] or n == '📢' else None)
    chat_rooms[chat_id]['users'].add(nickname)

    chat_rooms[chat_id]['msgs'].append(('📢', f'`{nickname}` присоединился к чату!'))
    msg_box.append(put_markdown(f'📢 `{nickname}` присоединился к чату'))

    refresh_task = run_async(refresh_msg(chat_id, nickname, msg_box))

    while True:
        data = await input_group("💭 Новое сообщение", [
            input(placeholder="Текст сообщения ...", name="msg"),
            actions(name="cmd", buttons=["Отправить", {'label': "Выйти из чата", 'type': 'cancel'}])
        ], validate = lambda m: ('msg', "Введите текст сообщения!") if m["cmd"] == "Отправить" and not m['msg'] else None)

        if data is None:
            break

        msg_box.append(put_markdown(f"`{nickname}`: {data['msg']}"))
        chat_rooms[chat_id]['msgs'].append((nickname, data['msg']))

    refresh_task.close()

    chat_rooms[chat_id]['users'].remove(nickname)
    toast("Вы вышли из чата!")
    msg_box.append(put_markdown(f'📢 Пользователь `{nickname}` покинул чат!'))
    chat_rooms[chat_id]['msgs'].append(('📢', f'Пользователь `{nickname}` покинул чат!'))

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
        
        last_idx = len(chat_rooms[chat_id]['msgs'])

if __name__ == "__main__":
    start_server(main, debug=True, port=8080, cdn=False)
