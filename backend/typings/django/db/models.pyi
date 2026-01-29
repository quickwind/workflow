from datetime import datetime
from typing import Any, ClassVar, Generic, Optional, TypeVar, Self

_M = TypeVar("_M", bound="Model")
_F = TypeVar("_F")

class QuerySet(Generic[_M]):
    def select_related(self, *args: Any, **kwargs: Any) -> Self: ...
    def filter(self, *args: Any, **kwargs: Any) -> Self: ...
    def first(self) -> Optional[_M]: ...
    @classmethod
    def as_manager(cls) -> "Manager[_M]": ...

class Manager(Generic[_M]):
    def select_related(self, *args: Any, **kwargs: Any) -> QuerySet[_M]: ...
    def filter(self, *args: Any, **kwargs: Any) -> QuerySet[_M]: ...
    def first(self) -> Optional[_M]: ...

class Model:
    objects: ClassVar[Manager[Any]]
    _default_manager: ClassVar[Manager[Any]]

class Field(Generic[_F]):
    def __get__(self, instance: Any, owner: Any) -> _F: ...

class CharField(Field[str]):
    def __init__(self, *args: Any, **kwargs: Any) -> None: ...

class SlugField(Field[str]):
    def __init__(self, *args: Any, **kwargs: Any) -> None: ...

class DateTimeField(Field[datetime]):
    def __init__(self, *args: Any, **kwargs: Any) -> None: ...

class BigAutoField(Field[int]):
    def __init__(self, *args: Any, **kwargs: Any) -> None: ...

class ForeignKey(Field[_M]):
    def __init__(
        self,
        to: Any,
        on_delete: Any,
        related_name: str | None = None,
        **kwargs: Any,
    ) -> None: ...

PROTECT: Any
