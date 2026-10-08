import subprocess
import sys


def test_importing_one_model_alone_can_flush_foreign_keys():
    """Regression: the worker imports only `Job`; its FK to `users` must still resolve."""
    code = (
        "from backend.models.job import Job\n"
        "from backend.models.base import Base\n"
        "from sqlalchemy.orm import configure_mappers\n"
        "configure_mappers()\n"
        "table = Base.metadata.tables['jobs']\n"
        "fk = next(iter(table.foreign_keys))\n"
        "assert fk.column.table.name == 'users'\n"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)

    assert result.returncode == 0, result.stderr
