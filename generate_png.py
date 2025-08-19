#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
使用Puppeteer生成PNG图片
"""

import asyncio
import json
import base64
from pathlib import Path

async def generate_png_with_puppeteer():
    """使用Puppeteer生成PNG图片"""
    try:
        import pyppeteer
        
        # 读取Mermaid代码
        mmd_file = Path("flow_diagrams/system_flow_diagram.mmd")
        if not mmd_file.exists():
            print("Mermaid文件不存在")
            return False
            
        with open(mmd_file, 'r', encoding='utf-8') as f:
            mermaid_code = f.read()
        
        # 创建HTML内容
        html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>系统详细流程图</title>
    <script src="https://cdn.jsdelivr.net/npm/mermaid/dist/mermaid.min.js"></script>
    <style>
        body {{
            margin: 0;
            padding: 20px;
            font-family: Arial, sans-serif;
        }}
        .mermaid {{
            text-align: center;
        }}
    </style>
</head>
<body>
    <div class="mermaid">
{mermaid_code}
    </div>
    
    <script>
        mermaid.initialize({{
            startOnLoad: true,
            theme: 'default',
            flowchart: {{
                useMaxWidth: true,
                htmlLabels: true,
                curve: 'basis'
            }}
        }});
    </script>
</body>
</html>
"""
        
        # 启动浏览器
        browser = await pyppeteer.launch()
        page = await browser.newPage()
        
        # 设置视口大小
        await page.setViewport({'width': 1920, 'height': 1080})
        
        # 加载HTML内容
        await page.setContent(html_content)
        
        # 等待Mermaid渲染完成
        await page.waitForFunction('document.querySelector(".mermaid svg")')
        await asyncio.sleep(2)  # 额外等待确保渲染完成
        
        # 获取SVG元素
        svg_element = await page.querySelector('.mermaid svg')
        if svg_element:
            # 获取SVG的边界框
            bbox = await page.evaluate('''(element) => {
                const bbox = element.getBBox();
                return {
                    x: bbox.x,
                    y: bbox.y,
                    width: bbox.width,
                    height: bbox.height
                };
            }''', svg_element)
            
            # 截图
            output_file = Path("flow_diagrams/system_flow_diagram.png")
            await page.screenshot({
                'path': str(output_file),
                'clip': {
                    'x': bbox['x'] - 20,
                    'y': bbox['y'] - 20,
                    'width': bbox['width'] + 40,
                    'height': bbox['height'] + 40
                }
            })
            
            print(f"PNG文件已生成: {output_file}")
            await browser.close()
            return True
        else:
            print("未找到SVG元素")
            await browser.close()
            return False
            
    except ImportError:
        print("需要安装pyppeteer: pip install pyppeteer")
        return False
    except Exception as e:
        print(f"生成PNG时出错: {e}")
        return False

def generate_simple_png():
    """生成简单的PNG文件（使用matplotlib）"""
    try:
        import matplotlib.pyplot as plt
        import matplotlib.patches as patches
        from matplotlib.patches import FancyBboxPatch
        
        # 创建图形
        fig, ax = plt.subplots(1, 1, figsize=(20, 16))
        ax.set_xlim(0, 100)
        ax.set_ylim(0, 100)
        ax.axis('off')
        
        # 定义颜色
        colors = {
            'start': '#e1f5fe',
            'process': '#f3e5f5', 
            'decision': '#fff3e0',
            'error': '#ffebee',
            'client': '#e8f5e8'
        }
        
        # 绘制主要流程
        # 系统启动
        ax.add_patch(FancyBboxPatch((10, 90), 15, 8, boxstyle="round,pad=0.3", 
                                   facecolor=colors['start'], edgecolor='black'))
        ax.text(17.5, 94, '系统启动', ha='center', va='center', fontsize=10, weight='bold')
        
        # startup_event
        ax.add_patch(FancyBboxPatch((35, 90), 15, 8, boxstyle="round,pad=0.3", 
                                   facecolor=colors['process'], edgecolor='black'))
        ax.text(42.5, 94, 'startup_event', ha='center', va='center', fontsize=9)
        
        # 初始化组件
        components = ['WebSocket服务器', 'LLM客户端', 'TTS客户端', '数字人客户端', 'STT客户端']
        for i, comp in enumerate(components):
            x = 10 + i * 16
            ax.add_patch(FancyBboxPatch((x, 75), 14, 6, boxstyle="round,pad=0.2", 
                                       facecolor=colors['client'], edgecolor='black'))
            ax.text(x + 7, 78, comp, ha='center', va='center', fontsize=8)
        
        # 数字人加入房间流程
        ax.add_patch(FancyBboxPatch((10, 60), 15, 8, boxstyle="round,pad=0.3", 
                                   facecolor=colors['process'], edgecolor='black'))
        ax.text(17.5, 64, 'join_room', ha='center', va='center', fontsize=10, weight='bold')
        
        # 流式查询处理
        ax.add_patch(FancyBboxPatch((35, 60), 15, 8, boxstyle="round,pad=0.3", 
                                   facecolor=colors['process'], edgecolor='black'))
        ax.text(42.5, 64, 'process_query_stream', ha='center', va='center', fontsize=9)
        
        # 流式处理管道
        ax.add_patch(FancyBboxPatch((60, 60), 15, 8, boxstyle="round,pad=0.3", 
                                   facecolor=colors['process'], edgecolor='black'))
        ax.text(67.5, 64, 'stream_pipeline', ha='center', va='center', fontsize=9)
        
        # TTS处理
        ax.add_patch(FancyBboxPatch((10, 45), 15, 8, boxstyle="round,pad=0.3", 
                                   facecolor=colors['process'], edgecolor='black'))
        ax.text(17.5, 49, 'safe_tts_synthesize', ha='center', va='center', fontsize=8)
        
        # 数字人驱动
        ax.add_patch(FancyBboxPatch((35, 45), 15, 8, boxstyle="round,pad=0.3", 
                                   facecolor=colors['process'], edgecolor='black'))
        ax.text(42.5, 49, 'drive_with_streaming_audio', ha='center', va='center', fontsize=8)
        
        # 语音控制
        ax.add_patch(FancyBboxPatch((60, 45), 15, 8, boxstyle="round,pad=0.3", 
                                   facecolor=colors['process'], edgecolor='black'))
        ax.text(67.5, 49, 'single_button_voice_control', ha='center', va='center', fontsize=8)
        
        # WebSocket处理
        ax.add_patch(FancyBboxPatch((10, 30), 15, 8, boxstyle="round,pad=0.3", 
                                   facecolor=colors['process'], edgecolor='black'))
        ax.text(17.5, 34, 'websocket_handler', ha='center', va='center', fontsize=9)
        
        # 离开房间
        ax.add_patch(FancyBboxPatch((35, 30), 15, 8, boxstyle="round,pad=0.3", 
                                   facecolor=colors['process'], edgecolor='black'))
        ax.text(42.5, 34, 'leave_room', ha='center', va='center', fontsize=10, weight='bold')
        
        # 连接重置
        ax.add_patch(FancyBboxPatch((60, 30), 15, 8, boxstyle="round,pad=0.3", 
                                   facecolor=colors['process'], edgecolor='black'))
        ax.text(67.5, 34, 'reset_connections', ha='center', va='center', fontsize=9)
        
        # 状态检查
        ax.add_patch(FancyBboxPatch((10, 15), 15, 8, boxstyle="round,pad=0.3", 
                                   facecolor=colors['process'], edgecolor='black'))
        ax.text(17.5, 19, 'get_connection_status', ha='center', va='center', fontsize=8)
        
        # 错误处理
        ax.add_patch(FancyBboxPatch((35, 15), 15, 8, boxstyle="round,pad=0.3", 
                                   facecolor=colors['error'], edgecolor='black'))
        ax.text(42.5, 19, '异常处理器', ha='center', va='center', fontsize=10, weight='bold')
        
        # 清理任务
        ax.add_patch(FancyBboxPatch((60, 15), 15, 8, boxstyle="round,pad=0.3", 
                                   facecolor=colors['start'], edgecolor='black'))
        ax.text(67.5, 19, 'cleanup_pending_requests', ha='center', va='center', fontsize=8)
        
        # 添加标题
        ax.text(50, 98, 'AI对话系统详细流程图', ha='center', va='center', fontsize=16, weight='bold')
        
        # 添加图例
        legend_elements = [
            patches.Patch(color=colors['start'], label='系统启动和清理任务'),
            patches.Patch(color=colors['process'], label='主要处理函数'),
            patches.Patch(color=colors['decision'], label='决策判断点'),
            patches.Patch(color=colors['error'], label='错误处理'),
            patches.Patch(color=colors['client'], label='客户端操作')
        ]
        ax.legend(handles=legend_elements, loc='upper right', bbox_to_anchor=(0.98, 0.98))
        
        # 保存图片
        output_file = Path("flow_diagrams/system_flow_diagram.png")
        plt.savefig(output_file, dpi=300, bbox_inches='tight', facecolor='white')
        plt.close()
        
        print(f"PNG文件已生成: {output_file}")
        return True
        
    except ImportError:
        print("需要安装matplotlib: pip install matplotlib")
        return False
    except Exception as e:
        print(f"生成PNG时出错: {e}")
        return False

async def main():
    """主函数"""
    print("=== 生成PNG图片 ===")
    
    # 确保输出目录存在
    output_dir = Path("flow_diagrams")
    output_dir.mkdir(exist_ok=True)
    
    # 尝试方法1：使用Puppeteer
    success = await generate_png_with_puppeteer()
    
    # 尝试方法2：使用matplotlib
    if not success:
        success = generate_simple_png()
    
    if success:
        print("PNG图片生成成功！")
    else:
        print("PNG生成失败，请使用HTML查看器查看流程图")

if __name__ == "__main__":
    asyncio.run(main())
