"""Real-ESRGAN 图像增强模块"""
from typing import Optional, Callable, Dict
from enum import Enum
from pathlib import Path
import numpy as np
import cv2
import subprocess
import tempfile
import os


class RealESRGANModel(str, Enum):
    """Real-ESRGAN 模型类型"""
    REALESRGAN_X4PLUS = "realesrgan-x4plus"                    # 通用模型
    REALESRGAN_X4PLUS_ANIME = "realesrgan-x4plus-anime"        # 动漫专用
    REALESR_ANIMEVIDEO_V3_X2 = "realesr-animevideov3-x2"        # 动漫视频 x2
    REALESR_ANIMEVIDEO_V3_X3 = "realesr-animevideov3-x3"        # 动漫视频 x3
    REALESR_ANIMEVIDEO_V3_X4 = "realesr-animevideov3-x4"        # 动漫视频 x4


# 模型信息
MODEL_INFO: Dict[str, dict] = {
    "realesrgan-x4plus": {
        "name": "RealESRGAN x4+ (通用)",
        "scale": 4,
        "description": "适用于各种真实世界图像的通用模型",
        "recommended": True
    },
    "realesrgan-x4plus-anime": {
        "name": "RealESRGAN x4+ Anime (动漫)",
        "scale": 4,
        "description": "专门针对动漫和插画优化",
        "recommended": True
    },
    "realesr-animevideov3-x2": {
        "name": "RealESRGAN AnimeVideo v3 x2",
        "scale": 2,
        "description": "动漫视频专用，2倍放大",
        "recommended": False
    },
    "realesr-animevideov3-x3": {
        "name": "RealESRGAN AnimeVideo v3 x3",
        "scale": 3,
        "description": "动漫视频专用，3倍放大",
        "recommended": False
    },
    "realesr-animevideov3-x4": {
        "name": "RealESRGAN AnimeVideo v3 x4",
        "scale": 4,
        "description": "动漫视频专用，4倍放大",
        "recommended": False
    },
}


class RealESRGANProcessor:
    """Real-ESRGAN 图像增强处理器"""
    
    def __init__(self, progress_callback: Optional[Callable[[str], None]] = None):
        self._progress_callback = progress_callback
        self._executable_path = self._find_executable()
        self._models_dir = self._find_models_dir()
        self._cancel_flag = False
    
    def cancel(self):
        """取消操作"""
        self._cancel_flag = True
    
    def _report_progress(self, message: str):
        """报告进度"""
        if self._progress_callback:
            self._progress_callback(message)
    
    def _find_executable(self) -> Optional[Path]:
        """查找 Real-ESRGAN 可执行文件"""
        project_root = Path(__file__).parent.parent.parent
        executable_path = project_root / "models" / "realesrgan" / "realesrgan-ncnn-vulkan.exe"
        
        if executable_path.exists():
            return executable_path
        return None
    
    def _find_models_dir(self) -> Optional[Path]:
        """查找模型目录"""
        project_root = Path(__file__).parent.parent.parent
        models_dir = project_root / "models" / "realesrgan" / "models"
        
        if models_dir.exists():
            return models_dir
        return None
    
    def is_available(self) -> bool:
        """检查 Real-ESRGAN 是否可用"""
        return self._executable_path is not None and self._models_dir is not None
    
    def get_available_models(self) -> list:
        """获取可用的模型列表"""
        available = []
        
        if not self._models_dir:
            return available
        
        for model_name, info in MODEL_INFO.items():
            # 检查模型文件是否存在
            param_path = self._models_dir / f"{model_name}.param"
            bin_path = self._models_dir / f"{model_name}.bin"
            
            available.append({
                "name": model_name,
                "display_name": info["name"],
                "scale": info["scale"],
                "description": info["description"],
                "recommended": info["recommended"],
                "installed": param_path.exists() and bin_path.exists(),
                "param_path": str(param_path) if param_path.exists() else None,
                "bin_path": str(bin_path) if bin_path.exists() else None
            })
        return available
    
    def process_image(self, image: np.ndarray, model_name: str = "realesrgan-x4plus", tile: int = 0) -> Optional[np.ndarray]:
        """
        处理单张图像
        
        Args:
            image: 输入图像 (H, W, 3) 或 (H, W, 4)
            model_name: 模型名称
            tile: 分块大小，0表示不使用分块
            
        Returns:
            增强后的图像，失败返回None
        """
        if not self.is_available():
            self._report_progress("Real-ESRGAN 不可用，请检查文件是否完整")
            return None
        
        # 检查模型是否可用
        models = self.get_available_models()
        model_info = next((m for m in models if m["name"] == model_name), None)
        if not model_info or not model_info["installed"]:
            self._report_progress(f"模型 {model_name} 未安装")
            return None
        
        # 创建临时文件
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_dir = Path(temp_dir)
            
            # 保存输入图像
            input_path = temp_dir / "input.png"
            if len(image.shape) == 3 and image.shape[2] == 4:
                # RGBA图像
                cv2.imwrite(str(input_path), cv2.cvtColor(image, cv2.COLOR_RGBA2BGRA))
            else:
                # RGB图像
                cv2.imwrite(str(input_path), cv2.cvtColor(image, cv2.COLOR_RGB2BGR))
            
            # 输出路径
            output_path = temp_dir / "output.png"
            
            # 构建命令
            cmd = [
                str(self._executable_path),
                "-i", str(input_path),
                "-o", str(output_path),
                "-n", model_name
            ]
            
            # 添加分块参数
            if tile > 0:
                cmd.extend(["-t", str(tile)])
            
            try:
                self._report_progress(f"开始处理图像，使用模型: {model_info['display_name']}")
                
                # 执行命令，实时读取输出
                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    cwd=str(self._executable_path.parent)
                )
                
                # 实时读取输出
                while True:
                    if self._cancel_flag:
                        process.terminate()
                        self._report_progress("处理已取消")
                        return None
                    
                    output = process.stdout.readline()
                    if output == '' and process.poll() is not None:
                        break
                    if output:
                        # 解析输出，提取进度信息
                        output = output.strip()
                        self._report_progress(f"处理中: {output}")
                
                # 检查返回码
                if process.returncode != 0:
                    self._report_progress(f"处理失败，返回码: {process.returncode}")
                    return None
                
                # 读取输出图像
                if not output_path.exists():
                    self._report_progress("未生成输出图像")
                    return None
                
                # 读取图像
                output_image = cv2.imread(str(output_path), cv2.IMREAD_UNCHANGED)
                
                if output_image is None:
                    self._report_progress("无法读取输出图像")
                    return None
                
                # 转换颜色空间
                if output_image.shape[2] == 4:
                    # BGRA转RGBA
                    output_image = cv2.cvtColor(output_image, cv2.COLOR_BGRA2RGBA)
                else:
                    # BGR转RGB
                    output_image = cv2.cvtColor(output_image, cv2.COLOR_BGR2RGB)
                
                self._report_progress("图像处理完成")
                return output_image
                
            except Exception as e:
                self._report_progress(f"处理错误: {str(e)}")
                return None
    
    def batch_process(self,
                     images: list,
                     model_name: str = "realesrgan-x4plus",
                     tile: int = 0,
                     progress_callback: Optional[Callable[[int, int, float], None]] = None) -> list:
        """
        批量处理图像
        
        Args:
            images: 输入图像列表
            model_name: 模型名称
            tile: 分块大小
            progress_callback: 进度回调函数
            
        Returns:
            增强后的图像列表
        """
        self._cancel_flag = False
        results = []
        total = len(images)
        
        for i, image in enumerate(images):
            if self._cancel_flag:
                break
            
            result = self.process_image(image, model_name, tile)
            results.append(result)
            
            if progress_callback:
                progress = (i + 1) / total * 100
                progress_callback(i + 1, total, progress)
        
        return results
    
    def get_executable_info(self) -> dict:
        """获取可执行文件信息"""
        info = {
            "available": self.is_available(),
            "executable_path": str(self._executable_path) if self._executable_path else None,
            "models_dir": str(self._models_dir) if self._models_dir else None,
            "version": "ncnn-vulkan"
        }
        
        if self._executable_path:
            info["executable_exists"] = self._executable_path.exists()
        
        if self._models_dir:
            info["models_dir_exists"] = self._models_dir.exists()
            info["model_count"] = len(list(self._models_dir.glob("*.param")))
        
        return info
