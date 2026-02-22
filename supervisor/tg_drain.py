"""Telegram user message drain loop."""
import threading
import time
import logging

log = logging.getLogger(__name__)

# Will be set by colab_launcher.py
_listener_queue = None
_dispatch_event = None


def _tg_drain_loop() -> None:
    """Poll _listener_queue every 100ms and dispatch tg_user_message events."""
    global _listener_queue, _dispatch_event
    if _listener_queue is None or _dispatch_event is None:
        log.error("tg_drain: _listener_queue or dispatch_event not initialized")
        return
    while True:
        try:
            evt = _listener_queue.get_nowait()
            _dispatch_event(evt, {"ctx": "tg_drain"})
        except Exception:
            time.sleep(0.1)  # 100ms poll interval


def start(queue, dispatch_fn):
    """Start the drain loop as a daemon thread."""
    global _listener_queue, _dispatch_event
    _listener_queue = queue
    _dispatch_event = dispatch_fn
    thread = threading.Thread(target=_tg_drain_loop, daemon=True, name="tg-drain")
    thread.start()
    log.info("tg_drain: started, polling _listener_queue every 100ms")
    return thread
