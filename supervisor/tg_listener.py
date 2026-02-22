async def _listener_loop(session_path: str, api_id: int, api_hash: str,
                          owner_tg_id: Optional[int]) -> None:
    try:
        from telethon import TelegramClient, events
    except ImportError:
        log.warning("telethon not installed — user-mode listener disabled")
        _stop_event.set()
        return

    global _consecutive_failures
    _consecutive_failures = 0

    client = TelegramClient(session_path, api_id, api_hash)
    try:
        await client.connect()

        if not await client.is_user_authorized():
            log.warning(
                "tg_listener: session not authorized — will retry in %ds", _AUTH_RETRY_SEC
            )
            await client.disconnect()
            await asyncio.sleep(_AUTH_RETRY_SEC)
            return

        me = await client.get_me()
        my_id = me.id
        my_username: Optional[str] = getattr(me, "username", None)
        log.info("tg_listener: ready as @%s (id=%s)", my_username or my_id, my_id)

        @client.on(events.NewMessage(incoming=True))
        async def _on_message(event):
            msg = event.message
            if not msg or not ((msg.text or "").strip() or msg.document):
                return

            sender = await event.get_sender()
            if sender is None:
                return
            sender_id = sender.id

            if sender_id == my_id:
                return

            first = getattr(sender, "first_name", "") or ""
            last  = getattr(sender, "last_name",  "") or ""
            name  = (first + " " + last).strip() or f"user_{sender_id}"
            uname = getattr(sender, "username", "") or ""

            reply_to_msg_id: Optional[int] = None
            if getattr(msg, "reply_to", None):
                reply_to_msg_id = getattr(msg.reply_to, "reply_to_msg_id", None)

            # Extract text, prioritizing documents for private messages
            text_content = msg.text or ""
            if event.is_private and msg.document:
                doc = msg.document
                doc_id = getattr(doc, "id", "")
                doc_mime = getattr(doc, "mime_type", "unknown")
                text_content = f"[Document received: id={doc_id}, mime={doc_mime}] " + text_content

            if event.is_private:
                if owner_tg_id and sender_id == owner_tg_id:
                    return
                log.info("tg_listener: DM from %s (@%s): %.80s", name, uname, text_content)
                _listener_queue.put({
                    "type":            "tg_user_message",
                    "chat_type":       "private",
                    "chat_id":         sender_id,
                    "chat_title":      name,
                    "msg_id":          msg.id,
                    "reply_to_msg_id": reply_to_msg_id,
                    "sender_id":       sender_id,
                    "sender_name":     name,
                    "sender_username": uname,
                    "text":            text_content,
                })

            elif event.is_group or event.is_channel:
                mentioned = await _is_mentioned(event, my_id, my_username)
                if not mentioned:
                    return
                try:
                    chat = await event.get_chat()
                    chat_title = getattr(chat, "title", "") or str(event.chat_id)
                except Exception:
                    chat_title = str(event.chat_id)

                log.info("tg_listener: GROUP_MENTION in '%s' from %s (@%s): %.80s",
                         chat_title, name, uname, text_content)
                _listener_queue.put({
                    "type":            "tg_group_mention",
                    "chat_type":       "group" if event.is_group else "channel",
                    "chat_id":         event.chat_id,
                    "chat_title":      chat_title,
                    "msg_id":          msg.id,
                    "reply_to_msg_id": reply_to_msg_id,
                    "sender_id":       sender_id,
                    "sender_name":     name,
                    "sender_username": uname,
                    "text":            text_content,
                })

    except Exception as exc:
        log.error("tg_listener: fatal error: %s", exc)
        _stop_event.set()