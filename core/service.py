import asyncio
import logging
from typing import Optional, Any, Dict
from datetime import datetime

class BaseService:
    def __init__(self, name: str):
        self.logger = logging.getLogger(name)
        self._queue: Optional[asyncio.Queue] = None
        self._process_task: Optional[asyncio.Task] = None
        self._running = False
        self._started_at: Optional[datetime] = None
        self._stats: Dict[str, Any] = {
            'processed_items': 0,
            'errors': 0,
            'last_error': None,
            'last_processed': None
        }

    @property
    def stats(self) -> Dict[str, Any]:
        """Получение статистики сервиса"""
        return {
            **self._stats,
            'running': self._running,
            'queue_size': self._queue.qsize() if self._queue else 0,
            'uptime': (datetime.now() - self._started_at).total_seconds() if self._started_at else 0
        }

    async def start(self):
        """Запуск сервиса"""
        if self._running:
            return
        self._running = True
        self._started_at = datetime.now()
        self._queue = asyncio.Queue()
        self._process_task = asyncio.create_task(self._process_queue())
        self.logger.info(f"Service {self.__class__.__name__} started")

    async def stop(self):
        """Остановка сервиса"""
        if not self._running:
            return
        self._running = False
        try:
            if self._queue:
                # Ждем завершения обработки очереди с таймаутом
                try:
                    await asyncio.wait_for(self._queue.join(), timeout=5.0)
                except asyncio.TimeoutError:
                    self.logger.warning("Queue processing timeout during shutdown")
                    
            if self._process_task:
                self._process_task.cancel()
                try:
                    await self._process_task
                except asyncio.CancelledError:
                    pass
                
            self.logger.info(f"Service {self.__class__.__name__} stopped")
            
        except Exception as e:
            self.logger.error(f"Error during service shutdown: {e}")
        finally:
            self._started_at = None

    async def add_task(self, item: Any):
        """Добавление задачи в очередь"""
        if not self._running:
            raise RuntimeError("Service is not running")
        await self._queue.put(item)

    async def _process_queue(self):
        """Обработка очереди"""
        try:
            while self._running:
                try:
                    item = await self._queue.get()
                    start_time = datetime.now()
                    
                    try:
                        await self._process_item(item)
                        self._stats['processed_items'] += 1
                        self._stats['last_processed'] = datetime.now()
                        
                        # Логируем длительные операции
                        processing_time = (datetime.now() - start_time).total_seconds()
                        if processing_time > 1.0:
                            self.logger.warning(f"Long processing time: {processing_time:.2f}s")
                            
                    except Exception as e:
                        self._stats['errors'] += 1
                        self._stats['last_error'] = str(e)
                        self.logger.error(f"Error processing item: {e}")
                    finally:
                        self._queue.task_done()
                        
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    self.logger.error(f"Queue processing error: {e}")
                    await asyncio.sleep(1)  # Предотвращаем спам ошибками
                    
        finally:
            # Очищаем очередь при остановке
            while not self._queue.empty():
                try:
                    self._queue.get_nowait()
                    self._queue.task_done()
                except asyncio.QueueEmpty:
                    break

    async def _process_item(self, item: Any):
        """Переопределите этот метод в дочерних классах"""
        raise NotImplementedError