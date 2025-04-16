"""Module for general logging functionalities and abstractions."""

import json
import logging
import os
from contextlib import contextmanager
from logging import Logger, config, getLogger
from typing import Any, Callable, Literal, TypedDict, TypeVar, TypeAlias

from envyaml import EnvYAML

PathLike: TypeAlias = str | os.PathLike[str]

LevelTypes = Literal[
    "CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG", "NOTSET", 50, 40, 30, 20, 10, 0
]
StrLevelTypes = Literal[
    "CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG", "NOTSET"]

T = TypeVar("T")


class LevelsDict(TypedDict):
    """Logger levels."""

    CRITICAL: Literal[50]
    ERROR: Literal[40]
    WARNING: Literal[30]
    INFO: Literal[20]
    DEBUG: Literal[10]
    NOTSET: Literal[0]


DEFAULT_LOG_LEVEL: StrLevelTypes = "INFO"

levels: LevelsDict = {
    "CRITICAL": 50,
    "ERROR": 40,
    "WARNING": 30,
    "INFO": 20,
    "DEBUG": 10,
    "NOTSET": 0,
}

DEFAULT_LOGGING_FILE = os.path.join(
    os.path.dirname(__file__), "resources", "logging.yaml"
)


def config_from_json(path_to_file: str = DEFAULT_LOGGING_FILE) -> None:
    """
    Configure logger from json.

    :param path_to_file: path to configuration file

    :type path_to_file: str

    :return: configuration for logger
    """
    with open(path_to_file, "rt") as fid:
        configFile = json.load(fid)
    config.dictConfig(configFile)


def config_from_yaml(path_to_file: str = DEFAULT_LOGGING_FILE) -> None:
    """
    Configure logger from yaml.

    :param path_to_file: path to configuration file

    :type path_to_file: str

    :return: configuration for logger
    """
    config.dictConfig(dict(EnvYAML(path_to_file, strict=False)))


def config_from_file(path_to_file: str = DEFAULT_LOGGING_FILE) -> None:
    """
    Configure logger from file.

    :param path_to_file: path to configuration file

    :type path_to_file: str

    :return: configuration for logger
    """
    readers = {
        ".yml": config_from_yaml,
        ".yaml": config_from_yaml,
        ".json": config_from_json,
    }

    _, file_extension = os.path.splitext(path_to_file)

    if file_extension not in readers.keys():
        raise NotImplementedError(
            f"Reader for file extension {file_extension} is not supported"
        )

    return readers[file_extension](path_to_file)


class WithLogging:
    """Base class to be used for providing a logger embedded in the class."""

    @property
    def logger(self) -> Logger:
        """Create logger.

        :return: default logger.
        """
        nameLogger = str(self.__class__).replace("<class '", "").replace("'>",
                                                                         "")
        return getLogger(nameLogger)

    def logResult(
            self, msg: Callable[..., str] | str, level: StrLevelTypes = "INFO"
    ) -> Callable[..., Any]:
        """Return a decorator to allow logging of inputs/outputs.

        :param msg: message to log
        :param level: logging level
        :return: wrapped method.
        """

        def wrap(x: Any) -> Any:
            if isinstance(msg, str):
                self.logger.log(levels[level], msg)
            else:
                self.logger.log(levels[level], msg(x))
            return x

        return wrap


def setup_logging(
        log_level: str, config_file: str | None = None,
        logger_name: str | None = None
) -> logging.Logger:
    """Set up logging from configuration file."""
    with environ(LOG_LEVEL=log_level) as _:
        config_from_file(config_file or DEFAULT_LOGGING_FILE)
    return logging.getLogger(logger_name) if logger_name else logging.root


@contextmanager
def environ(*remove, **update):
    """
    Temporarily updates the ``os.environ`` dictionary in-place.

    The ``os.environ`` dictionary is updated in-place so that the modification
    is sure to work in all situations.

    :param remove: Environment variables to remove.
    :param update: Dictionary of environment variables and values to add/update.
    """
    env = os.environ
    update = update or {}
    remove = remove or []

    # List of environment variables being updated or removed.
    stomped = (set(update.keys()) | set(remove)) & set(env.keys())
    # Environment variables and values to restore on exit.
    update_after = {k: env[k] for k in stomped}
    # Environment variables and values to remove on exit.
    remove_after = frozenset(k for k in update if k not in env)

    try:
        [env.pop(k, None) for k in remove]
        env.update(update)
        yield
    finally:
        [env.pop(k) for k in remove_after]
        env.update(update_after)


from functools import wraps
from typing import TypeVar

A=TypeVar("A")

def safe(f: Callable[..., A]) -> Callable[..., A]:
    """Decorator to convert unsafe functions to safe functions, that returns Either monads"""
    @wraps(f)
    def wrap(*args, **kwargs) -> A | None:
        try:
            return f(*args, **kwargs)
        except Exception as e:
            logging.getLogger(str(f)).warning(f"Catching function {f} with exception {e}")
            return None
    return wrap
