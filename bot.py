import os
import json
import requests
import re
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import tempfile
from urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter
from typing import Optional, Dict, Any
import asyncio
from datetime import datetime


load_dotenv()
BOT_TOKEN = os.getenv('BOT_TOKEN')


session = requests.Session()
retries = Retry(
    total=3,
    backoff_factor=0.1,
    status_forcelist=[500, 502, 503, 504],
    allowed_methods=["GET"]
)
session.mount('https://', HTTPAdapter(max_retries=retries))


API_URL = "https://card.wb.ru/cards/v1/detail"
DEFAULT_HEADERS = {
    'Accept': 'application/json',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36'
}
IMAGE_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
    'Accept': 'image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8',
    'Referer': 'https://www.wildberries.ru/'
}

def get_api_params(product_id: str) -> Dict[str, Any]:
    """Generate parameters for API request."""
    return {
        "appType": "1",
        "curr": "rub",
        "dest": "-1257786",
        "regions": "80,38,83,4,64,33,68,70,30,40,86,75,69,1,31,66,110,48,22,71,114",
        "spp": "0",
        "nm": product_id
    }

def format_price(price_kopecks: int) -> float:
    """Convert price from kopecks to rubles."""
    return price_kopecks / 100

def generate_image_urls(article: str) -> list[str]:
    """Generate possible image URLs for the product."""
    vol = str(article)[:4]
    part = str(article)[:6]
    return [
        f"https://basket-{str(num).zfill(2)}.wbbasket.ru/vol{vol}/part{part}/{article}/images/big/1.webp"
        for num in range(1, 17)
    ]

async def fetch_product_image(image_urls: list[str]) -> Optional[bytes]:
    """Try to fetch product image from multiple URLs."""
    for image_url in image_urls:
        try:
            print(f"Trying to download image from: {image_url}")
            img_response = session.get(image_url, headers=IMAGE_HEADERS, timeout=15)
            if img_response.status_code == 200 and len(img_response.content) > 1000:
                return img_response.content
            print(f"Failed to download image, status code: {img_response.status_code}, content length: {len(img_response.content)}")
        except Exception as e:
            print(f"Failed to download image from {image_url}: {str(e)}")
    return None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command."""
    await update.message.reply_text(
        "Привет! 👋\nОтправь мне ссылку на товар с Wildberries, "
        "и я покажу тебе фото товара, артикул и цену."
    )

async def parse_wildberries(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle product URL and return product information."""
    url = update.message.text.split('?')[0]
    
    if not re.search(r'wildberries\.ru/catalog/\d+/detail', url):
        await update.message.reply_text("Пожалуйста, отправьте корректную ссылку на товар Wildberries.")
        return

    try:
        await update.message.chat.send_action('typing')
        

        product_id_match = re.search(r'/catalog/(\d+)/detail', url)
        if not product_id_match:
            await update.message.reply_text("Не удалось найти ID товара в ссылке. Убедитесь, что ссылка правильная.")
            return
            
        product_id = product_id_match.group(1)
        

        response = session.get(
            API_URL,
            params=get_api_params(product_id),
            headers=DEFAULT_HEADERS,
            timeout=10
        )
        data = response.json()
        
        if not data.get('data', {}).get('products'):
            await update.message.reply_text("Не удалось найти информацию о товаре. Возможно, товар больше не доступен.")
            return
        

        product = data['data']['products'][0]
        article = str(product.get('id', 'Нет артикула'))
        price = format_price(product.get('salePriceU', product.get('priceU', 0)))
        brand = product.get('brand', '')
        name = product.get('name', '')
        
        message = f"🏷 {brand} - {name}\n📦 Артикул: {article}\n💰 Цена: {price:,.2f} ₽"


        image_content = await fetch_product_image(generate_image_urls(article))
        
        if image_content:
            await update.message.reply_photo(
                photo=image_content,
                caption=message
            )
        else:
            await update.message.reply_text(message + "\n⚠️ Не удалось загрузить изображение товара.")
    
    except Exception as e:
        print(f"Error [{datetime.now()}]: {str(e)}")
        await update.message.reply_text("Произошла ошибка при получении информации о товаре. Попробуйте снова.")

def main():
    """Initialize and start the bot."""
    application = Application.builder().token(BOT_TOKEN).build()
    

    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, parse_wildberries))
    

    print("Bot started...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
