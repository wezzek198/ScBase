import nest_asyncio
nest_asyncio.apply()

import logging
import json
import os
import re
import random
import traceback
import asyncio
import sys
from typing import Dict, Optional, List, Tuple
from datetime import datetime
from enum import Enum

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, PhotoSize
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters
)

# Telethon для User API
from telethon import TelegramClient
from telethon.tl.functions.users import GetUsersRequest
from telethon.tl.types import User

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Получаем путь к папке, где находится скрипт
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# Конфигурация - пути относительно папки скрипта
DB_FILE = os.path.join(SCRIPT_DIR, 'data', 'scammers_db.json')
CONFIG_FILE = os.path.join(SCRIPT_DIR, 'config.json')
IMAGES_FOLDER = os.path.join(SCRIPT_DIR, 'bot_images')
ADMIN_CHAT_ID = -1003660247060  # ID админ-чата


# Username бота для отображения в сообщениях
BOT_USERNAME = "wzkbScamBaseBot"

TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_API_ID = os.getenv('TELEGRAM_API_ID')
TELEGRAM_API_HASH = os.getenv('TELEGRAM_API_HASH')

# Канал для обязательной подписки
REQUIRED_CHANNEL_ID = -1002129588192  # ID канала для подписки
REQUIRED_CHANNEL_USERNAME = "@wzkbnews"  # Username канала

# Права доступа
class UserRole(Enum):
    USER = "user"        # Обычный пользователь
    ADMIN = "admin"      # Администратор (может добавлять/редактировать в админ-чате)
    SPECIAL_ADMIN = "special_admin"  # Спец-админ (может удалять)
    OWNER = "owner"      # Владелец (все права)

# Конфигурация по умолчанию
DEFAULT_CONFIG = {
    "owner_id": 1307172745,  # Ваш ID
    "special_admins": [7294311247],  # ID спец-админов
    "admins": [],  # ID обычных админов
    "admin_chat_id": ADMIN_CHAT_ID,  # ID админ-чата
    "admin_chat_username": "wzkbScamBaseChat",  # Username админ-чата
    "required_channel_id": REQUIRED_CHANNEL_ID,
    "required_channel_username": REQUIRED_CHANNEL_USERNAME,
    "images": {
        "scammer_found": None,
        "user_clean": None,
        "warning": None,
        "admin": None
    },
    "restrict_add_to_admin_chat": True,
    "check_subscription": True  # Включить проверку подписки
}

class Config:
    def __init__(self, config_file: str = CONFIG_FILE):
        self.config_file = config_file
        self.config = self.load_config()
        self.ensure_images_folder()
    
    def ensure_images_folder(self):
        """Создать папку для картинок, если её нет"""
        if not os.path.exists(IMAGES_FOLDER):
            os.makedirs(IMAGES_FOLDER)
            logger.info(f"Создана папка для картинок: {IMAGES_FOLDER}")
    
    def load_config(self) -> Dict:
        """Загрузка конфигурации из файла"""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    loaded_config = json.load(f)
                    config = DEFAULT_CONFIG.copy()
                    config.update(loaded_config)
                    return config
            except Exception as e:
                logger.error(f"Ошибка загрузки конфига: {e}")
                return DEFAULT_CONFIG.copy()
        return DEFAULT_CONFIG.copy()
    
    def save_config(self):
        """Сохранение конфигурации"""
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Ошибка сохранения конфига: {e}")
    
    def get_user_role(self, user_id: int) -> UserRole:
        """Получение роли пользователя"""
        try:
            user_id_int = int(user_id) if isinstance(user_id, str) and user_id.isdigit() else user_id
            
            if user_id_int == self.config['owner_id']:
                return UserRole.OWNER
            elif user_id_int in self.config['special_admins']:
                return UserRole.SPECIAL_ADMIN
            elif user_id_int in self.config['admins']:
                return UserRole.ADMIN
            else:
                return UserRole.USER
        except (ValueError, TypeError):
            return UserRole.USER
    
    def is_admin(self, user_id: int) -> bool:
        """Проверка, является ли пользователь администратором"""
        try:
            if isinstance(user_id, str):
                if user_id.isdigit():
                    user_id_int = int(user_id)
                else:
                    return False
            else:
                user_id_int = user_id
            
            user_role = self.get_user_role(user_id_int)
            return user_role in [UserRole.ADMIN, UserRole.SPECIAL_ADMIN, UserRole.OWNER]
        except Exception as e:
            logger.error(f"Ошибка проверки админа: {e}")
            return False
    
    def is_admin_chat(self, chat_id: int) -> bool:
        """Проверка, является ли чат админ-чатом"""
        return chat_id == self.config['admin_chat_id']
    
    def add_admin(self, user_id: int, role: UserRole):
        """Добавление администратора"""
        try:
            user_id_int = int(user_id) if isinstance(user_id, str) else user_id
            
            if user_id_int == self.config['owner_id']:
                return False, "Этот пользователь уже является владельцем"
            
            if role == UserRole.ADMIN:
                if user_id_int in self.config['admins']:
                    return False, "Пользователь уже является администратором"
                if user_id_int in self.config['special_admins']:
                    return False, "Пользователь уже является спец-админом"
                self.config['admins'].append(user_id_int)
            elif role == UserRole.SPECIAL_ADMIN:
                if user_id_int in self.config['special_admins']:
                    return False, "Пользователь уже является спец-админом"
                if user_id_int in self.config['admins']:
                    self.config['admins'].remove(user_id_int)
                self.config['special_admins'].append(user_id_int)
            
            self.save_config()
            return True, "Успешно добавлен"
        except Exception as e:
            logger.error(f"Ошибка добавления админа: {e}")
            return False, f"Ошибка: {str(e)}"
    
    def remove_admin(self, user_id: int):
        """Удаление администратора"""
        try:
            user_id_int = int(user_id) if isinstance(user_id, str) else user_id
            
            if user_id_int == self.config['owner_id']:
                return False, "Нельзя удалить владельца"
            
            removed = False
            if user_id_int in self.config['admins']:
                self.config['admins'].remove(user_id_int)
                removed = True
            if user_id_int in self.config['special_admins']:
                self.config['special_admins'].remove(user_id_int)
                removed = True
            
            if removed:
                self.save_config()
                return True, "Администратор удален"
            else:
                return False, "Пользователь не является администратором"
        except Exception as e:
            logger.error(f"Ошибка удаления админа: {e}")
            return False, f"Ошибка: {str(e)}"
    
    def list_admins(self) -> Dict[str, List[int]]:
        """Получить список всех администраторов"""
        return {
            'owner': self.config['owner_id'],
            'special_admins': self.config['special_admins'],
            'admins': self.config['admins']
        }
    
    def update_image_file(self, image_type: str, file_path: str):
        """Обновление пути к файлу картинки"""
        if image_type in self.config['images']:
            self.config['images'][image_type] = file_path
            self.save_config()
    
    def get_image_file(self, image_type: str) -> Optional[str]:
        """Получить путь к файлу картинки"""
        file_path = self.config['images'].get(image_type)
        if file_path and os.path.exists(file_path):
            return file_path
        return None
    
    def update_admin_chat(self, chat_id: int, chat_username: str = None):
        """Обновление ID админ-чата и его username"""
        self.config['admin_chat_id'] = chat_id
        if chat_username:
            self.config['admin_chat_username'] = chat_username
        self.save_config()
    
    def get_admin_chat_username(self) -> Optional[str]:
        """Получить username админ-чата"""
        return self.config.get('admin_chat_username')
    
    def get_required_channel(self) -> Dict:
        """Получить информацию о канале для подписки"""
        return {
            'id': self.config.get('required_channel_id', REQUIRED_CHANNEL_ID),
            'username': self.config.get('required_channel_username', REQUIRED_CHANNEL_USERNAME)
        }
    
    def is_check_subscription_enabled(self) -> bool:
        """Проверка включена ли проверка подписки"""
        return self.config.get('check_subscription', True)
    
    def set_check_subscription(self, enabled: bool):
        """Включить/выключить проверку подписки"""
        self.config['check_subscription'] = enabled
        self.save_config()

class TelegramUserAPI:
    """Класс для работы с Telegram User API (через Telethon)"""
    def __init__(self, api_id: int, api_hash: str):
        self.api_id = api_id
        self.api_hash = api_hash
        self.session_name = os.path.join(SCRIPT_DIR, 'telegram_session')
        self.client = None
        self.is_connected = False
        
    async def connect(self):
        """Подключиться к Telegram API"""
        try:
            print("🔌 Подключаюсь к Telegram User API...")
            if not self.is_connected:
                self.client = TelegramClient(
                    self.session_name,
                    self.api_id,
                    self.api_hash,
                    device_model="ScamBot User API",
                    system_version="1.0",
                    app_version="1.0",
                    lang_code="en"
                )
                
                await self.client.start()
                self.is_connected = True
                print("✅ Telegram User API подключен")
                return True
        except Exception as e:
            print(f"❌ Ошибка подключения Telegram User API: {e}")
            logger.error(f"Ошибка подключения Telegram User API: {e}")
            return False
    
    async def get_user_info(self, identifier: str):
        """Получить информацию о пользователе по username или ID"""
        try:
            if not self.is_connected:
                if not await self.connect():
                    return None
            
            clean_identifier = identifier.replace('@', '').strip()
            
            if clean_identifier.isdigit():
                try:
                    user_id = int(clean_identifier)
                    users = await self.client(GetUsersRequest([user_id]))
                    
                    if users and len(users) > 0:
                        user = users[0]
                        if isinstance(user, User):
                            return self._format_user_info(user)
                except Exception as e:
                    logger.debug(f"Не удалось получить по ID {clean_identifier}: {e}")
            
            try:
                user = await self.client.get_entity(f"@{clean_identifier}")
                if isinstance(user, User):
                    return self._format_user_info(user)
            except Exception as e:
                logger.debug(f"Не удалось получить по username {clean_identifier}: {e}")
                try:
                    user = await self.client.get_entity(clean_identifier)
                    if isinstance(user, User):
                        return self._format_user_info(user)
                except Exception as e2:
                    logger.debug(f"Не удалось получить по clean_identifier {clean_identifier}: {e2}")
            
            return None
            
        except Exception as e:
            logger.error(f"Ошибка в get_user_info для {identifier}: {e}")
            return None
    
    def _format_user_info(self, user: User) -> Dict:
        """Форматировать информацию о пользователе"""
        username = user.username or ""
        
        if not username:
            if user.first_name:
                username = user.first_name
                if user.last_name:
                    username += f" {user.last_name}"
            else:
                username = f"id{user.id}"
        
        return {
            'id': user.id,
            'username': username,
            'first_name': user.first_name or "",
            'last_name': user.last_name or "",
            'phone': user.phone or "",
            'bot': user.bot,
            'premium': getattr(user, 'premium', False),
            'scam': getattr(user, 'scam', False),
            'fake': getattr(user, 'fake', False),
            'verified': getattr(user, 'verified', False)
        }
    
    async def close(self):
        """Закрыть соединение"""
        if self.client and self.is_connected:
            await self.client.disconnect()
            self.is_connected = False
            print("🔌 Telegram User API отключен")

class ScamDatabase:
    def __init__(self, db_file: str = DB_FILE):
        self.db_file = db_file
        self.db = self.load_db()
    
    def load_db(self) -> Dict:
        """Загрузка базы данных из файла"""
        if os.path.exists(self.db_file):
            try:
                with open(self.db_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Ошибка загрузки базы: {e}")
                return {}
        return {}
    
    def save_db(self):
        """Сохранение базы данных в файл"""
        try:
            with open(self.db_file, 'w', encoding='utf-8') as f:
                json.dump(self.db, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Ошибка сохранения базы: {e}")
    
    def add_scammer(self, user_id: str, username: str, 
                   reason: str, added_by: int, chat_id: int = None,
                   country: str = None, proof_link: str = None) -> Tuple[bool, str, bool]:
        """Добавление скамера в базу или обновление существующего"""
        try:
            if user_id.isdigit():
                if config.is_admin(int(user_id)):
                    return False, "Нельзя добавить администратора в базу скамеров", False
            
            is_new = False
            if user_id in self.db:
                user_data = self.db[user_id]
                if user_data.get('status') == 'active':
                    existing_reasons = user_data.get('reasons', [])
                    if reason not in existing_reasons:
                        existing_reasons.append(reason)
                        user_data['reasons'] = existing_reasons
                    
                    user_data['reports'] = user_data.get('reports', 0) + 1
                    
                    if proof_link:
                        proofs = user_data.get('proofs', [])
                        if proof_link not in proofs:
                            proofs.append(proof_link)
                            user_data['proofs'] = proofs
                    
                    if username and username != user_data.get('username'):
                        user_data['username'] = username
                    
                    self.db[user_id] = user_data
                    self.save_db()
                    return True, "Обновлена запись в базе", False
                else:
                    is_new = True
            else:
                is_new = True
            
            if is_new:
                self.db[user_id] = {
                    'username': username,
                    'user_id': user_id,
                    'reasons': [reason],
                    'country': country,
                    'scam_chance': 100,
                    'proofs': [proof_link] if proof_link else [],
                    'added_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'added_by': added_by,
                    'added_from_chat': chat_id,
                    'reports': 1,
                    'status': 'active'
                }
                self.save_db()
                return True, "Успешно добавлен", True
            
        except Exception as e:
            logger.error(f"Ошибка добавления скамера: {e}")
            logger.error(traceback.format_exc())
            return False, f"Ошибка добавления: {str(e)}", False
    
    def check_user(self, user_id: str) -> Optional[Dict]:
        """Проверка пользователя в базе"""
        user_data = self.db.get(user_id)
        if user_data and user_data.get('status') == 'active':
            return user_data
        return None
    
    def find_scammer_by_username(self, username: str) -> Optional[Dict]:
        """Поиск скамера по username (с @ или без)"""
        clean_username = username.replace('@', '').lower()
        
        for user_id, info in self.db.items():
            if info.get('status') == 'active':
                db_username = info.get('username', '').replace('@', '').lower()
                if db_username == clean_username:
                    return info
                if user_id == clean_username:
                    return info
        return None
    
    def remove_scammer(self, user_id: str) -> bool:
        """Удаление скамера из базы"""
        if user_id in self.db:
            self.db[user_id]['status'] = 'removed'
            self.db[user_id]['removed_date'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            self.save_db()
            return True
        return False
    
    def permanently_delete_scammer(self, user_id: str) -> bool:
        """Полное удаление скамера из базы"""
        if user_id in self.db:
            del self.db[user_id]
            self.save_db()
            return True
        return False
    
    def increment_reports(self, user_id: str):
        """Увеличение счетчика жалоб"""
        if user_id in self.db:
            self.db[user_id]['reports'] = self.db[user_id].get('reports', 0) + 1
            self.save_db()
    
    def set_country(self, user_id: str, country: str):
        """Установка страны для скамера"""
        if user_id in self.db:
            self.db[user_id]['country'] = country
            self.save_db()
    
    def get_stats(self) -> Dict:
        """Получение статистики"""
        active_scammers = [u for u in self.db.values() if u.get('status') == 'active']
        total_scammers = len(active_scammers)
        total_reports = sum(user.get('reports', 0) for user in active_scammers)
        removed_scammers = len([u for u in self.db.values() if u.get('status') == 'removed'])
        
        return {
            'total_scammers': total_scammers,
            'total_reports': total_reports,
            'removed_scammers': removed_scammers,
            'total_in_db': len(self.db)
        }
    
    def search_by_country(self, country: str) -> List[Dict]:
        """Поиск скамеров по стране"""
        return [user for user in self.db.values() 
                if user.get('country', '').lower() == country.lower() 
                and user.get('status') == 'active']
    
    def get_recent_scammers(self, limit: int = 10) -> List[Dict]:
        """Получение последних добавленных скамеров"""
        active_scammers = [u for u in self.db.values() if u.get('status') == 'active']
        sorted_scammers = sorted(active_scammers, 
                                key=lambda x: x.get('added_date', ''), 
                                reverse=True)
        return sorted_scammers[:limit]

# Инициализация
config = Config()
db = ScamDatabase()
telegram_api = None

# Проверка прав
def has_permission(user_id: int, required_role: UserRole) -> bool:
    """Проверка наличия прав у пользователя"""
    user_role = config.get_user_role(user_id)
    
    role_hierarchy = {
        UserRole.USER: 0,
        UserRole.ADMIN: 1,
        UserRole.SPECIAL_ADMIN: 2,
        UserRole.OWNER: 3
    }
    
    return role_hierarchy[user_role] >= role_hierarchy[required_role]

def can_add_scammer(user_id: int, chat_id: int) -> bool:
    """Проверка, может ли пользователь добавлять скамеров в данном чате"""
    user_role = config.get_user_role(user_id)
    
    if user_role == UserRole.OWNER:
        return True
    
    if config.is_admin_chat(chat_id):
        return user_role in [UserRole.ADMIN, UserRole.SPECIAL_ADMIN, UserRole.OWNER]
    
    return False

async def check_subscription(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Проверка подписки пользователя на канал"""
    try:
        # Если проверка подписки отключена - пропускаем
        if not config.is_check_subscription_enabled():
            return True
            
        # Админы и владелец не проверяются
        if config.is_admin(user_id):
            return True
            
        channel_info = config.get_required_channel()
        channel_id = channel_info['id']
        
        try:
            # Пытаемся получить статус подписки
            chat_member = await context.bot.get_chat_member(chat_id=channel_id, user_id=user_id)
            
            # Проверяем статусы, которые означают подписку
            if chat_member.status in ['member', 'administrator', 'creator', 'owner']:
                return True
            else:
                return False
                
        except Exception as e:
            logger.error(f"Ошибка проверки подписки пользователя {user_id}: {e}")
            # Если не удалось проверить, пропускаем (на всякий случай)
            return True
            
    except Exception as e:
        logger.error(f"Ошибка в check_subscription: {e}")
        return True

async def require_subscription(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Проверка подписки перед выполнением команды"""
    user_id = update.effective_user.id
    
    # Проверяем подписку
    is_subscribed = await check_subscription(user_id, context)
    
    if not is_subscribed:
        channel_info = config.get_required_channel()
        channel_username = channel_info['username']
        
        keyboard = [
            [InlineKeyboardButton("📢 Подписаться на канал", url=f"https://t.me/{channel_username.replace('@', '')}")],
            [InlineKeyboardButton("✅ Я подписался", callback_data="check_subscription")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"⚠️ *Для использования бота необходимо подписаться на канал!*\n\n"
            f"📢 Канал: {channel_username}\n"
            f"👥 Там публикуются важные новости и обновления\n\n"
            f"1. Нажмите кнопку 'Подписаться на канал'\n"
            f"2. Подпишитесь на канал\n"
            f"3. Нажмите 'Я подписался'\n\n"
            f"*После подписки вы сможете пользоваться ботом!*",
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
        return False
    
    return True

async def check_subscription_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик кнопки проверки подписки"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    
    if query.data == "check_subscription":
        # Проверяем подписку еще раз
        is_subscribed = await check_subscription(user_id, context)
        
        if is_subscribed:
            await query.message.edit_text(
                "✅ *Отлично! Вы подписаны!*\n\n"
                "Теперь вы можете пользоваться всеми функциями бота.\n"
                "Используйте /start для начала работы.",
                parse_mode='Markdown'
            )
        else:
            await query.answer("❌ Вы еще не подписались на канал!", show_alert=True)

def get_admin_role_text(user_id: int) -> str:
    """Получить текст роли администратора"""
    user_role = config.get_user_role(user_id)
    
    if user_role == UserRole.OWNER:
        return "👑 ВЛАДЕЛЕЦ БОТА"
    elif user_role == UserRole.SPECIAL_ADMIN:
        return "🛡️ СПЕЦ-АДМИНИСТРАТОР"
    elif user_role == UserRole.ADMIN:
        return "👮 АДМИНИСТРАТОР"
    else:
        return "👤 ПОЛЬЗОВАТЕЛЬ"

def get_scam_chance_for_user(user_id: str, is_admin: bool = False, is_scammer: bool = False) -> int:
    """Получить процент скама для пользователя"""
    if is_scammer:
        return 100
    elif is_admin:
        return 0
    else:
        return random.randint(1, 10)

def get_scammer_info(user_identifier: str) -> Tuple[Optional[Dict], bool, bool]:
    """
    Найти информацию о скамере по username или ID
    Возвращает: (инфо_о_скамере, найден_ли_по_username, найден_ли_по_id)
    """
    clean_identifier = user_identifier.replace('@', '')
    
    found_by_id = False
    found_by_username = False
    
    if clean_identifier.isdigit():
        scammer_info = db.check_user(clean_identifier)
        if scammer_info:
            return scammer_info, False, True
    
    scammer_info = db.find_scammer_by_username(clean_identifier)
    if scammer_info:
        return scammer_info, True, False
    
    return None, False, False

async def get_user_info_from_tg(identifier: str) -> Tuple[Optional[str], Optional[str]]:
    """Получить ID и username пользователя из Telegram через User API"""
    try:
        if telegram_api is None:
            logger.error("Telegram API еще не инициализирован")
            return None, identifier
        
        clean_identifier = identifier.replace('@', '').strip()
        
        user_info = await telegram_api.get_user_info(clean_identifier)
        
        if user_info:
            user_id = str(user_info['id'])
            username = user_info['username']
            
            if username.startswith('@'):
                username = username[1:]
            
            if not username or username.startswith('id'):
                if user_info['first_name']:
                    username = user_info['first_name']
                    if user_info['last_name']:
                        username += f" {user_info['last_name']}"
                else:
                    username = f"id{user_id}"
            
            return user_id, username
        
        scammer_info = db.find_scammer_by_username(clean_identifier)
        if scammer_info:
            return scammer_info['user_id'], scammer_info['username']
        
        return None, clean_identifier
        
    except Exception as e:
        logger.error(f"Ошибка получения информации о пользователе {identifier}: {e}")
        return None, clean_identifier

def create_proof_link(chat_id: int, message_id: int) -> str:
    """Создать корректную ссылку на сообщение в Telegram"""
    try:
        chat_username = config.get_admin_chat_username()
        
        if chat_username:
            clean_username = chat_username.replace('@', '')
            return f"https://t.me/{clean_username}/{message_id}"
        
        if str(chat_id).startswith('-100'):
            channel_id = str(chat_id).replace('-100', '')
            return f"https://t.me/c/{channel_id}/{message_id}"
        
        elif str(chat_id).startswith('-'):
            group_id = str(chat_id).replace('-', '')
            return f"https://t.me/c/{group_id}/{message_id}"
        
        return f"https://t.me/c/{abs(chat_id)}/{message_id}"
        
    except Exception as e:
        logger.error(f"Ошибка создания ссылки: {e}")
        return f"https://t.me/c/{abs(chat_id)}/{message_id}"

# ====== КОМАНДЫ ДЛЯ УПРАВЛЕНИЯ АДМИНАМИ ======

async def add_admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Добавить администратора"""
    try:
        user_id = update.effective_user.id
        
        if not has_permission(user_id, UserRole.SPECIAL_ADMIN):
            await update.message.reply_text("❌ У вас нет прав для добавления администраторов!")
            return
        
        if not context.args or len(context.args) < 1:
            await update.message.reply_text(
                "❌ Неверный формат!\n"
                "✅ Правильно: `/addadmin 123456789`\n"
                "📝 Пример: `/addadmin 8064767053`",
                parse_mode='Markdown'
            )
            return
        
        new_admin_id = context.args[0]
        
        if not new_admin_id.isdigit():
            await update.message.reply_text("❌ ID администратора должен быть числом!")
            return
        
        if int(new_admin_id) == user_id:
            await update.message.reply_text("❌ Нельзя добавить самого себя!")
            return
        
        if int(new_admin_id) == config.config['owner_id']:
            await update.message.reply_text("❌ Этот пользователь уже является владельцем!")
            return
        
        success, message = config.add_admin(new_admin_id, UserRole.ADMIN)
        
        if success:
            await update.message.reply_text(
                f"✅ Администратор `{new_admin_id}` успешно добавлен!\n\n"
                f"👮 Роль: Обычный администратор\n"
                f"🛠️ Может: Добавлять скамеров в админ-чате",
                parse_mode='Markdown'
            )
            
            try:
                await context.bot.send_message(
                    chat_id=int(new_admin_id),
                    text=f"🎉 *Вы назначены администратором!*\n\n"
                         f"🤖 Бот: @{BOT_USERNAME}\n"
                         f"👮 Роль: Обычный администратор\n"
                         f"🛠️ Права: Можете добавлять скамеров в админ-чате\n\n"
                         f"💬 Админ-чат: Настройте у владельца",
                    parse_mode='Markdown'
                )
            except Exception as e:
                logger.error(f"Не удалось уведомить нового админа: {e}")
        else:
            await update.message.reply_text(f"❌ {message}")
            
    except Exception as e:
        logger.error(f"Ошибка в команде /addadmin: {e}", exc_info=True)
        await update.message.reply_text("❌ Произошла ошибка. Попробуйте позже.")

async def add_special_admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Добавить спец-администратора"""
    try:
        user_id = update.effective_user.id
        
        if not has_permission(user_id, UserRole.OWNER):
            await update.message.reply_text("❌ Только владелец может добавлять спец-администраторов!")
            return
        
        if not context.args or len(context.args) < 1:
            await update.message.reply_text(
                "❌ Неверный формат!\n"
                "✅ Правильно: `/addspecial 123456789`\n"
                "📝 Пример: `/addspecial 8064767053`",
                parse_mode='Markdown'
            )
            return
        
        new_admin_id = context.args[0]
        
        if not new_admin_id.isdigit():
            await update.message.reply_text("❌ ID администратора должен быть числом!")
            return
        
        if int(new_admin_id) == user_id:
            await update.message.reply_text("❌ Вы уже являетесь владельцем!")
            return
        
        success, message = config.add_admin(new_admin_id, UserRole.SPECIAL_ADMIN)
        
        if success:
            await update.message.reply_text(
                f"✅ Спец-администратор `{new_admin_id}` успешно добавлен!\n\n"
                f"👮 Роль: Спец-администратор\n"
                f"🛠️ Может: Добавлять скамеров и удалять их из базы",
                parse_mode='Markdown'
            )
            
            try:
                await context.bot.send_message(
                    chat_id=int(new_admin_id),
                    text=f"🎉 *Вы назначены спец-администратором!*\n\n"
                         f"🤖 Бот: @{BOT_USERNAME}\n"
                         f"👮 Роль: Спец-администратор\n"
                         f"🛠️ Права: Можете добавлять и удалять скамеров\n\n"
                         f"💬 Админ-чат: Настройте у владельца",
                    parse_mode='Markdown'
                )
            except Exception as e:
                logger.error(f"Не удалось уведомить нового спец-админа: {e}")
        else:
            await update.message.reply_text(f"❌ {message}")
            
    except Exception as e:
        logger.error(f"Ошибка в команде /addspecial: {e}", exc_info=True)
        await update.message.reply_text("❌ Произошла ошибка. Попробуйте позже.")

async def remove_admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Удалить администратора"""
    try:
        user_id = update.effective_user.id
        
        if not has_permission(user_id, UserRole.SPECIAL_ADMIN):
            await update.message.reply_text("❌ У вас нет прав для удаления администраторов!")
            return
        
        if not context.args or len(context.args) < 1:
            await update.message.reply_text(
                "❌ Неверный формат!\n"
                "✅ Правильно: `/removeadmin 123456789`\n"
                "📝 Пример: `/removeadmin 8064767053`",
                parse_mode='Markdown'
            )
            return
        
        admin_id_to_remove = context.args[0]
        
        if not admin_id_to_remove.isdigit():
            await update.message.reply_text("❌ ID администратора должен быть числом!")
            return
        
        if int(admin_id_to_remove) == user_id:
            if config.get_user_role(user_id) == UserRole.OWNER:
                await update.message.reply_text("❌ Нельзя удалить владельца!")
                return
        
        success, message = config.remove_admin(admin_id_to_remove)
        
        if success:
            await update.message.reply_text(
                f"✅ Администратор `{admin_id_to_remove}` успешно удален!",
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text(f"❌ {message}")
            
    except Exception as e:
        logger.error(f"Ошибка в команде /removeadmin: {e}", exc_info=True)
        await update.message.reply_text("❌ Произошла ошибка. Попробуйте позже.")

async def list_admins_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать список администраторов"""
    try:
        user_id = update.effective_user.id
        
        if not has_permission(user_id, UserRole.ADMIN):
            await update.message.reply_text("❌ У вас нет прав для просмотра списка администраторов!")
            return
        
        admins = config.list_admins()
        
        admins_text = f"""
📋 *СПИСОК АДМИНИСТРАТОРОВ*

👑 *Владелец:* `{admins['owner']}`

🛡️ *Спец-администраторы ({len(admins['special_admins'])}):*
"""
        
        if admins['special_admins']:
            for admin_id in admins['special_admins']:
                admins_text += f"• `{admin_id}`\n"
        else:
            admins_text += "Нет спец-администраторов\n"
        
        admins_text += f"\n👮 *Обычные администраторы ({len(admins['admins'])}):*\n"
        
        if admins['admins']:
            for admin_id in admins['admins']:
                admins_text += f"• `{admin_id}`\n"
        else:
            admins_text += "Нет обычных администраторов\n"
        
        admins_text += f"\n📊 *Всего администраторов:* {len(admins['special_admins']) + len(admins['admins']) + 1}"
        
        await update.message.reply_text(admins_text, parse_mode='Markdown')
        
    except Exception as e:
        logger.error(f"Ошибка в команде /listadmins: {e}", exc_info=True)
        await update.message.reply_text("❌ Произошла ошибка. Попробуйте позже.")

# ====== КОМАНДА ДОБАВЛЕНИЯ СКАМЕРА ======

async def add_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /add - только в админ-чате"""
    try:
        chat_id = update.effective_chat.id
        user_id = update.effective_user.id
        
        if not can_add_scammer(user_id, chat_id):
            if config.is_admin_chat(chat_id):
                await update.message.reply_text("❌ У вас нет прав для добавления скамеров в этом чате!")
            else:
                await update.message.reply_text(
                    f"❌ Добавлять скамеров можно только в админ-чате!\n\n"
                    f"ℹ️ Для проверки пользователей используйте команду /check\n"
                    f"📝 Для добавления обратитесь к администраторам."
                )
            return
        
        if not context.args or len(context.args) < 2:
            await update.message.reply_text(
                "❌ Неверный формат!\n"
                "✅ Правильно: `/add @username Причина обмана`\n"
                "✅ Или: `/add username Причина обмана` (без @)\n"
                "✅ Или: `/add 123456789 Причина обмана`\n\n"
                "📝 *Пример:* `/add @scammer123 Обман при продаже аккаунта`",
                parse_mode='Markdown'
            )
            return
        
        user_identifier = context.args[0].replace('@', '')
        reason = ' '.join(context.args[1:])
        
        searching_msg = await update.message.reply_text(
            f"🔍 *Поиск пользователя...*\n\n"
            f"Идентификатор: `{user_identifier}`\n"
            f"Причина: {reason}\n\n"
            f"⏳ Запрашиваю информацию из Telegram...",
            parse_mode='Markdown'
        )
        
        user_id_to_add, username = await get_user_info_from_tg(user_identifier)
        
        await searching_msg.delete()
        
        if not user_id_to_add:
            scammer_info = db.find_scammer_by_username(user_identifier)
            if scammer_info:
                user_id_to_add = scammer_info['user_id']
                username = scammer_info['username']
            else:
                user_id_to_add = user_identifier
                username = user_identifier
        
        if not username:
            username = f"id{user_id_to_add}"
        
        if username.lower() == BOT_USERNAME.lower().replace('@', ''):
            await update.message.reply_text("❌ Нельзя добавить самого бота в базу!")
            return
        
        if str(user_id_to_add) == str(config.config['owner_id']):
            await update.message.reply_text("❌ Нельзя добавить владельца бота в базу!")
            return
        
        if user_id_to_add.isdigit() and config.is_admin(int(user_id_to_add)):
            await update.message.reply_text("❌ Нельзя добавить администратора в базу скамеров!")
            return
        
        proof_link = create_proof_link(chat_id, update.message.message_id)
        
        success, message, is_new = db.add_scammer(
            user_id=user_id_to_add,
            username=username,
            reason=reason,
            added_by=user_id,
            chat_id=chat_id,
            proof_link=proof_link
        )
        
        if success:
            scammer_info = db.check_user(user_id_to_add)
            if not scammer_info:
                scammer_info = db.find_scammer_by_username(username)
            
            display_username = username
            if not display_username.startswith('@'):
                display_username = f"@{display_username}"
            
            warning_image = config.get_image_file("warning")
            try:
                if warning_image and os.path.exists(warning_image):
                    with open(warning_image, 'rb') as photo:
                        await update.message.reply_photo(
                            photo=photo,
                            caption=f"""
⚠️ *СКАМЕР ДОБАВЛЕН!*

👤 *Пользователь:* {display_username}
🆔 *ID:* `{user_id_to_add}`
📝 *Причина:* {reason}
📊 *Жалоб:* {scammer_info['reports'] if scammer_info else 1}
👮 *Добавил:* {get_admin_role_text(user_id)}
📅 *Дата:* {datetime.now().strftime('%d.%m.%Y %H:%M')}
🔗 *Доказательство:* {proof_link}

✅ *{'Новая запись добавлена' if is_new else 'Запись обновлена'} в базе данных!*
                            """,
                            parse_mode='Markdown'
                        )
                else:
                    await update.message.reply_text(
                        f"⚠️ *СКАМЕР ДОБАВЛЕН!*\n\n"
                        f"👤 *Пользователь:* {display_username}\n"
                        f"🆔 *ID:* `{user_id_to_add}`\n"
                        f"📝 *Причина:* {reason}\n"
                        f"📊 *Жалоб:* {scammer_info['reports'] if scammer_info else 1}\n"
                        f"👮 *Добавил:* {get_admin_role_text(user_id)}\n"
                        f"📅 *Дата:* {datetime.now().strftime('%d.%m.%Y %H:%M')}\n"
                        f"🔗 *Доказательство:* {proof_link}\n\n"
                        f"✅ *{'Новая запись добавлена' if is_new else 'Запись обновлена'} в базе данных!*",
                        parse_mode='Markdown'
                    )
            except Exception as e:
                logger.error(f"Ошибка отправки фото: {e}")
                await update.message.reply_text(
                    f"✅ Скамер {display_username} {'добавлен' if is_new else 'обновлен'} в базе!\n"
                    f"Причина: {reason}\n"
                    f"Жалоб: {scammer_info['reports'] if scammer_info else 1}\n"
                    f"ID: {user_id_to_add}",
                    parse_mode='Markdown'
                )
            
            keyboard = [[InlineKeyboardButton("🌍 Установить Страну", callback_data=f"set_country_{user_id_to_add}")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text("Хотите указать страну скамера?", reply_markup=reply_markup)
            
            if config.config['owner_id']:
                try:
                    await context.bot.send_message(
                        chat_id=config.config['owner_id'],
                        text=f"🔔 *Новый скамер {'добавлен' if is_new else 'обновлен'}!*\n\n"
                             f"👤 {display_username}\n"
                             f"🆔 `{user_id_to_add}`\n"
                             f"📝 {reason}\n"
                             f"📊 Жалоб: {scammer_info['reports'] if scammer_info else 1}\n"
                             f"👮 Добавил: {get_admin_role_text(user_id)}\n"
                             f"💬 Чат: Админ-чат\n"
                             f"🔗 Доказательство: {proof_link}",
                        parse_mode='Markdown'
                    )
                except Exception as e:
                    logger.error(f"Ошибка уведомления владельца: {e}")
        else:
            await update.message.reply_text(f"⚠️ {message}")
            
    except Exception as e:
        logger.error(f"Ошибка в команде /add: {e}", exc_info=True)
        await update.message.reply_text("❌ Произошла ошибка при добавлении. Попробуйте позже.")

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start с кнопочным меню"""
    # Проверяем подписку
    is_subscribed = await require_subscription(update, context)
    if not is_subscribed:
        return
    
    user_id = update.effective_user.id
    user_role = config.get_user_role(user_id)
    
    # Создаем кнопки в зависимости от роли пользователя
    keyboard = []
    
    # Основные команды (видны всем)
    keyboard.append([
        InlineKeyboardButton("🔍 Проверить пользователя", callback_data="menu_check"),
        InlineKeyboardButton("👤 Проверить себя", callback_data="menu_checkme")
    ])
    
    keyboard.append([
        InlineKeyboardButton("📊 Статистика", callback_data="menu_stats"),
        InlineKeyboardButton("📚 Помощь", callback_data="menu_help")
    ])
    
    # Кнопка для админов и выше
    if user_role in [UserRole.ADMIN, UserRole.SPECIAL_ADMIN, UserRole.OWNER]:
        keyboard.append([
            InlineKeyboardButton("👮 Администраторы", callback_data="menu_admins")
        ])
    
    # Кнопка для спец-админов и выше
    if user_role in [UserRole.SPECIAL_ADMIN, UserRole.OWNER]:
        keyboard.append([
            InlineKeyboardButton("🛡️ Спец-администраторы", callback_data="menu_special_admins")
        ])
    
    # Кнопка для владельца
    if user_role == UserRole.OWNER:
        keyboard.append([
            InlineKeyboardButton("👑 Владелец", callback_data="menu_owner")
        ])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    welcome_text = f"""
🚫 *AntiScam Database*

🤖 *Добро пожаловать в базу данных скамеров!*

👤 *Ваша роль:* {get_admin_role_text(user_id)}

⁉  *Занести обидчика в базу:* @wzkbScamBaseChat

📋 *Доступные команды:*
Используйте кнопки ниже для навигации

⚠️ *Всегда используйте гарантов для безопасных сделок!*
    """
    
    await update.message.reply_text(welcome_text, parse_mode='Markdown', reply_markup=reply_markup)

# ====== МЕНЮ КОМАНД ======

async def show_basic_commands_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать меню основных команд"""
    query = update.callback_query
    await query.answer()
    
    commands_text = """
📚 *Основные команды:*

🔍 */check [@username или ID]* - Проверить пользователя
*Примеры:*
• `/check @username` - с @
• `/check username` - без @
• `/check 123456789` - по ID
• `/check https://t.me/username` - по ссылке

👤 */checkme* - Проверить себя
📊 */stats* - Статистика базы данных
📚 */help* - Полная помощь по командам

⚠️ *Всегда используйте гарантов для безопасных сделок!*
    """
    
    await query.message.reply_text(commands_text, parse_mode='Markdown')

async def show_admin_commands_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать меню команд для админов"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    user_role = config.get_user_role(user_id)
    
    if user_role not in [UserRole.ADMIN, UserRole.SPECIAL_ADMIN, UserRole.OWNER]:
        await query.message.reply_text("❌ У вас нет прав для просмотра этого меню!")
        return
    
    commands_text = f"""
👮 *Команды для администраторов:*

*В админ-чате:*
📝 */add @username Причина* - Добавить/обновить скамера
*Пример:* `/add @scammer123 Обман при продаже аккаунта`

*Для управления админами:*
👥 */listadmins* - Список всех администраторов

*Ваша роль:* {get_admin_role_text(user_id)}

⚠️ *Команды /add работают только в админ-чате!*
    """
    
    await query.message.reply_text(commands_text, parse_mode='Markdown')

async def show_special_admin_commands_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать меню команд для спец-админов"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    user_role = config.get_user_role(user_id)
    
    if user_role not in [UserRole.SPECIAL_ADMIN, UserRole.OWNER]:
        await query.message.reply_text("❌ У вас нет прав для просмотра этого меню!")
        return
    
    commands_text = f"""
🛡️ *Команды для спец-администраторов:*

*Все команды администраторов плюс:*

*Управление админами:*
➕ */addadmin ID* - Добавить обычного админа
*Пример:* `/addadmin 123456789`

➖ */removeadmin ID* - Удалить админа
*Пример:* `/removeadmin 123456789`

*Управление скамерами:*
🗑️ Можно удалять скамеров через кнопку в профиле

*Ваша роль:* {get_admin_role_text(user_id)}
    """
    
    await query.message.reply_text(commands_text, parse_mode='Markdown')

async def show_owner_commands_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать меню команд для владельца"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    user_role = config.get_user_role(user_id)
    
    if user_role != UserRole.OWNER:
        await query.message.reply_text("❌ Только владелец может просматривать это меню!")
        return
    
    commands_text = f"""
👑 *Команды для владельца:*

*Все команды админов и спец-админов плюс:*

*Управление спец-админами:*
➕ */addspecial ID* - Добавить спец-админа
*Пример:* `/addspecial 123456789`

*Управление настройками:*
💬 */setadminchat* - Установить админ-чат
📢 */setchannel @username* - Установить канал для подписки
🆔 */setchannelid -1001234567890* - Установить ID канала
🔧 */togglesubscription* - Вкл/выкл проверку подписки

*Загрузка картинок (в ЛС бота):*
Отправьте фото с подписью:
• #scammer - красная картинка для скамеров
• #clean - зеленая картинка для чистых  
• #warning - желтая картинка для предупреждений
• #admin - синяя картинка для админов

*Дополнительные команды:*
🆔 */getchannelid* - Получить ID текущего чата

*Ваша роль:* {get_admin_role_text(user_id)}
    """
    
    await query.message.reply_text(commands_text, parse_mode='Markdown')

async def check_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /check - работает везде"""
    # Проверяем подписку
    is_subscribed = await require_subscription(update, context)
    if not is_subscribed:
        return
    
    try:
        if not context.args:
            await update.message.reply_text(
                "❌ Укажите username или ID пользователя\n"
                "Примеры:\n"
                "• `/check @username` - с @\n"
                "• `/check username` - без @\n"
                "• `/check 123456789` - по ID\n"
                "• `/check https://t.me/username` - по ссылке",
                parse_mode='Markdown'
            )
            return
        
        user_identifier = ' '.join(context.args)
        
        if user_identifier.startswith('https://t.me/'):
            user_identifier = user_identifier.replace('https://t.me/', '')
        
        searching_msg = await update.message.reply_text(
            f"🔍 *Поиск пользователя...*\n\n"
            f"Идентификатор: `{user_identifier}`\n"
            f"⏳ Запрашиваю информацию из Telegram...",
            parse_mode='Markdown'
        )
        
        real_user_id, real_username = await get_user_info_from_tg(user_identifier)
        
        display_username = real_username or user_identifier.replace('@', '')
        display_user_id = real_user_id or user_identifier
        
        if real_user_id:
            search_identifier = real_user_id
            if not real_username:
                real_username = f"id{real_user_id}"
        else:
            search_identifier = user_identifier.replace('@', '')
        
        scammer_info = None
        
        if real_user_id:
            scammer_info = db.check_user(real_user_id)
        
        if not scammer_info:
            scammer_info = db.find_scammer_by_username(search_identifier)
        
        is_admin_user = False
        if real_user_id and real_user_id.isdigit():
            is_admin_user = config.is_admin(int(real_user_id))
        elif scammer_info:
            try:
                is_admin_user = config.is_admin(int(scammer_info['user_id']))
            except:
                pass
        
        if scammer_info:
            image_file = config.get_image_file("scammer_found")
            status_emoji = "🔴"
            status_text = "ЧЕЛОВЕК ЕСТЬ В БАЗЕ!"
            scam_chance = 100
            country = scammer_info.get('country') or 'None'
            reports = scammer_info.get('reports', 1)
            username_display = scammer_info['username']
            user_id_display = scammer_info['user_id']
        elif is_admin_user:
            image_file = config.get_image_file("admin")
            status_emoji = "🔵"
            status_text = "АДМИНИСТРАТОР БОТА"
            scam_chance = 0
            country = 'None'
            reports = 0
            username_display = display_username
            user_id_display = display_user_id if display_user_id.isdigit() else 'Админ'
        else:
            image_file = config.get_image_file("user_clean")
            status_emoji = "🟢"
            status_text = "ЧЕЛОВЕКА НЕТ В БАЗЕ!"
            scam_chance = random.randint(1, 10)
            country = 'None'
            reports = 1
            username_display = display_username
            user_id_display = display_user_id
        
        await searching_msg.delete()
        
        if username_display and not username_display.startswith('@'):
            username_display_formatted = f"@{username_display}"
        else:
            username_display_formatted = username_display
        
        response = f"""
{status_emoji} /check {username_display_formatted}  
👤 {username_display_formatted} [{user_id_display}]  

*{status_text}*  

🎯 Шанс скама: *{scam_chance}%*  
🌍 Страна: {country}  

👁️ Скаммеров в базе: *{db.get_stats()['total_scammers']}*  
⚠️ *Всегда идите через гарантов, чтобы сделки проходили безопасно!*  

{datetime.now().strftime('%d %B %Y')} | 🔒 {reports} | @{BOT_USERNAME}
        """
        
        if not scammer_info and not is_admin_user:
            response += "\n*НЕТ В БАЗЕ*"
        
        keyboard = [
            [
                InlineKeyboardButton("📋 Профиль", callback_data=f"profile_{user_id_display if scammer_info else 'none'}"),
                InlineKeyboardButton("⚠️ Как Слить", callback_data="how_to_report")
            ],
            [
                InlineKeyboardButton("🌍 Установить Страну", 
                                   callback_data=f"set_country_{scammer_info['user_id'] if scammer_info else 'none'}"),
                InlineKeyboardButton("🛡️ Кто Гарант", callback_data="what_is_guarantor")
            ]
        ]
        
        if scammer_info and has_permission(update.effective_user.id, UserRole.SPECIAL_ADMIN):
            keyboard.append([
                InlineKeyboardButton("🗑️ Удалить из базы", callback_data=f"remove_{scammer_info['user_id']}")
            ])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        try:
            if image_file and os.path.exists(image_file):
                with open(image_file, 'rb') as photo:
                    await update.message.reply_photo(
                        photo=photo,
                        caption=response,
                        parse_mode='Markdown',
                        reply_markup=reply_markup
                    )
            else:
                await update.message.reply_text(response, parse_mode='Markdown', reply_markup=reply_markup)
        except Exception as e:
            logger.error(f"Ошибка отправки фото: {e}")
            await update.message.reply_text(response, parse_mode='Markdown', reply_markup=reply_markup)
    except Exception as e:
        logger.error(f"Ошибка в команде /check: {e}", exc_info=True)
        await update.message.reply_text("❌ Произошла ошибка при проверке. Попробуйте позже.")

# Функции для работы с кнопками
async def show_profile(query, scammer_id: str):
    """Показать подробный профиль скамера"""
    try:
        scammer_info = db.check_user(scammer_id)
        if not scammer_info:
            scammer_info = db.find_scammer_by_username(scammer_id)
        
        if not scammer_info:
            await query.message.reply_text("❌ Профиль не найден.")
            return
        
        username_display = scammer_info['username']
        if not username_display.startswith('@'):
            username_display = f"@{username_display}"
        
        profile_text = f"""
📋 *ПРОФИЛЬ СКАМЕРА*

👤 *Username:* {username_display}
🆔 *ID:* `{scammer_info['user_id']}`
📊 *Жалоб:* {scammer_info.get('reports', 1)}
🌍 *Страна:* {scammer_info.get('country', 'Не указана')}
📅 *Добавлен:* {scammer_info.get('added_date', 'Неизвестно')}
👮 *Добавил:* Администратор
        
📝 *Причины жалоб:*
"""
        
        reasons = scammer_info.get('reasons', ['Причина не указана'])
        for i, reason in enumerate(reasons, 1):
            profile_text += f"{i}. {reason}\n"
        
        profile_text += "\n🔗 *Доказательства:*\n"
        
        proofs = scammer_info.get('proofs', [])
        if proofs:
            for i, proof in enumerate(proofs, 1):
                profile_text += f"{i}. {proof}\n"
        else:
            profile_text += "Нет доказательств в базе\n"
        
        await query.message.reply_text(profile_text, parse_mode='Markdown')
        
    except Exception as e:
        logger.error(f"Ошибка показа профиля: {e}")
        await query.message.reply_text("❌ Ошибка при загрузке профиля.")

async def set_country_dialog(query, scammer_id: str):
    """Диалог установки страны"""
    keyboard = [
        [
            InlineKeyboardButton("🇷🇺 Россия", callback_data=f"country_{scammer_id}_RU"),
            InlineKeyboardButton("🇺🇦 Украина", callback_data=f"country_{scammer_id}_UA")
        ],
        [
            InlineKeyboardButton("🇧🇾 Беларусь", callback_data=f"country_{scammer_id}_BY"),
            InlineKeyboardButton("🇰🇿 Казахстан", callback_data=f"country_{scammer_id}_KZ")
        ],
        [
            InlineKeyboardButton("🇺🇸 США", callback_data=f"country_{scammer_id}_US"),
            InlineKeyboardButton("🇪🇺 ЕС", callback_data=f"country_{scammer_id}_EU")
        ],
        [
            InlineKeyboardButton("🇹🇷 Турция", callback_data=f"country_{scammer_id}_TR"),
            InlineKeyboardButton("🇦🇿 Азербайджан", callback_data=f"country_{scammer_id}_AZ")
        ],
        [
            InlineKeyboardButton("❌ Отмена", callback_data="cancel_country")
        ]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.reply_text(
        "🌍 *Выберите страну для скамера:*",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def remove_scammer_dialog(query, user_id: int, scammer_id: str):
    """Диалог удаления скамера из базы"""
    if not has_permission(user_id, UserRole.SPECIAL_ADMIN):
        await query.message.reply_text("❌ У вас нет прав для удаления скамеров!")
        return
    
    scammer_info = db.check_user(scammer_id)
    if not scammer_info:
        await query.message.reply_text("❌ Скамер не найден в базе.")
        return
    
    keyboard = [
        [
            InlineKeyboardButton("✅ Да, удалить", callback_data=f"confirm_remove_{scammer_id}"),
            InlineKeyboardButton("❌ Отмена", callback_data="cancel_remove")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    username_display = scammer_info['username']
    if not username_display.startswith('@'):
        username_display = f"@{username_display}"
    
    await query.message.reply_text(
        f"⚠️ *Подтвердите удаление:*\n\n"
        f"👤 {username_display}\n"
        f"🆔 `{scammer_info['user_id']}`\n"
        f"📝 Причин: {len(scammer_info.get('reasons', []))}\n"
        f"📊 Жалоб: {scammer_info.get('reports', 1)}\n\n"
        f"Вы уверены, что хотите удалить этого скамера из базы?",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def save_photo_to_file(context: ContextTypes.DEFAULT_TYPE, photo: PhotoSize, image_type: str) -> Optional[str]:
    """Сохранить фото из сообщения в файл"""
    try:
        file = await context.bot.get_file(photo.file_id)
        
        filename = f"{image_type}.jpg"
        save_path = os.path.join(IMAGES_FOLDER, filename)
        
        await file.download_to_drive(save_path)
        
        config.update_image_file(image_type, save_path)
        
        logger.info(f"Картинка сохранена: {save_path}")
        return save_path
        
    except Exception as e:
        logger.error(f"Ошибка сохранения фото {image_type}: {e}")
        logger.error(traceback.format_exc())
        return None

async def handle_photo_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик для загрузки картинок с тегами"""
    try:
        user_id = update.effective_user.id
        
        if not has_permission(user_id, UserRole.OWNER):
            return
        
        if not update.message.caption:
            await update.message.reply_text("❌ Укажите тег в подписи к фото!")
            return
        
        caption = update.message.caption.strip().lower()
        
        if '#scammer' in caption:
            image_type = "scammer_found"
            image_name = "красная (для скамеров)"
        elif '#clean' in caption:
            image_type = "user_clean"
            image_name = "зеленая (для чистых)"
        elif '#warning' in caption:
            image_type = "warning"
            image_name = "желтая (для предупреждений)"
        elif '#admin' in caption:
            image_type = "admin"
            image_name = "синяя (для админов)"
        else:
            await update.message.reply_text("❌ Неизвестный тег! Используйте: #scammer, #clean, #warning, #admin")
            return
        
        photo = update.message.photo[-1] if update.message.photo else None
        
        if not photo:
            await update.message.reply_text("❌ Не найдено фото в сообщении!")
            return
        
        saved_path = await save_photo_to_file(context, photo, image_type)
        
        if saved_path:
            await update.message.reply_text(f"✅ {image_name} картинка успешно сохранена!")
        else:
            await update.message.reply_text("❌ Ошибка при сохранении картинки!")
            
    except Exception as e:
        logger.error(f"Ошибка обработки фото: {e}", exc_info=True)
        await update.message.reply_text("❌ Ошибка при обработке фото!")

async def button_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик нажатий на кнопки"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    user_id = query.from_user.id
    
    logger.info(f"Нажата кнопка: {data} пользователем {user_id}")
    
    if data.startswith("profile_"):
        scammer_id = data.replace("profile_", "")
        if scammer_id != "none":
            await show_profile(query, scammer_id)
        else:
            await query.message.reply_text("❌ Профиль не найден в базе.")
    
    elif data == "how_to_report":
        await query.message.reply_text(
            "📢 *Как сообщить о скамере:*\n\n"
            "1. Соберите доказательства (скрины переписки, платежей)\n"
            "2. Обратитесь в админ-чат бота @wzkbScamBaseChat\n"
            "3. Предоставьте доказательства администратору\n"
            "4. Администратор добавит скамера в базу\n\n"
            "⚠️ *Только администраторы могут добавлять скамеров!*",
            parse_mode='Markdown'
        )
    
    elif data.startswith("set_country_"):
        scammer_id = data.replace("set_country_", "")
        if scammer_id != "none":
            await set_country_dialog(query, scammer_id)
        else:
            await query.message.reply_text("❌ Сначала нужно добавить пользователя в базу.")
    
    elif data == "what_is_guarantor":
        await query.message.reply_text(
            "🛡️ *Кто такой гарант и зачем он нужен:*\n\n"
            "Гарант — это нейтральная сторона, которая обеспечивает безопасность сделки.\n\n"
            "✅ *Преимущества использования гаранта:*\n"
            "• Продавец получает деньги только после передачи товара\n"
            "• Покупатель платит только после получения товара\n"
            "• Гарант проверяет легитимность сделки\n"
            "• Защита от мошенничества с обеих сторон\n\n"
            "📌 *Рекомендуем всегда использовать гарантов для крупных сделок!*",
            parse_mode='Markdown'
        )
    
    elif data.startswith("remove_"):
        scammer_id = data.replace("remove_", "")
        await remove_scammer_dialog(query, user_id, scammer_id)
    
    elif data.startswith("country_"):
        parts = data.split('_')
        if len(parts) >= 3:
            scammer_id = parts[1]
            country_code = parts[2]
            
            country_names = {
                'RU': '🇷🇺 Россия',
                'UA': '🇺🇦 Украина',
                'BY': '🇧🇾 Беларусь',
                'KZ': '🇰🇿 Казахстан',
                'US': '🇺🇸 США',
                'EU': '🇪🇺 Европа',
                'TR': '🇹🇷 Турция',
                'AZ': '🇦🇿 Азербайджан'
            }
            
            country_name = country_names.get(country_code, f"Страна {country_code}")
            db.set_country(scammer_id, country_name)
            
            await query.message.reply_text(f"✅ Страна установлена: {country_name}")
    
    elif data.startswith("confirm_remove_"):
        scammer_id = data.replace("confirm_remove_", "")
        
        if not has_permission(user_id, UserRole.SPECIAL_ADMIN):
            await query.message.reply_text("❌ У вас нет прав для удаления скамеров!")
            return
        
        if db.remove_scammer(scammer_id):
            await query.message.reply_text("✅ Скамер успешно удален из базы!")
        else:
            await query.message.reply_text("❌ Ошибка при удалении скамера.")
    
    elif data == "cancel_remove" or data == "cancel_country":
        await query.message.reply_text("❌ Действие отменено.")
    
    elif data == "check_subscription":
        await check_subscription_button(update, context)
    
    # Обработка меню
    elif data == "menu_check":
        await query.message.reply_text(
            "🔍 *Проверка пользователя:*\n\n"
            "Используйте команду `/check` с одним из параметров:\n\n"
            "• `/check @username` - по username с @\n"
            "• `/check username` - по username без @\n"
            "• `/check 123456789` - по ID\n"
            "• `/check https://t.me/username` - по ссылке\n\n"
            "*Пример:* `/check @example_user`",
            parse_mode='Markdown'
        )
    
    elif data == "menu_checkme":
        await query.message.reply_text(
            "👤 *Проверка себя:*\n\n"
            "Используйте команду `/checkme` чтобы проверить себя в базе данных.\n\n"
            "*Просто отправьте:* `/checkme`",
            parse_mode='Markdown'
        )
    
    elif data == "menu_stats":
        await query.message.reply_text(
            "📊 *Статистика базы:*\n\n"
            "Используйте команду `/stats` чтобы увидеть статистику базы данных.\n\n"
            "*Просто отправьте:* `/stats`",
            parse_mode='Markdown'
        )
    
    elif data == "menu_help":
        await help_command_menu(query)
    
    elif data == "menu_admins":
        await show_admin_commands_menu(update, context)
    
    elif data == "menu_special_admins":
        await show_special_admin_commands_menu(update, context)
    
    elif data == "menu_owner":
        await show_owner_commands_menu(update, context)
    
    else:
        await query.message.reply_text("❌ Неизвестная команда кнопки.")

async def help_command_menu(query):
    """Показать меню помощи"""
    help_text = """
📚 *Помощь по боту:*

В случае возникновения технических неполадок обращайтесь в поддержку бота: @otecwzkb
    """
    await query.message.reply_text(help_text, parse_mode='Markdown')

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /help"""
    # Проверяем подписку
    is_subscribed = await require_subscription(update, context)
    if not is_subscribed:
        return
    
    user_id = update.effective_user.id
    user_role = config.get_user_role(user_id)
    
    help_text = """
📚 *Помощь по командам:*

/check @username или ID - Проверить пользователя
/checkme - Проверить себя
Занести скамера в базу - @wzkbScamBaseChat
В случае возникновения технических неполадок обращайтесь в поддержку бота: @otecwzkb

⚠️ *Всегда используйте гарантов для безопасных сделок!*
    """
    
    await update.message.reply_text(help_text, parse_mode='Markdown')

async def checkme_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /checkme"""
    # Проверяем подписку
    is_subscribed = await require_subscription(update, context)
    if not is_subscribed:
        return
    
    try:
        user = update.effective_user
        user_id = str(user.id)
        username = user.username or user.first_name or f"id{user.id}"
        
        is_admin_user = config.is_admin(user.id)
        
        scammer_info = db.check_user(user_id)
        
        if scammer_info:
            image_file = config.get_image_file("scammer_found")
            status_emoji = "🔴"
            status_text = "ВЫ ЕСТЬ В БАЗЕ!"
            scam_chance = 100
            country = scammer_info.get('country') or 'None'
            reports = scammer_info.get('reports', 1)
        elif is_admin_user:
            image_file = config.get_image_file("admin")
            status_emoji = "🔵"
            status_text = "АДМИНИСТРАТОР БОТА"
            scam_chance = 0
            country = 'None'
            reports = 0
        else:
            image_file = config.get_image_file("user_clean")
            status_emoji = "🟢"
            status_text = "ВАС НЕТ В БАЗЕ!"
            scam_chance = random.randint(1, 10)
            country = 'None'
            reports = 1
        
        if not username.startswith('@'):
            username_display = f"@{username}"
        else:
            username_display = username
        
        response = f"""
{status_emoji} /checkme  
👤 {username_display} [{user_id}]  

*{status_text}*  

🎯 Шанс скама: *{scam_chance}%*  
🌍 Страна: {country}  

👁️ Скаммеров в базе: *{db.get_stats()['total_scammers']}*  
⚠️ *Всегда идите через гарантов, чтобы сделки проходили безопасно!*  

{datetime.now().strftime('%d %B %Y')} | 🔒 {reports} | @{BOT_USERNAME}
        """
        
        keyboard = [
            [
                InlineKeyboardButton("📋 Профиль", callback_data=f"profile_{user_id if scammer_info else 'none'}"),
                InlineKeyboardButton("⚠️ Как Слить", callback_data="how_to_report")
            ],
            [
                InlineKeyboardButton("🌍 Установить Страну", 
                                   callback_data=f"set_country_{scammer_info['user_id'] if scammer_info else 'none'}"),
                InlineKeyboardButton("🛡️ Кто Гарант", callback_data="what_is_guarantor")
            ]
        ]
        
        if scammer_info and has_permission(update.effective_user.id, UserRole.SPECIAL_ADMIN):
            keyboard.append([
                InlineKeyboardButton("🗑️ Удалить из базы", callback_data=f"remove_{scammer_info['user_id']}")
            ])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        try:
            if image_file and os.path.exists(image_file):
                with open(image_file, 'rb') as photo:
                    await update.message.reply_photo(
                        photo=photo,
                        caption=response,
                        parse_mode='Markdown',
                        reply_markup=reply_markup
                    )
            else:
                await update.message.reply_text(response, parse_mode='Markdown', reply_markup=reply_markup)
        except Exception as e:
            logger.error(f"Ошибка отправки фото: {e}")
            await update.message.reply_text(response, parse_mode='Markdown', reply_markup=reply_markup)
            
    except Exception as e:
        logger.error(f"Ошибка в команде /checkme: {e}", exc_info=True)
        await update.message.reply_text("❌ Произошла ошибка при проверке. Попробуйте позже.")

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /stats"""
    # Проверяем подписку
    is_subscribed = await require_subscription(update, context)
    if not is_subscribed:
        return
    
    stats = db.get_stats()
    
    stats_text = f"""
📊 *СТАТИСТИКА БАЗЫ ДАННЫХ*

🔴 *Активных скамеров:* {stats['total_scammers']}
📈 *Всего жалоб:* {stats['total_reports']}
🗑️ *Удаленных записей:* {stats['removed_scammers']}
💾 *Всего в базе:* {stats['total_in_db']}

📅 *Обновлено:* {datetime.now().strftime('%d.%m.%Y %H:%M')}
👨‍💻 *Владелец:* @otecwzkb
🤖 *Бот:* @{BOT_USERNAME}

⚠️ *Всегда проверяйте пользователей перед сделками!*
    """
    
    await update.message.reply_text(stats_text, parse_mode='Markdown')

async def set_admin_chat_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда для установки админ-чата (только владелец)"""
    try:
        user_id = update.effective_user.id
        
        if not has_permission(user_id, UserRole.OWNER):
            await update.message.reply_text("❌ Только владелец может устанавливать админ-чат!")
            return
        
        chat_id = update.effective_chat.id
        chat_title = update.effective_chat.title or "Админ-чат"
        chat_username = update.effective_chat.username
        
        config.update_admin_chat(chat_id, chat_username)
        
        await update.message.reply_text(
            f"✅ *Админ-чат установлен!*\n\n"
            f"📝 *Название:* {chat_title}\n"
            f"🆔 *ID:* `{chat_id}`\n"
            f"👤 *Username:* {f'@{chat_username}' if chat_username else 'Отсутствует'}\n\n"
            f"Теперь администраторы могут добавлять скамеров в этом чате.",
            parse_mode='Markdown'
        )
        
    except Exception as e:
        logger.error(f"Ошибка в команде set_admin_chat: {e}", exc_info=True)
        await update.message.reply_text("❌ Произошла ошибка. Попробуйте позже.")

async def toggle_subscription_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Включить/выключить проверку подписки (только владелец)"""
    try:
        user_id = update.effective_user.id
        
        if not has_permission(user_id, UserRole.OWNER):
            await update.message.reply_text("❌ Только владелец может управлять проверкой подписки!")
            return
        
        current_state = config.is_check_subscription_enabled()
        new_state = not current_state
        
        config.set_check_subscription(new_state)
        
        channel_info = config.get_required_channel()
        
        if new_state:
            await update.message.reply_text(
                f"✅ *Проверка подписки ВКЛЮЧЕНА!*\n\n"
                f"📢 Канал: {channel_info['username']}\n"
                f"🆔 ID: `{channel_info['id']}`\n\n"
                f"Теперь пользователи должны подписаться на канал, чтобы использовать бота.",
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text(
                "✅ *Проверка подписки ВЫКЛЮЧЕНА!*\n\n"
                "Теперь пользователи могут использовать бота без подписки на канал.",
                parse_mode='Markdown'
            )
        
    except Exception as e:
        logger.error(f"Ошибка в команде toggle_subscription: {e}", exc_info=True)
        await update.message.reply_text("❌ Произошла ошибка. Попробуйте позже.")

async def set_channel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Установить канал для обязательной подписки (только владелец)"""
    try:
        user_id = update.effective_user.id
        
        if not has_permission(user_id, UserRole.OWNER):
            await update.message.reply_text("❌ Только владелец может устанавливать канал для подписки!")
            return
        
        if not context.args or len(context.args) < 1:
            await update.message.reply_text(
                "❌ Неверный формат!\n"
                "✅ Правильно: `/setchannel @username`\n"
                "✅ Или: `/setchannel -1001234567890` (ID канала)\n\n"
                "📝 Пример: `/setchannel @wzkbnews`",
                parse_mode='Markdown'
            )
            return
        
        channel_identifier = context.args[0]
        
        # Если это username
        if channel_identifier.startswith('@'):
            channel_username = channel_identifier
            channel_id = None
            
            await update.message.reply_text(
                f"✅ *Username канала установлен:* {channel_username}\n\n"
                f"⚠️ *Внимание:* Для работы проверки подписки необходимо:\n"
                f"1. Добавить бота в канал {channel_username}\n"
                f"2. Дать боту права администратора в канале\n"
                f"3. Получить ID канала командой /getchannelid в канале\n"
                f"4. Установить ID командой `/setchannelid -1001234567890`",
                parse_mode='Markdown'
            )
            
        # Если это ID
        elif channel_identifier.startswith('-100') and channel_identifier[4:].isdigit():
            channel_id = int(channel_identifier)
            config.config['required_channel_id'] = channel_id
            config.save_config()
            
            await update.message.reply_text(
                f"✅ *ID канала установлен:* `{channel_id}`\n\n"
                f"Теперь проверка подписки будет работать для этого канала.",
                parse_mode='Markdown'
            )
        
        else:
            await update.message.reply_text(
                "❌ Неверный формат!\n"
                "Должно быть:\n"
                "• @username канала (например: @wzkbnews)\n"
                "• ID канала в формате -1001234567890",
                parse_mode='Markdown'
            )
        
    except Exception as e:
        logger.error(f"Ошибка в команде /setchannel: {e}", exc_info=True)
        await update.message.reply_text("❌ Произошла ошибка. Попробуйте позже.")

async def get_channel_id_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получить ID текущего чата/канала"""
    try:
        chat_id = update.effective_chat.id
        chat_title = update.effective_chat.title or "Без названия"
        chat_username = update.effective_chat.username
        
        await update.message.reply_text(
            f"📊 *Информация о чате:*\n\n"
            f"📝 *Название:* {chat_title}\n"
            f"🆔 *ID:* `{chat_id}`\n"
            f"👤 *Username:* {f'@{chat_username}' if chat_username else 'Отсутствует'}\n"
            f"👥 *Тип чата:* {update.effective_chat.type}\n\n"
            f"💡 *Для установки канала подписки используйте:*\n"
            f"`/setchannelid {chat_id}`",
            parse_mode='Markdown'
        )
        
    except Exception as e:
        logger.error(f"Ошибка в команде /getchannelid: {e}", exc_info=True)
        await update.message.reply_text("❌ Произошла ошибка. Попробуйте позже.")

async def set_channel_id_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Установить ID канала для подписки"""
    try:
        user_id = update.effective_user.id
        
        if not has_permission(user_id, UserRole.OWNER):
            await update.message.reply_text("❌ Только владелец может устанавливать ID канала!")
            return
        
        if not context.args or len(context.args) < 1:
            await update.message.reply_text(
                "❌ Неверный формат!\n"
                "✅ Правильно: `/setchannelid -1001234567890`\n\n"
                f"📝 Чтобы получить ID канала:\n"
                f"1. Добавьте бота в канал\n"
                f"2. Дайте боту права администратора\n"
                f"3. Отправьте команду /getchannelid в канале",
                parse_mode='Markdown'
            )
            return
        
        channel_id_str = context.args[0]
        
        if not channel_id_str.startswith('-100') or not channel_id_str[4:].isdigit():
            await update.message.reply_text(
                "❌ ID канала должен быть в формате -1001234567890!\n"
                "Это ID супергруппы/канала в Telegram.",
                parse_mode='Markdown'
            )
            return
        
        channel_id = int(channel_id_str)
        config.config['required_channel_id'] = channel_id
        config.save_config()
        
        channel_info = config.get_required_channel()
        
        await update.message.reply_text(
            f"✅ *ID канала установлен!*\n\n"
            f"🆔 *ID канала:* `{channel_id}`\n"
            f"👤 *Username:* {channel_info['username']}\n\n"
            f"Теперь проверка подписки будет работать для этого канала.\n"
            f"Статус проверки: {'ВКЛЮЧЕНА' if config.is_check_subscription_enabled() else 'ВЫКЛЮЧЕНА'}",
            parse_mode='Markdown'
        )
        
    except Exception as e:
        logger.error(f"Ошибка в команде /setchannelid: {e}", exc_info=True)
        await update.message.reply_text("❌ Произошла ошибка. Попробуйте позже.")

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик ошибок"""
    logger.error(f"Ошибка: {context.error}", exc_info=True)
    if update and update.message:
        try:
            await update.message.reply_text("❌ Произошла ошибка. Попробуйте позже.")
        except:
            pass

async def init_telegram_api():
    """Инициализация Telegram User API"""
    global telegram_api
    try:
        print("🔌 Инициализация Telegram User API...")
        telegram_api = TelegramUserAPI(TELEGRAM_API_ID, TELEGRAM_API_HASH)
        connected = await telegram_api.connect()
        if connected:
            print("✅ Telegram User API успешно подключен")
            return True
        else:
            print("⚠️ Telegram User API не подключен, но бот продолжит работу")
            print("⚠️ Функция получения информации о пользователях будет ограничена")
            return False
    except Exception as e:
        print(f"❌ Критическая ошибка подключения Telegram User API: {e}")
        print(f"⚠️ Telegram User API не подключен, но бот продолжит работу")
        return False

async def main():
    """Основная функция запуска бота"""
    try:
        print("=" * 50)
        print("🚀 НАЧИНАЮ ЗАПУСК БОТА...")
        print(f"📁 Текущая директория: {os.getcwd()}")
        print(f"📁 Директория скрипта: {SCRIPT_DIR}")
        print(f"🤖 Токен бота: {TOKEN[:10]}...{TOKEN[-5:]}")
        print("=" * 50)
        
        print(f"🔍 Проверка файлов конфигурации...")
        print(f"   ✅ Файл конфигурации: {'СУЩЕСТВУЕТ' if os.path.exists(CONFIG_FILE) else '❌ ОТСУТСТВУЕТ'}")
        print(f"   ✅ База данных: {'СУЩЕСТВУЕТ' if os.path.exists(DB_FILE) else '❌ ОТСУТСТВУЕТ'}")
        print(f"   ✅ Папка для картинок: {'СУЩЕСТВУЕТ' if os.path.exists(IMAGES_FOLDER) else '❌ ОТСУТСТВУЕТ'}")
        
        if not os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(DEFAULT_CONFIG, f, ensure_ascii=False, indent=2)
            print(f"✅ Создан файл конфигурации: {CONFIG_FILE}")
        
        if not os.path.exists(DB_FILE):
            with open(DB_FILE, 'w', encoding='utf-8') as f:
                json.dump({}, f, ensure_ascii=False, indent=2)
            print(f"✅ Создана база данных: {DB_FILE}")
        
        if not os.path.exists(IMAGES_FOLDER):
            os.makedirs(IMAGES_FOLDER)
            print(f"✅ Создана папка для картинок: {IMAGES_FOLDER}")
        
        print("\n🔌 Инициализация Telegram API...")
        await init_telegram_api()
        
        print("\n🤖 Создание приложения бота...")
        application = Application.builder().token(TOKEN).build()
        print("✅ Приложение создано")
        
        print("\n📋 Регистрация обработчиков команд...")
        
        # Основные команды (с проверкой подписки)
        application.add_handler(CommandHandler("start", start_command))
        application.add_handler(CommandHandler("help", help_command))
        application.add_handler(CommandHandler("check", check_command))
        application.add_handler(CommandHandler("checkme", checkme_command))
        application.add_handler(CommandHandler("stats", stats_command))
        
        # Команды для админов (в админ-чате)
        application.add_handler(CommandHandler("add", add_command))
        
        # Команды для управления админами
        application.add_handler(CommandHandler("addadmin", add_admin_command))
        application.add_handler(CommandHandler("addspecial", add_special_admin_command))
        application.add_handler(CommandHandler("removeadmin", remove_admin_command))
        application.add_handler(CommandHandler("listadmins", list_admins_command))
        
        # Команда для установки админ-чата
        application.add_handler(CommandHandler("setadminchat", set_admin_chat_command))
        
        # Команды для управления подпиской
        application.add_handler(CommandHandler("togglesubscription", toggle_subscription_command))
        application.add_handler(CommandHandler("setchannel", set_channel_command))
        application.add_handler(CommandHandler("getchannelid", get_channel_id_command))
        application.add_handler(CommandHandler("setchannelid", set_channel_id_command))
        
        # Обработчик для фото с тегами (только для владельца)
        application.add_handler(MessageHandler(filters.PHOTO & filters.CaptionRegex(r'#(scammer|clean|warning|admin)'), handle_photo_message))
        
        # Обработчик нажатий на кнопки
        application.add_handler(CallbackQueryHandler(button_callback_handler))
        
        # Регистрируем обработчик ошибок
        application.add_error_handler(error_handler)
        print("✅ Все обработчики зарегистрированы")
        
        try:
            bot_info = await application.bot.get_me()
            print(f"\n🤖 Информация о боте:")
            print(f"   Имя: {bot_info.first_name}")
            print(f"   Username: @{bot_info.username}")
            print(f"   ID: {bot_info.id}")
        except Exception as e:
            print(f"⚠️ Не удалось получить информацию о боте: {e}")
        
        channel_info = config.get_required_channel()
        print(f"\n📢 Канал для подписки:")
        print(f"   ID: {channel_info['id']}")
        print(f"   Username: {channel_info['username']}")
        print(f"   Проверка подписки: {'ВКЛЮЧЕНА' if config.is_check_subscription_enabled() else 'ВЫКЛЮЧЕНА'}")
        
        print(f"\n{'='*50}")
        print(f"✅ БОТ УСПЕШНО ЗАПУЩЕН!")
        print(f"🤖 Имя бота: @{BOT_USERNAME}")
        print(f"📊 Файл базы данных: {DB_FILE}")
        print(f"⚙️ Файл конфигурации: {CONFIG_FILE}")
        print(f"🖼️ Папка для картинок: {IMAGES_FOLDER}")
        print(f"👑 Владелец ID: {config.config['owner_id']}")
        print(f"💬 Админ-чат ID: {config.config['admin_chat_id']}")
        print(f"👤 Username админ-чата: {config.get_admin_chat_username()}")
        print(f"🛡️ Спец-админы: {config.config['special_admins']}")
        print(f"👮 Админы: {config.config['admins']}")
        print(f"{'='*50}")
        print("📡 Ожидание команд...")
        print("Для остановки нажмите Ctrl+C")
        
        # Запускаем polling
        await application.run_polling(allowed_updates=Update.ALL_TYPES, close_loop=False)
        
    except Exception as e:
        print(f"\n❌ КРИТИЧЕСКАЯ ОШИБКА ПРИ ЗАПУСКЕ БОТА: {e}")
        logger.error(f"Критическая ошибка при запуске бота: {e}", exc_info=True)
        
        if telegram_api and telegram_api.is_connected:
            await telegram_api.close()
        
        print("\n⏳ Завершение работы...")
        await asyncio.sleep(2)
        raise

if __name__ == '__main__':
    try:
        import sys
        print(f"🐍 Python версия: {sys.version}")
        
        sys.setrecursionlimit(10000)
        
        # Используем старый метод запуска для совместимости с nest_asyncio
        loop = asyncio.get_event_loop()
        loop.run_until_complete(main())
        
    except KeyboardInterrupt:
        print("\n\n🛑 Бот остановлен пользователем (Ctrl+C)")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Непредвиденная ошибка: {e}")
        logger.error(f"Непредвиденная ошибка: {e}", exc_info=True)

        sys.exit(1)