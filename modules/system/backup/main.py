import shutil
from datetime import datetime
from pathlib import Path
from core.module_api import ModuleInterface, ModuleMetadata

class BackupModule(ModuleInterface):
    async def setup(self, kernel):
        self.kernel = kernel
        self.logger = logging.getLogger('backup')
        
        self.metadata = ModuleMetadata(
            name="system.backup",
            version="1.0.0",
            description="Модуль резервного копирования"
        )

        # Создаем директории
        self.backup_dir = Path("data/backups")
        self.backup_dir.mkdir(parents=True, exist_ok=True)

        return self

    async def cleanup(self):
        pass

    async def register_handlers(self, bot):
        pass

    async def create_backup(self):
        """Создание резервной копии базы данных"""
        try:
            db_file = Path("data/db/database.db")
            if not db_file.exists():
                raise FileNotFoundError("Database file not found")

            # Формируем имя файла бэкапа
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_file = self.backup_dir / f"backup_{timestamp}.db"

            # Копируем файл БД
            shutil.copy2(db_file, backup_file)
            
            # Сжимаем бэкап
            shutil.make_archive(str(backup_file), 'gzip', self.backup_dir, backup_file.name)
            
            # Удаляем несжатый файл
            backup_file.unlink()
            
            self.logger.info(f"Created backup: {backup_file}.gz")
            return True
            
        except Exception as e:
            self.logger.error(f"Backup creation failed: {e}")
            return False