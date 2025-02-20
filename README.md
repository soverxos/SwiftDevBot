# SwiftDevBot

SwiftDevBot is a Telegram bot.

## Features

- System monitoring and management
- Automated backups
- Advanced logging
- Statistics collection
- Notification system
- REST API interface
- Security management
- Task scheduling

## Installation

1. Create virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # Linux/MacOS
venv\Scripts\activate   # Windows
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Configure bot:
- Copy `config.yml.example` to `config.yml`
- Set your bot token and other settings

4. Run bot:
```bash
python main.py
```

## Project Structure

- `core/` - Core system files
- `modules/` - Bot modules
  - `system/` - System modules
  - `user/` - User modules
- `logs/` - Log files
- `backups/` - Backup files
- `data/` - Database and other data

## Commands

### Admin Commands
- `/admin` - Access admin panel
- `/backup` - Manage backups
- `/stats` - View statistics
- `/logs` - View system logs
- `/notifications` - Manage notifications

### User Commands
- `/start` - Start bot
- `/help` - Show help
- `/settings` - User settings

## Development

### Code Style
This project follows PEP 8 guidelines. Use the following tools:
- `black` for code formatting
- `flake8` for linting
- `mypy` for type checking

### Testing
Run tests with pytest:
```bash
pytest
```

### Documentation
Generate documentation:
```bash
cd docs
make html
```

## License

MIT License.

## Author

SoverX - Шевченко Дмитрий
