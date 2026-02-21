import asyncio
import os
import json
from telethon import TelegramClient
from collections import defaultdict
import re

# Configuration
SESSION_PATH = '/home/a/ouroboros_repo/session.session'
API_ID = 24553863
API_HASH = '9364ce0067c945a18425912fb9ab92bb'
GROUP_USERNAME = 'it_laboratory_bar'

def calculate_gayness_score(message_text):
    """
    Calculate a 'gayness' score for a message based on:
    - Self-identification ("я гей", "я лесбиянка", etc.)
    - LGBTQ+ keywords (прин, сиськи, кабардинка, etc.)
    - Emojis (🌈, 💋, 🏳️‍🌈, 💖, etc.)
    - Context (dating, relationships, pride events)
    - Selfies (implied by high activity)
    
    Returns a score from 0 to 100.
    """
    if not message_text:
        return 0
    
    text = message_text.lower()
    score = 0
    
    # Direct self-identification (+50)
    if any(word in text for word in ['я гей', 'я лесбиянка', 'я бисексуал', 'я транс', 'я кьют', 'я квіт', 'я queer']):
        score += 50
    
    # LGBTQ+ keywords (+20 each)
    lgbt_keywords = [
        'прин', 'сиськи', 'кабардинка', 'кабардинец', 'кабардинки',
        'гей-парад', 'прайд', 'лесбиянки', 'бисексуал', 'транс', 'квіт',
        'queer', 'gay', 'lesbian', 'bisexual', 'trans', 'pride',
        'розмова про секс', 'сексуальність', 'інта', 'інтимність',
        ' Dating', ' relationships', 'love', 'dating', 'Partner',
        'boyfriend', 'girlfriend', 'partner', 'husband', 'wife',
    ]
    for keyword in lgbt_keywords:
        if keyword.lower() in text:
            score += 20
    
    # Emojis (+10 each)
    emoji_scores = [
        ('🌈', 10), ('🏳️‍🌈', 10), ('💖', 5), ('💋', 5), ('🌸', 3),
        ('🦋', 3), ('🦄', 3), ('✨', 2), ('🌸', 2), ('🌷', 2),
    ]
    for emoji, pts in emoji_scores:
        if emoji in message_text:
            score += pts
    
    # Contextual indicators (+15)
    context_indicators = [
        'мой парень', 'моя девушка', 'мои друзья', 'на свидании',
        'люблю его', 'люблю её', 'люблю их', 'мы вместе',
        'дата', 'свидание', 'интим', 'сексуальный', 'сексуальность',
    ]
    for indicator in context_indicators:
        if indicator in text:
            score += 15
    
    # Selfies/self-promotion (+10)
    if any(word in text for word in ['самка', 'самец', 'я красава', 'я красавчик', 'я красавица']):
        score += 10
    
    # Cap at 100
    return min(score, 100)


async def main():
    print("Connecting to Telegram...")
    client = TelegramClient(SESSION_PATH, API_ID, API_HASH)
    await client.start()
    print("✅ Connected as", (await client.get_me()).username)
    
    # Get the group entity
    print(f"\nFetching group: {GROUP_USERNAME}")
    try:
        group = await client.get_entity(GROUP_USERNAME)
        print(f"✅ Found group: {group.title}")
    except Exception as e:
        print(f"❌ Error getting group: {e}")
        return
    
    # Read messages
    print(f"\nReading messages from {GROUP_USERNAME}...")
    messages = []
    async for msg in client.iter_messages(group, limit=500):
        if msg.sender_id:
            sender = await client.get_entity(msg.sender_id)
            sender_name = sender.username or f"{sender.first_name or ''} {sender.last_name or ''}".strip() or str(sender.id)
        else:
            sender_name = "[deleted]"
        
        score = calculate_gayness_score(msg.text or '')
        
        messages.append({
            'id': msg.id,
            'sender': sender_name,
            'sender_id': msg.sender_id,
            'text': msg.text or '',
            'score': score,
            'date': msg.date.isoformat() if msg.date else ''
        })
    
    print(f"✅ Read {len(messages)} messages")
    
    # Aggregate scores by user
    user_scores = defaultdict(lambda: {'total': 0, 'count': 0, 'messages': []})
    for msg in messages:
        sender = msg['sender']
        user_scores[sender]['total'] += msg['score']
        user_scores[sender]['count'] += 1
        user_scores[sender]['messages'].append(msg)
    
    # Calculate average scores and percentages
    user_stats = []
    for sender, data in user_scores.items():
        if data['count'] > 0:
            avg_score = data['total'] / data['count']
            user_stats.append({
                'sender': sender,
                'sender_id': data['messages'][0]['sender_id'],
                'message_count': data['count'],
                'avg_score': round(avg_score, 1),
                'total_score': data['total'],
                'gayness_pct': round(avg_score, 1)
            })
    
    # Sort by gayness percentage
    user_stats.sort(key=lambda x: x['gayness_pct'], reverse=True)
    
    # Take top 10
    top_10 = user_stats[:10]
    
    # Generate report
    report_lines = [
        f"📊 **Топ 10 по 'геискости' в '{group.title}'**",
        f"Анализ: {len(messages)} сообщений от {len(user_stats)} участников",
        ""
    ]
    
    for i, user in enumerate(top_10, 1):
        report_lines.append(f"{i}. @{user['sender']} — {user['gayness_pct']}% ({user['message_count']} сообщений)")
    
    report_lines.append("")
    report_lines.append("*Анализ основан на keywords, эмодзи и контексте обсуждений.*")
    
    report = "\n".join(report_lines)
    
    # Send report to group
    print(f"\nSending report to {GROUP_USERNAME}...")
    await client.send_message(GROUP_USERNAME, report)
    print("✅ Report sent!")
    
    # Save detailed analysis to file
    with open('tg_analysis_results.json', 'w', encoding='utf-8') as f:
        json.dump({
            'group': group.title,
            'total_messages': len(messages),
            'total_users': len(user_stats),
            'top_10': top_10,
            'all_users': user_stats
        }, f, ensure_ascii=False, indent=2)
    print("\n✅ Detailed results saved to tg_analysis_results.json")
    
    await client.disconnect()
    print("\n✅ Done!")


if __name__ == '__main__':
    asyncio.run(main())
