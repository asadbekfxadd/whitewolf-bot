from dataclasses import dataclass
from environs import Env

env = Env()
env.read_env()


@dataclass
class Config:
    BOT_TOKEN: str
    CHANNEL_ID: str       # например: @whitewolf_fx или -1001234567890
    ANTHROPIC_API_KEY: str
    ADMIN_ID: int         # твой Telegram ID для уведомлений об ошибках


config = Config(
    BOT_TOKEN=env.str("BOT_TOKEN"),
    CHANNEL_ID=env.str("CHANNEL_ID"),
    ANTHROPIC_API_KEY=env.str("ANTHROPIC_API_KEY"),
    ADMIN_ID=env.int("ADMIN_ID"),
)
