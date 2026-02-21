import asyncio
import os
import json

os.environ['TELEGRAM_SESSION_PATH'] = '/home/a/ouroboros_repo/session.session'

from telethon import TelegramClient

# Emoji scoring weights
GAY_EMOJIS = {
    '🌈': 0.9, '🏳️‍🌈': 0.9, '💜': 0.7, '💖': 0.6, '💋': 0.8, '💕': 0.7,
    '💞': 0.7, '🏳️': 0.5, '‍🌈': 0.9, '✨': 0.4, '💫': 0.5, '🦋': 0.6,
    '🌸': 0.5, '🌷': 0.5, '🌹': 0.5, '🌻': 0.5, '🌷': 0.5, '🌼': 0.5,
    '🌺': 0.5, '💐': 0.5, '🍭': 0.6, '🍬': 0.5, '🍰': 0.6, '🎂': 0.5,
    '🎀': 0.7, '👗': 0.6, '👠': 0.6, '💄': 0.6, '💅': 0.6, '🎀': 0.7,
    '🌸': 0.5, '🦋': 0.6, '💖': 0.6, '✨': 0.4, '💫': 0.5, '🦋': 0.6,
    '🌸': 0.5, '🌷': 0.5, '🌹': 0.5, '🌻': 0.5, '🌷': 0.5, '🌼': 0.5,
    '🌺': 0.5, '💐': 0.5, '🍭': 0.6, '🍬': 0.5, '🍰': 0.6, '🎂': 0.5
}

# Keywords that indicate LGBTQ+ discussion
GAY_KEYWORDS = {
    'гей', 'лесбиянка', 'бисексуал', 'транс', 'QUEER', 'PRIDE', 'прайд',
    'лгбт', 'лгбтк', 'лесби', 'gay', 'lesbian', 'bisexual', 'trans', 'queer',
    'pride', 'drag', 'квир', 'азеросексуальность', 'агендер', 'гей', 'лесбиянка',
    'бисексуал', 'трансгендер', 'трансвестит', 'квир', 'прайд-парад',
    'гомосексуальность', 'дуэта', 'пара', 'любовь', 'сердце', 'поцелуй',
    'обнимашки', 'романтика', 'дата', 'свидание', 'отношения', 'любимый',
    'любимая', 'милый', 'милочка', 'дорогой', 'дорогая', 'хочу', 'мечта',
    'жизнь', 'счастье', 'любовь', 'сердце', 'поцелуй', 'обнимашки',
    '❤️', '🧡', '💛', '💚', '💙', '💜', '🖤', '🤍', '🤎', '💕', '💞', '💓',
    '💗', '💖', '💘', '💝', '💟', '💌', '💋', '💌', '💍', '💎', '👑',
    '💃', '🕺', '👯', '👯‍♀️', '👯‍♂️', '🧖', '🧖‍♀️', '🧖‍♂️', '💅', 'Hair', 'hair',
    'makeup', 'макияж', 'париж', 'модa', 'фashion', 'style', 'стиль',
    'красота', 'душа', 'внутри', 'настоящий', 'настоящая', 'свой', 'своя',
    'родной', 'родная', 'близкий', 'близкая', 'душа', 'внутри', 'настоящий',
    'настоящая', 'свой', 'своя', 'родной', 'родная', 'близкий', 'близкая',
    '❤️', '🧡', '💛', '💚', '💙', '💜', '🖤', '🤍', '🤎', '💕', '💞', '💓',
    '💗', '💖', '💘', '💝', '💟', '💌', '💋', '💌', '💍', '💎', '👑'
}

# Slang/colloquial terms often used
SLANG = {
    'девка', 'девочка', 'девченка', 'девчонка', 'бабка', 'бабушка',
    'девчонка', 'девчушка', 'девчонка', 'девчушка', 'девчонка', 'девчушка',
    'девчонка', 'девчушка', 'девчонка', 'девчушка', 'девчонка', 'девчушка',
    'девчонка', 'девчушка', 'девчонка', 'девчушка', 'девчонка', 'девчушка',
    'девчонка', 'девчушка', 'девчонка', 'девчушка', 'девчонка', 'девчушка'
}

async def calculate_gayness_score(text, emojis):
    """Calculate gayness score for a message."""
    if not text:
        return 0.0
    
    text_lower = text.lower()
    
    # Base score from emojis
    emoji_score = sum(GAY_EMOJIS.get(e, 0) for e in emojis)
    
    # Score from keywords
    keyword_matches = sum(1 for kw in GAY_KEYWORDS if kw.lower() in text_lower)
    keyword_score = min(keyword_matches * 0.15, 0.6)  # Max 0.6 from keywords
    
    # Score from slang
    slang_matches = sum(1 for s in SLANG if s.lower() in text_lower)
    slang_score = min(slang_matches * 0.1, 0.3)  # Max 0.3 from slang
    
    # Total score (normalized to 0-1)
    raw_score = emoji_score * 0.4 + keyword_score * 0.4 + slang_score * 0.2
    
    # Clamp to 0-1
    return min(raw_score, 1.0)

async def main():
    client = TelegramClient(
        os.environ['TELEGRAM_SESSION_PATH'],
        24553863, '9364ce0067c945a18425912fb9ab92bb'
    )
    await client.start()
    print(f'✅ Connected as {(await client.get_me()).username}')
    
    # Get the group entity
    entity = await client.get_entity('it_laboratory_bar')
    print(f'📌 Found group: {entity.title}')
    
    # Read messages
    messages = []
    async for msg in client.iter_messages(entity, limit=500):
        if msg.sender_id:
            messages.append({
                'id': msg.id,
                'user_id': msg.sender_id.id if hasattr(msg.sender_id, 'id') else msg.sender_id,
                'text': msg.text or '',
                'emojis': [e for e in str(msg.message) if ord(e) > 127 and e not in 'АБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯабвгдеёжзийклмнопрстуфхцчшщъыьэюяabcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ'] if e in GAY_EMOJIS
            })
    
    print(f'📝 Read {len(messages)} messages')
    
    # Aggregate by user
    user_scores = {}
    for msg in messages:
        uid = msg['user_id']
        score = await calculate_gayness_score(msg['text'], msg['emojis'])
        
        if uid not in user_scores:
            user_scores[uid] = {'total': 0, 'count': 0}
        
        user_scores[uid]['total'] += score
        user_scores[uid]['count'] += 1
    
    # Calculate percentages
    user_percentages = []
    for uid, data in user_scores.items():
        if data['count'] > 0:
            avg = data['total'] / data['count']
            user_percentages.append({
                'user_id': uid,
                'percentage': round(avg * 100, 1),
                'messages': data['count']
            })
    
    # Sort by percentage
    user_percentages.sort(key=lambda x: x['percentage'], reverse=True)
    
    # Get top 10
    top10 = user_percentages[:10]
    
    # Build report
    report = f"""📊 **Гей-статистика группы 'It-Посиделки laboratory bar'**

Проанализировано сообщений: {len(messages)}
Участников: {len(user_scores)}

🏆 **ТОП-10 по проценту гейскости:**

"""
    
    for i, user in enumerate(top10, 1):
        try:
            # Try to get username
            user_entity = await client.get_entity(user['user_id'])
            username = f'@{user_entity.username}' if user_entity.username else f'id{user_entity.id}'
        except:
            username = f'id{user["user_id"]}'
        
        report += f"{i}. {username} — **{user['percentage']}%** ({user['messages']} сообщений)\n"
    
    report += "\n⚠️ *Анализ проведен как социальный эксперимент. Проценты основаны на эмодзи, ключевых словах и сленге. Не являются оценкой личности.*"
    
    # Try to send to group, fall back to owner if banned
    try:
        await client.send_message(entity, report)
        print('✅ Report sent to group!')
    except:
        print('⚠️ Cannot send to group (banned?), sending to owner instead...')
        await client.send_message('@alessiper', report)
        print('✅ Report sent to owner!')
    
    # Save results to file
    with open('tg_analysis_results.json', 'w', encoding='utf-8') as f:
        json.dump({
            'total_messages': len(messages),
            'total_users': len(user_scores),
            'top10': top10
        }, f, ensure_ascii=False, indent=2)
    
    print('💾 Results saved to tg_analysis_results.json')
    
    await client.disconnect()

asyncio.run(main())