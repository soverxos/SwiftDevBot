# modules/system/api/main.py
from core.module_api import ModuleInterface
from aiohttp import web
import logging
import json
import jwt
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import asyncio
from functools import wraps
import yaml
import socket

class APIService:
    def __init__(self, kernel):
        self.kernel = kernel
        self.logger = logging.getLogger('api')
        self.config = self._load_config()
        self.app = web.Application()
        self.setup_routes()
        self.tokens = {}  # кэш токенов

    def _load_config(self) -> dict:
        with open("config.yml", 'r') as f:
            config = yaml.safe_load(f)
        return config.get('api', {})

    def setup_routes(self):
        """Настройка маршрутов API"""
        # Аутентификация
        self.app.router.add_post('/api/auth', self.auth)

        # Пользователи
        self.app.router.add_get('/api/users', self.get_users)
        self.app.router.add_get('/api/users/{user_id}', self.get_user)

        # Модули
        self.app.router.add_get('/api/modules', self.get_modules)
        self.app.router.add_post('/api/modules/{module_id}/toggle', self.toggle_module)

        # Логи
        self.app.router.add_get('/api/logs', self.get_logs)

        # Статистика
        self.app.router.add_get('/api/stats', self.get_stats)

        # Задачи
        self.app.router.add_get('/api/tasks', self.get_tasks)
        self.app.router.add_post('/api/tasks', self.create_task)
        self.app.router.add_delete('/api/tasks/{task_id}', self.delete_task)

    def auth_required(func):
        """Декоратор для проверки JWT токена"""
        @wraps(func)
        async def wrapper(self, request):
            try:
                auth_header = request.headers.get('Authorization')
                if not auth_header or not auth_header.startswith('Bearer '):
                    raise web.HTTPUnauthorized(text='Invalid token')

                token = auth_header.split(' ')[1]
                payload = jwt.decode(
                    token,
                    self.config['jwt_secret'],
                    algorithms=['HS256']
                )

                # Проверяем токен в кэше
                if token not in self.tokens:
                    raise web.HTTPUnauthorized(text='Token expired')

                request['user_id'] = payload['user_id']
                return await func(self, request)

            except jwt.ExpiredSignatureError:
                raise web.HTTPUnauthorized(text='Token expired')
            except jwt.InvalidTokenError:
                raise web.HTTPUnauthorized(text='Invalid token')

        return wrapper

    async def generate_token(self, user_id: int) -> str:
        """Генерация JWT токена"""
        payload = {
            'user_id': user_id,
            'exp': datetime.utcnow() + timedelta(
                hours=self.config.get('token_lifetime', 24)
            )
        }

        token = jwt.encode(
            payload,
            self.config['jwt_secret'],
            algorithm='HS256'
        )

        # Сохраняем в кэш
        self.tokens[token] = payload
        return token

    async def auth(self, request):
        """Аутентификация и получение токена"""
        try:
            data = await request.json()
            api_key = data.get('api_key')

            if api_key != self.config['api_key']:
                raise web.HTTPUnauthorized(text='Invalid API key')

            token = await self.generate_token(0)  # 0 = system user
            return web.json_response({'token': token})

        except json.JSONDecodeError:
            raise web.HTTPBadRequest(text='Invalid JSON')

    @auth_required
    async def get_users(self, request):
        """Получение списка пользователей"""
        db = self.kernel.get_service('database')
        users = await db.fetch_all("SELECT * FROM users")
        return web.json_response({'users': users})

    @auth_required
    async def get_user(self, request):
        """Получение информации о пользователе"""
        user_id = request.match_info['user_id']
        db = self.kernel.get_service('database')
        user = await db.fetch_one(
            "SELECT * FROM users WHERE id = ?",
            (user_id,)
        )

        if not user:
            raise web.HTTPNotFound(text='User not found')

        return web.json_response({'user': user})

    @auth_required
    async def get_modules(self, request):
        """Получение списка модулей"""
        modules = []
        for module_id, module in self.kernel.modules.items():
            modules.append({
                'id': module_id,
                'name': module.__class__.__name__,
                'enabled': module.enabled if hasattr(module, 'enabled') else True
            })
        return web.json_response({'modules': modules})

    @auth_required
    async def toggle_module(self, request):
        """Включение/выключение модуля"""
        module_id = request.match_info['module_id']
        module_manager = self.kernel.get_service('module_manager')

        try:
            data = await request.json()
            enabled = data.get('enabled', True)

            if enabled:
                await module_manager.enable_module(module_id)
            else:
                await module_manager.disable_module(module_id)

            return web.json_response({'status': 'success'})

        except Exception as e:
            raise web.HTTPBadRequest(text=str(e))

    @auth_required
    async def get_logs(self, request):
        """Получение логов"""
        logger = self.kernel.get_service('logger')

        level = request.query.get('level')
        module = request.query.get('module')
        limit = int(request.query.get('limit', 100))

        logs = await logger.get_logs(
            level=level,
            module=module,
            limit=limit
        )
        return web.json_response({'logs': logs})

    @auth_required
    async def get_stats(self, request):
        """Получение статистики"""
        stats = self.kernel.get_service('stats')
        data = await stats.get_stats()
        return web.json_response({'stats': data})

    @auth_required
    async def get_tasks(self, request):
        """Получение списка задач"""
        scheduler = self.kernel.get_service('scheduler')
        tasks = []

        for task in scheduler.tasks.values():
            tasks.append({
                'id': task.id,
                'name': task.name,
                'cron': task.cron,
                'enabled': task.enabled,
                'last_run': task.last_run,
                'next_run': task.next_run
            })

        return web.json_response({'tasks': tasks})

    @auth_required
    async def create_task(self, request):
        """Создание новой задачи"""
        try:
            data = await request.json()
            scheduler = self.kernel.get_service('scheduler')

            task = await scheduler.add_task(
                name=data['name'],
                cron=data['cron'],
                handler=data['handler'],
                args=data.get('args', []),
                kwargs=data.get('kwargs', {})
            )

            return web.json_response({
                'status': 'success',
                'task_id': task.id
            })

        except Exception as e:
            raise web.HTTPBadRequest(text=str(e))

    @auth_required
    async def delete_task(self, request):
        """Удаление задачи"""
        task_id = request.match_info['task_id']
        scheduler = self.kernel.get_service('scheduler')

        if await scheduler.remove_task(int(task_id)):
            return web.json_response({'status': 'success'})
        else:
            raise web.HTTPNotFound(text='Task not found')

class APIModule(ModuleInterface):
    async def setup(self, kernel):
        self.kernel = kernel
        self.logger = logging.getLogger('system.api')

        port = 8080
        
        # Поиск свободного порта
        while not self._is_port_available(port) and port < 8090:
            port += 1
            
        if not self._is_port_available(port):
            raise RuntimeError("Не удалось найти свободный порт для API")
            
        self.config['port'] = port

        # Создаём сервис API
        self.api = APIService(kernel)

        # Регистрируем сервис
        await kernel.get_service('registry').register_service(
            'api',
            self.api
        )

        # Запускаем веб-сервер
        runner = web.AppRunner(self.api.app)
        await runner.setup()

        config = self.api.config
        site = web.TCPSite(
            runner,
            config.get('host', 'localhost'),
            config.get('port', 8080)
        )
        await site.start()

        self.logger.info(
            f"API server started at http://{config.get('host', 'localhost')}:"
            f"{config.get('port', 8080)}"
        )

    def _is_port_available(self, port):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(('127.0.0.1', port))
                return True
            except socket.error:
                return False

    async def cleanup(self):
        """Очистка ресурсов"""
        await self.api.app.shutdown()
        self.logger.info("API server stopped")
