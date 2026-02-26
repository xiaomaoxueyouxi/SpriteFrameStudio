"""I2V视频生成工作线程"""
import time
from datetime import datetime
from typing import Optional
from pathlib import Path
from PySide6.QtCore import QThread, Signal

from src.core.comfyui_client import ComfyUIClient


def log(message: str):
    """带时间戳的控制台日志输出"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"[{timestamp}] {message}")
from src.utils.i2v_config import (
    GENERATION_MODE_I2V, GENERATION_MODE_FLF2V,
    DEFAULT_WIDTH, DEFAULT_HEIGHT, DEFAULT_FRAMES, DEFAULT_STEPS,
    DEFAULT_POSITIVE_PROMPT, DEFAULT_NEGATIVE_PROMPT,
    DEFAULT_LORA_NAME, DEFAULT_LORA_STRENGTH
)


class I2VWorker(QThread):
    """I2V视频生成工作线程"""
    
    # 信号定义
    progress = Signal(int, int, str)  # current, total, status_message
    status_changed = Signal(str)  # status_message
    finished = Signal(str, str)  # video_path, prompt_id (成功时)
    error = Signal(str)  # error_message
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._client = ComfyUIClient()
        self._cancelled = False
        
        # 生成参数
        self.mode: str = GENERATION_MODE_I2V
        self.start_image_path: str = ""
        self.end_image_path: str = ""  # FLF2V模式需要
        self.positive_prompt: str = DEFAULT_POSITIVE_PROMPT
        self.negative_prompt: str = DEFAULT_NEGATIVE_PROMPT
        self.width: int = DEFAULT_WIDTH
        self.height: int = DEFAULT_HEIGHT
        self.frames: int = DEFAULT_FRAMES
        self.steps: int = DEFAULT_STEPS
        self.seed: int = -1
        self.lora_name: str = DEFAULT_LORA_NAME
        self.lora_strength: float = DEFAULT_LORA_STRENGTH
        self.output_dir: str = ""  # 输出目录
        
        # 当前prompt_id
        self._prompt_id: Optional[str] = None
    
    def set_parameters(
        self,
        start_image_path: str,
        end_image_path: str = "",
        mode: str = GENERATION_MODE_I2V,
        positive_prompt: str = None,
        negative_prompt: str = None,
        width: int = None,
        height: int = None,
        frames: int = None,
        steps: int = None,
        seed: int = None,
        lora_name: str = None,
        lora_strength: float = None,
        output_dir: str = ""
    ):
        """设置生成参数"""
        self.mode = mode
        self.start_image_path = start_image_path
        self.end_image_path = end_image_path
        self.positive_prompt = positive_prompt or DEFAULT_POSITIVE_PROMPT
        self.negative_prompt = negative_prompt or DEFAULT_NEGATIVE_PROMPT
        self.width = width or DEFAULT_WIDTH
        self.height = height or DEFAULT_HEIGHT
        self.frames = frames or DEFAULT_FRAMES
        self.steps = steps or DEFAULT_STEPS
        self.seed = seed if seed is not None else -1
        self.lora_name = lora_name or DEFAULT_LORA_NAME
        self.lora_strength = lora_strength if lora_strength is not None else DEFAULT_LORA_STRENGTH
        self.output_dir = output_dir
    
    def run(self):
        """执行视频生成"""
        try:
            self._cancelled = False
            
            log("=" * 50)
            log("开始视频生成任务")
            log(f"生成模式: {self.mode}")
            log(f"首帧图片: {self.start_image_path}")
            if self.end_image_path:
                log(f"尾帧图片: {self.end_image_path}")
            log(f"分辨率: {self.width}x{self.height}, 帧数: {self.frames}, 步数: {self.steps}")
            log(f"种子: {self.seed if self.seed > 0 else '随机'}, LoRA: {self.lora_name} (强度: {self.lora_strength})")
            log("=" * 50)
            
            # 1. 检查连接
            log("[步骤1/6] 检查ComfyUI连接...")
            self.status_changed.emit("正在连接ComfyUI...")
            if not self._client.check_connection():
                log("❌ 无法连接到ComfyUI服务器")
                self.error.emit("无法连接到ComfyUI服务器，请确保ComfyUI已启动")
                return
            log("✓ ComfyUI连接成功")
            
            if self._cancelled:
                return
            
            # 2. 上传首帧图片
            log("[步骤2/6] 上传首帧图片...")
            self.status_changed.emit("正在上传首帧图片...")
            start_image_name = self._client.upload_image(self.start_image_path)
            if not start_image_name:
                log("❌ 上传首帧图片失败")
                self.error.emit("上传首帧图片失败")
                return
            log(f"✓ 首帧上传成功: {start_image_name}")
            
            if self._cancelled:
                return
            
            # 3. 如果有尾帧图片，上传尾帧（FLF2V模式）
            end_image_name = None
            if self.end_image_path:
                log("[步骤3/6] 上传尾帧图片...")
                self.status_changed.emit("正在上传尾帧图片...")
                end_image_name = self._client.upload_image(self.end_image_path)
                if not end_image_name:
                    log("❌ 上传尾帧图片失败")
                    self.error.emit("上传尾帧图片失败")
                    return
                log(f"✓ 尾帧上传成功: {end_image_name}")
            else:
                log("[步骤3/6] 跳过尾帧上传 (I2V模式)")
            
            if self._cancelled:
                return
            
            # 4. 构建工作流
            log("[步骤4/6] 构建工作流...")
            self.status_changed.emit("正在构建工作流...")
            workflow = self._client.build_workflow(
                start_image_name=start_image_name,
                end_image_name=end_image_name,
                mode=self.mode,
                positive_prompt=self.positive_prompt,
                negative_prompt=self.negative_prompt,
                width=self.width,
                height=self.height,
                frames=self.frames,
                steps=self.steps,
                seed=self.seed,
                lora_name=self.lora_name,
                lora_strength=self.lora_strength
            )
            log("✓ 工作流构建完成")
            
            if self._cancelled:
                return
            
            # 5. 提交工作流
            log("[步骤5/6] 提交工作流到ComfyUI队列...")
            self.status_changed.emit("正在提交任务...")
            self._prompt_id = self._client.queue_prompt(workflow)
            if not self._prompt_id:
                log("❌ 提交工作流失败")
                self.error.emit("提交工作流失败")
                return
            log(f"✓ 工作流已提交, prompt_id: {self._prompt_id}")
            
            if self._cancelled:
                return
            
            # 6. 等待执行完成
            log("[步骤6/6] 等待视频生成...")
            log("(这可能需要几分钟时间，请耐心等待)")
            self.status_changed.emit("正在生成视频...")
            video_path = self._wait_for_completion()
            
            if video_path:
                log("=" * 50)
                log(f"✓ 视频生成成功!")
                log(f"保存路径: {video_path}")
                log("=" * 50)
                self.finished.emit(video_path, self._prompt_id)
            elif not self._cancelled:
                log("❌ 获取生成结果失败")
                self.error.emit("获取生成结果失败")
                
        except Exception as e:
            log(f"❌ 生成过程出错: {str(e)}")
            self.error.emit(f"生成过程出错: {str(e)}")
    
    def _wait_for_completion(self, timeout: int = 600) -> Optional[str]:
        """
        等待生成完成
        
        Args:
            timeout: 超时时间（秒）
            
        Returns:
            生成的视频路径，失败返回None
        """
        start_time = time.time()
        check_interval = 3  # 每3秒检查一次
        last_log_time = 0
        check_count = 0
        
        log(f"开始轮询任务状态 (超时: {timeout}秒)")
        
        while time.time() - start_time < timeout:
            if self._cancelled:
                log("任务已取消")
                return None
            
            check_count += 1
            history = self._client.get_history(self._prompt_id)
            
            if history and self._prompt_id in history:
                prompt_history = history[self._prompt_id]
                
                # 检查是否完成
                outputs = prompt_history.get('outputs', {})
                if outputs:
                    log(f"✓ 任务执行完成，正在获取输出文件...")
                    # 查找视频输出
                    for node_id, node_output in outputs.items():
                        videos = node_output.get('videos', [])
                        if videos:
                            video_info = videos[0]
                            filename = video_info.get('filename')
                            subfolder = video_info.get('subfolder', '')
                            
                            if filename:
                                log(f"找到视频文件: {filename}")
                                log("正在下载视频...")
                                # 下载视频
                                video_data = self._client.get_output_video(
                                    filename,
                                    video_info.get('type', 'output')
                                )
                                if video_data:
                                    # 保存到本地
                                    if self.output_dir:
                                        save_path = Path(self.output_dir) / filename
                                    else:
                                        save_path = Path(self.start_image_path).parent / filename
                                    
                                    save_path.parent.mkdir(parents=True, exist_ok=True)
                                    with open(save_path, 'wb') as f:
                                        f.write(video_data)
                                    
                                    log(f"✓ 视频已保存 ({len(video_data) / 1024 / 1024:.2f} MB)")
                                    return str(save_path)
                                else:
                                    log("❌ 下载视频失败")
            
            # 更新进度（模拟）
            elapsed = int(time.time() - start_time)
            self.progress.emit(elapsed, timeout, f"生成中... {elapsed}秒")
            
            # 每10秒输出一次状态
            if elapsed - last_log_time >= 10:
                log(f"生成中... 已等待 {elapsed} 秒 (检查次数: {check_count})")
                last_log_time = elapsed
            
            time.sleep(check_interval)
        
        log(f"❌ 任务超时 ({timeout}秒)")
        return None
    
    def cancel(self):
        """取消生成"""
        self._cancelled = True
        if self._prompt_id:
            self._client.interrupt()
        self.status_changed.emit("已取消")
    
    def get_client(self) -> ComfyUIClient:
        """获取ComfyUI客户端实例"""
        return self._client
