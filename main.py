import pymorphy2
from telebot import *
import vk_api
from datetime import datetime
import re
from geopy.geocoders import Nominatim
from geopy.distance import geodesic
import time

bot = telebot.TeleBot('7183192392:AAG53TBa0Xd0DPp2ahiI2SZrKqricU6gqu4', parse_mode='HTML')
c1 = types.BotCommand(command='start', description='Нажмите, чтобы активировать бота')
c2 = types.BotCommand(command='add', description='Добавить слово, с которым следует исключать посты')
c3 = types.BotCommand(command='delete', description='Убрать слово из списка исключенных')
c4 = types.BotCommand(command='spisok', description='Посмотреть список исключенных слов')
bot.set_my_commands([c1, c2, c3, c4])

toke = 'vk1.a.yJP2YueD-SJh3Rd3eNFX0m8_W4-T2achjEZ1YeBscS5sGZOpv5lh12RBnWIK4oGNqedCz8-gpKshI2ohUTsxWSqSGebNZs8SGP81spFb-td1P5kbMyRaNTa77Jpa4h78cb0m-iNBCEQ-Z6VKc2hZ6z1aSeN8ikmf52hkZy8S18cRtn30oI3aqbVcrylQhXpGIrxZJdGAV_mJ_4SSsvOvFQ'
vk_session = vk_api.VkApi(token=toke)
vk = vk_session.get_api()
morph = pymorphy2.MorphAnalyzer()
excluded_words = ['школа', 'детский', 'сад', 'школьник', 'доу', 'сош']
# Преобразуем список исключенных слов в начальную форму (леммы)
excluded_words_lemmas = [morph.parse(word)[0].normal_form for word in excluded_words]

# Добавление нового слова в список
@bot.message_handler(commands=['add'])
def add_excluded_word(message):
    bot.send_message(message.chat.id, 'Введите слово, которое следует исключить:')
    bot.register_next_step_handler(message, save_excluded_word)

def save_excluded_word(message):
    word = message.text.lower()
    word_lemma = morph.parse(word)[0].normal_form
    excluded_words_lemmas.append(word_lemma)
    bot.send_message(message.chat.id, f"Слово '{word}' добавлено в список исключенных. Текущий список:\n" + "\n".join(excluded_words_lemmas))

@bot.message_handler(commands=['spisok'])

def spiso(message):
    bot.send_message(message.chat.id, f"Текущий список исключенных слов:\n" + "\n".join(excluded_words_lemmas))
# Удаление слова из списка
@bot.message_handler(commands=['delete'])
def remove_excluded_word(message):
    bot.send_message(message.chat.id, 'Введите слово, которое нужно удалить:')
    bot.register_next_step_handler(message, delete_excluded_word)

def delete_excluded_word(message):
    word = message.text.lower()
    word_lemma = morph.parse(word)[0].normal_form
    if word_lemma in excluded_words_lemmas:
        excluded_words_lemmas.remove(word_lemma)
        bot.send_message(message.chat.id, f"Слово '{word}' удалено из списка.")
    else:
        bot.send_message(message.chat.id, f"Слово '{word}' не найдено в списке.")
# Старт бота
@bot.message_handler(commands=['start'])
def get_user_text(message):
    bot.send_message(message.chat.id, 'Введите ключевые слова для поиска новостей:')
    bot.register_next_step_handler(message, ask_post_count)

# Запрос количества постов
def ask_post_count(message):
    search_query = message.text
    bot.send_message(message.chat.id, 'Введите количество постов:')
    bot.register_next_step_handler(message, lambda msg: ask_city(msg, search_query))

# Запрос города
def ask_city(message, search_query):
    count = int(message.text)
    bot.send_message(message.chat.id, 'Введите город, в котором необходимо найти новости:')
    bot.register_next_step_handler(message, lambda msg: search_posts(msg, search_query, count))

# Функция для отправки длинных сообщений
def send_long_message(chat_id, text):
    max_message_length = 4096
    for i in range(0, len(text), max_message_length):
        bot.send_message(chat_id, text[i:i + max_message_length])

# Поиск новостей с учетом геометки и исключенных слов
def search_posts(message, search_query, count):
    w = 0
    try:
        geolocator = Nominatim(user_agent="my_vk_news_bot_v1.0")
        city = message.text
        location = geolocator.geocode(city)
        ex = morph.parse(city).normal_form
        if location:
            lat = location.latitude
            lon = location.longitude
            bot.send_message(message.chat.id, f"Ищем новости в городе {city}...")

            # Запрос новостей из VK
            response = vk.newsfeed.search(q=search_query, count=count * 2, extended=1, v=5.131, latitude=lat, longitude=lon, radius=50000)

            filtered_posts = []
            if 'items' in response:
                users = {user['id']: f"{user['first_name']} {user['last_name']}" for user in response.get('profiles', [])}
                groups = {group['id']: group['name'] for group in response.get('groups', [])}

                for item in response['items']:
                    post_text = item['text']

                    # Лемматизация текста поста
                    post_words = post_text.split()
                    post_lemmas = [morph.parse(word)[0].normal_form for word in post_words]

                    # Проверка на наличие исключенных слов
                    if any(word in excluded_words_lemmas for word in post_lemmas):
                        continue

                    # Фильтрация по геометке
                    if 'geo' in item and 'coordinates' in item['geo']:
                        post_lat = float(item['geo']['coordinates']['latitude'])
                        post_lon = float(item['geo']['coordinates']['longitude'])

                        distance = geodesic((lat, lon), (post_lat, post_lon)).km
                        if distance > 50:  # Ограничиваем радиус поиска 50 км
                            continue

                    # Фильтрация по названию группы
                    owner_id = item['owner_id']
                    if owner_id < 0:  # Это группа
                        group_name = groups.get(abs(owner_id), "")
                        group_lemmas = [morph.parse(word)[0].normal_form for word in group_name.split()]
                        if any(kw in group_lemmas for kw in excluded_words_lemmas):
                            continue  # Пропускаем посты, если название группы содержит исключенные слова

                    filtered_posts.append(item)

                    # Прекращаем поиск, если достигли нужного количества постов
                    if len(filtered_posts) >= count:
                        break

            # Отправка результатов пользователю
            if filtered_posts:
                for item in filtered_posts:
                    post_text = item['text']
                    post_date = datetime.fromtimestamp(item['date']).strftime('%Y-%m-%d %H:%M:%S')
                    owner_id = item['owner_id']
                    post_id = item['id']

                    if owner_id > 0:
                        author_name = users.get(owner_id, "Неизвестный пользователь")
                    else:
                        author_name = groups.get(abs(owner_id), "Неизвестная группа")

                    post_link = f"https://vk.com/wall{owner_id}_{post_id}"

                    # Формируем сообщение
                    message_text = f"<b>Автор:</b> {author_name}\n<b>Дата поста:</b> {post_date}\n<b>Текст поста:</b> {post_text}\n<a href='{post_link}'>Ссылка на пост</a>\n"

                    # Отправляем сообщение
                    send_long_message(message.chat.id, message_text)
            else:
                bot.send_message(message.chat.id, "Новостей не найдено.")
        else:
            bot.send_message(message.chat.id, "Не удалось найти новости по вашему запросу.")
    except Exception as e:
        bot.send_message(message.chat.id, f"Произошла ошибка: {str(e)}")

bot.polling(none_stop=True)