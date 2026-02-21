#!/usr/bin/env python3
"""Analyze 'It-Посиделки laboratory bar' group for gayness stats."""
import asyncio
import json
import os

from telethon import TelegramClient

# Configuration
SESSION_PATH = '/home/a/ouroboros_repo/session.session'
API_ID = 24553863
API_HASH = '9364ce0067c945a18425912fb9ab92bb'
GROUP_USERNAME = '@it_laboratory_bar'
OWNER_USERNAME = '@alessiper'  # Send report to myself

# Scoring rules
def score_message(text, username):
    """Score a message on how 'gay' it is (0-100)."""
    if not text:
        return 0
    
    text_lower = text.lower()
    score = 0
    
    # Self-identification
    if 'я гей' in text_lower or 'я лесбиянка' in text_lower or 'я бисексуал' in text_lower:
        score += 30
    if 'я трансгендер' in text_lower or 'я квинт' in text_lower:
        score += 25
    
    # LGBTQ+ terms
    gay_terms = ['геи', 'лесбиянки', 'бисексуалы', 'транс', 'квинт', 'прайд', 'queer', 'lgbt', 'lgbtq']
    for term in gay_terms:
        if term in text_lower:
            score += 15
    
    # Emojis
    if '🏳️‍🌈' in text or '🌈' in text:
        score += 20
    if '💋' in text:
        score += 10
    if '❤️' in text:
        score += 5
    
    # Relationship context
    relationship_terms = ['парень', 'девушка', 'бойфренд', 'гёрлфренд', 'отношения', 'свидание', 'любовь', 'встречаемся']
    for term in relationship_terms:
        if term in text_lower:
            score += 10
    
    # Prank/ironic (lower score)
    if 'шутка' in text_lower or 'тест' in text_lower:
        score = max(0, score - 20)
    
    return min(100, max(0, score))


async def main():
    print('Connecting to Telegram...')
    client = TelegramClient(SESSION_PATH, API_ID, API_HASH)
    await client.start()
    print(f'✅ Connected as {(await client.get_me()).username}')
    
    # Get the group entity
    print(f'\nFetching group: {GROUP_USERNAME}')
    try:
        entity = await client.get_entity(GROUP_USERNAME)
        print(f'✅ Found group: {entity.title}')
    except Exception as e:
        print(f'❌ Error fetching group: {e}')
        await client.disconnect()
        return
    
    # Read messages
    print(f'\nReading messages from {GROUP_USERNAME}...')
    messages = []
    async for msg in client.iter_messages(entity, limit=500):
        if msg.sender_id:
            messages.append({
                'id': msg.id,
                'text': msg.text or '',
                'user_id': msg.sender_id,
                'username': msg.sender.username if msg.sender else None,
                'date': msg.date
            })
    print(f'✅ Read {len(messages)} messages')
    
    # Score users
    user_scores = {}
    user_messages = {}
    for msg in messages:
        user_id = msg['user_id']
        username = msg['username'] or f'unknown_{user_id}'
        text = msg['text']
        
        if user_id not in user_scores:
            user_scores[user_id] = {'score': 0, 'count': 0, 'username': username}
        
        score = score_message(text, username)
        user_scores[user_id]['score'] += score
        user_scores[user_id]['count'] += 1
    
    # Calculate percentages
    for user_id, data in user_scores.items():
        data['percentage'] = round(data['score'] / data['count'], 1) if data['count'] > 0 else 0
    
    # Sort and get top 10
    sorted_users = sorted(user_scores.values(), key=lambda x: x['percentage'], reverse=True)[:10]
    
    # Build report
    report = f"📊 **Гей-статистика группы '{entity.title}'**\n\n"
    report += f"Проанализировано сообщений: {len(messages)}\n"
    report += f"Участников: {len(user_scores)}\n\n"
    
    report += "🏆 **ТОП-10 по проценту гейскости:**\n\n"
    for i, user in enumerate(sorted_users, 1):
        report += f"{i}. @{user['username']} — **{user['percentage']}%**\n"
    
    report += f"\n⚠️ *Анализ проведен как социальный эксперимент. Проценты основаны на контексте сообщений.*"
    
    # Try to send to group first
    try:
        await client.send_message(GROUP_USERNAME, report)
        print('✅ Report sent to group!')
    except Exception as e:
        print(f'⚠️ Cannot send to group: {e}')
        print('Sending report to owner instead...')
        try:
            await client.send_message(OWNER_USERNAME, report)
            print('✅ Report sent to owner!')
        except Exception as e2:
            print(f'❌ Failed to send to owner: {e2}')
            # Save to file
            with open('tg_analysis_results.json', 'w', encoding='utf-8') as f:
                json.dump({
                    'report': report,
                    'messages_analyzed': len(messages),
                    'users_analyzed': len(user_scores),
                    'top_10': sorted_users
                }, f, ensure_ascii=False, indent=2)
            print('💾 Report saved to tg_analysis_results.json')
    
    await client.disconnect()


if __name__ == '__main__':
    asyncio.run(main())
