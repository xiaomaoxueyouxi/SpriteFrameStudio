"""检查ONNX模型的输入输出规格"""
import onnxruntime as ort
import sys

model_path = r"../models/sharp/2x-AnimeSharpV2_ESRGAN_Soft_fp16.onnx"

print(f"检查模型: {model_path}")
print("=" * 50)

try:
    session = ort.InferenceSession(model_path, providers=['CPUExecutionProvider'])
    
    print("\n【模型输入】")
    for inp in session.get_inputs():
        print(f"  名称: {inp.name}")
        print(f"  形状: {inp.shape}")
        print(f"  类型: {inp.type}")
        print()
    
    print("【模型输出】")
    for out in session.get_outputs():
        print(f"  名称: {out.name}")
        print(f"  形状: {out.shape}")
        print(f"  类型: {out.type}")
        print()
    
    print("【运行时信息】")
    print(f"  onnxruntime 版本: {ort.__version__}")
    print(f"  可用 Providers: {ort.get_available_providers()}")
    print(f"  实际使用: {session.get_providers()}")
    
    print("\n✓ 模型加载成功！可以使用。")
    
except Exception as e:
    print(f"\n✗ 模型加载失败: {e}")
    sys.exit(1)
