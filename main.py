from astrbot.api.event import filter, AstrMessageEvent
import astrbot.api.message_components as Comp
from astrbot.api.star import Context, Star, register
from astrbot.api import AstrBotConfig
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.utils.session_waiter import (
    session_waiter,
    SessionController,
)
from astrbot import logger
import aiohttp
import json
import os
import traceback

@register("nikki_s", "Lynn", "秘密", "1.0.12")
class MyPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig = None):
        super().__init__(context)
        
        # 从配置获取服务器地址，如果没有则使用默认值
        self.config = config or {}
        self.server_url = self.config.get("server_url", "http://localhost:5000")
        
        # 本地配置文件路径
        self.config_file = os.path.join(context.base_path, "config.json")
        
        # 地点列表
        self.locations = [
            "花田民居", "村口集市", "染织工坊", "落石谷", "悠悠草坡", 
            "虫鸣花坡", "绿野活动区", "绿野码头", "女王行宫遗迹", "边境哨所",
            "溪声林地", "巨树河谷", "陨愿山岭", "曙光山地", "镇郊林区",
            "湖畔街区", "大许愿树广场", "栖愿遗迹", "福鸣瀑布", "麦浪农场",
            "欢乐市集", "乘风磨坊", "涟漪庄园", "星空钓场", "石之冠",
            "丰饶古村", "呜呜车站"
        ]
        
        # 会话超时时间（秒）
        self.timeout = 10
        
        # 打印配置信息
        logger.info(f"✓ 服务器地址: {self.server_url}")
        
        # 初始化：从服务器拉取配置
        context.register_task(self._init_config(), "初始化配置")
    
    async def _init_config(self):
        """初始化：从服务器拉取配置文件到本地"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.server_url}/config") as resp:
                    if resp.status == 200:
                        config = await resp.json()
                        self._save_local_config(config)
                        logger.info(f"✓ 成功从服务器拉取配置: {config}")
                    else:
                        logger.warning(f"⚠ 服务器返回错误: {resp.status}")
                        # 如果拉取失败，创建空配置
                        self._save_local_config({"favorites": []})
        except Exception as e:
            logger.error(f"✗ 初始化配置失败: {e}")
            # 创建空配置
            self._save_local_config({"favorites": []})
    
    def _load_local_config(self) -> dict:
        """加载本地配置文件"""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            else:
                return {"favorites": []}
        except Exception as e:
            logger.error(f"✗ 读取本地配置失败: {e}")
            return {"favorites": []}
    
    def _save_local_config(self, config: dict):
        """保存配置到本地文件"""
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
            logger.info(f"✓ 本地配置已保存")
        except Exception as e:
            logger.error(f"✗ 保存本地配置失败: {e}")
    
    async def _upload_config(self) -> tuple[bool, str]:
        """上传配置到服务器"""
        try:
            config = self._load_local_config()
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.server_url}/config",
                    json=config,
                    headers={'Content-Type': 'application/json'}
                ) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        return True, "配置已同步到服务器！"
                    else:
                        return False, f"服务器返回错误: {resp.status}"
        except Exception as e:
            logger.error(f"✗ 上传配置失败: {e}")
            return False, f"上传失败: {str(e)}"

    @filter.command("关注列表")
    async def fav_list_show(self, event: AstrMessageEvent):
        """显示当前关注列表"""
        config = self._load_local_config()
        favorites = config.get("favorites", [])
        
        if not favorites:
            msg = "当前没有关注列表"
        else:
            msg = "当前关注列表：\n"
            for idx, location in enumerate(favorites, 1):
                msg += f"{idx}. {location}\n"
            msg = msg.strip()
        
        yield event.plain_result(msg)

    @filter.command("增加")
    async def fav_list_add(self, event: AstrMessageEvent):
        """添加关注地点"""
        # 解析参数
        args = event.message_str.replace("增加", "").strip().split()
        index = int(args[0]) if args and args[0].isdigit() else 0
        
        # 如果直接输入了序号，直接添加
        if index and 1 <= index <= len(self.locations):
            location = self.locations[index - 1]
            config = self._load_local_config()
            favorites = config.get("favorites", [])
            
            if location in favorites:
                yield event.plain_result(f"「{location}」已经在关注列表中了！")
            else:
                favorites.append(location)
                config["favorites"] = favorites
                self._save_local_config(config)
                yield event.plain_result(f"✓ 已添加「{location}」到关注列表\n别忘了使用「保存」命令同步到服务器哦！")
        
        # 没有输入序号，显示地点列表等待用户选择
        else:
            # 显示地点列表
            location_list = "请选择要添加的地点（回复序号）：\n"
            for idx, location in enumerate(self.locations, 1):
                location_list += f"{idx}. {location}\n"
            location_list = location_list.strip()
            
            await event.send(event.plain_result(location_list))
            
            # 等待用户输入序号
            @session_waiter(timeout=self.timeout, record_history_chains=False)
            async def location_waiter(controller: SessionController, event: AstrMessageEvent):
                user_input = event.message_str.strip()
                
                if not user_input.isdigit():
                    await event.send(event.plain_result("请输入有效的序号！"))
                    return
                
                index = int(user_input)
                if index < 1 or index > len(self.locations):
                    await event.send(event.plain_result(f"序号超出范围，请输入1-{len(self.locations)}之间的数字！"))
                    return
                
                location = self.locations[index - 1]
                config = self._load_local_config()
                favorites = config.get("favorites", [])
                
                if location in favorites:
                    await event.send(event.plain_result(f"「{location}」已经在关注列表中了！"))
                else:
                    favorites.append(location)
                    config["favorites"] = favorites
                    self._save_local_config(config)
                    await event.send(event.plain_result(f"✓ 已添加「{location}」到关注列表\n别忘了使用「保存」命令同步到服务器哦！"))
                
                controller.stop()
            
            try:
                await location_waiter(event)
            except TimeoutError:
                yield event.plain_result("操作超时！")
            except Exception as e:
                logger.error(traceback.format_exc())
                logger.error(f"添加关注失败: {e}")
                yield event.plain_result(f"操作失败: {str(e)}")
        
        event.stop_event()

    @filter.command("删除")
    async def fav_list_del(self, event: AstrMessageEvent):
        """删除关注地点"""
        config = self._load_local_config()
        favorites = config.get("favorites", [])
        
        if not favorites:
            yield event.plain_result("当前关注列表为空，没有可删除的项目！")
            return
        
        # 解析参数
        args = event.message_str.replace("删除", "").strip().split()
        index = int(args[0]) if args and args[0].isdigit() else 0
        
        # 如果直接输入了序号，直接删除
        if index and 1 <= index <= len(favorites):
            removed_location = favorites.pop(index - 1)
            config["favorites"] = favorites
            self._save_local_config(config)
            yield event.plain_result(f"✓ 已删除「{removed_location}」\n别忘了使用「保存」命令同步到服务器哦！")
        
        # 没有输入序号，显示当前关注列表等待用户选择
        else:
            # 显示当前关注列表
            fav_list = "请选择要删除的地点（回复序号）：\n"
            for idx, location in enumerate(favorites, 1):
                fav_list += f"{idx}. {location}\n"
            fav_list = fav_list.strip()
            
            await event.send(event.plain_result(fav_list))
            
            # 等待用户输入序号
            @session_waiter(timeout=self.timeout, record_history_chains=False)
            async def delete_waiter(controller: SessionController, event: AstrMessageEvent):
                user_input = event.message_str.strip()
                
                if not user_input.isdigit():
                    await event.send(event.plain_result("请输入有效的序号！"))
                    return
                
                index = int(user_input)
                if index < 1 or index > len(favorites):
                    await event.send(event.plain_result(f"序号超出范围，请输入1-{len(favorites)}之间的数字！"))
                    return
                
                removed_location = favorites.pop(index - 1)
                config["favorites"] = favorites
                self._save_local_config(config)
                await event.send(event.plain_result(f"✓ 已删除「{removed_location}」\n别忘了使用「保存」命令同步到服务器哦！"))
                
                controller.stop()
            
            try:
                await delete_waiter(event)
            except TimeoutError:
                yield event.plain_result("操作超时！")
            except Exception as e:
                logger.error(traceback.format_exc())
                logger.error(f"删除关注失败: {e}")
                yield event.plain_result(f"操作失败: {str(e)}")
        
        event.stop_event()

    @filter.command("清空")
    async def fav_list_clr(self, event: AstrMessageEvent):
        """清空关注列表"""
        config = self._load_local_config()
        favorites = config.get("favorites", [])
        
        if not favorites:
            msg = "关注列表已经是空的了！"
        else:
            config["favorites"] = []
            self._save_local_config(config)
            msg = "✓ 已清空关注列表\n别忘了使用「保存」命令同步到服务器哦！"
        
        yield event.plain_result(msg)

    @filter.command("保存")
    async def fav_list_save(self, event: AstrMessageEvent):
        """保存配置到服务器"""
        success, message = await self._upload_config()
        
        if success:
            msg = f"✓ {message}"
        else:
            msg = f"✗ {message}"
        
        yield event.plain_result(msg)

    async def terminate(self):
        """插件卸载时的清理工作"""
        logger.info("nikki_s 插件已卸载")
