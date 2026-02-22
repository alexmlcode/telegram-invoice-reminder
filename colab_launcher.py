        _tg_listener.start(
            session_path=_tg_session,
            api_id=_tg_api_id,
            api_hash=_tg_api_hash,
            owner_tg_id=_tg_owner_id,
        )

        # ----------------------------
        # 6.2.1) tg_drain loop
        # ----------------------------
        def _tg_drain_loop():
            import time
            import logging as _log
            from supervisor.events import dispatch_event
            while True:
                try:
                    evt = _tg_listener.get_queue().get_nowait()
                    dispatch_event(evt, ctx=None)
                except Exception:
                    pass
                time.sleep(0.1)  # 100ms poll interval

        _tg_drain_thread = threading.Thread(
            target=_tg_drain_loop,
            daemon=True,
            name="tg-drain"
        )
        _tg_drain_thread.start()

        _log.getLogger(__name__).info("tg_listener and tg_drain started")
    except Exception as _e:
        import logging as _log
        _log.getLogger(__name__).warning("Failed to start tg_listener: %s", _e)