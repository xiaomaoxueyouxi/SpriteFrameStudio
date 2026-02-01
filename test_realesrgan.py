"""测试 Real-ESRGAN 集成功能"""
from pathlib import Path
import numpy as np
import cv2

from src.core.realesrgan_processor import RealESRGANProcessor

def test_realesrgan():
    """测试 Real-ESRGAN 处理器"""
    print("开始测试 Real-ESRGAN 集成...")
    
    # 创建处理器实例
    processor = RealESRGANProcessor()
    
    # 检查是否可用
    if not processor.is_available():
        print("❌ Real-ESRGAN 不可用，请检查文件是否完整")
        return False
    
    print("✅ Real-ESRGAN 可用")
    
    # 获取可执行文件信息
    info = processor.get_executable_info()
    print(f"📁 可执行文件路径: {info['executable_path']}")
    print(f"📁 模型目录: {info['models_dir']}")
    print(f"🔢 模型数量: {info['model_count']}")
    
    # 获取可用模型
    models = processor.get_available_models()
    print(f"\n📋 可用模型列表:")
    for model in models:
        status = "✅" if model["installed"] else "❌"
        print(f"{status} {model['display_name']} (x{model['scale']}) - {model['description']}")
    
    # 测试处理单张图像
    print("\n🧪 测试处理单张图像...")
    
    # 创建一个简单的测试图像
    test_image = np.zeros((100, 100, 3), dtype=np.uint8)
    cv2.putText(test_image, "Test", (20, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
    
    # 保存测试图像
    test_input = Path("test_input.png")
    cv2.imwrite(str(test_input), test_image)
    print(f"创建测试图像: {test_input}")
    
    # 选择一个已安装的模型
    installed_models = [m for m in models if m["installed"]]
    if not installed_models:
        print("❌ 没有已安装的模型")
        return False
    
    model_name = installed_models[0]["name"]
    print(f"使用模型: {model_name}")
    
    # 处理图像
    try:
        enhanced = processor.process_image(test_image, model_name=model_name, tile=0)
        if enhanced is not None:
            print(f"✅ 图像处理成功")
            print(f"输入尺寸: {test_image.shape}")
            print(f"输出尺寸: {enhanced.shape}")
            
            # 保存处理后的图像
            test_output = Path("test_output.png")
            cv2.imwrite(str(test_output), cv2.cvtColor(enhanced, cv2.COLOR_RGB2BGR))
            print(f"保存处理结果: {test_output}")
        else:
            print("❌ 图像处理失败")
    except Exception as e:
        print(f"❌ 处理错误: {str(e)}")
    
    print("\n测试完成！")
    return True

if __name__ == "__main__":
    test_realesrgan()
