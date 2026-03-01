"""SmoothMix视频生成工作线程"""
import time
import random
import json
import shutil
import gc
from datetime import datetime
from typing import Optional, Dict, List
from pathlib import Path
from PySide6.QtCore import QThread, Signal
import requests
import threading
import asyncio
import websockets

from utils.smoothmix_config import (
    COMFYUI_URL, COMFYUI_WS_URL, SMOOTHMIX_DIR, SMOOTHMIX_OUTPUT_DIR
)


# 工作流类型
WORKFLOW_SMOOTHMIX = "smoothmix"  # SmoothMix人物版
WORKFLOW_GENERIC = "generic"      # 通用版


class SmoothMixTask:
    """单个生成任务"""
    def __init__(self, task_id: int, start_image: str, end_image: str = "", 
                 prompt: str = "", negative_prompt: str = "", width: int = 368, height: int = 704,
                 frames: int = 33, fps: int = 16, steps: int = 4, seed: int = -1,
                 sage_attention: bool = False, workflow_type: str = WORKFLOW_SMOOTHMIX):
        self.task_id = task_id
        self.start_image = start_image
        self.end_image = end_image or start_image
        self.prompt = prompt
        self.negative_prompt = negative_prompt
        self.width = width
        self.height = height
        self.frames = frames
        self.fps = fps
        self.steps = steps
        self.seed = seed if seed > 0 else random.randint(0, 2**31 - 1)
        self.sage_attention = sage_attention
        self.workflow_type = workflow_type
        self.status = "pending"
        self.prompt_id: Optional[str] = None
        self.output_path: Optional[str] = None
        self.error_msg: Optional[str] = None
        self.start_time: Optional[float] = None
        self.end_time: Optional[float] = None
        self.create_time: float = time.time()  # 创建时间
    
    def get_elapsed_time(self) -> str:
        """获取耗时"""
        if self.start_time and self.end_time:
            elapsed = self.end_time - self.start_time
            minutes = int(elapsed // 60)
            seconds = int(elapsed % 60)
            return f"{minutes}分{seconds}秒"
        elif self.start_time:
            elapsed = time.time() - self.start_time
            minutes = int(elapsed // 60)
            seconds = int(elapsed % 60)
            return f"{minutes}分{seconds}秒"
        return ""
    
    def get_create_time_str(self) -> str:
        """获取创建时间字符串"""
        dt = datetime.fromtimestamp(self.create_time)
        return dt.strftime("%m-%d %H:%M")
    
    def to_dict(self) -> dict:
        """序列化为字典"""
        return {
            "task_id": self.task_id,
            "start_image": self.start_image,
            "end_image": self.end_image,
            "prompt": self.prompt,
            "negative_prompt": self.negative_prompt,
            "width": self.width,
            "height": self.height,
            "frames": self.frames,
            "fps": self.fps,
            "steps": self.steps,
            "seed": self.seed,
            "sage_attention": self.sage_attention,
            "workflow_type": self.workflow_type,
            "status": self.status,
            "output_path": self.output_path,
            "error_msg": self.error_msg,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "create_time": self.create_time
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "SmoothMixTask":
        """从字典反序列化"""
        task = cls(
            task_id=data["task_id"],
            start_image=data["start_image"],
            end_image=data.get("end_image", ""),
            prompt=data.get("prompt", ""),
            negative_prompt=data.get("negative_prompt", ""),
            width=data.get("width", 368),
            height=data.get("height", 704),
            frames=data.get("frames", 33),
            fps=data.get("fps", 16),
            steps=data.get("steps", 4),
            seed=data.get("seed", -1),
            sage_attention=data.get("sage_attention", False),
            workflow_type=data.get("workflow_type", WORKFLOW_SMOOTHMIX)
        )
        task.status = data.get("status", "pending")
        task.output_path = data.get("output_path")
        task.error_msg = data.get("error_msg")
        task.start_time = data.get("start_time")
        task.end_time = data.get("end_time")
        task.create_time = data.get("create_time", time.time())
        return task


class SmoothMixWorker(QThread):
    """SmoothMix视频生成工作线程"""
    
    task_started = Signal(int, str)
    task_progress = Signal(int, int, int, str)
    task_completed = Signal(int, str)
    task_failed = Signal(int, str)
    queue_changed = Signal(int)
    status_changed = Signal(str)
    log_message = Signal(str)  # 新增：日志信号
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._cancelled = False
        self._tasks: List[SmoothMixTask] = []
        self._current_task: Optional[SmoothMixTask] = None
        self._task_counter = 0
        self._ws = None
        self._running = False
        self.base_url = COMFYUI_URL
        self.ws_url = COMFYUI_WS_URL
        self.client_id = f"smoothmix_{random.randint(1000, 9999)}"
        self.output_dir = Path(__file__).parent.parent.parent / "output" / "smoothmix"
        self.comfyui_output_dir = SMOOTHMIX_OUTPUT_DIR  # ComfyUI输出目录
        self._queue_start_time: Optional[float] = None
        self._completed_count = 0
        # 用于WebSocket通知任务完成
        self._execution_complete = threading.Event()
        self._execution_error: Optional[str] = None
        # 追踪节点执行进度
        self._executed_nodes: List[str] = []
        self._current_prompt_id: Optional[str] = None
        # 任务队列文件路径
        self._queue_file = Path(__file__).parent.parent.parent / "output" / "smoothmix_queue.json"
        # 加载保存的任务
        self._load_tasks()
    
    def _log(self, message: str):
        """输出日志到UI"""
        # print 可能导致Qt弹框闪退，禁用
        self.log_message.emit(message)  # 发送不带时间戳的消息
        
    def add_task(self, start_image: str, end_image: str = "", prompt: str = "",
                 negative_prompt: str = "", width: int = 368, height: int = 704, frames: int = 33,
                 fps: int = 16, steps: int = 4, seed: int = -1, sage_attention: bool = False,
                 workflow_type: str = WORKFLOW_SMOOTHMIX) -> int:
        self._task_counter += 1
        task = SmoothMixTask(
            task_id=self._task_counter,
            start_image=start_image,
            end_image=end_image or start_image,
            prompt=prompt,
            negative_prompt=negative_prompt,
            width=width,
            height=height,
            frames=frames,
            fps=fps,
            steps=steps,
            seed=seed,
            sage_attention=sage_attention,
            workflow_type=workflow_type
        )
        self._tasks.append(task)
        self._save_tasks()  # 保存任务队列
        self.queue_changed.emit(len([t for t in self._tasks if t.status == "pending"]))
        self._log(f"任务 {task.task_id} 已添加到队列")
        return task.task_id
    
    def remove_task(self, task_id: int) -> bool:
        for i, task in enumerate(self._tasks):
            if task.task_id == task_id and task.status == "pending":
                self._tasks.pop(i)
                self._save_tasks()  # 保存任务队列
                self.queue_changed.emit(len([t for t in self._tasks if t.status == "pending"]))
                return True
        return False
    
    def clear_queue(self):
        self._tasks = [t for t in self._tasks if t.status in ("running", "completed", "failed")]
        self._save_tasks()
        self.queue_changed.emit(len([t for t in self._tasks if t.status == "pending"]))
    
    def get_queue_length(self) -> int:
        return len([t for t in self._tasks if t.status == "pending"])
    
    def get_all_tasks(self) -> List[SmoothMixTask]:
        return self._tasks.copy()
    
    def _save_tasks(self):
        """保存任务队列到文件"""
        try:
            self._queue_file.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "task_counter": self._task_counter,
                "tasks": [t.to_dict() for t in self._tasks]
            }
            with open(self._queue_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            pass  # 不用print，避免弹框闪退
    
    def _load_tasks(self):
        """从文件加载任务队列"""
        try:
            if self._queue_file.exists():
                with open(self._queue_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                self._task_counter = data.get("task_counter", 0)
                # 加载时去重（按task_id）
                seen_ids = set()
                unique_tasks = []
                for t in data.get("tasks", []):
                    task = SmoothMixTask.from_dict(t)
                    if task.task_id not in seen_ids:
                        seen_ids.add(task.task_id)
                        # 将running状态重置为pending（程序重启后需要重新执行）
                        if task.status == "running":
                            task.status = "pending"
                            task.start_time = None
                        unique_tasks.append(task)
                self._tasks = unique_tasks
                # 保存去重后的结果
                if len(unique_tasks) != len(data.get("tasks", [])):
                    self._save_tasks()
                # 记录加载结果（延迟发送，因为信号可能还没连接）
                self._loaded_task_count = len(self._tasks)
            else:
                self._loaded_task_count = 0
        except Exception as e:
            self._tasks = []
            self._task_counter = 0
            self._loaded_task_count = -1  # 表示加载失败
    
    def delete_task(self, task_id: int) -> bool:
        """删除指定任务"""
        for i, task in enumerate(self._tasks):
            if task.task_id == task_id:
                if task.status == "running":
                    return False  # 不能删除正在执行的任务
                self._tasks.pop(i)
                self._save_tasks()
                self.queue_changed.emit(self.get_queue_length())
                return True
        return False
    
    def check_connection(self) -> bool:
        try:
            response = requests.get(f"{self.base_url}/system_stats", timeout=5)
            return response.status_code == 200
        except:
            return False
    
    def upload_image(self, image_path: str) -> Optional[str]:
        try:
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
                    return result.get('name', Path(image_path).name)
        except Exception as e:
            self._log(f"上传图片失败: {e}")
        return None
    
    def load_workflow(self, workflow_type: str = WORKFLOW_SMOOTHMIX) -> Optional[Dict]:
        """加载工作流文件"""
        if workflow_type == WORKFLOW_GENERIC:
            workflow_file = "Wan22-FLF2V-Generic.json"
        else:
            workflow_file = "SmoothMix-FLF2V.json"
        
        workflow_path = Path(__file__).parent.parent.parent / "workflows" / workflow_file
        if workflow_path.exists():
            with open(workflow_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        self._log(f"工作流文件不存在: {workflow_path}")
        return None
    
    def build_workflow(self, task: SmoothMixTask, start_image_name: str, end_image_name: str) -> Dict:
        workflow = self.load_workflow(task.workflow_type)
        if not workflow:
            raise ValueError("无法加载工作流模板")
        
        if task.workflow_type == WORKFLOW_GENERIC:
            # 通用版工作流节点映射
            workflow["52"]["inputs"]["image"] = start_image_name
            workflow["72"]["inputs"]["image"] = end_image_name
            workflow["6"]["inputs"]["text"] = task.prompt
            workflow["7"]["inputs"]["text"] = task.negative_prompt
            workflow["64"]["inputs"]["width"] = task.width
            workflow["64"]["inputs"]["height"] = task.height
            workflow["65"]["inputs"]["width"] = task.width
            workflow["65"]["inputs"]["height"] = task.height
            workflow["83"]["inputs"]["width"] = task.width
            workflow["83"]["inputs"]["height"] = task.height
            workflow["83"]["inputs"]["length"] = task.frames
            workflow["101"]["inputs"]["steps"] = task.steps * 2  # 通用版步数是总步数
            workflow["102"]["inputs"]["steps"] = task.steps * 2
            workflow["101"]["inputs"]["end_at_step"] = task.steps
            workflow["102"]["inputs"]["start_at_step"] = task.steps
            workflow["101"]["inputs"]["noise_seed"] = task.seed
            workflow["103"]["inputs"]["frame_rate"] = task.fps
            # Sage Attention
            sage_value = "auto" if task.sage_attention else "disabled"
            workflow["96"]["inputs"]["sage_attention"] = sage_value
            workflow["98"]["inputs"]["sage_attention"] = sage_value
        else:
            # SmoothMix版工作流节点映射
            workflow["237"]["inputs"]["image"] = start_image_name
            workflow["238"]["inputs"]["image"] = end_image_name
            workflow["241"]["inputs"]["text"] = task.prompt
            workflow["240"]["inputs"]["text"] = task.negative_prompt
            workflow["252"]["inputs"]["value"] = task.width
            workflow["253"]["inputs"]["value"] = task.height
            workflow["285"]["inputs"]["value"] = task.frames
            workflow["254"]["inputs"]["value"] = task.steps
            workflow["229"]["inputs"]["seed"] = task.seed
            workflow["236"]["inputs"]["frame_rate"] = task.fps
            # Sage Attention
            sage_value = "auto" if task.sage_attention else "disabled"
            workflow["265"]["inputs"]["sage_attention"] = sage_value
            workflow["266"]["inputs"]["sage_attention"] = sage_value
        
        return workflow
    
    def queue_prompt(self, workflow: Dict) -> Optional[str]:
        try:
            payload = {"prompt": workflow, "client_id": self.client_id}
            response = requests.post(f"{self.base_url}/prompt", json=payload, timeout=30)
            if response.status_code == 200:
                result = response.json()
                return result.get('prompt_id')
        except Exception as e:
            self._log(f"提交工作流失败: {e}")
        return None
    
    def get_history(self, prompt_id: str) -> Optional[Dict]:
        try:
            response = requests.get(f"{self.base_url}/history/{prompt_id}", timeout=10)
            if response.status_code == 200:
                return response.json()
        except:
            pass
        return None
    
    def interrupt(self):
        try:
            requests.post(f"{self.base_url}/interrupt", timeout=5)
        except:
            pass
    
    def _start_ws_listener(self):
        """启动WebSocket监听"""
        self._running = True
        
        def ws_thread():
            asyncio.run(self._ws_listen())
        
        self._ws_thread = threading.Thread(target=ws_thread, daemon=True)
        self._ws_thread.start()
    
    def _stop_ws_listener(self):
        self._running = False
    
    async def _ws_listen(self):
        uri = f"{self.ws_url}?clientId={self.client_id}"
        try:
            async with websockets.connect(uri, compression=None) as ws:
                self._log("WebSocket已连接，开始监听进度...")
                while self._running:
                    try:
                        msg = await asyncio.wait_for(ws.recv(), timeout=2.0)
                        if isinstance(msg, bytes):
                            continue  # 跳过二进制消息
                        data = json.loads(msg)
                        self._handle_ws_message(data)
                    except asyncio.TimeoutError:
                        continue
                    except json.JSONDecodeError:
                        continue
                    except Exception as e:
                        self._log(f"WebSocket消息错误: {e}")
        except Exception as e:
            self._log(f"WebSocket连接失败: {e}")
            self._log("将使用基础轮询模式")
    
    def _handle_ws_message(self, data: Dict):
        """处理WebSocket消息"""
        msg_type = data.get('type')
        msg_data = data.get('data', {})
        
        # 获取消息的prompt_id，检查是否是当前任务
        prompt_id = msg_data.get('prompt_id', '')
        
        if msg_type == 'progress':
            # ComfyUI的progress是采样进度
            value = msg_data.get('value', 0)
            max_value = msg_data.get('max', 100)
            if self._current_task and max_value > 0:
                pct = int(value / max_value * 100)
                self.task_progress.emit(
                    self._current_task.task_id, pct, 100,
                    f"采样进度: {value}/{max_value}"
                )
        elif msg_type == 'executing':
            node = msg_data.get('node')
            if node:
                # 记录执行的节点
                if node not in self._executed_nodes:
                    self._executed_nodes.append(node)
                self.status_changed.emit(f"执行节点: {node}")
            elif node is None and prompt_id == self._current_prompt_id:
                # node为None表示当前prompt执行完成
                self._log(f"收到执行完成信号 (prompt: {prompt_id[:8]}...)")
        elif msg_type == 'execution_start':
            self._log(f"ComfyUI任务开始: {prompt_id[:8] if prompt_id else ''}...")
            self._executed_nodes.clear()
        elif msg_type == 'execution_success':
            # 任务执行成功！
            if prompt_id == self._current_prompt_id:
                self._log(f"ComfyUI任务成功完成!")
                self._execution_complete.set()
        elif msg_type == 'execution_error':
            # 任务执行失败
            if prompt_id == self._current_prompt_id:
                error_msg = msg_data.get('exception_message', '执行出错')
                self._log(f"ComfyUI任务执行失败: {error_msg}")
                self._execution_error = error_msg
                self._execution_complete.set()
        elif msg_type == 'executed':
            # 单个节点执行完成
            node = msg_data.get('node', '')
            if node:
                self.status_changed.emit(f"节点 {node} 完成")
    
    def run(self):
        self._cancelled = False
        self._queue_start_time = time.time()
        self._completed_count = 0
        self._start_ws_listener()
        
        pending_count = len([t for t in self._tasks if t.status == "pending"])
        self._log(f"========== 开始处理队列 ({pending_count} 个任务) ==========")
        
        while not self._cancelled:
            self._current_task = None
            for task in self._tasks:
                if task.status == "pending":
                    self._current_task = task
                    break
            
            if not self._current_task:
                break
            
            self._execute_task(self._current_task)
            if self._current_task.status == "completed":
                self._completed_count += 1
        
        self._stop_ws_listener()
        
        # 显示队列总耗时
        if self._queue_start_time:
            total_elapsed = time.time() - self._queue_start_time
            mins = int(total_elapsed // 60)
            secs = int(total_elapsed % 60)
            self._log(f"========== 队列完成 ==========")
            self._log(f"  完成: {self._completed_count} 个任务, 总耗时: {mins}分{secs}秒")
    
    def _execute_task(self, task: SmoothMixTask):
        task.status = "running"
        task.start_time = time.time()
        
        # 显示任务信息
        prompt_preview = task.prompt[:50] + "..." if len(task.prompt) > 50 else task.prompt
        duration = task.frames / task.fps if task.fps > 0 else 0
        self._log(f"========== 任务 {task.task_id} 开始 ==========")
        self._log(f"  提示词: {prompt_preview or '(无)'}")
        self._log(f"  分辨率: {task.width}x{task.height}, 帧数: {task.frames}, FPS: {task.fps}, 时长: {duration:.1f}秒")
        self._log(f"  步数: {task.steps}, 种子: {task.seed}")
        self.task_started.emit(task.task_id, f"任务 {task.task_id}")
        
        try:
            if not self.check_connection():
                raise Exception("ComfyUI未连接")
            
            if self._cancelled:
                return
            
            self._log("上传首帧图片...")
            start_image_name = self.upload_image(task.start_image)
            if not start_image_name:
                raise Exception("上传首帧图片失败")
            
            if self._cancelled:
                return
            
            self._log("上传尾帧图片...")
            end_image_name = self.upload_image(task.end_image)
            if not end_image_name:
                raise Exception("上传尾帧图片失败")
            
            if self._cancelled:
                return
            
            self._log("构建工作流...")
            workflow = self.build_workflow(task, start_image_name, end_image_name)
            
            if self._cancelled:
                return
            
            self._log("提交工作流...")
            task.prompt_id = self.queue_prompt(workflow)
            if not task.prompt_id:
                raise Exception("提交工作流失败")
            
            self._log(f"prompt_id: {task.prompt_id}")
            
            # 设置当前prompt_id用于WebSocket匹配
            self._current_prompt_id = task.prompt_id
            self._execution_complete.clear()
            self._execution_error = None
            
            video_path = self._wait_for_completion(task)
            
            if video_path:
                task.status = "completed"
                task.output_path = video_path
                task.end_time = time.time()
                elapsed = task.get_elapsed_time()
                self._log(f"========== 任务 {task.task_id} 完成 ==========")
                self._log(f"  耗时: {elapsed}")
                self._log(f"  输出: {video_path}")
                self.task_completed.emit(task.task_id, video_path)
            else:
                raise Exception("获取视频失败")
                
        except Exception as e:
            task.status = "failed"
            task.error_msg = str(e)
            task.end_time = time.time()
            elapsed = task.get_elapsed_time()
            self._log(f"========== 任务 {task.task_id} 失败 ==========")
            self._log(f"  耗时: {elapsed}")
            self._log(f"  错误: {e}")
            self.task_failed.emit(task.task_id, str(e))
        
        finally:
            self._save_tasks()  # 保存任务队列
            self.queue_changed.emit(self.get_queue_length())
    
    def cleanup_memory(self):
        """清理ComfyUI内存（公开方法）"""
        try:
            requests.post(f"{self.base_url}/free", json={"unload_models": True, "free_memory": True}, timeout=10)
            self._log("已释放ComfyUI内存")
            return True
        except:
            return False
    
    def _wait_for_completion(self, task: SmoothMixTask, timeout: int = 1800) -> Optional[str]:
        """等待任务完成，使用WebSocket事件通知而非轮询"""
        start_time = time.time()
        
        # 等待WebSocket通知完成，每5秒检查一次
        while time.time() - start_time < timeout:
            if self._cancelled:
                return None
            
            # 等待execution_success或execution_error消息
            if self._execution_complete.wait(timeout=5):
                # 收到完成信号
                if self._execution_error:
                    raise Exception(self._execution_error)
                
                # 成功完成，获取输出视频
                return self._get_output_video(task)
            
            # 未收到信号，也检查一下history作为备用
            history = self.get_history(task.prompt_id)
            if history and task.prompt_id in history:
                outputs = history[task.prompt_id].get('outputs', {})
                if outputs:
                    self._log("通过history检测到任务完成")
                    return self._get_output_video(task)
        
        self._log(f"等待超时 ({timeout}秒)")
        return None
    
    def _get_output_video(self, task: SmoothMixTask) -> Optional[str]:
        """获取输出视频文件"""
        # 等待文件写入完成
        time.sleep(2)
        
        comfyui_output = self.comfyui_output_dir
        
        self._log(f"查找视频目录: {comfyui_output}")
        
        if not comfyui_output.exists():
            self._log(f"目录不存在!")
            return None
        
        # 查找最近修改的mp4文件（任务开始后生成的）
        mp4_files = list(comfyui_output.glob("*.mp4"))
        self._log(f"找到 {len(mp4_files)} 个mp4文件")
        
        if mp4_files:
            # 找任务开始后创建的最新文件
            recent_files = [f for f in mp4_files if f.stat().st_mtime >= task.start_time - 10]
            self._log(f"任务期间生成: {len(recent_files)} 个")
            
            if recent_files:
                latest = max(recent_files, key=lambda f: f.stat().st_mtime)
            else:
                latest = max(mp4_files, key=lambda f: f.stat().st_mtime)
            
            self._log(f"选中文件: {latest.name}")
            self.output_dir.mkdir(parents=True, exist_ok=True)
            save_path = self.output_dir / f"task_{task.task_id}_{latest.name}"
            shutil.copy2(latest, save_path)
            
            return str(save_path)
        
        self._log("未找到mp4文件")
        return None
    
    def cancel(self):
        self._cancelled = True
        self.interrupt()
        self._stop_ws_listener()
    
    def cancel_current(self):
        if self._current_task:
            self._current_task.status = "failed"
            self._current_task.error_msg = "用户取消"
            self._current_task.end_time = time.time()
            self._save_tasks()
            self._log(f"任务 {self._current_task.task_id} 已取消")
            self.task_failed.emit(self._current_task.task_id, "用户取消")
        self.interrupt()
        self._execution_complete.set()  # 解除等待阻塞
