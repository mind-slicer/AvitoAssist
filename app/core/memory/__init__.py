import sys
import os

# Add workspace root to path for imports
_workspace_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _workspace_root not in sys.path:
    sys.path.insert(0, _workspace_root)

# Import managers directly to avoid circular imports
from app.core.memory.raw_data_manager import RawDataManager
from app.core.memory.knowledge_manager import KnowledgeManager

# Import MemoryManager from the parent module (app/core/memory.py)
# Using direct file import to bypass the package
import importlib.util
_memory_spec = importlib.util.spec_from_file_location(
    "_memory_module",
    os.path.join(os.path.dirname(os.path.dirname(__file__)), "memory.py")
)
_memory_module = importlib.util.module_from_spec(_memory_spec)
_memory_spec.loader.exec_module(_memory_module)
MemoryManager = _memory_module.MemoryManager

__all__ = ['RawDataManager', 'KnowledgeManager', 'MemoryManager']