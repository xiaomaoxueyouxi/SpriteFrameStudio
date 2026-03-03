"""作者信息面板"""
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton, QGroupBox, QScrollArea
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont


class AboutPanel(QWidget):
    """作者信息面板"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(15)

        # 创建一个滚动区域，以便内容过多时可以滚动
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("""
            QScrollArea {
                border: none;
                background-color: transparent;
            }
        """)

        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setSpacing(20)

        # 项目标题
        title_label = QLabel("SpriteFrameStudio")
        title_label.setStyleSheet("""
            QLabel {
                font-size: 28px;
                font-weight: bold;
                color: #0078d4;
            }
        """)
        title_label.setAlignment(Qt.AlignCenter)
        scroll_layout.addWidget(title_label)

        # 作者信息
        author_group = QGroupBox("作者信息")
        author_layout = QVBoxLayout(author_group)
        author_layout.setSpacing(10)

        author_layout.addWidget(QLabel("作者：小猫学游戏"))
        author_layout.addWidget(QLabel("QQ反馈群：722160123"))

        bilibili_label = QLabel('<a href="https://space.bilibili.com/627968233">哔哩哔哩主页</a>')
        bilibili_label.setOpenExternalLinks(True)
        bilibili_label.setStyleSheet("color: #00a1d6;")
        author_layout.addWidget(bilibili_label)

        github_label = QLabel('<a href="https://github.com/game-cat/SpriteFrameStudio">GitHub 仓库</a>')
        github_label.setOpenExternalLinks(True)
        github_label.setStyleSheet("color: #fff;")
        author_layout.addWidget(github_label)

        scroll_layout.addWidget(author_group)

        # 项目介绍
        intro_group = QGroupBox("项目介绍")
        intro_layout = QVBoxLayout(intro_group)
        intro_layout.setSpacing(8)

        intro_text = QLabel(
            "SpriteFrameStudio 是一款功能强大的视频处理工具，专为游戏开发、动画制作和精灵图素材提取设计。"
            "它集成了先进的 AI 姿势检测、背景去除和图像优化功能，能够帮助用户快速从视频中提取高质量的帧序列，"
            "轻松制作游戏精灵图和动画素材。"
        )
        intro_text.setWordWrap(True)
        intro_text.setStyleSheet("color: #ccc;")
        intro_layout.addWidget(intro_text)

        scroll_layout.addWidget(intro_group)

        # 核心功能
        features_group = QGroupBox("核心功能")
        features_layout = QVBoxLayout(features_group)
        features_layout.setSpacing(6)

        features = [
            "• 智能帧提取：支持自定义 FPS 和时间范围，精准提取视频片段",
            "• 多模式分析：RTMPose 姿势检测、分区域 SSIM 比对、轮廓与图像匹配",
            "• 背景处理：AI 智能抠图、传统颜色过滤（绿幕、蓝幕等）",
            "• 图像后期优化：批量缩放、边缘优化、描边与裁剪",
            "• 高效导出：支持批量处理与多种导出格式",
            "• 视频生成：集成 Wan2.2 和 SmoothMix 模型进行 AI 视频生成",
        ]

        for feature in features:
            feat_label = QLabel(feature)
            feat_label.setWordWrap(True)
            feat_label.setStyleSheet("color: #aaa;")
            features_layout.addWidget(feat_label)

        scroll_layout.addWidget(features_group)

        # 开源协议
        license_group = QGroupBox("开源协议")
        license_layout = QVBoxLayout(license_group)
        license_layout.setSpacing(6)

        license_text = QLabel(
            "本项目采用 CC BY 4.0（署名4.0国际）开源协议。\n\n"
            "协议要求：\n"
            "• 允许商用：可用于商业项目\n"
            "• 允许修改：可以自由修改和衍生\n"
            "• 允许分发：可以分发和共享\n"
            "• 必须署名：任何使用或衍生作品必须明显标注原作者名字"
        )
        license_text.setWordWrap(True)
        license_text.setStyleSheet("color: #aaa;")
        license_layout.addWidget(license_text)

        scroll_layout.addWidget(license_group)

        # 第三方组件
        third_party_group = QGroupBox("第三方组件")
        third_party_layout = QVBoxLayout(third_party_group)
        third_party_layout.setSpacing(6)

        third_party_text = QLabel(
            "本项目使用了以下开源组件：\n\n"
            "• RTMPose - Apache 2.0（模型权重仅限非商业用途）\n"
            "• rembg - MIT\n"
            "• PyTorch - BSD\n"
            "• OpenCV - Apache 2.0\n"
            "• PySide6 - LGPL"
        )
        third_party_text.setWordWrap(True)
        third_party_text.setStyleSheet("color: #aaa;")
        third_party_layout.addWidget(third_party_text)

        scroll_layout.addWidget(third_party_group)

        # 感谢
        thanks_group = QGroupBox("感谢")
        thanks_layout = QVBoxLayout(thanks_group)
        thanks_layout.setSpacing(6)

        thanks_text = QLabel(
            "感谢所有为该项目贡献代码、提出建议和反馈问题的朋友们！\n\n"
            "特别感谢：Grealt 提供的视频区间选择功能"
        )
        thanks_text.setWordWrap(True)
        thanks_text.setStyleSheet("color: #aaa;")
        thanks_layout.addWidget(thanks_text)

        scroll_layout.addWidget(thanks_group)

        scroll_layout.addStretch()

        scroll.setWidget(scroll_content)
        layout.addWidget(scroll)
