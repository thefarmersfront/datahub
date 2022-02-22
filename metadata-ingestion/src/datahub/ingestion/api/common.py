from abc import ABCMeta, abstractmethod
from dataclasses import dataclass
from typing import Dict, Generic, Iterable, Optional, Tuple, TypeVar

from datahub.ingestion.api.committable import Committable
from datahub.ingestion.graph.client import DatahubClientConfig, DataHubGraph

T = TypeVar("T")


@dataclass
class RecordEnvelope(Generic[T]):
    record: T
    metadata: dict


@dataclass
class _WorkUnitId(metaclass=ABCMeta):
    id: str


# For information on why the WorkUnit class is structured this way
# and is separating the dataclass portion from the abstract methods, see
# https://github.com/python/mypy/issues/5374#issuecomment-568335302.
class WorkUnit(_WorkUnitId, metaclass=ABCMeta):
    @abstractmethod
    def get_metadata(self) -> dict:
        pass


class PipelineContext:
    def __init__(
        self,
        run_id: str,
        datahub_api: Optional[DatahubClientConfig] = None,
        pipeline_name: Optional[str] = None,
        dry_run: bool = False,
        preview_mode: bool = False,
    ) -> None:
        self.run_id = run_id
        self.graph = DataHubGraph(datahub_api) if datahub_api is not None else None
        self.pipeline_name = pipeline_name
        self.dry_run_mode = dry_run
        self.preview_mode = preview_mode
        self.reporters: Dict[str, Committable] = dict()
        self.checkpointers: Dict[str, Committable] = dict()

    def register_checkpointer(self, committable: Committable) -> None:
        if committable.name in self.checkpointers:
            raise IndexError(
                f"Checkpointing provider {committable.name} already registered."
            )
        self.checkpointers[committable.name] = committable

    def register_reporter(self, committable: Committable) -> None:
        if committable.name in self.reporters:
            raise IndexError(
                f"Reporting provider {committable.name} already registered."
            )
        self.reporters[committable.name] = committable

    def get_reporters(self) -> Iterable[Committable]:
        for committable in self.reporters.values():
            yield committable

    def get_committables(self) -> Iterable[Tuple[str, Committable]]:
        for reporting_item_commitable in self.reporters.items():
            yield reporting_item_commitable
        for checkpointing_item_commitable in self.checkpointers.items():
            yield checkpointing_item_commitable
