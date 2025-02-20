from typing import Dict, List, Any, Callable, Coroutine
import asyncio
from datetime import datetime
import logging
from collections import defaultdict

class Event:
    """Класс события"""
    def __init__(self, name: str, data: Any = None, sender: str = None):
        self.name = name
        self.data = data
        self.sender = sender
        self.timestamp = datetime.now()
        self.processed = False
        self.results = []

class EventManager:
    """Менеджер событий"""
    def __init__(self):
        self._handlers: Dict[str, List[Callable]] = defaultdict(list)
        self._middleware: List[Callable] = []
        self._history: List[Event] = []
        self._max_history = 1000
        self._logger = logging.getLogger('events')

    async def emit(self, event_name: str, data: Any = None, sender: str = None) -> Event:
        """Отправка события"""
        event = Event(event_name, data, sender)

        # Применяем middleware
        for middleware in self._middleware:
            try:
                event = await middleware(event)
                if not event:  # Middleware может отменить событие
                    return None
            except Exception as e:
                self._logger.error(f"Middleware error: {e}")
                continue

        # Вызываем обработчики
        if event_name in self._handlers:
            for handler in self._handlers[event_name]:
                try:
                    result = await handler(event)
                    event.results.append(result)
                except Exception as e:
                    self._logger.error(f"Handler error: {e}")
                    continue

        event.processed = True
        self._add_to_history(event)
        return event

    def subscribe(self, event_name: str, handler: Callable) -> None:
        """Подписка на событие"""
        if handler not in self._handlers[event_name]:
            self._handlers[event_name].append(handler)

    def unsubscribe(self, event_name: str, handler: Callable) -> None:
        """Отписка от события"""
        if event_name in self._handlers:
            self._handlers[event_name].remove(handler)
            if not self._handlers[event_name]:
                del self._handlers[event_name]

    def add_middleware(self, middleware: Callable) -> None:
        """Добавление middleware"""
        if middleware not in self._middleware:
            self._middleware.append(middleware)

    def remove_middleware(self, middleware: Callable) -> None:
        """Удаление middleware"""
        if middleware in self._middleware:
            self._middleware.remove(middleware)

    def _add_to_history(self, event: Event) -> None:
        """Добавление события в историю"""
        self._history.append(event)
        if len(self._history) > self._max_history:
            self._history.pop(0)

    def get_history(self, event_name: str = None) -> List[Event]:
        """Получение истории событий"""
        if event_name:
            return [e for e in self._history if e.name == event_name]
        return self._history.copy()

    async def wait_for(self, event_name: str, timeout: float = None) -> Event:
        """Ожидание определенного события"""
        future = asyncio.Future()

        async def handler(event: Event):
            if not future.done():
                future.set_result(event)
                self.unsubscribe(event_name, handler)

        self.subscribe(event_name, handler)
        try:
            return await asyncio.wait_for(future, timeout)
        except asyncio.TimeoutError:
            self.unsubscribe(event_name, handler)
            raise

    def clear_handlers(self, event_name: str = None) -> None:
        """Очистка обработчиков"""
        if event_name:
            if event_name in self._handlers:
                del self._handlers[event_name]
        else:
            self._handlers.clear()

    def clear_history(self) -> None:
        """Очистка истории событий"""
        self._history.clear()

    @property
    def registered_events(self) -> List[str]:
        """Список зарегистрированных событий"""
        return list(self._handlers.keys())
