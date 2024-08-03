from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from boa.network import NetworkEnv, EthereumRPC
from boa import Env
import boa
from gaboon.constants.vars import CONFIG_NAME, DOT_ENV_FILE
import tomllib
from dotenv import load_dotenv
import os


@dataclass
class Network:
    name: str
    url: str | None = None
    is_fork: bool = False
    extra_data: dict[str, Any] = field(default_factory=dict)
    _network_env: NetworkEnv | Env | None = None

    def _create_env(self) -> NetworkEnv | Env:
        if self.is_fork:
            self._network_env = Env()
            self._network_env.fork(self.url)
            self._network_env.set_nickname(self.name)
        else:
            self._network_env = NetworkEnv(EthereumRPC(self.url), nickname=self.name)
        return self._network_env

    def get_or_create_env(self) -> NetworkEnv | Env:
        if self._network_env:
            boa.set_env(self._network_env)
            return self._network_env
        new_env: NetworkEnv | Env = self._create_env()
        boa.set_env(new_env)
        return new_env

    @property
    def alias(self) -> str:
        return self.name

    @property
    def identifier(self) -> str:
        return self.name


class _Networks:
    _networks: dict[str, Network]

    def __init__(self, toml_data: dict):
        self._networks = {}
        self.custom_networks_counter = 0
        for key, value in toml_data["networks"].items():
            network = Network(
                name=key,
                is_fork=value.get("fork", False),
                url=value.get("url", None),
                extra_data=value.get("extra_data", {}),
            )
            setattr(self, key, network)
            self._networks[key] = network

    def __len__(self):
        return len(self._networks)

    def get_active_network(self) -> Network:
        if boa.env.nickname in self._networks:
            return self._networks[boa.env.nickname]
        new_network = Network(name=boa.env.nickname)
        self._networks[new_network.name] = new_network
        return new_network

    def get_network_by_name(self, alias: str) -> Network:
        return self._networks[alias]

    # TODO
    # REVIEW: i think it might be better to delegate to `boa.set_env`
    # so the usage would be like:
    # ```
    # boa.set_env_from_network(gaboon.networks.zksync)
    # ```
    # otherwise it is too confusing where gaboon ends and boa starts.
    def set_active_network(self, name_or_url: str | Network, is_fork: bool = False):
        if isinstance(name_or_url, Network):
            env_to_set: NetworkEnv = name_or_url.get_or_create_env()
            self._networks[name_or_url.name] = env_to_set
        else:
            if name_or_url.startswith("http"):
                new_network = self._create_custom_network(name_or_url, is_fork=is_fork)
                env_to_set: NetworkEnv | Env = new_network.get_or_create_env()
            else:
                if name_or_url in self._networks:
                    env_to_set: NetworkEnv | Env = self._networks[
                        name_or_url
                    ].get_or_create_env()
                else:
                    raise ValueError(
                        f"Network {name_or_url} not found. Please pass a valid URL/RPC or valid network name."
                    )

    def _create_custom_network(self, url: str, is_fork: bool = False) -> Network:
        new_network = Network(
            name=f"custom_{self.custom_networks_counter}", url=url, is_fork=is_fork
        )
        self._networks[new_network.name] = new_network
        self.custom_networks_counter += 1
        return new_network


class Config:
    _project_root: Path
    networks: _Networks
    extra_data: dict[str, str] | None

    def __init__(self, root_path: Path):
        self._project_root = root_path
        config_path: Path = root_path.joinpath(CONFIG_NAME)
        if config_path.exists():
            self._load_config(config_path)

    def _load_config(self, config_path: Path):
        toml_data: dict = self.read_gaboon_config(config_path)
        self._load_env_file()
        toml_data = self.expand_env_vars(toml_data)
        self.networks = _Networks(toml_data)

    def _load_env_file(self):
        load_dotenv(dotenv_path=self.project_root.joinpath(DOT_ENV_FILE))

    def read_gaboon_config(self, config_path: Path) -> dict:
        if not str(config_path).endswith("/gaboon.toml"):
            config_path = config_path.joinpath("gaboon.toml")
        if not config_path.exists():
            raise FileNotFoundError(f"Config file not found: {config_path}")
        with open(config_path, "rb") as f:
            return tomllib.load(f)

    def expand_env_vars(self, value):
        if isinstance(value, str):
            return os.path.expandvars(value)
        elif isinstance(value, dict):
            return {k: self.expand_env_vars(v) for k, v in value.items()}
        elif isinstance(value, list):
            return [self.expand_env_vars(item) for item in value]
        else:
            return value

    def get_active_network(self):
        return self.networks.get_active_network()

    def get_root(self) -> Path:
        return self._project_root

    def set_active_network(
        self,
    ):
        self.networks.set_active_network(self)

    @property
    def project_root(self) -> Path:
        return self._project_root

    @staticmethod
    def load_config_from_path(config_path: Path | None = None) -> "Config":
        if config_path is None:
            config_path = Config.find_project_root()
        return Config(config_path)

    @staticmethod
    def find_project_root(start_path: Path | str = Path.cwd()) -> Path:
        current_path = Path(start_path).resolve()
        while True:
            # Move up to the parent directory
            parent_path = current_path.parent
            if parent_path == current_path:
                # We've reached the root directory without finding gaboon.toml
                raise FileNotFoundError(
                    "Could not find gaboon.toml or src directory with Vyper contracts in any parent directory"
                )

            if (current_path / CONFIG_NAME).exists():
                return current_path

            # Check for src directory with .vy files in current directory
            src_path = current_path / "src"
            if src_path.is_dir() and any(src_path.glob("*.vy")):
                return current_path

            current_path = parent_path

_config: Config = None

def get_config() -> Config:
    global _config
    return _config


def initialize_global_config():
    global _config
    assert _config is None
    _config = Config.load_config_from_path()
