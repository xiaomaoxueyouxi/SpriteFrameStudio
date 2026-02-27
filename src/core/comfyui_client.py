"""ComfyUI API客户端"""
import json
import uuid
import asyncio
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional, Callable, Dict, Any
import requests
import websockets


def log(message: str):
    """带时间戳的控制台日志输出"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"[{timestamp}] {message}")

from src.utils.i2v_config import (
    COMFYUI_URL, COMFYUI_WS_URL,
    WORKFLOW_TEMPLATE_PATH,
    GENERATION_MODE_I2V, GENERATION_MODE_FLF2V,
    DEFAULT_WIDTH, DEFAULT_HEIGHT, DEFAULT_FRAMES, DEFAULT_STEPS,
    DEFAULT_POSITIVE_PROMPT, DEFAULT_NEGATIVE_PROMPT,
    DEFAULT_LORA_NAME, DEFAULT_LORA_STRENGTH,
    SAMPLER_NAME, SCHEDULER
)


class ComfyUIClient:
    """ComfyUI API客户端，用于与ComfyUI服务器通信"""
    
    def __init__(self, client_id: str = None):
        self.client_id = client_id or f"spriteframe_{uuid.uuid4().hex[:8]}"
        self.base_url = COMFYUI_URL
        self.ws_url = COMFYUI_WS_URL
        self._ws = None
        self._ws_thread = None
        self._running = False
        self._progress_callback: Optional[Callable] = None
        self._status_callback: Optional[Callable] = None
        
    def check_connection(self) -> bool:
        """检查ComfyUI服务器连接状态"""
        try:
            response = requests.get(f"{self.base_url}/system_stats", timeout=5)
            return response.status_code == 200
        except:
            return False
    
    def get_loras(self) -> list:
        """获取可用的LoRA模型列表"""
        try:
            response = requests.get(f"{self.base_url}/models/loras", timeout=10)
            if response.status_code == 200:
                return response.json()
        except:
            pass
        return []
    
    def upload_image(self, image_path: str) -> Optional[str]:
        """
        上传图片到ComfyUI input目录
        
        Args:
            image_path: 图片路径
            
        Returns:
            上传后的文件名，失败返回None
        """
        try:
            file_size = Path(image_path).stat().st_size / 1024  # KB
            log(f"上传图片: {Path(image_path).name} ({file_size:.1f} KB)")
            with open(image_path, 'rb') as f:
                files = {'image': (Path(image_path).name, f, 'image/png')}
                data = {'overwrite': 'true'}
                response = requests.post(
                    f"{self.base_url}/upload/image",
                    files=files,
                    data=data,
                    timeout=30
                )
                if response.status_code == 200:
                    result = response.json()
                    uploaded_name = result.get('name', Path(image_path).name)
                    log(f"上传成功: {uploaded_name}")
                    return uploaded_name
                else:
                    log(f"上传失败: HTTP {response.status_code}")
        except Exception as e:
            log(f"上传图片异常: {e}")
        return None
    
    def load_workflow_template(self) -> Optional[Dict]:
        """加载工作流模板（统一使用FLF2V模板）"""
        try:
            if WORKFLOW_TEMPLATE_PATH.exists():
                with open(WORKFLOW_TEMPLATE_PATH, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            print(f"加载工作流模板失败: {e}")
        return None
    
    def build_workflow(
        self,
        start_image_name: str,
        end_image_name: str = None,
        mode: str = GENERATION_MODE_I2V,
        positive_prompt: str = DEFAULT_POSITIVE_PROMPT,
        negative_prompt: str = DEFAULT_NEGATIVE_PROMPT,
        width: int = DEFAULT_WIDTH,
        height: int = DEFAULT_HEIGHT,
        frames: int = DEFAULT_FRAMES,
        steps: int = DEFAULT_STEPS,
        seed: int = -1,
        lora_name: str = DEFAULT_LORA_NAME,
        lora_strength: float = DEFAULT_LORA_STRENGTH,
    ) -> Dict:
        """
        构建工作流JSON
        
        统一使用FLF2V模板，I2V模式时尾帧设置为首帧相同
        
        Args:
            start_image_name: 首帧图片文件名
            end_image_name: 尾帧图片文件名（I2V模式可省略，会自动设为首帧）
            mode: 生成模式，i2v或flf2v
            positive_prompt: 正向提示词
            negative_prompt: 负向提示词
            width: 输出宽度
            height: 输出高度
            frames: 帧数
            steps: 采样步数
            seed: 随机种子，-1表示随机
            lora_name: LoRA模型名称
            lora_strength: LoRA强度
            
        Returns:
            工作流JSON字典
        """
        workflow = self.load_workflow_template()
        if not workflow:
            raise ValueError("无法加载工作流模板")
        
        # 生成随机种子
        import random
        actual_seed = seed if seed > 0 else random.randint(0, 2**32 - 1)
        
        # I2V模式时，尾帧设置为首帧相同
        actual_end_image = end_image_name if end_image_name else start_image_name
        
        # 节点52: 加载首帧图片
        workflow["52"]["inputs"]["image"] = start_image_name
        
        # 节点72: 加载尾帧图片（I2V模式时与首帧相同）
        workflow["72"]["inputs"]["image"] = actual_end_image
        
        # 节点6: 正向提示词
        workflow["6"]["inputs"]["text"] = positive_prompt
        
        # 节点7: 负向提示词（原项目逻辑：默认与正向相同）
        actual_negative = negative_prompt if negative_prompt else positive_prompt
        workflow["7"]["inputs"]["text"] = actual_negative
        
        # 保留cfg值不修改（模板默认3.5）
        # workflow["101"]["inputs"]["cfg"] = 3.5
        # workflow["102"]["inputs"]["cfg"] = 3.5
        
        # 节点83: 帧数和尺寸
        workflow["83"]["inputs"]["length"] = frames
        workflow["83"]["inputs"]["width"] = width
        workflow["83"]["inputs"]["height"] = height
        
        # 节点101, 102: 采样步数和种子
        workflow["101"]["inputs"]["steps"] = steps
        workflow["101"]["inputs"]["noise_seed"] = actual_seed
        workflow["102"]["inputs"]["steps"] = steps
        
        # 节点111, 112: LoRA配置
        # 如果不选择风格LoRA，将强度设为0（跳过风格LoRA）
        if lora_name and lora_name != "(无风格LoRA)":
            workflow["111"]["inputs"]["lora_name"] = lora_name
            workflow["111"]["inputs"]["strength_model"] = lora_strength
            workflow["112"]["inputs"]["lora_name"] = lora_name
            workflow["112"]["inputs"]["strength_model"] = lora_strength
        else:
            # 不使用风格LoRA，强度设为0
            workflow["111"]["inputs"]["strength_model"] = 0
            workflow["112"]["inputs"]["strength_model"] = 0
            lora_name = "(无)"
        
        # 调试：打印关键参数
        log(f"工作流参数:")
        log(f"  首帧: {start_image_name}, 尾帧: {actual_end_image}")
        log(f"  分辨率: {width}x{height}, 帧数: {frames}, 步数: {steps}")
        log(f"  种子: {actual_seed}")
        log(f"  正向提示词: {positive_prompt[:50]}..." if len(positive_prompt) > 50 else f"  正向提示词: {positive_prompt}")
        log(f"  负向提示词: {actual_negative[:50]}..." if len(actual_negative) > 50 else f"  负向提示词: {actual_negative}")
        log(f"  风格LoRA: {lora_name}")
        log(f"  风格LoRA(节点111): {workflow['111']['inputs']['lora_name']} (强度: {workflow['111']['inputs']['strength_model']})")
        log(f"  风格LoRA(节点112): {workflow['112']['inputs']['lora_name']} (强度: {workflow['112']['inputs']['strength_model']})")
        log(f"  基础LoRA(节点94): {workflow['94']['inputs']['lora_name']} (强度: {workflow['94']['inputs']['strength_model']})")
        log(f"  基础LoRA(节点95): {workflow['95']['inputs']['lora_name']} (强度: {workflow['95']['inputs']['strength_model']})")
        
        # 保存实际提交的工作流供调试
        import json
        debug_path = Path(__file__).parent.parent.parent / "debug_workflow.json"
        with open(debug_path, 'w', encoding='utf-8') as f:
            json.dump(workflow, f, ensure_ascii=False, indent=2)
        log(f"调试: 工作流已保存到 {debug_path}")
        
        return workflow
    
    def queue_prompt(self, workflow: Dict) -> Optional[str]:
        """
        提交工作流到队列
        
        Args:
            workflow: 工作流JSON
            
        Returns:
            prompt_id，失败返回None
        """
        try:
            log("正在提交工作流...")
            payload = {
                "prompt": workflow,
                "client_id": self.client_id
            }
            response = requests.post(
                f"{self.base_url}/prompt",
                json=payload,
                timeout=30
            )
            if response.status_code == 200:
                result = response.json()
                prompt_id = result.get('prompt_id')
                log(f"工作流已入队, prompt_id: {prompt_id}")
                return prompt_id
            else:
                log(f"提交失败: HTTP {response.status_code} - {response.text[:200]}")
        except Exception as e:
            log(f"提交工作流异常: {e}")
        return None
    
    def get_history(self, prompt_id: str) -> Optional[Dict]:
        """获取执行历史"""
        try:
            response = requests.get(
                f"{self.base_url}/history/{prompt_id}",
                timeout=10
            )
            if response.status_code == 200:
                return response.json()
        except Exception as e:
            print(f"获取历史失败: {e}")
        return None
    
    def get_output_video(self, filename: str, output_dir: str = "output") -> Optional[bytes]:
        """
        获取生成的视频文件
        
        Args:
            filename: 文件名
            output_dir: 输出目录类型
            
        Returns:
            视频文件二进制数据
        """
        try:
            params = {"filename": filename, "type": output_dir}
            response = requests.get(
                f"{self.base_url}/view",
                params=params,
                timeout=60
            )
            if response.status_code == 200:
                return response.content
        except Exception as e:
            print(f"获取视频失败: {e}")
        return None
    
    def interrupt(self):
        """中断当前执行"""
        try:
            requests.post(f"{self.base_url}/interrupt", timeout=5)
        except:
            pass
    
    def clear_queue(self):
        """清空队列"""
        try:
            requests.post(
                f"{self.base_url}/queue",
                json={"clear": True},
                timeout=5
            )
        except:
            pass
    
    def start_ws_listener(
        self,
        progress_callback: Callable[[int, int, Optional[str]], None] = None,
        status_callback: Callable[[str], None] = None
    ):
        """
        启动WebSocket监听线程
        
        Args:
            progress_callback: 进度回调 (current, total, node_id)
            status_callback: 状态回调 (status_message)
        """
        self._progress_callback = progress_callback
        self._status_callback = status_callback
        self._running = True
        
        def ws_loop():
            asyncio.run(self._ws_listen())
        
        self._ws_thread = threading.Thread(target=ws_loop, daemon=True)
        self._ws_thread.start()
    
    def stop_ws_listener(self):
        """停止WebSocket监听"""
        self._running = False
        self._ws = None
    
    async def _ws_listen(self):
        """WebSocket监听协程"""
        try:
            uri = f"{self.ws_url}?clientId={self.client_id}"
            async with websockets.connect(uri) as ws:
                self._ws = ws
                if self._status_callback:
                    self._status_callback("已连接到ComfyUI")
                
                while self._running:
                    try:
                        message = await asyncio.wait_for(ws.recv(), timeout=1.0)
                        data = json.loads(message)
                        await self._handle_ws_message(data)
                    except asyncio.TimeoutError:
                        continue
                    except websockets.ConnectionClosed:
                        break
        except Exception as e:
            if self._status_callback:
                self._status_callback(f"WebSocket连接失败: {e}")
    
    async def _handle_ws_message(self, data: Dict):
        """处理WebSocket消息"""
        msg_type = data.get('type')
        msg_data = data.get('data', {})
        
        if msg_type == 'progress':
            # 进度更新
            if self._progress_callback:
                value = msg_data.get('value', 0)
                max_value = msg_data.get('max', 100)
                node = msg_data.get('node')
                self._progress_callback(value, max_value, node)
        
        elif msg_type == 'executing':
            # 执行状态
            node = msg_data.get('node')
            if node:
                if self._status_callback:
                    self._status_callback(f"正在执行节点: {node}")
            else:
                # node为None表示执行完成
                if self._status_callback:
                    self._status_callback("执行完成")
        
        elif msg_type == 'execution_error':
            # 执行错误
            if self._status_callback:
                error_msg = msg_data.get('exception_message', '未知错误')
                self._status_callback(f"执行错误: {error_msg}")
        
        elif msg_type == 'status':
            # 队列状态
            status = msg_data.get('status', {})
            remaining = status.get('remaining', 0)
            if self._status_callback and remaining > 0:
                self._status_callback(f"队列中还有 {remaining} 个任务")
