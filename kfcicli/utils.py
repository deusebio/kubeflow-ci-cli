"""Module for general logging functionalities and abstractions."""

import io
import json
import logging
import os
import re
from configparser import ConfigParser
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

A = TypeVar("A")


def safe(f: Callable[..., A]) -> Callable[..., A]:
    """Decorator to convert unsafe functions to safe functions, that returns Either monads"""

    @wraps(f)
    def wrap(*args, **kwargs) -> A | None:
        try:
            return f(*args, **kwargs)
        except Exception as e:
            logging.getLogger(str(f)).warning(
                f"Catching function {f} with exception {e}")
            return None

    return wrap


# Taken from https://gist.github.com/Jip-Hop/d82781da424724b4018bdfc5a2f1318b
class CommentConfigParser(ConfigParser):
    """Comment preserving ConfigParser.
    Limitation: No support for indenting section headers,
    comments and keys. They should have no leading whitespace.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Backup _comment_prefixes
        self._comment_prefixes_backup = self._comment_prefixes
        # Unset _comment_prefixes so comments won't be skipped
        self._comment_prefixes = ()
        # Starting point for the comment IDs
        self._comment_id = 0
        # Default delimiter to use
        delimiter = self._delimiters[0]
        # Template to store comments as key value pair
        self._comment_template = "#{0} " + delimiter + " {1}"
        # Regex to match the comment prefix
        self._comment_regex = re.compile(
            r"^#\d+\s*" + re.escape(delimiter) + r"[^\S\n]*")
        # Regex to match cosmetic newlines (skips newlines in multiline values):
        # consecutive whitespace from start of line followed by a line not starting with whitespace
        self._cosmetic_newlines_regex = re.compile(r"^(\s+)(?=^\S)",
                                                   re.MULTILINE)
        # List to store comments above the first section
        self._top_comments = []

    def _find_cosmetic_newlines(self, text):
        # Indices of the lines containing cosmetic newlines
        cosmetic_newline_indices = set()
        for match in re.finditer(self._cosmetic_newlines_regex, text):
            start_index = text.count("\n", 0, match.start())
            end_index = start_index + text.count("\n", match.start(),
                                                 match.end())
            cosmetic_newline_indices.update(range(start_index, end_index))

        return cosmetic_newline_indices

    def _read(self, fp, fpname):
        lines = fp.readlines()
        cosmetic_newline_indices = self._find_cosmetic_newlines("".join(lines))

        above_first_section = True
        # Preprocess config file to preserve comments
        for i, line in enumerate(lines):
            if line.startswith("["):
                above_first_section = False
            elif above_first_section:
                # Remove this line for now
                lines[i] = ""
                self._top_comments.append(line)
            elif i in cosmetic_newline_indices or line.startswith(
                    self._comment_prefixes_backup
            ):
                # Store cosmetic newline or comment with unique key
                lines[i] = self._comment_template.format(self._comment_id, line)
                self._comment_id += 1

        # Feed the preprocessed file to the original _read method
        return super()._read(io.StringIO("".join(lines)), fpname)

    def write(self, fp, space_around_delimiters=True):
        # Write the config to an in-memory file
        with io.StringIO() as sfile:
            super().write(sfile, space_around_delimiters)
            # Start from the beginning of sfile
            sfile.seek(0)
            lines = sfile.readlines()

        cosmetic_newline_indices = self._find_cosmetic_newlines("".join(lines))

        for i, line in enumerate(lines):
            if i in cosmetic_newline_indices:
                # Remove newlines added below each section by .write()
                lines[i] = ""
                continue
            # Remove the comment prefix (if regex matches)
            lines[i] = self._comment_regex.sub("", line, 1)

        fp.write("".join(self._top_comments + lines).rstrip())

    def clear(self):
        # Also clear the _top_comments
        self._top_comments = []
        super().clear()
