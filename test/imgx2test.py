import numpy as np
import onnxruntime as ort
from PIL import Image
import time

# -------------------------- 配置项（只需改这3个路径/参数） --------------------------
MODEL_PATH = r"../models/sharp/2x-AnimeSharpV2_ESRGAN_Soft_fp16.onnx"  # 你的模型路径
INPUT_IMG = "test.png"  # 输入图片
OUTPUT_IMG = "upscaled_clear.png"  # 输出清晰图
# -----------------------------------------------------------------------------------

# 1. 加载模型 + 强制优先用GPU（CPU模式会自动兜底）
# 关闭fp16优化，避免兼容性问题
ort.set_default_logger_severity(3)  # 关闭冗余日志
session = ort.InferenceSession(
    MODEL_PATH,
    providers=['CUDAExecutionProvider', 'CPUExecutionProvider'],
    provider_options=[{'device_id': 0}]  # GPU设备ID（单卡默认0）
)

# 2. 【关键】自动获取模型的真实输入节点名（再也不用猜input/x/input_0了）
input_meta = session.get_inputs()[0]
INPUT_NAME = input_meta.name  # 模型实际的输入张量名（比如x/input_0）
INPUT_SHAPE = input_meta.shape  # 模型输入形状（比如[1,3,H,W]）
INPUT_DTYPE = input_meta.type  # 模型输入类型（大概率是tensor(float)，即float32）
print(f"✅ 模型真实输入信息：")
print(f"   张量名: {INPUT_NAME}, 形状: {INPUT_SHAPE}, 数据类型: {INPUT_DTYPE}")

# 检查实际运行的设备
actual_providers = session.get_providers()
print(f"\n✅ 实际使用设备: {actual_providers}")
if 'CUDAExecutionProvider' not in actual_providers:
    print("⚠️ 警告: GPU未启用，使用CPU处理（速度较慢，建议安装CUDA+cuDNN）")

# 3. 读取图片 + 预处理（严格匹配模型要求）
img = Image.open(INPUT_IMG).convert("RGB")  # 强制RGB，避免透明通道干扰
img_h, img_w = img.size[1], img.size[0]
print(f"\n✅ 输入图片尺寸: {img.size} (W×H)")

# 预处理核心：HWC(RGB) → CHW → 加batch维度 → 保持float32（不转fp16、不归一化！）
# 原因：AnimeSharpV2要求输入是[0,255]的float32原始像素值
arr = np.array(img, dtype=np.float32)  # 形状：(H, W, 3)，值范围[0,255]
arr = arr.transpose(2, 0, 1)  # HWC → CHW，形状：(3, H, W)
arr = np.expand_dims(arr, axis=0)  # 加batch维度，形状：(1, 3, H, W)
print(f"✅ 输入张量形状: {arr.shape}, 数据类型: {arr.dtype}, 值范围: [{arr.min():.0f}, {arr.max():.0f}]")

# 4. 模型推理（用自动获取的INPUT_NAME，而非硬编码的input）
print(f"\n🚀 开始超分推理...")
start_time = time.time()
# 关键：输入字典的key必须是模型真实的INPUT_NAME
output = session.run(None, {INPUT_NAME: arr})[0]
elapsed = time.time() - start_time
print(f"✅ 推理完成，耗时: {elapsed:.2f} 秒")
print(f"✅ 输出张量形状: {output.shape}")

# 5. 后处理 + 保存图片（逆预处理，严格防像素值溢出）
output = output[0]  # 去掉batch维度，形状：(3, 2H, 2W)
output = output.transpose(1, 2, 0)  # CHW → HWC，形状：(2H, 2W, 3)
# 核心：裁剪到严格2倍尺寸（避免模型边缘补零）+ 防溢出 + 转uint8
output = output[:img_h*2, :img_w*2, :]  # 裁剪到输入的2倍，避免多余像素
output = np.clip(output, 0, 255).astype(np.uint8)  # 强制像素值在[0,255]，避免花屏

# 保存高清图（用PIL保存，默认高质量，避免二次压缩）
result = Image.fromarray(output)
print(f"\n✅ 输出图片尺寸: {result.size} (W×H)（严格2倍放大）")
result.save(OUTPUT_IMG, quality=95)  # quality=95 保证高清，不压缩
print(f"✅ 高清图已保存到: {OUTPUT_IMG}")