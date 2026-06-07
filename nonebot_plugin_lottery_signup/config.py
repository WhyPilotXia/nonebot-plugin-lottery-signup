from nonebot import get_plugin_config
from pydantic import BaseModel


class Config(BaseModel):
    notion_token: str = ""
    lottery_contact_data_source_id: str = "31e70d82-c716-8034-b23d-000ba20878af"

    @property
    def notion_enabled(self) -> bool:
        return bool(self.notion_token.strip())


plugin_config = get_plugin_config(Config)

if plugin_config.notion_enabled and not plugin_config.lottery_contact_data_source_id.strip():
    raise ValueError("启用 Notion 去重时必须配置 lottery_contact_data_source_id")
