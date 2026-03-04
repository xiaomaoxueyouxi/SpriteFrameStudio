"""将 BiRefNet PyTorch 模型转换为 ONNX 格式
解决 torchvision::deform_conv2d 不支持 ONNX 导出的问题
"""
import sys
import torch
from pathlib import Path

# 路径配置
CODE_DIR = Path(__file__).parent.parent / "src" / "tools" / "BiRefNet-main"
PTH_PATH = Path(__file__).parent.parent / "models" / "birefnet_finetuned_toonout.pth"
OUTPUT_DIR = Path(__file__).parent.parent / "models" / "birefnet"
INPUT_SIZE = (1024, 1024)


def register_deform_conv2d_symbolic():
    """注册 torchvision::deform_conv2d 的 ONNX symbolic（映射到 ONNX DeformConv 算子，opset 19+）"""
    from torch.onnx import register_custom_op_symbolic

    def symbolic_deform_conv2d(g, input, offset, mask, weight, bias,
                               stride_h, stride_w,
                               pad_h, pad_w,
                               dil_h, dil_w,
                               n_weight_grps, n_offset_grps, use_mask):
        # 获取 kernel_shape
        # 尝试多种方式获取权重形状
        kernel_shape = None
        
        # 方式1: 通过 type().sizes()
        try:
            weight_type = weight.type()
            if weight_type and hasattr(weight_type, 'sizes') and weight_type.sizes():
                sizes = weight_type.sizes()
                if len(sizes) >= 2:
                    kernel_shape = [int(sizes[-2]), int(sizes[-1])]
        except:
            pass
        
        # 方式2: 通过 node 的 t() 方法（需要属性名参数）
        if kernel_shape is None:
            try:
                weight_node = weight.node()
                if weight_node and weight_node.kind() == 'onnx::Constant':
                    tensor = weight_node.t('value')
                    if tensor is not None and len(tensor.shape) >= 2:
                        kernel_shape = [int(tensor.shape[-2]), int(tensor.shape[-1])]
            except:
                pass
        
        # 回退：使用默认值
        if kernel_shape is None:
            kernel_shape = [3, 3]  # BiRefNet 中通常使用 3x3 卷积

        # 构建输入列表，根据 use_mask 决定是否包含 mask
        inputs = [input, weight, offset, bias]
        if use_mask:
            inputs.insert(2, mask)

        # 将参数转换为整数（处理可能是张量的情况）
        def to_int(val):
            if hasattr(val, 'node'):
                # 是 Value 对象，尝试获取常量值
                node = val.node()
                if node.kind() == 'onnx::Constant':
                    t = node.t('value')
                    return int(t.item()) if t.numel() == 1 else int(t[0].item())
                return 1  # 默认值
            return int(val)

        return g.op(
            "DeformConv",
            *inputs,
            dilations_i=[to_int(dil_h), to_int(dil_w)],
            group_i=to_int(n_weight_grps),
            kernel_shape_i=kernel_shape,
            offset_group_i=to_int(n_offset_grps),
            pads_i=[to_int(pad_h), to_int(pad_w), to_int(pad_h), to_int(pad_w)],
            strides_i=[to_int(stride_h), to_int(stride_w)],
        )

    register_custom_op_symbolic("torchvision::deform_conv2d", symbolic_deform_conv2d, 19)
    print("[INFO] 已注册 deform_conv2d -> ONNX DeformConv 自定义算子")


def convert(fp16: bool = False):
    tag = "fp16" if fp16 else "fp32"
    output_name = "model_toonout_fp16.onnx" if fp16 else "model_toonout.onnx"
    output_path = OUTPUT_DIR / output_name

    print(f"[1/4] 加载 BiRefNet 模型 ({tag})...")
    print(f"       代码路径: {CODE_DIR}")
    print(f"       权重路径: {PTH_PATH}")

    # 添加源代码路径
    sys.path.insert(0, str(CODE_DIR))
    
    # 从本地代码导入模型
    from birefnet.models.birefnet import BiRefNet
    from birefnet.config import Config
    
    # 创建模型实例
    config = Config()
    model = BiRefNet(bb_pretrained=False)
    
    # 加载权重
    state_dict = torch.load(PTH_PATH, map_location='cpu')
    
    # 处理键名不匹配：移除 'module._orig_mod.' 前缀
    new_state_dict = {}
    for key, value in state_dict.items():
        new_key = key.replace('module._orig_mod.', '')
        new_state_dict[new_key] = value
    
    model.load_state_dict(new_state_dict)
    model.eval()

    device = "cpu"
    if fp16:
        model.half()
    model.to(device)

    print(f"[2/4] 准备 dummy input ({INPUT_SIZE[0]}x{INPUT_SIZE[1]})...")
    dtype = torch.float16 if fp16 else torch.float32
    dummy_input = torch.randn(1, 3, INPUT_SIZE[0], INPUT_SIZE[1], dtype=dtype, device=device)

    print(f"[3/4] 导出 ONNX -> {output_path}...")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    class BiRefNetWrapper(torch.nn.Module):
        def __init__(self, model):
            super().__init__()
            self.model = model

        def forward(self, x):
            outputs = self.model(x)[-1].sigmoid()
            return outputs

    wrapper = BiRefNetWrapper(model)
    if fp16:
        wrapper.half()
    wrapper.eval()

    # 注册自定义算子
    register_deform_conv2d_symbolic()

    torch.onnx.export(
        wrapper,
        dummy_input,
        str(output_path),
        opset_version=19,
        input_names=["input"],
        output_names=["output"],
        dynamic_axes={
            "input": {0: "batch_size"},
            "output": {0: "batch_size"},
        },
    )

    size_mb = output_path.stat().st_size / (1024 * 1024)
    print(f"[4/4] 完成! {output_path} ({size_mb:.1f} MB)")


if __name__ == "__main__":
    print("=" * 50)
    print("BiRefNet PyTorch -> ONNX 转换工具")
    print("=" * 50)
    print()

    convert(fp16=False)
    print()
    convert(fp16=True)