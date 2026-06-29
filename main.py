"""
🎨 Color Canvas Bot - Professional Color Palette Generator
Generate beautiful color palettes, extract colors from images, and more!
"""

import os
import io
import logging
import random
import math
import json
from datetime import datetime
from typing import Dict, List, Tuple, Optional
from colormath.color_objects import sRGBColor, LabColor
from colormath.color_conversions import convert_color
from colormath.color_diff import delta_e_cie2000

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    Message,
    CallbackQuery,
    BufferedInputFile,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from dotenv import load_dotenv
import webcolors

# ==================== CONFIGURATION ====================

load_dotenv()

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("❌ TELEGRAM_BOT_TOKEN is required!")

BOT_NAME = "Color Canvas Bot"
BOT_USERNAME = "color_canvas_bot"
BOT_VERSION = "1.0.0"

storage = MemoryStorage()
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=storage)

# ==================== CONSTANTS ====================

# Color harmony rules
HARMONY_RULES = {
    "monochromatic": {"label": "🎨 Monochromatic", "count": 5},
    "complementary": {"label": "🔄 Complementary", "count": 2},
    "analogous": {"label": "🌈 Analogous", "count": 5},
    "triadic": {"label": "🔺 Triadic", "count": 3},
    "tetradic": {"label": "🔲 Tetradic", "count": 4},
    "square": {"label": "⬜ Square", "count": 4},
    "split_complementary": {"label": "✂️ Split Complementary", "count": 3},
    "double_split": {"label": "✨ Double Split", "count": 4},
}

# Color names and hex values for suggestions
COMMON_COLORS = {
    "red": "#FF0000",
    "crimson": "#DC143C",
    "pink": "#FFC0CB",
    "orange": "#FFA500",
    "gold": "#FFD700",
    "yellow": "#FFFF00",
    "lime": "#00FF00",
    "green": "#008000",
    "teal": "#008080",
    "cyan": "#00FFFF",
    "blue": "#0000FF",
    "navy": "#000080",
    "purple": "#800080",
    "magenta": "#FF00FF",
    "violet": "#EE82EE",
    "brown": "#A52A2A",
    "beige": "#F5F5DC",
    "white": "#FFFFFF",
    "gray": "#808080",
    "black": "#000000",
    "maroon": "#800000",
    "olive": "#808000",
    "coral": "#FF7F50",
    "indigo": "#4B0082",
    "lavender": "#E6E6FA",
    "mint": "#98FF98",
    "peach": "#FFDAB9",
    "sky": "#87CEEB",
    "slate": "#708090",
    "wheat": "#F5DEB3",
}

# ==================== USER DATA ====================

class ColorStates(StatesGroup):
    WAITING_HEX = State()
    WAITING_COLOR_NAME = State()
    WAITING_IMAGE = State()
    WAITING_PALETTE_NAME = State()

user_data: Dict[int, Dict] = {}

def get_user_data(user_id: int) -> Dict:
    if user_id not in user_data:
        user_data[user_id] = {
            "palettes": [],  # Saved palettes
            "history": [],   # Recent colors
            "settings": {
                "palette_count": 5,
                "harmony": "monochromatic",
            }
        }
    return user_data[user_id]

# ==================== KEYBOARDS ====================

def main_menu() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🎨 Generate Palette", callback_data="generate"),
        InlineKeyboardButton(text="🎯 Color Info", callback_data="color_info")
    )
    builder.row(
        InlineKeyboardButton(text="🖼️ Extract from Image", callback_data="extract"),
        InlineKeyboardButton(text="💾 Saved Palettes", callback_data="saved")
    )
    builder.row(
        InlineKeyboardButton(text="⚙️ Settings", callback_data="settings"),
        InlineKeyboardButton(text="❓ Help", callback_data="help")
    )
    return builder.as_markup()

def harmony_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for harmony_id, harmony_data in HARMONY_RULES.items():
        builder.row(InlineKeyboardButton(
            text=harmony_data["label"],
            callback_data=f"harmony_{harmony_id}"
        ))
    builder.row(InlineKeyboardButton(text="🔙 Back", callback_data="back_menu"))
    return builder.as_markup()

def palette_count_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for count in [3, 4, 5, 6, 8, 10]:
        builder.row(InlineKeyboardButton(
            text=f"🎨 {count} Colors",
            callback_data=f"count_{count}"
        ))
    builder.row(InlineKeyboardButton(text="🔙 Back", callback_data="back_settings"))
    return builder.as_markup()

def saved_palettes_keyboard(user_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    data = get_user_data(user_id)
    palettes = data.get("palettes", [])
    
    if palettes:
        for idx, palette in enumerate(palettes[-8:], 1):
            name = palette.get("name", f"Palette {idx}")
            colors = palette.get("colors", [])
            emojis = "".join(["⬛" for _ in colors[:3]])
            builder.row(InlineKeyboardButton(
                text=f"{emojis} {name}",
                callback_data=f"load_{idx-1}"
            ))
    else:
        builder.row(InlineKeyboardButton(
            text="📭 No saved palettes",
            callback_data="noop"
        ))
    
    builder.row(InlineKeyboardButton(text="🔙 Back", callback_data="back_menu"))
    return builder.as_markup()

# ==================== COLOR UTILITIES ====================

def hex_to_rgb(hex_color: str) -> Tuple[int, int, int]:
    """Convert hex color to RGB tuple"""
    hex_color = hex_color.lstrip('#')
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))

def rgb_to_hex(r: int, g: int, b: int) -> str:
    """Convert RGB tuple to hex color"""
    return f"#{r:02x}{g:02x}{b:02x}"

def hex_to_color_name(hex_color: str) -> str:
    """Get closest color name from hex"""
    try:
        # Try exact match
        return webcolors.hex_to_name(hex_color)
    except:
        try:
            # Try closest match
            rgb = hex_to_rgb(hex_color)
            closest = webcolors.rgb_to_name((rgb[0], rgb[1], rgb[2]))
            return closest
        except:
            return "Unknown"

def rgb_to_hsl(r: int, g: int, b: int) -> Tuple[int, int, int]:
    """Convert RGB to HSL"""
    r, g, b = r/255.0, g/255.0, b/255.0
    max_c = max(r, g, b)
    min_c = min(r, g, b)
    l = (max_c + min_c) / 2
    if max_c == min_c:
        h = s = 0
    else:
        d = max_c - min_c
        s = d / (2 - max_c - min_c) if l > 0.5 else d / (max_c + min_c)
        if max_c == r:
            h = ((g - b) / d) % 6
        elif max_c == g:
            h = (b - r) / d + 2
        else:
            h = (r - g) / d + 4
        h *= 60
        if h < 0:
            h += 360
    return (int(round(h)), int(round(s * 100)), int(round(l * 100)))

def generate_palette(base_color: str, harmony: str, count: int) -> List[str]:
    """Generate a color palette based on harmony rule"""
    rgb = hex_to_rgb(base_color)
    h, s, l = rgb_to_hsl(rgb[0], rgb[1], rgb[2])
    
    if harmony == "monochromatic":
        palette = []
        for i in range(count):
            new_l = max(10, min(90, l + (i - count//2) * 15))
            new_s = max(20, min(80, s + (i - count//2) * 5))
            rgb_val = hsl_to_rgb(h, new_s, new_l)
            palette.append(rgb_to_hex(*rgb_val))
        return palette
    
    elif harmony == "complementary":
        comp_h = (h + 180) % 360
        return [base_color, rgb_to_hex(*hsl_to_rgb(comp_h, s, l))]
    
    elif harmony == "analogous":
        palette = []
        for i in range(count):
            angle = h + (i - count//2) * 25
            rgb_val = hsl_to_rgb(angle % 360, s, l)
            palette.append(rgb_to_hex(*rgb_val))
        return palette
    
    elif harmony == "triadic":
        angles = [h, (h + 120) % 360, (h + 240) % 360]
        palette = []
        for angle in angles[:count]:
            rgb_val = hsl_to_rgb(angle, s, l)
            palette.append(rgb_to_hex(*rgb_val))
        return palette
    
    elif harmony == "tetradic":
        angles = [h, (h + 90) % 360, (h + 180) % 360, (h + 270) % 360]
        palette = []
        for angle in angles[:count]:
            rgb_val = hsl_to_rgb(angle, s, l)
            palette.append(rgb_to_hex(*rgb_val))
        return palette
    
    elif harmony == "square":
        angles = [h, (h + 90) % 360, (h + 180) % 360, (h + 270) % 360]
        palette = []
        for angle in angles[:count]:
            rgb_val = hsl_to_rgb(angle, s, l)
            palette.append(rgb_to_hex(*rgb_val))
        return palette
    
    elif harmony == "split_complementary":
        comp = (h + 180) % 360
        angles = [h, (comp - 30) % 360, (comp + 30) % 360]
        palette = []
        for angle in angles[:count]:
            rgb_val = hsl_to_rgb(angle, s, l)
            palette.append(rgb_to_hex(*rgb_val))
        return palette
    
    elif harmony == "double_split":
        comp = (h + 180) % 360
        angles = [h, (comp - 30) % 360, (comp + 30) % 360, (h + 60) % 360]
        palette = []
        for angle in angles[:count]:
            rgb_val = hsl_to_rgb(angle, s, l)
            palette.append(rgb_to_hex(*rgb_val))
        return palette
    
    return [base_color]

def hsl_to_rgb(h: float, s: float, l: float) -> Tuple[int, int, int]:
    """Convert HSL to RGB"""
    h = h / 360
    s = s / 100
    l = l / 100
    
    if s == 0:
        r = g = b = l
    else:
        def hue_to_rgb(p, q, t):
            if t < 0: t += 1
            if t > 1: t -= 1
            if t < 1/6: return p + (q - p) * 6 * t
            if t < 1/2: return q
            if t < 2/3: return p + (q - p) * (2/3 - t) * 6
            return p
        
        q = l * (1 + s) if l < 0.5 else l + s - l * s
        p = 2 * l - q
        r = hue_to_rgb(p, q, h + 1/3)
        g = hue_to_rgb(p, q, h)
        b = hue_to_rgb(p, q, h - 1/3)
    
    return (int(round(r * 255)), int(round(g * 255)), int(round(b * 255)))

def get_contrast_ratio(color1: str, color2: str) -> float:
    """Calculate contrast ratio between two colors"""
    def luminance(r, g, b):
        rgb = [r/255, g/255, b/255]
        for i, c in enumerate(rgb):
            if c <= 0.03928:
                rgb[i] = c / 12.92
            else:
                rgb[i] = ((c + 0.055) / 1.055) ** 2.4
        return 0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]
    
    rgb1 = hex_to_rgb(color1)
    rgb2 = hex_to_rgb(color2)
    l1 = luminance(rgb1[0], rgb1[1], rgb1[2])
    l2 = luminance(rgb2[0], rgb2[1], rgb2[2])
    
    if l1 > l2:
        return (l1 + 0.05) / (l2 + 0.05)
    else:
        return (l2 + 0.05) / (l1 + 0.05)

def suggest_text_color(hex_color: str) -> str:
    """Suggest text color (black or white) for readability"""
    rgb = hex_to_rgb(hex_color)
    # Use perceived brightness
    brightness = (rgb[0] * 299 + rgb[1] * 587 + rgb[2] * 114) / 1000
    return "#000000" if brightness > 128 else "#FFFFFF"

# ==================== IMAGE GENERATION ====================

def create_palette_image(colors: List[str], width: int = 800, height: int = 400) -> bytes:
    """Create a visual palette image with color swatches"""
    try:
        img = Image.new('RGB', (width, height), color='#F5F5F5')
        draw = ImageDraw.Draw(img)
        
        # Draw title
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 24)
            small_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 18)
        except:
            font = ImageFont.load_default()
            small_font = font
        
        # Draw palette swatches
        swatch_width = (width - 60) // len(colors)
        swatch_height = height - 100
        
        for i, color in enumerate(colors):
            x = 30 + i * swatch_width
            y = 50
            
            # Draw swatch
            rgb = hex_to_rgb(color)
            draw.rectangle([x, y, x + swatch_width - 10, y + swatch_height], 
                          fill=rgb, outline=(200, 200, 200))
            
            # Draw hex code
            text = color.upper()
            bbox = draw.textbbox((0, 0), text, font=small_font)
            text_x = x + (swatch_width - 10 - (bbox[2] - bbox[0])) // 2
            text_y = y + swatch_height + 10
            
            # Use white or black text for contrast
            text_color = suggest_text_color(color)
            draw.text((text_x, text_y), text, fill=text_color, font=small_font)
        
        # Add footer
        footer = f"🎨 Color Canvas Bot - Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        bbox = draw.textbbox((0, 0), footer, font=small_font)
        draw.text(((width - (bbox[2] - bbox[0])) // 2, height - 25), 
                 footer, fill=(150, 150, 150), font=small_font)
        
        # Convert to bytes
        img_bytes = io.BytesIO()
        img.save(img_bytes, format='PNG', optimize=True)
        img_bytes.seek(0)
        return img_bytes.read()
        
    except Exception as e:
        logger.error(f"❌ Palette image error: {str(e)}")
        return create_palette_fallback(colors)

def create_palette_fallback(colors: List[str]) -> bytes:
    """Create simple fallback palette image"""
    try:
        height = 50 + len(colors) * 40
        img = Image.new('RGB', (400, height), color='#FFFFFF')
        draw = ImageDraw.Draw(img)
        
        for i, color in enumerate(colors):
            y = 20 + i * 40
            rgb = hex_to_rgb(color)
            draw.rectangle([20, y, 380, y + 30], fill=rgb)
            draw.text((390, y), color, fill=(0, 0, 0))
        
        img_bytes = io.BytesIO()
        img.save(img_bytes, format='PNG')
        img_bytes.seek(0)
        return img_bytes.read()
        
    except:
        return b""

def create_color_info_image(hex_color: str) -> bytes:
    """Create an image showing detailed color information"""
    try:
        width, height = 600, 500
        img = Image.new('RGB', (width, height), color='#FFFFFF')
        draw = ImageDraw.Draw(img)
        
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 20)
            bold_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 24)
        except:
            font = ImageFont.load_default()
            bold_font = font
        
        # Draw color swatch
        rgb = hex_to_rgb(hex_color)
        draw.rectangle([50, 50, 250, 250], fill=rgb)
        
        # Draw info
        color_name = hex_to_color_name(hex_color)
        h, s, l = rgb_to_hsl(rgb[0], rgb[1], rgb[2])
        contrast = get_contrast_ratio(hex_color, "#FFFFFF")
        
        info_lines = [
            f"🎯 Color: {color_name}",
            f"🔢 Hex: {hex_color.upper()}",
            f"🔴 RGB: {rgb[0]}, {rgb[1]}, {rgb[2]}",
            f"🌈 HSL: {h}°, {s}%, {l}%",
            f"⚡ Contrast Ratio: {contrast:.2f}:1",
            f"📱 Text: {suggest_text_color(hex_color)}",
        ]
        
        y = 70
        for line in info_lines:
            draw.text((280, y), line, fill=(0, 0, 0), font=font)
            y += 35
        
        # Add footer
        footer = f"🎨 Color Canvas Bot"
        bbox = draw.textbbox((0, 0), footer, font=font)
        draw.text(((width - (bbox[2] - bbox[0])) // 2, height - 30), 
                 footer, fill=(150, 150, 150), font=font)
        
        img_bytes = io.BytesIO()
        img.save(img_bytes, format='PNG', optimize=True)
        img_bytes.seek(0)
        return img_bytes.read()
        
    except Exception as e:
        logger.error(f"❌ Color info image error: {str(e)}")
        return b""

def extract_colors_from_image(image_data: bytes, count: int = 5) -> List[str]:
    """Extract dominant colors from an image"""
    try:
        img = Image.open(io.BytesIO(image_data))
        img = img.resize((100, 100))
        pixels = list(img.getdata())
        
        # Simple color quantization
        color_counts = {}
        for pixel in pixels:
            # Round to nearest 10 for quantization
            r = round(pixel[0] / 10) * 10
            g = round(pixel[1] / 10) * 10
            b = round(pixel[2] / 10) * 10
            key = (r, g, b)
            color_counts[key] = color_counts.get(key, 0) + 1
        
        # Sort by frequency
        sorted_colors = sorted(color_counts.items(), key=lambda x: x[1], reverse=True)
        
        # Convert to hex
        colors = []
        for color, _ in sorted_colors[:count]:
            hex_color = rgb_to_hex(color[0], color[1], color[2])
            colors.append(hex_color)
        
        return colors
        
    except Exception as e:
        logger.error(f"❌ Color extraction error: {str(e)}")
        return ["#FF0000", "#00FF00", "#0000FF", "#FFFF00", "#FF00FF"]

def format_size(bytes_count: int) -> str:
    for unit in ['B', 'KB', 'MB']:
        if bytes_count < 1024:
            return f"{bytes_count:.1f} {unit}"
        bytes_count /= 1024
    return f"{bytes_count:.1f} GB"

# ==================== COMMAND HANDLERS ====================

@dp.message(Command("start"))
async def cmd_start(message: Message):
    user = message.from_user
    data = get_user_data(user.id)
    
    welcome = (
        f"🎨 **Welcome to {BOT_NAME}!**\n\n"
        f"👋 Hello @{user.username or 'User'}!\n\n"
        f"Your professional color palette generator and color tools.\n\n"
        f"✨ **Features:**\n"
        f"• 🎨 Generate beautiful color palettes\n"
        f"• 🎯 Get detailed color information\n"
        f"• 🖼️ Extract colors from images\n"
        f"• 💾 Save your favorite palettes\n"
        f"• 🌈 Multiple harmony rules\n\n"
        f"📊 You have {len(data['palettes'])} saved palettes\n\n"
        f"🚀 Tap **Generate Palette** below to start!"
    )
    
    await message.reply(
        welcome,
        parse_mode="Markdown",
        reply_markup=main_menu()
    )

@dp.message(Command("generate"))
async def cmd_generate(message: Message, state: FSMContext):
    await state.set_state(ColorStates.WAITING_COLOR_NAME)
    await message.reply(
        "🎨 **Generate a Color Palette**\n\n"
        "Send me a color name or hex code:\n\n"
        "📝 **Examples:**\n"
        "• `blue` - by name\n"
        "• `#FF5733` - by hex\n"
        "• `255, 87, 51` - by RGB\n\n"
        "Or tap a suggestion below:\n"
        "Send /cancel to cancel.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardBuilder().row(
            InlineKeyboardButton(text="🔴 Red", callback_data="suggest_red"),
            InlineKeyboardButton(text="🔵 Blue", callback_data="suggest_blue"),
            InlineKeyboardButton(text="🟢 Green", callback_data="suggest_green")
        ).row(
            InlineKeyboardButton(text="🟡 Yellow", callback_data="suggest_yellow"),
            InlineKeyboardButton(text="🟣 Purple", callback_data="suggest_purple"),
            InlineKeyboardButton(text="🟠 Orange", callback_data="suggest_orange")
        ).row(
            InlineKeyboardButton(text="⚪ White", callback_data="suggest_white"),
            InlineKeyboardButton(text="⚫ Black", callback_data="suggest_black"),
            InlineKeyboardButton(text="🩷 Pink", callback_data="suggest_pink")
        ).as_markup()
    )

@dp.message(Command("settings"))
async def cmd_settings(message: Message):
    user_id = message.from_user.id
    data = get_user_data(user_id)
    settings = data["settings"]
    
    text = (
        "⚙️ **Settings**\n\n"
        f"🎨 Harmony: {HARMONY_RULES[settings['harmony']]['label']}\n"
        f"📊 Colors per palette: {settings['palette_count']}\n\n"
        "Customize your preferences:"
    )
    
    await message.reply(
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardBuilder().row(
            InlineKeyboardButton(text="🌈 Harmony Rule", callback_data="change_harmony"),
            InlineKeyboardButton(text="📊 Color Count", callback_data="change_count")
        ).row(
            InlineKeyboardButton(text="🔙 Back", callback_data="back_menu")
        ).as_markup()
    )

@dp.message(Command("help"))
async def cmd_help(message: Message):
    help_text = (
        "❓ **Help & Support**\n\n"
        "🤖 **How to use:**\n"
        "1. Generate palettes with /generate\n"
        "2. Get color info with /color\n"
        "3. Extract colors from images\n"
        "4. Save your favorite palettes\n\n"
        "📌 **Commands:**\n"
        "/start - Main menu\n"
        "/generate - Generate palette\n"
        "/color [hex] - Color info\n"
        "/extract - Extract from image\n"
        "/saved - View saved palettes\n"
        "/settings - Change preferences\n"
        "/help - This help\n"
        "/about - About the bot\n"
        "/cancel - Cancel operation"
    )
    await message.reply(help_text, parse_mode="Markdown")

@dp.message(Command("about"))
async def cmd_about(message: Message):
    about = (
        f"🎨 **{BOT_NAME}**\n\n"
        f"📦 Version: {BOT_VERSION}\n"
        f"👤 Username: @{BOT_USERNAME}\n\n"
        "A professional color palette generator\n"
        "and color tools for designers and developers.\n\n"
        "✨ **Features:**\n"
        "• 8 Color Harmony Rules\n"
        "• Color Information\n"
        "• Image Color Extraction\n"
        "• Save/Manage Palettes\n"
        "• Contrast Checking\n"
        "• Color Name Detection\n\n"
        "🔒 **Privacy:**\n"
        "No data is stored permanently.\n\n"
        "⭐ Made with ❤️ for Telegram"
    )
    await message.reply(about, parse_mode="Markdown")

@dp.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.reply(
        "✅ **Cancelled**\n\n"
        "Operation cancelled successfully.",
        parse_mode="Markdown",
        reply_markup=main_menu()
    )

@dp.message(Command("color"))
async def cmd_color(message: Message):
    args = message.text.split()
    if len(args) < 2:
        await message.reply(
            "🎯 **Color Information**\n\n"
            "Usage: `/color [hex]`\n\n"
            "Example: `/color #FF5733`\n"
            "Or: `/color FF5733`",
            parse_mode="Markdown"
        )
        return
    
    color_input = args[1]
    if not color_input.startswith('#'):
        color_input = f"#{color_input}"
    
    try:
        rgb = hex_to_rgb(color_input)
        await show_color_info(message, color_input)
    except:
        await message.reply("❌ Invalid color format. Use hex like `#FF5733`", parse_mode="Markdown")

@dp.message(Command("extract"))
async def cmd_extract(message: Message, state: FSMContext):
    await state.set_state(ColorStates.WAITING_IMAGE)
    await message.reply(
        "🖼️ **Extract Colors from Image**\n\n"
        "Send me an image, and I'll extract the dominant colors!\n\n"
        "Supported formats: JPG, PNG, WEBP\n\n"
        "Send /cancel to cancel."
    )

@dp.message(Command("saved"))
async def cmd_saved(message: Message):
    user_id = message.from_user.id
    await message.reply(
        "💾 **Saved Palettes**\n\n"
        "Your saved color palettes:",
        reply_markup=saved_palettes_keyboard(user_id)
    )

# ==================== MESSAGE HANDLERS ====================

@dp.message(ColorStates.WAITING_COLOR_NAME)
async def handle_color_name(message: Message, state: FSMContext):
    if message.text.startswith("/"):
        return
    
    user_input = message.text.strip().lower()
    
    # Try to parse color
    color_hex = None
    
    # Check if it's a hex code
    if user_input.startswith('#'):
        try:
            hex_to_rgb(user_input)
            color_hex = user_input
        except:
            pass
    
    # Check if it's a color name
    if not color_hex:
        for name, hex_val in COMMON_COLORS.items():
            if name in user_input:
                color_hex = hex_val
                break
    
    # Check if it's RGB
    if not color_hex and ',' in user_input:
        try:
            parts = user_input.split(',')
            r, g, b = int(parts[0].strip()), int(parts[1].strip()), int(parts[2].strip())
            color_hex = rgb_to_hex(r, g, b)
        except:
            pass
    
    if not color_hex:
        await message.reply(
            "❌ I don't recognize that color.\n\n"
            "Try:\n"
            "• Hex: `#FF5733`\n"
            "• Name: `blue`\n"
            "• RGB: `255, 87, 51`",
            parse_mode="Markdown"
        )
        return
    
    # Generate palette
    await generate_palette_response(message, color_hex, state)

@dp.message(ColorStates.WAITING_IMAGE)
async def handle_image(message: Message, state: FSMContext):
    if message.text and message.text.startswith("/"):
        return
    
    if not message.photo and not (message.document and message.document.mime_type.startswith("image/")):
        await message.reply("❌ Please send an image file.")
        return
    
    processing = await message.reply("🖼️ **Extracting colors from your image...**", parse_mode="Markdown")
    
    try:
        if message.photo:
            file_id = message.photo[-1].file_id
        else:
            file_id = message.document.file_id
        
        file = await bot.get_file(file_id)
        image_data = await bot.download_file(file.file_path)
        image_bytes = image_data.read() if hasattr(image_data, 'read') else image_data
        
        # Extract colors
        colors = extract_colors_from_image(image_bytes, 5)
        
        # Create palette image
        palette_img = create_palette_image(colors)
        input_file = BufferedInputFile(palette_img, filename="extracted_palette.png")
        
        # Create response
        color_list = "\n".join([f"• {color}" for color in colors])
        response = (
            f"🎨 **Colors Extracted!**\n\n"
            f"Found these dominant colors:\n\n"
            f"{color_list}\n\n"
            f"💾 Save this palette with /save\n"
            f"🔄 Generate more palettes with /generate"
        )
        
        await message.reply_photo(
            photo=input_file,
            caption=response,
            parse_mode="Markdown"
        )
        
        await processing.delete()
        
    except Exception as e:
        logger.error(f"❌ Extraction error: {str(e)}")
        await message.reply("❌ Failed to extract colors. Please try again with a different image.")
        await processing.delete()
    
    await state.clear()

# ==================== CALLBACK HANDLERS ====================

@dp.callback_query()
async def handle_callback(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    
    user_id = callback.from_user.id
    data = get_user_data(user_id)
    settings = data["settings"]
    action = callback.data
    
    # ============ NAVIGATION ============
    if action == "back_menu":
        await callback.message.edit_text(
            "🎨 **Main Menu**\n\n"
            "What would you like to do?",
            parse_mode="Markdown",
            reply_markup=main_menu()
        )
        return
    
    # ============ SUGGESTIONS ============
    elif action.startswith("suggest_"):
        color_name = action.replace("suggest_", "")
        for name, hex_val in COMMON_COLORS.items():
            if name == color_name:
                await generate_palette_response(callback.message, hex_val, state)
                return
    
    # ============ GENERATE PALETTE ============
    elif action == "generate":
        await cmd_generate(callback.message, state)
        return
    
    # ============ SETTINGS ============
    elif action == "settings":
        await cmd_settings(callback.message)
        return
    
    elif action == "change_harmony":
        await callback.message.edit_text(
            "🌈 **Select Harmony Rule**\n\n"
            "Choose how colors are generated:",
            parse_mode="Markdown",
            reply_markup=harmony_keyboard()
        )
        return
    
    elif action == "change_count":
        await callback.message.edit_text(
            "📊 **Select Color Count**\n\n"
            "How many colors per palette?",
            parse_mode="Markdown",
            reply_markup=palette_count_keyboard()
        )
        return
    
    elif action.startswith("harmony_"):
        harmony = action.replace("harmony_", "")
        if harmony in HARMONY_RULES:
            settings["harmony"] = harmony
            await callback.message.edit_text(
                f"✅ **Harmony Updated!**\n\n"
                f"New harmony: {HARMONY_RULES[harmony]['label']}",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardBuilder().row(
                    InlineKeyboardButton(text="🔙 Back", callback_data="back_settings")
                ).as_markup()
            )
        return
    
    elif action.startswith("count_"):
        count = int(action.replace("count_", ""))
        settings["palette_count"] = count
        await callback.message.edit_text(
            f"✅ **Color Count Updated!**\n\n"
            f"New count: {count} colors per palette",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardBuilder().row(
                InlineKeyboardButton(text="🔙 Back", callback_data="back_settings")
            ).as_markup()
        )
        return
    
    elif action == "back_settings":
        await cmd_settings(callback.message)
        return
    
    # ============ COLOR INFO ============
    elif action == "color_info":
        await callback.message.edit_text(
            "🎯 **Color Information**\n\n"
            "Send me a color in any format:\n"
            "• Hex: `#FF5733`\n"
            "• Name: `blue`\n"
            "• RGB: `255, 87, 51`\n\n"
            "Or tap a color below:",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardBuilder().row(
                InlineKeyboardButton(text="🔴 Red", callback_data="info_red"),
                InlineKeyboardButton(text="🔵 Blue", callback_data="info_blue"),
                InlineKeyboardButton(text="🟢 Green", callback_data="info_green")
            ).row(
                InlineKeyboardButton(text="🟡 Yellow", callback_data="info_yellow"),
                InlineKeyboardButton(text="🟣 Purple", callback_data="info_purple"),
                InlineKeyboardButton(text="🟠 Orange", callback_data="info_orange")
            ).row(
                InlineKeyboardButton(text="🔙 Back", callback_data="back_menu")
            ).as_markup()
        )
        return
    
    elif action.startswith("info_"):
        color_name = action.replace("info_", "")
        for name, hex_val in COMMON_COLORS.items():
            if name == color_name:
                await show_color_info(callback.message, hex_val)
                return
    
    # ============ EXTRACT FROM IMAGE ============
    elif action == "extract":
        await cmd_extract(callback.message, state)
        return
    
    # ============ SAVED PALETTES ============
    elif action == "saved":
        await callback.message.edit_text(
            "💾 **Saved Palettes**\n\n"
            "Your saved color palettes:",
            reply_markup=saved_palettes_keyboard(user_id)
        )
        return
    
    elif action.startswith("load_"):
        idx = int(action.replace("load_", ""))
        palettes = data.get("palettes", [])
        if idx < len(palettes):
            palette = palettes[idx]
            colors = palette.get("colors", [])
            name = palette.get("name", f"Palette {idx+1}")
            
            palette_img = create_palette_image(colors)
            input_file = BufferedInputFile(palette_img, filename="palette.png")
            
            await callback.message.reply_photo(
                photo=input_file,
                caption=f"💾 **{name}**\n\n" + "\n".join([f"• {c}" for c in colors])
            )
        return
    
    # ============ SAVE PALETTE ============
    elif action == "save_palette":
        await callback.message.edit_text(
            "💾 **Save Palette**\n\n"
            "Send a name for this palette.\n"
            "Example: `Sunset Vibes`\n\n"
            "Send /cancel to cancel."
        )
        await state.set_state(ColorStates.WAITING_PALETTE_NAME)
        return
    
    # ============ HELP ============
    elif action == "help":
        await cmd_help(callback.message)
        return
    
    # ============ REGENERATE ============
    elif action == "regenerate":
        # Get last generated palette
        history = data.get("history", [])
        if history:
            last = history[-1]
            if "palette" in last:
                await generate_palette_response(callback.message, last["palette"], state)
        return

# ==================== HELPER FUNCTIONS ====================

async def generate_palette_response(message: Message, base_color: str, state: FSMContext):
    """Generate and send palette response"""
    user_id = message.from_user.id
    data = get_user_data(user_id)
    settings = data["settings"]
    
    processing = await message.reply("🎨 **Generating your palette...**", parse_mode="Markdown")
    
    try:
        harmony = settings["harmony"]
        count = settings["palette_count"]
        
        colors = generate_palette(base_color, harmony, count)
        
        # Create palette image
        palette_img = create_palette_image(colors)
        input_file = BufferedInputFile(palette_img, filename="palette.png")
        
        # Create response text
        color_list = "\n".join([f"• {color}" for color in colors])
        harmony_label = HARMONY_RULES[harmony]["label"]
        
        response = (
            f"🎨 **Your Color Palette**\n\n"
            f"🌈 Harmony: {harmony_label}\n"
            f"📊 Colors: {len(colors)}\n"
            f"🎯 Base: {base_color}\n\n"
            f"**Colors:**\n{color_list}\n\n"
            f"💾 Save with /save\n"
            f"🔄 Generate another with /generate"
        )
        
        # Store in history
        data["history"].append({
            "palette": base_color,
            "colors": colors,
            "harmony": harmony,
            "timestamp": datetime.now().isoformat()
        })
        
        # Store palette data for saving
        data["last_palette"] = colors
        
        await message.reply_photo(
            photo=input_file,
            caption=response,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardBuilder().row(
                InlineKeyboardButton(text="💾 Save Palette", callback_data="save_palette"),
                InlineKeyboardButton(text="🔄 Regenerate", callback_data="regenerate")
            ).row(
                InlineKeyboardButton(text="🏠 Menu", callback_data="back_menu")
            ).as_markup()
        )
        
        await processing.delete()
        
    except Exception as e:
        logger.error(f"❌ Palette generation error: {str(e)}")
        await message.reply("❌ Failed to generate palette. Please try again.")
        await processing.delete()
    
    await state.clear()

async def show_color_info(message: Message, hex_color: str):
    """Show detailed color information"""
    try:
        rgb = hex_to_rgb(hex_color)
        h, s, l = rgb_to_hsl(rgb[0], rgb[1], rgb[2])
        color_name = hex_to_color_name(hex_color)
        contrast_white = get_contrast_ratio(hex_color, "#FFFFFF")
        contrast_black = get_contrast_ratio(hex_color, "#000000")
        
        # Create image
        img_data = create_color_info_image(hex_color)
        input_file = BufferedInputFile(img_data, filename="color_info.png")
        
        response = (
            f"🎯 **Color Information**\n\n"
            f"📛 Name: {color_name}\n"
            f"🔢 Hex: {hex_color.upper()}\n"
            f"🔴 RGB: {rgb[0]}, {rgb[1]}, {rgb[2]}\n"
            f"🌈 HSL: {h}°, {s}%, {l}%\n"
            f"⚡ Contrast White: {contrast_white:.2f}:1\n"
            f"⚡ Contrast Black: {contrast_black:.2f}:1\n"
            f"📱 Text: {suggest_text_color(hex_color)}\n\n"
            f"💡 Create a palette with /generate"
        )
        
        await message.reply_photo(
            photo=input_file,
            caption=response,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardBuilder().row(
                InlineKeyboardButton(text="🎨 Generate Palette", callback_data="generate"),
                InlineKeyboardButton(text="🔙 Back", callback_data="back_menu")
            ).as_markup()
        )
        
    except Exception as e:
        logger.error(f"❌ Color info error: {str(e)}")
        await message.reply("❌ Failed to get color information.")

@dp.message(ColorStates.WAITING_PALETTE_NAME)
async def handle_palette_name(message: Message, state: FSMContext):
    if message.text.startswith("/"):
        return
    
    user_id = message.from_user.id
    data = get_user_data(user_id)
    
    name = message.text.strip()
    colors = data.get("last_palette", [])
    
    if not colors:
        await message.reply("❌ No palette to save. Generate a palette first!")
        await state.clear()
        return
    
    # Save palette
    palette = {
        "name": name,
        "colors": colors,
        "created": datetime.now().isoformat()
    }
    
    if "palettes" not in data:
        data["palettes"] = []
    
    data["palettes"].append(palette)
    
    await message.reply(
        f"✅ **Palette Saved!**\n\n"
        f"📛 Name: {name}\n"
        f"🎨 Colors: {len(colors)}\n\n"
        f"View all saved palettes with /saved",
        parse_mode="Markdown"
    )
    
    await state.clear()

# ==================== MESSAGE HANDLERS ====================

@dp.message()
async def handle_other(message: Message):
    if message.text and message.text.startswith("/"):
        return
    
    # Try to parse as color
    user_input = message.text.strip().lower() if message.text else ""
    
    if user_input:
        try:
            # Try hex
            if user_input.startswith('#'):
                hex_to_rgb(user_input)
                await show_color_info(message, user_input)
                return
            
            # Try color name
            for name, hex_val in COMMON_COLORS.items():
                if name in user_input:
                    await show_color_info(message, hex_val)
                    return
            
            # Try RGB
            if ',' in user_input:
                parts = user_input.split(',')
                r, g, b = int(parts[0].strip()), int(parts[1].strip()), int(parts[2].strip())
                hex_color = rgb_to_hex(r, g, b)
                await show_color_info(message, hex_color)
                return
        except:
            pass
    
    await message.reply(
        "❓ I don't understand that.\n\n"
        "Try:\n"
        "• /start for the main menu\n"
        "• /generate to create a palette\n"
        "• A color name like 'blue'\n"
        "• A hex code like '#FF5733'",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardBuilder().row(
            InlineKeyboardButton(text="🏠 Menu", callback_data="back_menu")
        ).as_markup()
    )

# ==================== ERROR HANDLER ====================

@dp.errors()
async def error_handler(update, exception):
    logger.error(f"❌ Error: {str(exception)}")
    if hasattr(update, 'message') and update.message:
        try:
            await update.message.reply(
                "❌ **Error**\n\n"
                "Something went wrong. Please try again.",
                parse_mode="Markdown"
            )
        except:
            pass

# ==================== MAIN ====================

async def main():
    try:
        logger.info("=" * 60)
        logger.info(f"🎨 {BOT_NAME} v{BOT_VERSION}")
        logger.info(f"🤖 Username: @{BOT_USERNAME}")
        logger.info("=" * 60)
        
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
        
    except Exception as e:
        logger.error(f"❌ Fatal: {str(e)}")
        raise
    finally:
        await bot.session.close()

if __name__ == "__main__":
    import asyncio
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("🛑 Bot stopped")
    except Exception as e:
        logger.error(f"💥 Fatal: {str(e)}")
