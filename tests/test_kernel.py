import pytest
from core.kernel import Kernel
from core.exceptions import ModuleError

@pytest.fixture
async def kernel():
    k = Kernel()
    await k.init("test_token")
    yield k
    await k.stop()

async def test_kernel_initialization(kernel):
    assert kernel._token == "test_token"
    assert kernel._running is False

async def test_module_loading(kernel):
    # Проверка загрузки тестового модуля
    await kernel._load_module("test_module")
    assert "test_module" in kernel._modules