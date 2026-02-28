"""SmoothMix视频生成工作线程"""
import time
import random
import json
import shutil
from datetime import datetime
from typing import Optional, Dict, List
from pathlib import Path
from PySide6.QtCore import QThread, Signal
import requests
import websockets
import asyncio
import threading


def log(message: str):
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"[{timestamp}] {message}")


class SmoothMixTask:
    """单个生成任务"""
    def __init__(self, task_id: int, start_image: str, end_image: str = "", 
                 prompt: str = "", negative_prompt: str = "", width: int = 368, height: int = 704,
                 frames: int = 33, steps: int = 4, seed: int = -1,
                 sage_attention: bool = False, enable_upscale: bool = False):
        self.task_id = task_id
        self.start_image = start_image
        self.end_image = end_image or start_image
        self.prompt = prompt
        self.negative_prompt = negative_prompt
        self.width = width
        self.height = height
        self.frames = frames
        self.steps = steps
        self.seed = seed if seed > 0 else random.randint(0, 2**31 - 1)
        self.sage_attention = sage_attention
        self.enable_upscale = enable_upscale
        self.status = "pending"
        self.prompt_id: Optional[str] = None
        self.output_path: Optional[str] = None
        self.error_msg: Optional[str] = None


class SmoothMixWorker(QThread):
    """SmoothMix视频生成工作线程"""
    
    task_started = Signal(int, str)
    task_progress = Signal(int, int, int, str)
    task_completed = Signal(int, str)
    task_failed = Signal(int, str)
    queue_changed = Signal(int)
    status_changed = Signal(str)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._cancelled = False
        self._tasks: List[SmoothMixTask] = []
        self._current_task: Optional[SmoothMixTask] = None
        self._task_counter = 0
        self._ws = None
        self._running = False
        self.base_url = "http://127.0.0.1:8189"
        self.ws_url = "ws://127.0.0.1:8189/ws"
        self.client_id = f"smoothmix_{random.randint(1000, 9999)}"
        self.output_dir = Path(__file__).parent.parent.parent.parent / "output" / "smoothmix"
        
    def add_task(self, start_image: str, end_image: str = "", prompt: str = "",
                 negative_prompt: str = "", width: int = 368, height: int = 704, frames: int = 33, 
                 steps: int = 4, seed: int = -1, sage_attention: bool = False,
                 enable_upscale: bool = False) -> int:
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
            steps=steps,
            seed=seed,
            sage_attention=sage_attention,
            enable_upscale=enable_upscale
        )
        self._tasks.append(task)
        self.queue_changed.emit(len([t for t in self._tasks if t.status == "pending"]))
        log(f"任务 {task.task_id} 已添加到队列")
        return task.task_id
    
    def remove_task(self, task_id: int) -> bool:
        for i, task in enumerate(self._tasks):
            if task.task_id == task_id and task.status == "pending":
                self._tasks.pop(i)
                self.queue_changed.emit(len([t for t in self._tasks if t.status == "pending"]))
                return True
        return False
    
    def clear_queue(self):
        self._tasks = [t for t in self._tasks if t.status in ("running", "completed", "failed")]
        self.queue_changed.emit(len([t for t in self._tasks if t.status == "pending"]))
    
    def get_queue_length(self) -> int:
        return len([t for t in self._tasks if t.status == "pending"])
    
    def get_all_tasks(self) -> List[SmoothMixTask]:
        return self._tasks.copy()
    
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
            log(f"上传图片失败: {e}")
        return None
    
    def load_workflow(self) -> Optional[Dict]:
        workflow_path = Path(__file__).parent.parent.parent / "workflows" / "SmoothMix-FLF2V.json"
        if workflow_path.exists():
            with open(workflow_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        log(f"工作流文件不存在: {workflow_path}")
        return None
    
    def build_workflow(self, task: SmoothMixTask, start_image_name: str, end_image_name: str) -> Dict:
        workflow = self.load_workflow()
        if not workflow:
            raise ValueError("无法加载工作流模板")
        
        workflow["237"]["inputs"]["image"] = start_image_name
        workflow["238"]["inputs"]["image"] = end_image_name
        workflow["241"]["inputs"]["text"] = task.prompt
        # 负向提示词 (节点240)
        if task.negative_prompt:
            workflow["240"]["inputs"]["text"] = task.negative_prompt
        workflow["252"]["inputs"]["value"] = task.width
        workflow["253"]["inputs"]["value"] = task.height
        workflow["285"]["inputs"]["value"] = str(task.frames)
        workflow["254"]["inputs"]["value"] = task.steps
        workflow["229"]["inputs"]["seed"] = task.seed
        
        # Sage Attention 加速 (节点265, 266)
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
            log(f"提交工作流失败: {e}")
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
        self._running = True
        def ws_loop():
            asyncio.run(self._ws_listen())
        self._ws_thread = threading.Thread(target=ws_loop, daemon=True)
        self._ws_thread.start()
    
    def _stop_ws_listener(self):
        self._running = False
        self._ws = None
    
    async def _ws_listen(self):
        try:
            uri = f"{self.ws_url}?clientId={self.client_id}"
            async with websockets.connect(uri) as ws:
                self._ws = ws
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
            log(f"WebSocket连接失败: {e}")
    
    async def _handle_ws_message(self, data: Dict):
        msg_type = data.get('type')
        msg_data = data.get('data', {})
        
        if msg_type == 'progress':
            value = msg_data.get('value', 0)
            max_value = msg_data.get('max', 100)
            node = msg_data.get('node', '')
            if self._current_task:
                progress_pct = int(value / max_value * 100) if max_value > 0 else 0
                self.task_progress.emit(
                    self._current_task.task_id, value, max_value,
                    f"节点 {node}: {progress_pct}%"
                )
        elif msg_type == 'executing':
            node = msg_data.get('node')
            if node and self._current_task:
                self.status_changed.emit(f"正在执行节点: {node}")
    
    def run(self):
        self._cancelled = False
        self._start_ws_listener()
        log(f"SmoothMix工作线程启动，队列长度: {len(self._tasks)}")
        
        while not self._cancelled:
            self._current_task = None
            for task in self._tasks:
                if task.status == "pending":
                    self._current_task = task
                    break
            
            if not self._current_task:
                break
            
            self._execute_task(self._current_task)
        
        self._stop_ws_listener()
        log("SmoothMix工作线程结束")
    
    def _execute_task(self, task: SmoothMixTask):
        task.status = "running"
        self.task_started.emit(task.task_id, f"开始执行任务 {task.task_id}")
        log(f"开始执行任务 {task.task_id}")
        
        try:
            if not self.check_connection():
                raise Exception("ComfyUI未连接")
            
            if self._cancelled:
                return
            
            log(f"任务 {task.task_id}: 上传首帧图片...")
            start_image_name = self.upload_image(task.start_image)
            if not start_image_name:
                raise Exception("上传首帧图片失败")
            
            if self._cancelled:
                return
            
            log(f"任务 {task.task_id}: 上传尾帧图片...")
            end_image_name = self.upload_image(task.end_image)
            if not end_image_name:
                raise Exception("上传尾帧图片失败")
            
            if self._cancelled:
                return
            
            log(f"任务 {task.task_id}: 构建工作流...")
            workflow = self.build_workflow(task, start_image_name, end_image_name)
            
            if self._cancelled:
                return
            
            log(f"任务 {task.task_id}: 提交工作流...")
            task.prompt_id = self.queue_prompt(workflow)
            if not task.prompt_id:
                raise Exception("提交工作流失败")
            
            log(f"任务 {task.task_id}: prompt_id = {task.prompt_id}")
            
            video_path = self._wait_for_completion(task)
            
            if video_path:
                task.status = "completed"
                task.output_path = video_path
                self.task_completed.emit(task.task_id, video_path)
                log(f"任务 {task.task_id} 完成: {video_path}")
            else:
                raise Exception("获取视频失败")
                
        except Exception as e:
            task.status = "failed"
            task.error_msg = str(e)
            self.task_failed.emit(task.task_id, str(e))
            log(f"任务 {task.task_id} 失败: {e}")
        
        finally:
            self.queue_changed.emit(self.get_queue_length())
    
    def _wait_for_completion(self, task: SmoothMixTask, timeout: int = 1800) -> Optional[str]:
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            if self._cancelled:
                return None
            
            history = self.get_history(task.prompt_id)
            
            if history and task.prompt_id in history:
                outputs = history[task.prompt_id].get('outputs', {})
                if outputs:
                    comfyui_output = Path(__file__).parent.parent.parent.parent / \
                        "portable_output" / "SpriteFrameStudio" / "Wan2.2-SmoothMix" / "ComfyUI" / "output"
                    
                    if comfyui_output.exists():
                        mp4_files = list(comfyui_output.glob("*.mp4"))
                        if mp4_files:
                            latest = max(mp4_files, key=lambda f: f.stat().st_mtime)
                            self.output_dir.mkdir(parents=True, exist_ok=True)
                            save_path = self.output_dir / f"task_{task.task_id}_{latest.name}"
                            shutil.copy2(latest, save_path)
                            
                            # 高清修复
                            if task.enable_upscale:
                                upscaled_path = self._upscale_video(str(save_path), task.task_id)
                                if upscaled_path:
                                    return upscaled_path
                            
                            return str(save_path)
            
            time.sleep(3)
        
        return None
    
    def _upscale_video(self, video_path: str, task_id: int) -> Optional[str]:
        """使用RealESRGAN进行高清修复"""
        try:
            log(f"任务 {task_id}: 开始高清修复...")
            self.status_changed.emit("正在进行高清修复...")
            
            import subprocess
            base_path = Path(__file__).parent.parent.parent.parent / "portable_output" / "SpriteFrameStudio" / "Wan2.2-SmoothMix"
            realesrgan_script = base_path / "res" / "inference_realesrgan_video.py"
            model_path = base_path / "res" / "RealESRGAN_x4plus.pth"
            python_exe = base_path / "py312" / "python.exe"
            
            if not realesrgan_script.exists():
                log(f"RealESRGAN脚本不存在: {realesrgan_script}")
                return None
            
            output_path = str(Path(video_path).with_stem(f"{Path(video_path).stem}_hd"))
            
            cmd = [
                str(python_exe),
                str(realesrgan_script),
                "-i", video_path,
                "-o", str(Path(video_path).parent),
                "-n", "RealESRGAN_x4plus",
                "-s", "4"
            ]
            
            env = {
                "PYTHONPATH": str(base_path / "res"),
                "TORCH_HOME": str(base_path / "cache")
            }
            
            import os
            env.update(os.environ)
            
            result = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=600)
            
            if result.returncode == 0:
                log(f"任务 {task_id}: 高清修复完成")
                # 找到修复后的视频
                hd_files = list(Path(video_path).parent.glob(f"*_out.mp4"))
                if hd_files:
                    return str(hd_files[-1])
            else:
                log(f"高清修复失败: {result.stderr}")
            
        except Exception as e:
            log(f"高清修复出错: {e}")
        
        return None
    
    def cancel(self):
        self._cancelled = True
        self.interrupt()
        self._stop_ws_listener()
    
    def cancel_current(self):
        if self._current_task:
            self._current_task.status = "failed"
            self._current_task.error_msg = "用户取消"
        self.interrupt()
