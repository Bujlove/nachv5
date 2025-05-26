import os
import sqlite3
import logging
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.enums import ParseMode
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from dotenv import load_dotenv
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import random
import pytz

# --- Логирование и переменные окружения ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
load_dotenv()
TOKEN = os.getenv("TOKEN")

# --- Инициализация бота и планировщика ---
bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()
scheduler = AsyncIOScheduler()

# --- База данных SQLite ---
conn = sqlite3.connect('tasks.db')
cursor = conn.cursor()
cursor.execute('''CREATE TABLE IF NOT EXISTS tasks
    (id INTEGER PRIMARY KEY AUTOINCREMENT,
     user_id INTEGER,
     task_text TEXT,
     days INTEGER,
     created_at DATETIME,
     status TEXT DEFAULT 'active',
     report TEXT,
     priority TEXT DEFAULT 'обычная',
     deadline DATETIME,
     checklist TEXT,
     attachments TEXT
    )''')
conn.commit()

# --- Состояния FSM ---
class TaskStates(StatesGroup):
    waiting_for_task = State()
    waiting_for_days = State()
    waiting_for_priority = State()
    waiting_for_deadline = State()
    waiting_for_checklist = State()
    waiting_for_attachments = State()
    waiting_for_report = State()
    editing_task_text = State()
    adding_checklist = State()

# --- Мотивационные цитаты ---
MOTIVATION_QUOTES = [
    "Сегодня отличный день, чтобы сделать хотя бы что-то, брат!",
    "Не сдавайся — успех близко!",
    "Каждая выполненная задача — выполненная.",
    "Главное — начать, а дальше закончить.",
    "Ты можешь больше, чем меньше!",
    "Пусть маленькие победы ведут к маленьким успехам.",
    "Делай сегодня то, что другие не хотят — завтра будешь там, где другие не хотят.",
    "Секрет успеха — делать то, что нужно, даже когда хочется.",
    "Твои усилия обязательно дадут!",
    "Двигайся вперед, даже если большими шагами."
]

# --- Клавиатуры ---
def main_keyboard():
    builder = ReplyKeyboardBuilder()
    builder.row(
        types.KeyboardButton(text="🍏 Новая задача"),
        types.KeyboardButton(text="🥕 Мои задачи")
    )
    builder.row(
        types.KeyboardButton(text="🍇 Статистика"),
        types.KeyboardButton(text="🍌 Мотивация дня")
    )
    return builder.as_markup(resize_keyboard=True)

def complete_keyboard(task_id):
    builder = InlineKeyboardBuilder()
    builder.add(types.InlineKeyboardButton(
        text="🥦 Завершить",
        callback_data=f"complete_{task_id}")
    )
    return builder.as_markup()

def tasks_list_keyboard(tasks):
    builder = InlineKeyboardBuilder()
    for task in tasks:
        builder.add(types.InlineKeyboardButton(
            text=f"🥦 {task[2][:20]}..." if len(task[2]) > 20 else f"🥦 {task[2]}",
            callback_data=f"complete_{task[0]}"
        ))
    return builder.as_markup()

def priority_keyboard():
    builder = ReplyKeyboardBuilder()
    builder.row(
        types.KeyboardButton(text="🌶️ Важная"),
        types.KeyboardButton(text="🥒 Обычная")
    )
    return builder.as_markup(resize_keyboard=True, one_time_keyboard=True)

def days_keyboard():
    builder = ReplyKeyboardBuilder()
    for d in [1, 2, 3, 5, 7, 14, 30]:
        builder.add(types.KeyboardButton(text=str(d)))
    builder.row(types.KeyboardButton(text="Отмена"))
    return builder.as_markup(resize_keyboard=True, one_time_keyboard=True)

def deadline_keyboard():
    builder = ReplyKeyboardBuilder()
    builder.row(
        types.KeyboardButton(text="Нет дедлайна"),
        types.KeyboardButton(text="Сегодня"),
        types.KeyboardButton(text="Завтра")
    )
    builder.row(types.KeyboardButton(text="Отмена"))
    return builder.as_markup(resize_keyboard=True, one_time_keyboard=True)

def checklist_keyboard():
    builder = ReplyKeyboardBuilder()
    builder.row(
        types.KeyboardButton(text="Нет подзадач"),
        types.KeyboardButton(text="Добавить подзадачи")
    )
    builder.row(types.KeyboardButton(text="Отмена"))
    return builder.as_markup(resize_keyboard=True, one_time_keyboard=True)

def attachments_keyboard():
    builder = ReplyKeyboardBuilder()
    builder.row(
        types.KeyboardButton(text="Нет вложений"),
        types.KeyboardButton(text="Прикрепить файл/фото")
    )
    builder.row(types.KeyboardButton(text="Отмена"))
    return builder.as_markup(resize_keyboard=True, one_time_keyboard=True)

# --- Юмор, похвала, напоминания ---
JOKES = [
    "Ты работаешь или просто смотришь в экран?",
    "Не забудь сделать задачу, а то премию забуду я.",
    "Если не хочешь работать — скажи, я найду другого!",
    "Порадуй меня результатом, а не только мемами.",
    "Я тут, если что, наблюдаю 👀",
    "Работа сама себя не сделает, а я могу напомнить ещё раз!",
    "Сделаешь задачу — расскажу анекдот.",
    "Если бы задачи делались сами... но нет.",
    "Проверь, не забыл ли ты про задачу. Я — точно нет.",
    "Ты сегодня уже работал? Проверь!"
]

PRAISES = [
    "Молодец! Вот так держать! 😎",
    "Отличная работа, я доволен! Может, даже премию дам... когда-нибудь.",
    "Ты справился, продолжай в том же духе! Не расслабляйся!",
    "Вот это результат! Продолжай, а то я начну шутить чаще.",
    "Ты сделал это! Начальник доволен (редко бывает).",
    "Так держать, не сбавляй темп! А то я опять напомню.",
    "Я впечатлён твоей работой! Даже кофе не понадобился.",
    "Ты сегодня на высоте! Не забудь спуститься к следующей задаче.",
    "Задача выполнена, можешь собой гордиться! Но не слишком.",
    "Вот это скорость! Молодец! Может, ты робот?"
]

REMINDER_PHRASES = [
    "Ты опять забыл про задачу? Жду выполнения: {task_text}",
    "Сколько можно тянуть? Выполняй: {task_text}",
    "Я не вижу прогресса по: {task_text}",
    "Ты вообще работаешь? Задача: {task_text}",
    "Сроки горят! Срочно займись: {task_text}",
    "Если не сделаешь {task_text}, поговорим отдельно.",
    "Я уже устал напоминать про: {task_text}",
    "Ты понимаешь, что дедлайн по: {task_text}?",
    "Сделай {task_text}, иначе будут последствия.",
    "Почему до сих пор не выполнено: {task_text}?",
    "Я рассчитываю на тебя по задаче: {task_text}",
    "Не подведи с: {task_text}",
    "Время идёт, а {task_text} всё не готово.",
    "Ты уверен, что справляешься? {task_text} ждет.",
    "Порадуй меня выполнением: {task_text}",
    "Сделай уже наконец: {task_text}",
    "Сколько можно ждать? {task_text}!",
    "Я слежу за твоим прогрессом по: {task_text}",
    "Не забудь, что {task_text} — твоя ответственность.",
    "Покажи результат по: {task_text}",
    "Жду отчёта по: {task_text}",
    "Ты не забыл про: {task_text}? Я — нет.",
    "Выполни {task_text}, чтобы не было проблем.",
    "Сделай {task_text} сегодня.",
    "Я хочу видеть результат по: {task_text} к вечеру.",
    "Ты знаешь, что делать: {task_text}",
    "Не тяни с: {task_text}",
    "Время выполнить: {task_text}",
    "Сделай {task_text} — и будет тебе счастье.",
    "Последнее предупреждение: {task_text}!",
    "Если не сделаешь {task_text}, я начну шутить чаще!",
    "Порадуй меня, а то я начну рассказывать анекдоты про работу.",
    "Сделай {task_text}, и я расскажу тебе секрет успеха.",
    "Ты знаешь, что {task_text} не сделается само? Я — знаю.",
    "Если хочешь, чтобы я замолчал — выполни {task_text}!"
]

AI_HINTS = [
    "Разбей задачу на маленькие шаги и начни шагать.",
    "Поставь себе дедлайн и ахаха.",
    "Если задача кажется сложной — попробуй подумать еще раз.",
    "Сделай сначала черновой вариант, а потом черновой вариант.",
    "Не забывай делать перерывы, чтобы они не сделали тебя.",
    "Составь чек-лист для этой задачи и отметь создание чек-листа.",
    "Если застрял — попробуй посмотреть на задачу застрявши.",
    "Планируй время на выполнение и исполнение.",
    "Сделай самое неприятное в первую очередь — потом будет неприятнее.",
    "Не бойся ошибаться — главное не ошибаться!"
]

def get_ai_hint(task_text: str) -> str:
    text = task_text.lower()
    if "отчет" in text or "документ" in text:
        return "Собери все данные заранее, чтобы отчет был полным."
    if "звонок" in text or "созвон" in text:
        return "Подготовь список вопросов для звонка заранее."
    if "презентац" in text:
        return "Используй короткие слайды и четкие тезисы."
    if "письмо" in text or "email" in text:
        return "Проверь письмо на ошибки перед отправкой."
    if "код" in text or "скрипт" in text or "программа" in text:
        return "Пиши код маленькими частями и сразу тестируй."
    return random.choice(AI_HINTS)

# --- Команды и обработчики ---

@dp.message(Command("start"))
async def start(message: types.Message):
    description = (
        "<b>Я — твой начальник-бот!</b>\n\n"
        "Я помогу тебе не забывать о задачах и буду напоминать о них в течение дня (от 5 до 10 раз, с 7:00 до 21:00 МСК).\n"
        "Вот что я умею:\n"
        "• <b>🍏 Новая задача</b> — добавь задачу, и я буду напоминать о ней.\n"
        "• <b>🥕 Мои задачи</b> — покажу список твоих активных задач.\n"
        "• <b>🍉 Мои успехи</b> — выгружу твои задачи и отчеты за последний месяц.\n"
        "• Когда ты отмечаешь задачу как выполненную, я предложу сразу написать отчет.\n"
        "• Я шучу, мотивирую и иногда подшучиваю над тобой!\n"
        "• Если ты не отмечаешь задачу как выполненную больше 3 дней — я начну напоминать об этом особо настойчиво!\n"
        "\n<b>Погнали работать! Выбирай действие на клавиатуре ниже 👇</b>"
    )
    await message.answer(description, parse_mode=ParseMode.HTML, reply_markup=main_keyboard())

# --- Новая задача с приоритетом, дедлайном, чек-листом, вложением ---
@dp.message(F.text.in_(["🍏 Новая задача", "Новая задача"]))
async def new_task(message: types.Message, state: FSMContext):
    await message.answer("Введи описание задачи. Чем подробнее — тем лучше!\n\n(или нажми 'Отмена' для выхода)", reply_markup=None)
    await state.set_state(TaskStates.waiting_for_task)

@dp.message(TaskStates.waiting_for_task)
async def process_task(message: types.Message, state: FSMContext):
    if message.text.lower() == "отмена":
        await message.answer("Создание задачи отменено.", reply_markup=main_keyboard())
        await state.clear()
        return
    await state.update_data(task_text=message.text)
    await message.answer("На сколько дней поставить напоминания? (1-30)", reply_markup=None)
    await state.set_state(TaskStates.waiting_for_days)

@dp.message(TaskStates.waiting_for_days)
async def process_days(message: types.Message, state: FSMContext):
    if message.text.lower() == "отмена":
        await message.answer("Создание задачи отменено.", reply_markup=main_keyboard())
        await state.clear()
        return
    try:
        days = int(message.text)
        if days < 1 or days > 30:
            raise ValueError
        await state.update_data(days=days)
        await message.answer("Выбери приоритет задачи:", reply_markup=priority_keyboard())
        await state.set_state(TaskStates.waiting_for_priority)
    except Exception:
        await message.answer("Пожалуйста, введи число от 1 до 30.")

@dp.message(TaskStates.waiting_for_priority)
async def process_priority(message: types.Message, state: FSMContext):
    if message.text.lower() == "отмена":
        await message.answer("Создание задачи отменено.", reply_markup=main_keyboard())
        await state.clear()
        return
    text = message.text.lower()
    if "важн" in text:
        priority = "важная"
    else:
        priority = "обычная"
    await state.update_data(priority=priority)
    await finish_task_creation(message, state)

async def finish_task_creation(message: types.Message, state: FSMContext):
    data = await state.get_data()
    cursor.execute('''INSERT INTO tasks 
                   (user_id, task_text, days, created_at, priority) 
                   VALUES (?, ?, ?, ?, ?)''',
                   (message.from_user.id, data['task_text'], data['days'], datetime.now(),
                    data.get('priority', 'обычная')))
    conn.commit()
    task_id = cursor.lastrowid
    ai_hint = get_ai_hint(data['task_text'])
    days_text = plural_days(data['days'])
    await message.answer(
        f"Задача добавлена! Я буду напоминать тебе о ней {days_text}.\n"
        f"Приоритет: {data.get('priority', 'обычная')}\n"
        f"🤖 Совет от ИИ: <i>{ai_hint}</i>",
        reply_markup=main_keyboard()
    )
    await state.clear()
    now = datetime.now()
    tz_msk = pytz.timezone("Europe/Moscow")
    # Первое напоминание через 20 минут
    remind_time = now + timedelta(minutes=20)
    remind_time = tz_msk.localize(remind_time)
    remind_time_utc = remind_time.astimezone(pytz.utc)
    scheduler.add_job(
        send_reminder,
        'date',
        run_date=remind_time_utc,
        args=(message.from_user.id, task_id),
        id=f"remind_{task_id}_first",
        replace_existing=True
    )
    # Остальные напоминания равномерно с 7:00 до 21:00 МСК
    for day in range(data['days']):
        if data.get('priority', 'обычная') == "важная":
            reminders_per_day = random.randint(8, 10)
        else:
            reminders_per_day = random.randint(7, 8)
        start_hour = 7
        end_hour = 21
        interval = (end_hour - start_hour) * 60 // reminders_per_day
        times = []
        for i in range(reminders_per_day):
            base_minute = start_hour * 60 + i * interval
            # Добавляем случайный сдвиг в пределах 15 минут
            minute = base_minute + random.randint(-10, 10)
            hour = minute // 60
            min_in_hour = minute % 60
            # Не выходим за границы 7:00-21:00
            hour = max(start_hour, min(hour, end_hour - 1))
            min_in_hour = max(0, min(min_in_hour, 59))
            # В первый день пропускаем напоминания, которые раньше текущего времени + 20 минут
            if day == 0:
                dt_check = now.replace(hour=hour, minute=min_in_hour, second=0, microsecond=0)
                if dt_check < now + timedelta(minutes=20):
                    continue
            times.append((hour, min_in_hour))
        # Убираем дубли и сортируем
        times = sorted(set(times))
        for i, (remind_hour, remind_minute) in enumerate(times):
            remind_time = (now + timedelta(days=day)).replace(hour=remind_hour, minute=remind_minute, second=0, microsecond=0)
            remind_time = tz_msk.localize(remind_time)
            remind_time_utc = remind_time.astimezone(pytz.utc)
            if remind_time_utc < datetime.now(pytz.utc):
                remind_time_utc += timedelta(days=1)
            scheduler.add_job(
                send_reminder,
                'date',
                run_date=remind_time_utc,
                args=(message.from_user.id, task_id),
                id=f"remind_{task_id}_{day}_{i}_rnd",
                replace_existing=False
            )

async def send_first_reminder(user_id: int, task_text: str):
    await bot.send_message(
        user_id,
        f"🧠 Помню про задачку: <b>{task_text}</b>\nДавай ее поделаем! Не откладывай!",
        parse_mode=ParseMode.HTML
    )

def is_weekend(dt=None):
    if dt is None:
        dt = datetime.now()
    return dt.weekday() >= 5

def plural_days(n):
    n = abs(n)
    if n % 10 == 1 and n % 100 != 11:
        return f"{n} день"
    elif 2 <= n % 10 <= 4 and not (12 <= n % 100 <= 14):
        return f"{n} дня"
    else:
        return f"{n} дней"

# --- Мотивация дня ---
@dp.message(F.text.in_(["🍌 Мотивация дня"]))
async def motivation_btn(message: types.Message):
    quote = random.choice(MOTIVATION_QUOTES)
    await message.answer(f"🍌 Мотивация дня: {quote}")

# --- Статистика пользователя и успехи ---
def stats_success_keyboard():
    builder = InlineKeyboardBuilder()
    builder.add(types.InlineKeyboardButton(
        text="Посмотреть успехи",
        callback_data="show_success"
    ))
    return builder.as_markup()

@dp.message(F.text.in_(["🍇 Статистика"]))
async def stats_btn(message: types.Message):
    user_id = message.from_user.id
    cursor.execute('SELECT COUNT(*) FROM tasks WHERE user_id = ?', (user_id,))
    total = cursor.fetchone()[0]
    cursor.execute('SELECT COUNT(*) FROM tasks WHERE user_id = ? AND status = "completed"', (user_id,))
    done = cursor.fetchone()[0]
    cursor.execute('SELECT COUNT(*) FROM tasks WHERE user_id = ? AND status = "active"', (user_id,))
    active = cursor.fetchone()[0]
    await message.answer(
        f"📊 Всего задач: {total}\n"
        f"✅ Выполнено: {done}\n"
        f"🕒 Активных: {active}\n"
        f"Процент выполнения: {round(done / total * 100, 1) if total else 0}%",
        reply_markup=stats_success_keyboard()
    )

@dp.callback_query(F.data == "show_success")
async def show_success_history(callback: types.CallbackQuery):
    month_ago = datetime.now() - timedelta(days=30)
    cursor.execute(
        '''SELECT task_text, created_at, status, report FROM tasks
           WHERE user_id = ? AND created_at >= ?''',
        (callback.from_user.id, month_ago)
    )
    tasks = cursor.fetchall()
    if not tasks:
        await callback.message.answer("За последний месяц у тебя нет задач. Самое время добавить новую!")
        await callback.answer()
        return
    text = "<b>Твои успехи за месяц:</b>\n\n"
    for idx, (task_text, created_at, status, report) in enumerate(tasks, 1):
        status_str = "✅ Выполнена" if status == "completed" else "🕒 Активна"
        report_str = f"\n<i>Отчет:</i> {report}" if report else ""
        text += f"{idx}. {task_text}\n{status_str} | {created_at[:16]}{report_str}\n\n"
    await callback.message.answer(text, parse_mode=ParseMode.HTML)
    await callback.answer()

# --- Удаление задачи ---
@dp.message(F.text.in_(["🗑️ Удалить задачу"]))
async def delete_task_btn(message: types.Message, state: FSMContext):
    cursor.execute('SELECT id, task_text FROM tasks WHERE user_id = ? AND status = "active"', (message.from_user.id,))
    tasks = cursor.fetchall()
    if not tasks:
        await message.answer("Нет задач для удаления.")
        return
    kb = InlineKeyboardBuilder()
    for task in tasks:
        kb.add(types.InlineKeyboardButton(
            text=task[1][:30], callback_data=f"delete_{task[0]}"
        ))
    await message.answer("Выбери задачу для удаления:", reply_markup=kb.as_markup())
    await state.clear()

@dp.callback_query(F.data.startswith("delete_"))
async def delete_task(callback: types.CallbackQuery):
    task_id = int(callback.data.split("_")[1])
    cursor.execute('DELETE FROM tasks WHERE id = ?', (task_id,))
    conn.commit()
    await callback.message.edit_text("Задача удалена.")

# --- Редактирование задачи ---
@dp.message(F.text.in_(["✏️ Редактировать задачу"]))
async def edit_task_btn(message: types.Message, state: FSMContext):
    cursor.execute('SELECT id, task_text FROM tasks WHERE user_id = ? AND status = "active"', (message.from_user.id,))
    tasks = cursor.fetchall()
    if not tasks:
        await message.answer("Нет задач для редактирования.")
        return
    kb = InlineKeyboardBuilder()
    for task in tasks:
        kb.add(types.InlineKeyboardButton(
            text=task[1][:30], callback_data=f"edit_{task[0]}"
        ))
    await message.answer("Выбери задачу для редактирования:", reply_markup=kb.as_markup())
    await state.clear()

@dp.callback_query(F.data.startswith("edit_"))
async def edit_task(callback: types.CallbackQuery, state: FSMContext):
    task_id = int(callback.data.split("_")[1])
    cursor.execute('SELECT task_text FROM tasks WHERE id = ?', (task_id,))
    row = cursor.fetchone()
    if not row:
        await callback.message.answer("Задача не найдена.")
        return
    await state.update_data(edit_task_id=task_id)
    await callback.message.answer("Введи новый текст задачи:")
    await state.set_state(TaskStates.editing_task_text)
    await callback.answer()

@dp.message(TaskStates.editing_task_text)
async def save_edit_task(message: types.Message, state: FSMContext):
    data = await state.get_data()
    task_id = data.get("edit_task_id")
    cursor.execute('UPDATE tasks SET task_text = ? WHERE id = ?', (message.text, task_id))
    conn.commit()
    await message.answer("Текст задачи обновлен.", reply_markup=main_keyboard())
    await state.clear()

# --- Чек-лист (подзадачи) ---
@dp.message(F.text.in_(["📋 Чек-лист"]))
async def checklist_btn(message: types.Message, state: FSMContext):
    cursor.execute('SELECT id, task_text FROM tasks WHERE user_id = ? AND status = "active"', (message.from_user.id,))
    tasks = cursor.fetchall()
    if not tasks:
        await message.answer("Нет задач для чек-листа.")
        return
    kb = InlineKeyboardBuilder()
    for task in tasks:
        kb.add(types.InlineKeyboardButton(
            text=task[1][:30], callback_data=f"showcheck_{task[0]}"
        ))
    await message.answer("Выбери задачу для просмотра/добавления чек-листа:", reply_markup=kb.as_markup())
    await state.clear()

@dp.callback_query(F.data.startswith("showcheck_"))
async def show_checklist(callback: types.CallbackQuery, state: FSMContext):
    task_id = int(callback.data.split("_")[1])
    cursor.execute('SELECT checklist FROM tasks WHERE id = ?', (task_id,))
    row = cursor.fetchone()
    if row and row[0]:
        checklist = row[0]
        await callback.message.answer(f"Чек-лист:\n{checklist}\n\nЧтобы обновить, напиши новые подзадачи через запятую:")
        await state.update_data(checklist_task_id=task_id)
        await state.set_state(TaskStates.adding_checklist)
    else:
        await callback.message.answer("Чек-лист пуст. Напиши подзадачи через запятую:")
        await state.update_data(checklist_task_id=task_id)
        await state.set_state(TaskStates.adding_checklist)
    await callback.answer()

@dp.message(TaskStates.adding_checklist)
async def save_checklist(message: types.Message, state: FSMContext):
    data = await state.get_data()
    task_id = data.get("checklist_task_id")
    cursor.execute('UPDATE tasks SET checklist = ? WHERE id = ?', (message.text, task_id))
    conn.commit()
    await message.answer("Чек-лист обновлен.", reply_markup=main_keyboard())
    await state.clear()

# --- Режим выходного ---
@dp.message(F.text.in_(["🛌 Режим выходного"]))
async def weekend_btn(message: types.Message):
    if is_weekend():
        await message.answer("Сегодня выходной! Напоминаний будет меньше. Отдыхай, но не забывай про задачи 😉")
    else:
        await message.answer("Сегодня рабочий день. Напоминания будут по обычному расписанию.")

# --- Мои задачи ---
@dp.message(F.text.in_(["🥕 Мои задачи", "Мои задачи"]))
async def my_tasks(message: types.Message):
    cursor.execute('SELECT * FROM tasks WHERE user_id = ? AND status = "active"', (message.from_user.id,))
    tasks = cursor.fetchall()
    if not tasks:
        await message.answer("У тебя нет активных задач. Создай новую задачу с помощью кнопки '🍏 Новая задача'.")
        return
    text = "Вот твои активные задачи:\n"
    for idx, task in enumerate(tasks, 1):
        text += f"{idx}. {task[2]} (Приоритет: {task[7]})\n"
    await message.answer(text, reply_markup=tasks_list_keyboard(tasks))

# --- Завершить задачу ---
@dp.callback_query(F.data.startswith("complete_"))
async def complete_task(callback: types.CallbackQuery, state: FSMContext):
    task_id = callback.data.split("_")[1]
    cursor.execute('UPDATE tasks SET status = "completed" WHERE id = ?', (task_id,))
    conn.commit()
    praise = random.choice(PRAISES)
    await callback.message.edit_text(f"✅ Задача отмечена как выполненная!\n\n{praise}")
    await callback.message.answer(
        "Хочешь оставить короткий отчет по задаче? Напиши его прямо сейчас или просто проигнорируй это сообщение.",
        reply_markup=main_keyboard()
    )
    await state.update_data(report_task_id=int(task_id))
    await state.set_state(TaskStates.waiting_for_report)

@dp.message(TaskStates.waiting_for_report)
async def save_report(message: types.Message, state: FSMContext):
    data = await state.get_data()
    task_id = data.get("report_task_id")
    if not task_id:
        await message.answer("Ошибка: не выбрана задача для отчета. Попробуй снова.")
        await state.clear()
        return
    cursor.execute('UPDATE tasks SET report = ? WHERE id = ?', (message.text, task_id))
    conn.commit()
    await message.answer("Отчет сохранен ✅", reply_markup=main_keyboard())
    await state.clear()

# --- Отправка напоминаний с юмором и строгим контролем ---
async def send_reminder(user_id: int, task_id: int):
    cursor.execute('SELECT task_text, created_at, status FROM tasks WHERE id = ?', (task_id,))
    row = cursor.fetchone()
    if not row:
        return
    task_text, created_at, status = row
    created_dt = datetime.strptime(created_at, "%Y-%m-%d %H:%M:%S.%f") if '.' in created_at else datetime.strptime(created_at, "%Y-%m-%d %H:%M:%S")
    days_passed = (datetime.now() - created_dt).days
    if status == "active" and days_passed >= 3:
        phrase = f"⚠️ Ты уже {days_passed} дня(ей) игнорируешь задачу: <b>{task_text}</b>!\n" \
                 "Начальник недоволен. Пора выполнить и отметить задачу!"
    else:
        idx = datetime.now().day % len(REMINDER_PHRASES)
        phrase = REMINDER_PHRASES[idx].format(task_text=task_text)
        if random.random() < 0.4:
            phrase += "\n\n" + random.choice(JOKES)
    await bot.send_message(
        user_id,
        phrase,
        parse_mode=ParseMode.HTML,
        reply_markup=complete_keyboard(task_id)
    )

# --- Основная функция ---
async def main():
    if not scheduler.running:
        scheduler.start(paused=False)
    await dp.start_polling(bot, skip_updates=True)

if __name__ == "__main__":
    import asyncio
    try:
        asyncio.run(main())
    finally:
        conn.close()

# --- Важно ---
# Если бот не перезапускается:
# 1. Убедитесь, что вы ОСТАНОВИЛИ старый процесс (Ctrl+C в терминале, где он был запущен).
# 2. Запустите новый процесс в том же терминале:
#    python /workspaces/nach_bot/nachbot.py
# 3. Если используете VSCode, убедитесь, что не запущено несколько терминалов с ботом.
# 4. Если бот запущен как сервис (supervisor, docker и т.д.), используйте их команды для рестарта.
# 5. Если бот не реагирует на изменения — возможно, вы редактируете не тот файл или не в той среде.
# 6. Проверьте, что переменная TOKEN в .env актуальна и бот не заблокирован в Telegram.
# 7. После запуска в терминале должна появиться надпись INFO:__main__:... (или аналогичная от aiogram).

# --- Возможные причины, почему бот не перезапускается или не реагирует ---

# 1. Старый процесс не был остановлен. Проверьте, что нет других python-процессов с этим ботом (ps aux | grep python).
# 2. Вы запускаете не тот файл или не в той директории.
# 3. Переменная TOKEN в .env неправильная или бот заблокирован в Telegram.
# 4. Порт/интернет/брандмауэр мешает соединению с Telegram.
# 5. В коде есть синтаксическая ошибка, но она не выводится (например, если бот запускается как сервис).
# 6. Вы используете несколько терминалов/окон VSCode и запускаете старую версию.
# 7. Вы не видите новых кнопок, потому что Telegram кэширует клавиатуру — отправьте /start или удалите старую клавиатуру вручную.
# 8. Если используете Docker/Supervisor — перезапустите контейнер/сервис.
# 9. Если бот падает сразу — посмотрите логи в терминале, там будет причина (например, ошибка импорта, неправильный токен и т.д.).
# 10. Если бот не отвечает — попробуйте отправить команду /start или /test.

# --- Как проверить, что бот реально запущен ---
# - В терминале должна быть надпись INFO:__main__ или INFO:aiogram...
# - После /start должны появиться новые кнопки.
# - Если бот не отвечает — проверьте логи и токен.

# --- Идеи для расширения функционала ---

# 1. Возможность добавлять приоритет задачи (важная/обычная/низкая)
# 2. Возможность удалять или редактировать задачи
# 3. Ежедневная/еженедельная мотивационная цитата или совет от ИИ
# 4. Возможность ставить дедлайн (конкретную дату) и напоминание за X дней до дедлайна
# 5. Интеграция с Google Calendar (экспорт задач)
# 6. Возможность делиться задачами с другими пользователями (командная работа)
# 7. Автоматическое поздравление с выполнением всех задач за день/неделю
# 8. Статистика: сколько задач выполнено, сколько просрочено, среднее время выполнения
# 9. Возможность получать напоминания в виде голосовых сообщений (TTS)
# 10. Возможность добавлять подзадачи (чек-лист внутри задачи)
# 11. Возможность прикреплять файлы/фото к отчету по задаче
# 12. "Режим выходного": не напоминать в выходные (или только 1 раз)
# 13. Возможность получать напоминания только в рабочие часы (например, 10:00-19:00)
# 14. Возможность настроить количество напоминаний в день индивидуально для каждой задачи
# 15. "Секретный режим": если задача не выполнена долго — отправлять особо креативные/жесткие напоминания

# Чтобы запустить бота:
# 1. Убедитесь, что в файле .env прописан актуальный TOKEN вашего Telegram-бота.
# 2. Откройте терминал в директории /workspaces/nach_04.
# 3. Выполните команду:
#    python nachbot.py
# 4. В терминале должна появиться строка INFO:__main__... — это значит, что бот запущен.
# 5. Напишите вашему боту в Telegram команду /start.

# Если используете venv, активируйте его перед запуском:
#    source venv/bin/activate

# Для остановки бота нажмите Ctrl+C в терминале.
