from typing import Type, TypeVar, Callable, Dict, Any

T = TypeVar('T')


class DependencyContainer:
    """
    Легковесный IoC Контейнер (Service Locator) для управления зависимостями.

    Обеспечивает инверсию управления (Inversion of Control).
    Позволяет регистрировать фабрики сервисов и извлекать их в контроллерах
    (или других слоях) без жесткой привязки к конкретной реализации.
    """

    def __init__(self):
        self._registry: Dict[Type, Callable[..., Any]] = {}

    def register(self, interface_or_class: Type[T], factory: Callable[..., T]) -> None:
        """
        Регистрирует зависимость в контейнере.

        Args:
            interface_or_class: Базовый класс или интерфейс (Protocol),
                по которому будет запрашиваться сервис.
            factory: Функция (или lambda), возвращающая настроенный экземпляр сервиса.
                Для Transient поведения фабрика должна возвращать новый объект.
                Для Singleton поведения фабрика должна возвращать один и тот же объект.
        """

        self._registry[interface_or_class] = factory

    def resolve(self, interface_or_class: Type[T]) -> T:
        """
        Извлекает (разрешает) готовую зависимость из контейнера.

        Args:
            interface_or_class: Тип сервиса, который необходимо получить.

        Returns:
            Готовый к использованию экземпляр сервиса.

        Raises:
            RuntimeError: Если запрошенный сервис не был зарегистрирован в контейнере.
        """
        factory = self._registry.get(interface_or_class)
        if not factory:
            raise Exception(f"Зависимость {interface_or_class.__name__} не зарегистрирована в DI-контейнере!")
        return factory()


container = DependencyContainer()
