import os
from pyrogram import filters
from pyrogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

# These will be imported from main.py
IMAGE_FORMATS = ['jpg', 'png', 'webp', 'bmp', 'gif', 'ico', 'tiff']
VIDEO_FORMATS = ['mp4', 'avi', 'mkv', 'mov', 'flv', 'webm', 'wmv', '3gp']
AUDIO_FORMATS = ['mp3', 'wav', 'ogg', 'aac', 'flac', 'm4a', 'wma']


def create_action_keyboard(file_type):
    """Create keyboard for action selection"""
    keyboard = [
        [InlineKeyboardButton("🗜️ Compress", callback_data=f"compress_{file_type}"),
         InlineKeyboardButton("🔄 Convert", callback_data=f"convert_{file_type}")],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel")]
    ]
    return InlineKeyboardMarkup(keyboard)


def create_compression_level_keyboard(file_type):
    """Create keyboard for compression level selection"""
    keyboard = [
        [InlineKeyboardButton("🔥 Maximum", callback_data=f"complvl_{file_type}_max"),
         InlineKeyboardButton("⚡ High", callback_data=f"complvl_{file_type}_high")],
        [InlineKeyboardButton("🔧 Medium", callback_data=f"complvl_{file_type}_med"),
         InlineKeyboardButton("✨ Low", callback_data=f"complvl_{file_type}_low")],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel")]
    ]
    return InlineKeyboardMarkup(keyboard)


def create_format_keyboard(file_type):
    """Create keyboard for format selection"""
    if file_type == 'image':
        formats = IMAGE_FORMATS
    elif file_type == 'video':
        formats = VIDEO_FORMATS
    elif file_type == 'audio':
        formats = AUDIO_FORMATS
    else:
        return None
    
    keyboard = []
    row = []
    for i, fmt in enumerate(formats):
        row.append(InlineKeyboardButton(fmt.upper(), callback_data=f"convert_{file_type}_{fmt}"))
        if (i + 1) % 3 == 0:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    
    keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data="cancel")])
    return InlineKeyboardMarkup(keyboard)


def setup_message_handlers(app, user_files):
    """Setup all message handlers"""
    
    @app.on_message(filters.photo)
    async def handle_photo(client, message: Message):
        user_id = message.from_user.id
        user_files[user_id] = {
            'type': 'image',
            'message': message,
            'file_id': message.photo.file_id,
            'format': 'jpg'
        }
        await message.reply_text(
            "📸 **Image received!**\n\nWhat would you like to do?",
            reply_markup=create_action_keyboard('image')
        )
    
    @app.on_message(filters.video)
    async def handle_video(client, message: Message):
        user_id = message.from_user.id
        
        if message.video.file_size > 2000 * 1024 * 1024:
            await message.reply_text("❌ Video too large! Maximum size is 2GB.")
            return
        
        user_files[user_id] = {
            'type': 'video',
            'message': message,
            'file_id': message.video.file_id,
            'format': 'mp4'
        }
        await message.reply_text(
            "🎥 **Video received!**\n\nWhat would you like to do?",
            reply_markup=create_action_keyboard('video')
        )
    
    @app.on_message(filters.audio)
    async def handle_audio(client, message: Message):
        user_id = message.from_user.id
        user_files[user_id] = {
            'type': 'audio',
            'message': message,
            'file_id': message.audio.file_id,
            'format': 'mp3'
        }
        await message.reply_text(
            "🎵 **Audio received!**\n\nWhat would you like to do?",
            reply_markup=create_action_keyboard('audio')
        )
    
    @app.on_message(filters.document)
    async def handle_document(client, message: Message):
        user_id = message.from_user.id
        file_name = message.document.file_name
        file_size = message.document.file_size
        ext = os.path.splitext(file_name)[1].lower()[1:]
        
        if file_size > 50 * 1024 * 1024:
            await message.reply_text("❌ File too large! Maximum size is 50MB.")
            return
        
        # Determine file type
        if ext in IMAGE_FORMATS:
            file_type = 'image'
        elif ext in VIDEO_FORMATS:
            file_type = 'video'
        elif ext in AUDIO_FORMATS:
            file_type = 'audio'
        elif ext == 'pdf':
            file_type = 'pdf'
        else:
            file_type = 'other'
        
        user_files[user_id] = {
            'type': file_type,
            'message': message,
            'file_id': message.document.file_id,
            'file_name': file_name,
            'format': ext
        }
        
        # Show appropriate keyboard
        if file_type in ['image', 'video', 'audio']:
            await message.reply_text(
                f"📄 **{file_type.capitalize()} received!**\n\nWhat would you like to do?",
                reply_markup=create_action_keyboard(file_type)
            )
        elif file_type == 'pdf':
            await message.reply_text(
                "📄 **PDF received!**\n\nWould you like to compress it?",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🗜️ Compress", callback_data="complvl_pdf_max")],
                    [InlineKeyboardButton("❌ Cancel", callback_data="cancel")]
                ])
            )
        else:
            await message.reply_text(
                "📦 **File received!**\n\nWould you like to compress it?",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🗜️ ZIP Compress", callback_data="complvl_other_max")],
                    [InlineKeyboardButton("❌ Cancel", callback_data="cancel")]
                ])
            )


def setup_callback_handlers(app, user_files, TaskQueue, process_compression, process_conversion):
    """Setup all callback query handlers"""
    
    @app.on_callback_query()
    async def handle_callback(client, callback_query: CallbackQuery):
        data = callback_query.data
        user_id = callback_query.from_user.id
        
        # Handle cancel
        if data == "cancel":
            if user_id in user_files:
                del user_files[user_id]
            await callback_query.message.edit_text("❌ Operation cancelled.")
            return
        
        # Check if user has file
        if user_id not in user_files:
            await callback_query.answer("❌ No file found! Please send a file first.", show_alert=True)
            return
        
        # Handle compress action (show level selection)
        if data.startswith("compress_") and data.count("_") == 1:
            file_type = data.split("_")[1]
            await callback_query.message.edit_text(
                "🎚️ **Select Compression Level:**\n\n"
                "🔥 **Maximum** - Smallest size, lower quality\n"
                "⚡ **High** - Recommended balance\n"
                "🔧 **Medium** - Good quality\n"
                "✨ **Low** - Best quality, larger size",
                reply_markup=create_compression_level_keyboard(file_type)
            )
            await callback_query.answer()
        
        # Handle compression level selection
        elif data.startswith("complvl_"):
            _, file_type, level = data.split("_")
            await callback_query.message.edit_text("⏳ Adding task to queue...")
            await TaskQueue.add_task(
                process_compression,
                client,
                callback_query.message,
                user_id,
                file_type,
                level
            )
            await callback_query.answer()
        
        # Handle convert action (show format selection)
        elif data.startswith("convert_") and data.count("_") == 1:
            file_type = data.split("_")[1]
            await callback_query.message.edit_text(
                "🔄 **Select Output Format:**",
                reply_markup=create_format_keyboard(file_type)
            )
            await callback_query.answer()
        
        # Handle format selection
        elif data.startswith("convert_") and data.count("_") == 2:
            _, file_type, output_format = data.split("_")
            await callback_query.message.edit_text("⏳ Adding task to queue...")
            await TaskQueue.add_task(
                process_conversion,
                client,
                callback_query.message,
                user_id,
                file_type,
                output_format
            )
            await callback_query.answer()
