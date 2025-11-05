from django.apps import AppConfig


class ChatConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.chat"
    
    def ready(self):
        """Инициализируем глобальный async event loop при старте Django"""
        from service.llm.async_loop import GlobalAsyncLoop
        # Инициализируем loop
        GlobalAsyncLoop()
        print("[CHAT APP] Global async event loop initialized")

