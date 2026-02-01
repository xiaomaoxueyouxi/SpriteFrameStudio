"""测试 Real-ESRGAN 进度显示功能"""
from pathlib import Path
import numpy as np
import cv2
import time

from src.core.realesrgan_processor import RealESRGANProcessor

def progress_callback(message):
    """进度回调函数"""
    print(f"[进度] {message}")

def test_progress_display():
    """测试进度显示功能"""
    print("开始测试 Real-ESRGAN 进度显示...")
    
    # 创建处理器实例，添加进度回调
    processor = RealESRGANProcessor(progress_callback=progress_callback)
    
    # 检查是否可用
    if not processor.is_available():
        print("❌ Real-ESRGAN 不可用，请检查文件是否完整")
        return False
    
    print("✅ Real-ESRGAN 可用")
    
    # 创建一个测试图像（稍大一些，以便看到处理过程）
    test_image = np.zeros((200, 200, 3), dtype=np.uint8)
    cv2.putText(test_image, "Test Image", (30, 100), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
    
    # 保存测试图像
    test_input = Path("test_progress_input.png")
    cv2.imwrite(str(test_input), test_image)
    print(f"创建测试图像: {test_input}")
    
    # 获取可用模型
    models = processor.get_available_models()
    installed_models = [m for m in models if m["installed"]]
    
    if not installed_models:
        print("❌ 没有已安装的模型")
        return False
    
    # 测试第一个模型
    model_name = installed_models[0]["name"]
    print(f"\n🧪 使用模型: {model_name}")
    print("开始处理图像，将显示详细进度...")
    
    # 记录开始时间
    start_time = time.time()
    
    # 处理图像
    try:
        enhanced = processor.process_image(test_image, model_name=model_name, tile=0)
        if enhanced is not None:
            print(f"✅ 图像处理成功")
            print(f"输入尺寸: {test_image.shape}")
            print(f"输出尺寸: {enhanced.shape}")
            print(f"处理时间: {time.time() - start_time:.2f} 秒")
            
            # 保存处理后的图像
            test_output = Path("test_progress_output.png")
            cv2.imwrite(str(test_output), cv2.cvtColor(enhanced, cv2.COLOR_RGB2BGR))
            print(f"保存处理结果: {test_output}")
        else:
            print("❌ 图像处理失败")
    except Exception as e:
        print(f"❌ 处理错误: {str(e)}")
    
    print("\n进度显示测试完成！")
    return True

if __name__ == "__main__":
    test_progress_display()
