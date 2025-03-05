from eventlet.patcher import monkey_patch

monkey_patch()

import random
import tempfile
import subprocess
import os
import shutil
from time import time, ctime
import sys
import random

from werkzeug.middleware.dispatcher import DispatcherMiddleware
import requests
import gradio as gr

def obfuscate_with_pyarmor(package_path):
    try:
        # 安装 pyarmor（如果还没安装）
        subprocess.run([sys.executable, '-m', 'pip', 'install', 'pyarmor'], check=True)
        
        # 使用 pyarmor 混淆整个包
        # --recursive 递归处理所有 .py 文件
        # --advanced 使用高级模式
        # --restrict 限制代码在特定平台运行
        # --exact 精确混淆模式
        subprocess.run([
            'pyarmor', 'obfuscate', 
            '--recursive',
            '--advanced', '2',
            '--restrict', '0',
            '--exact',
            os.path.join(package_path, 'embykeeperweb', '__init__.py')
        ], check=True)
        
        # 将混淆后的文件移回原位置
        dist_dir = os.path.join(package_path, 'dist')
        if os.path.exists(dist_dir):
            for root, dirs, files in os.walk(dist_dir):
                for file in files:
                    src_path = os.path.join(root, file)
                    rel_path = os.path.relpath(src_path, dist_dir)
                    dst_path = os.path.join(package_path, rel_path)
                    os.makedirs(os.path.dirname(dst_path), exist_ok=True)
                    shutil.move(src_path, dst_path)
            shutil.rmtree(dist_dir)
        
        return True
    except Exception as e:
        print(f"Obfuscation failed: {e}", flush=True)
        return False

def setup_embykeeper():
    try:
        # 使用固定的GitHub release下载地址
        release_url = "https://github.com/emby-keeper/emby-keeper/archive/refs/tags/v7.1.1.tar.gz"
        
        # 创建临时目录
        temp_dir = tempfile.mkdtemp()
        print(f"Working in temporary directory: {temp_dir}", flush=True)
        
        # 下载压缩包
        print("Downloading release...", flush=True)
        response = requests.get(release_url, stream=True)  # 使用流式下载
        response.raise_for_status()
        
        # 保存并解压
        tarfile_path = os.path.join(temp_dir, "release.tar.gz")
        with open(tarfile_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
        
        # 解压文件
        print("Extracting files...", flush=True)
        import tarfile
        with tarfile.open(tarfile_path) as tar:
            def is_within_limits(members):
                base = os.path.dirname(temp_dir)
                for member in members:
                    path = os.path.join(base, member.name)
                    if not path.startswith(base):
                        continue
                    yield member
            tar.extractall(temp_dir, members=is_within_limits(tar))
            
        # 获取解压后的目录名（通常是 emby-keeper-7.1.1）
        extracted_dir = os.path.join(temp_dir, "emby-keeper-7.1.1")
        
        # 混淆代码
        print("Obfuscating code...", flush=True)
        if not obfuscate_with_pyarmor(extracted_dir):
            raise Exception("Obfuscation failed")
        
        # 安装包
        print("Installing package...", flush=True)
        subprocess.run([sys.executable, '-m', 'pip', 'install', '-e', extracted_dir], check=True)
        
        return True
    except Exception as e:
        print(f"Setup failed: {e}", flush=True)
        return False

def setup_flask():
    from embykeeperweb.app import app, socketio, bp
    app.config["BASE_PREFIX"] = "/ek"
    # 设置静态文件路径
    app.static_url_path = f"{app.config['BASE_PREFIX']}/assets"
    app.view_functions.pop('static', None)
    app.add_url_rule(
        f"{app.static_url_path}/<path:filename>",
        endpoint="static",
        view_func=app.send_static_file
    )
    # 注册蓝图
    app.register_blueprint(bp, url_prefix=app.config["BASE_PREFIX"])
    # 设置配置
    app.config["args"] = ["--public"]
    app.config["config"] = os.environ.get("EK_CONFIG", "")
    # 启动进程
    from embykeeperweb.app import start_proc
    if not os.environ.get("WAIT_START", False):
        start_proc(instant=True)
    return app, socketio

def promptgen(choice, num, artist):
  t = time()
  print(ctime(t))

  if choice == "Prompt Generator v0.1":
    prompt = open('pr1.txt').read().splitlines()
  elif choice == "Prompt Generator v0.2":
    prompt = open('pr2.txt').read().splitlines()

  if int(num) < 1 or int(num) > 20:
    num = 10
  
  if int(artist) < 0 or int(artist) > 40:
    artist = 2

  vocab = len(prompt)
  generated = []
  artists_num = 0
  while len(sorted(set(generated), key=lambda d: generated.index(d))) < int(num):
    rand = random.choice(prompt)
    if rand.startswith('art by') and artists_num < int(artist):
        artists_num +=1 
        generated.append(rand)
    elif not rand.startswith('art by'):
        generated.append(rand)
  print(', '.join(set(generated)) + '\n\n')
  return ', '.join(set(generated))

demo = gr.Blocks()

with demo:
  gr.HTML(
        """
            <div style="text-align: center; margin: 0 auto;">
              <div style="display: inline-flex;align-items: center;gap: 0.8rem;font-size: 1.75rem;">
                <h1 style="font-weight: 900; margin-bottom: 7px;margin-top:5px">
                  Simple Prompt Generator v0.6 (Gradio Demo)
                </h1>
              </div>
              <p style="margin-bottom: 10px; font-size: 94%; line-height: 23px;">
                Simple prompt generation script for Midjourney, DALLe, Stable and Disco diffusion and etc neural networks. <br> <p>More examples in <a class='link-info' href="https://github.com/WiNE-iNEFF/Simple_Prompt_Generator" target="_blank">Github</a> and <a class='link-info' href="https://wine-ineff.github.io/Simple_Prompt_Generator/" target="_blank">Project site</a></p>
              </p>
              <center>
                <img style="display: inline-block, margin-right: 1%;" src='https://visitor-badge.laobi.icu/badge?page_id=WiNE-iNEFF.Simple_Prompt_Generator&left_color=red&right_color=green&left_text=Visitors' alt='visitor badge'>
                <img style="display: inline-block, margin-right: 1%;" src='https://visitor-badge.laobi.icu/badge?page_id=WiNE-iNEFF.HF_Simple_Prompt_Generator&left_color=red&right_color=green&left_text=Visitors' alt='visitor badge'>
              </center>
            </div>
        """
    )
  with gr.Column():
    model_size = gr.Radio(["Prompt Generator v0.1(Better quality)", "Prompt Generator v0.2(More tags)"], label="Model Variant", value="Prompt Generator v0.1(Better quality)")
    number = gr.Number(value="10", label="Num of tag (MAX 20)", show_label=True)
    artist = gr.Number(value="2", label="Num of artist (Standart 2)", show_label=True)
    out = gr.Textbox(lines=4, label="Generated Prompts")
  greet_btn = gr.Button("Generate")
  greet_btn.click(fn=promptgen, inputs=[model_size, number, artist], outputs=out, concurrency_limit=4)
  gr.HTML(
            """
                <div class="footer">
                    <div style='text-align: center;'>Simple Prompt Generator by <a href='https://twitter.com/wine_ineff' target='_blank'>Artsem Holub (WiNE-iNEFF)</a><br>More information about this demo and script your can find in <a class='link-info' href="https://github.com/WiNE-iNEFF/Simple_Prompt_Generator" target="_blank">Github</a> and <a class='link-info' href="https://wine-ineff.github.io/Simple_Prompt_Generator/" target="_blank">Project site</a></div>
               </div>
           """
        )

# 主程序入口
if __name__ == "__main__":
    # 先设置 demo
    demo.queue()
    demo_app = demo.app  # 获取 Gradio 的 WSGI app
    
    print("Setting up Embykeeper...", flush=True)
    embykeeper_ready = setup_embykeeper()
    
    if embykeeper_ready:
        print("Setting up Flask application...", flush=True)
        flask_app, socketio = setup_flask()
        
        # 创建调度中间件，将主路由交给 Gradio，/ek 路径交给 Flask
        app = DispatcherMiddleware(demo_app, {
            '/ek': flask_app
        })
        
        # 使用 werkzeug 的服务器运行组合后的应用
        from werkzeug.serving import run_simple
        print("Starting server...", flush=True)
        run_simple('0.0.0.0', 7860, app, use_reloader=False, use_debugger=False)
    else:
        print("Failed to setup Embykeeper, running Gradio only...", flush=True)
        demo.launch(server_name="0.0.0.0", server_port=7860)