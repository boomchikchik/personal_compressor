import os
import logging
import asyncio
import threading
from queue import Queue
from datetime import datetime
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message
from concurrent.futures import ThreadPoolExecutor

from cleanup_manager import CleanupManager
from message_handlers import setup_message_handlers, setup_callback_handlers
from process_handlers import process_compression, process_conversion

# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[logging.FileHandler('bot.log'), logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# Bot Configuration
API_ID = 13216322
API_HASH = "15e5e632a8a0e52251ac8c3ccbe462c7"
BOT_TOKEN = "7335432995:AAG3phsMDhohsuStZY7m1PyoeLhNY73KYpA"
ADMIN_ID = 5993556795

# Initialize bot
app = Client("file_compression_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# Queue and threading
task_queue = Queue()
processing_lock = threading.Lock()
executor = ThreadPoolExecutor(max_workers=4)

# Storage
user_files = {}
active_tasks = {}

# Configuration
MAX_CONCURRENT_TASKS = 3
current_tasks = 0

# Supported formats
IMAGE_FORMATS = ['jpg', 'png', 'webp', 'bmp', 'gif', 'ico', 'tiff']
VIDEO_FORMATS = ['mp4', 'avi', 'mkv', 'mov', 'flv', 'webm', 'wmv', '3gp']
AUDIO_FORMATS = ['mp3', 'wav', 'ogg', 'aac', 'flac', 'm4a', 'wma']


async def notify_admin(error_message, user_id=None, traceback_str=None):
    """Send error notification to admin"""
    try:
        notification = f"""🚨 **Bot Error Alert**

⏰ Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
👤 User ID: {user_id or 'Unknown'}
❌ Error: {error_message}

**Traceback:**
```
{traceback_str or 'No traceback'}
```"""
        await app.send_message(ADMIN_ID, notification)
    except Exception as e:
        logger.error(f"Admin notify failed: {e}")


class TaskQueue:
    """Manage task queue and processing"""
    
    @staticmethod
    async def add_task(task_func, *args, **kwargs):
        global current_tasks
        
        user_id = args[2] if len(args) > 2 else None
        
        if current_tasks >= MAX_CONCURRENT_TASKS:
            position = task_queue.qsize() + 1
            message = args[1] if len(args) > 1 else None
            if message:
                await message.edit_text(
                    f"⏳ **Task Added to Queue**\n\n"
                    f"Position: #{position}\n"
                    f"Current tasks: {current_tasks}/{MAX_CONCURRENT_TASKS}\n\n"
                    f"Please wait..."
                )
        
        task_queue.put((task_func, args, kwargs, user_id))
        asyncio.create_task(TaskQueue.process_queue())
    
    @staticmethod
    async def process_queue():
        global current_tasks
        
        while not task_queue.empty() and current_tasks < MAX_CONCURRENT_TASKS:
            if task_queue.empty():
                break
            
            task_func, args, kwargs, user_id = task_queue.get()
            
            current_tasks += 1
            active_tasks[user_id] = datetime.now()
            
            try:
                # Add user_files and notify_admin to kwargs
                await task_func(*args, user_files=user_files, notify_admin_func=notify_admin, **kwargs)
            except Exception as e:
                logger.error(f"Task error: {e}")
                import traceback
                await notify_admin(str(e), user_id, traceback.format_exc())
            finally:
                current_tasks -= 1
                if user_id in active_tasks:
                    del active_tasks[user_id]
                task_queue.task_done()


# ===== COMMAND HANDLERS =====

@app.on_message(filters.command("start"))
async def start_command(client, message: Message):
    await message.reply_text("""🤖 **Welcome to Multi-Function File Bot!**

I can help you with:
📸 **Image**: Compress & Convert  
🎥 **Video**: Compress & Convert
🎵 **Audio**: Compress & Convert
📄 **PDF**: Compress documents
📦 **Files**: ZIP compression

**Features:**
✅ Real-time progress tracking
✅ Smart compression algorithms
✅ Queue management system
✅ Automatic cleanup

**How to use:**
Just send me any file to get started! 🚀

Use /help for more information.""")


@app.on_message(filters.command("help"))
async def help_command(client, message: Message):
    await message.reply_text("""📖 **Help & Information**

**Compression Levels:**
🔥 **Maximum** - Smallest file size, lower quality
⚡ **High** - Recommended balance (default)
🔧 **Medium** - Good quality, moderate compression
✨ **Low** - Best quality, minimal compression

**Supported Formats:**
📸 Images: JPG, PNG, WebP, BMP, GIF, ICO, TIFF
🎥 Videos: MP4, AVI, MKV, MOV, FLV, WebM, WMV, 3GP
🎵 Audio: MP3, WAV, OGG, AAC, FLAC, M4A, WMA
📄 Documents: PDF

**Commands:**
/start - Start the bot
/help - Show this help message
/queue - Check queue status

**Admin Commands:**
/setqueue <number> - Set max concurrent tasks
/stats - View bot statistics
/cleanup - Force cleanup temp files

**Limits:**
• Maximum file size: 50MB
• Files are automatically deleted after processing
• Progress updates every 1-2 seconds""")


@app.on_message(filters.command("setqueue") & filters.user(ADMIN_ID))
async def set_queue_limit(client, message: Message):
    global MAX_CONCURRENT_TASKS
    
    try:
        limit = int(message.text.split()[1])
        if limit < 1 or limit > 10:
            await message.reply_text("❌ Limit must be between 1 and 10")
            return
        
        MAX_CONCURRENT_TASKS = limit
        await message.reply_text(f"✅ Maximum concurrent tasks set to: {limit}")
        logger.info(f"Admin changed MAX_CONCURRENT_TASKS to {limit}")
    except (IndexError, ValueError):
        await message.reply_text("❌ Usage: /setqueue <number>\nExample: /setqueue 5")


@app.on_message(filters.command("stats") & filters.user(ADMIN_ID))
async def bot_stats(client, message: Message):
    await message.reply_text(f"""📊 **Bot Statistics**

⚙️ **Current tasks**: {current_tasks}/{MAX_CONCURRENT_TASKS}
⏳ **Queue length**: {task_queue.qsize()}
👥 **Active users**: {len(active_tasks)}
📝 **Stored files**: {len(user_files)}

**System Info:**
✅ Bot is running smoothly
🔄 Auto-cleanup: Enabled
📊 Progress tracking: Enabled""")


@app.on_message(filters.command("cleanup") & filters.user(ADMIN_ID))
async def force_cleanup(client, message: Message):
    msg = await message.reply_text("🧹 Cleaning up temporary files...")
    CleanupManager.cleanup_all()
    await msg.edit_text("✅ Cleanup complete! All temporary directories have been removed.")


@app.on_message(filters.command("queue"))
async def queue_status(client, message: Message):
    await message.reply_text(
        f"**📊 Queue Status**\n\n"
        f"🔄 **Processing**: {current_tasks}/{MAX_CONCURRENT_TASKS}\n"
        f"⏳ **Waiting**: {task_queue.qsize()}\n\n"
        f"{'⚠️ Queue is full, new tasks will wait' if current_tasks >= MAX_CONCURRENT_TASKS else '✅ Queue has space available'}"
    )


# Setup handlers
setup_message_handlers(app, user_files)
setup_callback_handlers(app, user_files, TaskQueue, process_compression, process_conversion)


if __name__ == "__main__":
    print("\n" + "="*50)
    print("🤖 File Compression Bot Starting...")
    print("="*50)
    print(f"👤 Admin ID: {ADMIN_ID}")
    print(f"📋 Queue system: Active")
    print(f"🔄 Max concurrent tasks: {MAX_CONCURRENT_TASKS}")
    print(f"✅ Multi-threading: Enabled")
    print(f"✅ Smart compression: Enabled")
    print(f"🧹 Auto cleanup: Enabled")
    print(f"📊 Progress tracking: Enhanced")
    print(f"🚨 Error notifications: Enabled")
    print("="*50)
    print("✅ Bot is ready to process files!")
    print("="*50 + "\n")
    
    try:
        app.run()
    except KeyboardInterrupt:
        print("\n🛑 Shutting down bot...")
        CleanupManager.cleanup_all()
        print("✅ Cleanup complete! Bot stopped successfully.")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        CleanupManager.cleanup_all()
        print("❌ Bot stopped due to error. Check logs for details.")
