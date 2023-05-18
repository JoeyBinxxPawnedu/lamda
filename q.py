import sqlite3
import json
import operator
import random
import telegram
import os
import logging
import time
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackQueryHandler

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')

def setup_database():
    conn = sqlite3.connect('highscores.db')
    cursor = conn.cursor()

    cursor.execute('''CREATE TABLE IF NOT EXISTS highscores
                      (user_id INTEGER, user_name TEXT, chat_id INTEGER, score INTEGER,
                       PRIMARY KEY (user_id, chat_id))''')

    conn.commit()
    conn.close()

def load_categories():
    categories = {}
    category_path = 'categories'
    for filename in os.listdir(category_path):
        if filename.endswith('.json'):
            category_name = os.path.splitext(filename)[0]
            with open(os.path.join(category_path, filename), 'r') as f:
                categories[category_name] = json.load(f)
    return categories

class QuizBot:
    def __init__(self, token):
        self.bot = telegram.Bot(token=token)
        self.updater = Updater(token=token, use_context=True)
        self.dispatcher = self.updater.dispatcher

        # Load the questions from the categories folder
        self.categories = load_categories()

        # Register the handlers
        self.register_handlers()

        # Set up the SQLite database for high scores
        setup_database()

    def register_handlers(self):
        self.dispatcher.add_handler(CommandHandler('start', self.start))
        self.dispatcher.add_handler(CommandHandler('cat', self.show_categories))
        self.dispatcher.add_handler(CallbackQueryHandler(self.select_category, pattern='^category:'))
        self.dispatcher.add_handler(CallbackQueryHandler(self.answer))
        self.dispatcher.add_handler(CommandHandler('score', self.score))
        self.dispatcher.add_handler(CommandHandler('highscores', self.highscores))
        self.dispatcher.add_handler(CommandHandler('leaderboard', self.leaderboard))
        self.dispatcher.add_handler(CommandHandler('end', self.end))
        self.dispatcher.add_handler(CommandHandler('next', self.next_question))

    def start(self, update, context):
        update.message.reply_text("Welcome to the quiz bot! Type /cat to select a category.")

    def show_categories(self, update, context):
        keyboard = [[InlineKeyboardButton(category_name, callback_data=f"category:{category_name}")] for category_name in self.categories.keys()]
        reply_markup = InlineKeyboardMarkup(keyboard)
        update.message.reply_text("Select a category:", reply_markup=reply_markup)

    def select_category(self, update, context):
        query = update.callback_query
        query.answer()
        category_name = query.data[9:]
        context.chat_data["current_category"] = category_name
        context.chat_data["current_questions"] = random.sample(self.categories[category_name]["questions"], 5)
        context.chat_data["current_question_index"] = 0
        context.chat_data["score"] = 0
        self.ask_question(update, context)

    def ask_question(self, update, context):
        current_question = context.chat_data["current_questions"][context.chat_data["current_question_index"]]
        context.chat_data["current_question"] = current_question
        choices = current_question["choices"]
        random.shuffle(choices)
        keyboard = [[InlineKeyboardButton(choice, callback_data=choice)] for choice in choices]
        reply_markup = InlineKeyboardMarkup(keyboard)
        update.message.reply_text(f"{current_question['question']}", reply_markup=reply_markup)

    def answer(self, update, context):
        query = update.callback_query
        query.answer()
        user_answer = query.data
        correct_answer = context.chat_data["current_question"]["answer"]
        if user_answer == correct_answer:
            context.chat_data["score"] += 1
            query.edit_message_text("Correct!")
        else:
            query.edit_message_text("Incorrect :(")
        context.chat_data["current_question_index"] += 1
        if context.chat_data["current_question_index"] == len(context.chat_data["current_questions"]):
            self.end_quiz(update, context)
        else:
            self.ask_question(update, context)

    def end_quiz(self, update, context):
        score = context.chat_data["score"]
        user_id = update.message.from_user.id
        user_name = update.message.from_user.username
        chat_id = update.message.chat_id
        self.save_highscore(user_id, user_name, chat_id, score)
        update.message.reply_text(f"Quiz ended! You scored {score} out of {len(context.chat_data['current_questions'])}. Type /cat to select another category.")

    def score(self, update, context):
        if "current_question" in context.chat_data:
            update.message.reply_text(f"You are on question {context.chat_data['current_question_index']+1} of {len(context.chat_data['current_questions'])} and your score is {context.chat_data['score']}.")
        else:
            update.message.reply_text("You are not currently in a quiz. Type /cat to select a category.")

    def save_highscore(self, user_id, user_name, chat_id, score):
        conn = sqlite3.connect('highscores.db')
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO highscores VALUES (?, ?, ?, ?)", (user_id, user_name, chat_id, score))
        conn.commit()
        conn.close()

    def highscores(self, update, context):
        conn = sqlite3.connect('highscores.db')
        cursor = conn.cursor()
        cursor.execute("SELECT user_name, score FROM highscores WHERE chat_id = ? ORDER BY score DESC LIMIT 10", (update.message.chat_id,))
        highscores = cursor.fetchall()
        conn.close()
        if len(highscores) == 0:
            update.message.reply_text("There are no high scores for this chat yet.")
        else:
            message = "High scores:\n"
            for i, (user_name, score) in enumerate(highscores):
                message += f"{i+1}. {user_name}: {score}\n"
            update.message.reply_text(message)

    def leaderboard(self, update, context):
        conn = sqlite3.connect('highscores.db')
        cursor = conn.cursor()
        cursor.execute("SELECT user_name, SUM(score) FROM highscores WHERE user_id = ? GROUP BY user_id ORDER BY SUM(score) DESC LIMIT 10", (update.message.from_user.id,))
        leaderboard = cursor.fetchall()
        conn.close()
        if len(leaderboard) == 0:
            update.message.reply_text("You have not played any quizzes yet.")
        else:
            message = "Your leaderboard:\n"
            for i, (user_name, total_score) in enumerate(leaderboard):
                message += f"{i+1}. {user_name}: {total_score}\n"
            update.message.reply_text(message)

    def end(self, update, context):
        if "current_question" in context.chat_data:
            self.end_quiz(update, context)
        else:
            update.message.reply_text("You are not currently in a quiz. Type /cat to select a category.")

    def next_question(self, update, context):
        if "current_question" in context.chat_data:
            self.answer(update, context)
        else:
            update.message.reply_text("You are not currently in a quiz. Type /cat to select a category.")

    def run(self):
        self.updater.start_polling()
        logging.info("QuizBot started.")
        while True:
            time.sleep(60)
            
if __name__ == '__main__':
    with open('token.txt', 'r') as f:
        token = f.read().strip()
    bot = QuizBot(token)
    bot.run()
