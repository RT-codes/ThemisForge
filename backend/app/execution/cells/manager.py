from app.config import settings
from app.execution.cells.contract import CellManager
from app.execution.cells.docker import DockerCellManager
from app.execution.cells.fake import FakeCellManager


def make_cell_manager() -> CellManager:
    return FakeCellManager(duration=2.0) if settings.cell_backend == "fake" else DockerCellManager()
