import logging
import shlex
from abc import ABC, abstractmethod
from typing import List, Dict, Callable
from Core.interfaces import IRenderer, IRenderable

class Args:
    def __init__(self, raw_input: str, command: str, params: List[str], flags: Dict[str, str]):
        self.raw_input = raw_input
        self.command = command.lower()
        self.params = params
        self.flags = flags

class ArgParser:
    @staticmethod
    def parse_args(raw_string: str) -> Args:
        cleaned = raw_string.strip()
        if not cleaned:
            return Args(raw_string, "", [], {})
        try:
            tokens = shlex.split(cleaned)
        except ValueError:
            tokens = cleaned.split()

        command = tokens[0]
        params: List[str] = []
        flags: Dict[str, str] = {}

        for token in tokens[1:]:
            if token.startswith("--") and "=" in token:
                key, val = token[2:].split("=", 1)
                flags[key] = val
            elif token.startswith("-"):
                flags[token.lstrip("-")] = "true"
            else:
                params.append(token)
        return Args(raw_string, command, params, flags)

class Command:
    def __init__(self, selector: str, description: str, handler: Callable[[Args], bool]):
        self.selector = selector.lower()
        self.description = description
        self.handler = handler

    def execute(self, args: Args) -> bool:
        return self.handler(args)

class ICommandStrategy(ABC):
    @abstractmethod
    def get_command_selectors(self) -> List[str]:
        pass

    @abstractmethod
    def get_commands_info(self) -> Dict[str, str]:
        pass

    @abstractmethod
    def register_command(self, command: Command) -> None:
        pass

    @abstractmethod
    def exec_command(self, selector: str, args: Args) -> bool:
        pass

class BaseCommandStrategy(ICommandStrategy):
    def __init__(self):
        self._commands: Dict[str, Command] = {}

    def register_command(self, command: Command) -> None:
        self._commands[command.selector] = command

    def get_command_selectors(self) -> List[str]:
        return list(self._commands.keys())

    def get_commands_info(self) -> Dict[str, str]:
        return {cmd.selector: cmd.description for cmd in self._commands.values()}

    def exec_command(self, selector: str, args: Args) -> bool:
        cmd = self._commands.get(selector.lower())
        if not cmd:
            return False
        return cmd.execute(args)

log = logging.getLogger("textgame")


class CLI:
    def __init__(self, debug: bool = False):
        self._strategies: List[ICommandStrategy] = []
        self._parser = ArgParser()
        self.debug = debug

    def use_strategy(self, strategy: ICommandStrategy) -> None:
        self._strategies.append(strategy)

    def get_all_commands(self) -> Dict[str, str]:
        all_cmds: Dict[str, str] = {}
        for strat in self._strategies:
            all_cmds.update(strat.get_commands_info())
        return all_cmds

    def exec_command(self, raw_string: str) -> bool:
        args = self._parser.parse_args(raw_string)
        if not args.command:
            return False

        for strategy in self._strategies:
            if args.command in strategy.get_command_selectors():
                try:
                    return strategy.exec_command(args.command, args)
                except Exception:
                    log.exception("Помилка під час виконання команди '%s'", raw_string)
                    if self.debug:
                        raise
                    print(f"[Внутрішня помилка] Команду '{args.command}' не виконано. "
                          f"Подробиці записано в журнал.")
                    return False

        print(f"[Помилка] Невідома команда '{args.command}'. Введіть 'help'.")
        return False

    def display(self, item: IRenderable) -> None:
        print(item.render())