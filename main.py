#!/usr/bin/env python3
"""
SwiftDevBot - Telegram Bot for Swift Development
Author: SoverX
Version: 1.0.0
"""

import asyncio
import logging
import yaml
import signal
from core.kernel import Kernel

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',  # Исправлено levellevel на levelname
    level=logging.INFO
)

async def main():
    """Main entry point for SwiftDevBot"""
    logger = logging.getLogger('SwiftDevBot')
    logger.info('Starting SwiftDevBot...')

    kernel = Kernel()
    stop_signal = asyncio.Event()

    def signal_handler():
        logger.info('Received stop signal')
        stop_signal.set()

    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, signal_handler)

    try:
        with open('config.yml', 'r') as f:
            config = yaml.safe_load(f)

        await kernel.init(config['bot']['token'])
        await kernel.start()
        logger.info('SwiftDevBot successfully started')

        await stop_signal.wait()
    except Exception as e:
        logger.error(f"Critical error: {e}")
    finally:
        logger.info('Shutting down SwiftDevBot...')
        await kernel.stop()
        logger.info('SwiftDevBot stopped')

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass  # Игнорируем KeyboardInterrupt здесь, так как он обрабатывается в main()
