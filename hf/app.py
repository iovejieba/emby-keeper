import os
import sys
import tempfile
import subprocess
import shutil
from pathlib import Path
import multiprocessing
import threading
import socket
from contextlib import closing

# --- Dependency Check ---
# Ensure necessary packages are installed before they are imported.
try:
    import httpx
    import uvicorn
    import gradio as gr
    from starlette.applications import Starlette
    from starlette.requests import Request
    from starlette.responses import StreamingResponse, Response
    from starlette.routing import Route, WebSocketRoute
    from starlette.websockets import WebSocket
    import websockets
    import asyncio
except ImportError:
    print(
        "Installing required packages: starlette, uvicorn[standard], httpx, websockets, gradio...", flush=True
    )
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "-U",
            "starlette",
            "uvicorn[standard]",
            "httpx",
            "websockets",
            "gradio",
        ],
        check=True,
    )
    # Re-import after installation
    import httpx
    import uvicorn
    import gradio as gr
    from starlette.applications import Starlette
    from starlette.requests import Request
    from starlette.responses import StreamingResponse, Response
    from starlette.routing import Route, WebSocketRoute
    from starlette.websockets import WebSocket
    import websockets
    import asyncio

# --- Configuration and Setup (Preserved and Adapted) ---

EK_VERSION = "7.4.6"
APP_DATA_DIR = Path(os.path.expanduser("~/.local/share/embykeeper"))
VERSION_CACHE_DIR = APP_DATA_DIR / "hf" / "version"


def get_free_port():
    """Gets a free port on localhost using the standard library."""
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
        s.bind(("", 0))
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        return s.getsockname()[1]


def obfuscate_with_pyarmor(package_path):
    # This function is preserved from the original file
    try:
        subprocess.run([sys.executable, "-m", "pip", "install", "pyarmor"], check=True)
        for pkg in ["embykeeper", "embykeeperweb"]:
            pkg_dir = os.path.join(package_path, pkg)
            if not os.path.exists(pkg_dir):
                continue
            subprocess.run(
                ["pyarmor", "gen", "--recursive", "--output", os.path.join(package_path, "dist"), pkg_dir],
                check=True,
            )
            dist_dir = os.path.join(package_path, "dist")
            if os.path.exists(dist_dir):
                shutil.copytree(dist_dir, pkg_dir, dirs_exist_ok=True)
                shutil.rmtree(dist_dir)
        return True
    except Exception as e:
        print(f"Error during obfuscation: {e}", flush=True)
        return False


def setup_embykeeper():
    # This function is preserved from the original file
    try:
        VERSION_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cached_version = VERSION_CACHE_DIR / f"emby-keeper-{EK_VERSION}"
        cached_tarball = VERSION_CACHE_DIR / f"emby-keeper-{EK_VERSION}.tar.gz"

        if cached_version.exists():
            print(f"Using cached version from {cached_version}", flush=True)
            # Since embykeeperweb is modified, we must ensure it's reinstalled from the correct source
            print("Ensuring local embykeeper is installed...", flush=True)
            subprocess.run([sys.executable, "-m", "pip", "install", str(cached_version)], check=True)
            return True

        temp_dir = tempfile.mkdtemp()
        tarball_path = os.path.join(temp_dir, "embykeeper.tar.gz")

        if cached_tarball.exists():
            shutil.copy2(cached_tarball, tarball_path)
        else:
            release_url = f"https://github.com/emby-keeper/emby-keeper/archive/refs/tags/v{EK_VERSION}.tar.gz"
            subprocess.run(["wget", "-q", release_url, "-O", tarball_path], check=True)
            shutil.copy2(tarball_path, cached_tarball)

        subprocess.run(["tar", "xf", tarball_path, "-C", temp_dir], check=True)
        os.remove(tarball_path)
        extracted_dir = os.path.join(temp_dir, f"emby-keeper-{EK_VERSION}")

        if not obfuscate_with_pyarmor(extracted_dir):
            raise Exception("Obfuscation failed")

        print("Installing dependencies...", flush=True)
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "-r", os.path.join(extracted_dir, "requirements.txt")],
            check=True,
        )
        subprocess.run([sys.executable, "-m", "pip", "install", extracted_dir], check=True)

        shutil.copytree(extracted_dir, cached_version, dirs_exist_ok=True)
        shutil.rmtree(temp_dir)
        return True
    except Exception as e:
        print(f"Error setting up EK: {e}", flush=True)
        return False


def run_gradio(port):
    # This function is preserved from the original file, but takes port as an argument
    import random
    from time import time, ctime

    def promptgen(choice, num, artist):
        # This function is preserved
        t = time()
        print(ctime(t))
        # ... (rest of the promptgen function is unchanged)
        if choice == "Prompt Generator v0.1(Better quality)":
            prompt = open("pr1.txt").read().splitlines()
        elif choice == "Prompt Generator v0.2(More tags)":
            prompt = open("pr2.txt").read().splitlines()
        if int(num) < 1 or int(num) > 20:
            num = 10
        if int(artist) < 0 or int(artist) > 40:
            artist = 2
        vocab = len(prompt)
        generated = []
        artists_num = 0
        while len(sorted(set(generated), key=lambda d: generated.index(d))) < int(num):
            rand = random.choice(prompt)
            if rand.startswith("art by") and artists_num < int(artist):
                artists_num += 1
                generated.append(rand)
            elif not rand.startswith("art by"):
                generated.append(rand)
        return ", ".join(set(generated))

    with gr.Blocks() as demo:
        # The Gradio UI layout is preserved
        gr.HTML(
            """
                <div style="text-align: center; margin: 0 auto;">
                  <div style="display: inline-flex;align-items: center;gap: 0.8rem;font-size: 1.75rem;">
                    <h1 style="font-weight: 900; margin-bottom: 7px;margin-top:5px">
                      Simple Prompt Generator v0.6 (Gradio Demo)
                    </h1>
                  </div>
                  <p style="margin-bottom: 10px; font-size: 94%; line-height: 23px;">
                    Simple prompt generation script for Midjourney. EmbyKeeper is in <a href="#" onclick="const url = window.location.href; const isHfSpaces = url.includes('spaces/'); const newUrl = isHfSpaces ? url.replace('huggingface.co/spaces/', '').replace('prompt-generator', 'prompt-generator.hf.space/ek') : '/ek'; window.open(newUrl, '_blank'); return false;">/ek</a> path. <br> <p>More examples in <a class='link-info' href="https://github.com/emby-keeper/emby-keeper" target="_blank">Github</a> and <a class='link-info' href="https://emby-keeper.github.io/" target="_blank">Project site</a></p>
                  </p>
                  <center>
                    <img style="display: inline-block, margin-right: 1%;" src='https://visitor-badge.laobi.icu/badge?page_id=WiNE-iNEFF.Simple_Prompt_Generator&left_color=red&right_color=green&left_text=Visitors' alt='visitor badge'>
                  </center>
                </div>
            """
        )  # Preserving the large HTML blocks
        with gr.Column():
            model_size = gr.Radio(
                ["Prompt Generator v0.1(Better quality)", "Prompt Generator v0.2(More tags)"],
                label="Model Variant",
                value="Prompt Generator v0.1(Better quality)",
            )
            number = gr.Number(value="10", label="Num of tag (MAX 20)", show_label=True)
            artist = gr.Number(value="2", label="Num of artist (Standart 2)", show_label=True)
            out = gr.Textbox(lines=4, label="Generated Prompts")
        greet_btn = gr.Button("Generate")
        greet_btn.click(fn=promptgen, inputs=[model_size, number, artist], outputs=out, concurrency_limit=4)
        gr.HTML(
            """
                <div class="footer">
                    <div style='text-align: center;'>Simple Prompt Generator by <a href='https://twitter.com/wine_ineff' target='_blank'>Artsem Holub (WiNE-iNEFF)</a><br>More information about this demo and script your can find in <a class='link-info' href="https://github.com/emby-keeper/emby-keeper" target="_blank">Github</a> and <a class='link-info' href="https://emby-keeper.github.io/" target="_blank">Project site</a></div>
               </div>
           """
        )

    demo.queue()
    print(f"Starting Gradio on port {port}", flush=True)
    demo.launch(server_name="0.0.0.0", server_port=port, share=False)


# --- New Modern Proxy Implementation ---

# Use a global client for connection pooling and better performance
client = httpx.AsyncClient()


async def http_proxy(request: Request):
    """A general-purpose HTTP reverse proxy using Starlette and HTTPX."""
    path = request.url.path
    
    # Determine the target backend based on the path
    target_port = ek_port if path.startswith("/ek") else gradio_port
        
    target_url = httpx.URL(
        scheme="http", host="127.0.0.1", port=target_port, path=path, query=request.url.query.encode("utf-8")
    )

    # To fix "Response content longer than Content-Length" errors from the backend,
    # we buffer the entire response. This allows us to create a new, clean
    # response with a guaranteed correct Content-Length header, avoiding streaming issues.
    try:
        # We read the entire request body before sending.
        body = await request.body()
        # Create a new, clean set of headers, excluding problematic ones.
        headers = dict(request.headers)
        headers.pop("host", None)

        resp = await client.request(
            method=request.method,
            url=target_url,
            headers=headers,
            content=body,
            timeout=60.0
        )

        # Create a new, clean set of response headers.
        # This is crucial to avoid forwarding incorrect Content-Length or
        # Transfer-Encoding headers from a misbehaving backend.
        response_headers = dict(resp.headers)
        response_headers.pop("content-length", None)
        response_headers.pop("content-encoding", None)
        response_headers.pop("transfer-encoding", None)
        
        # Return a standard Response. Starlette will automatically calculate
        # the correct Content-Length for the buffered content.
        return Response(
            content=resp.content,
            status_code=resp.status_code,
            headers=response_headers,
        )

    except httpx.ConnectError:
        return Response(f"Backend service at {target_url} is unavailable.", status_code=502)
    except Exception as e:
        print(f"An unexpected error occurred in http_proxy: {e}", flush=True)
        return Response("An internal proxy error occurred.", status_code=500)


async def ws_proxy(websocket: WebSocket):
    """A general-purpose WebSocket reverse proxy using the 'websockets' library."""
    path = websocket.url.path

    # Determine target WebSocket URL based on path
    if path.startswith("/socket.io") or path.startswith("/ek/socket.io"):
        target_port = ek_port
    elif path.startswith("/queue/join"):  # Gradio's WebSocket path
        target_port = gradio_port
    else:
        await websocket.close(code=1003)
        return

    target_ws_url = f"ws://127.0.0.1:{target_port}{path}"

    # Add query params to the target URL
    query_string = websocket.url.query
    if query_string:
        target_ws_url += f"?{query_string}"

    await websocket.accept()

    try:
        # Use the 'websockets' library to connect to the backend
        async with websockets.connect(
            target_ws_url,
            extra_headers=websocket.headers.raw,  # Pass raw headers
            subprotocols=websocket.scope.get("subprotocols", []),
        ) as backend_ws:
            # Run two tasks concurrently:
            # 1. Forward messages from client to backend
            # 2. Forward messages from backend to client
            fwd_to_backend = asyncio.create_task(forward_to_backend(websocket, backend_ws))
            fwd_to_client = asyncio.create_task(forward_to_client(backend_ws, websocket))

            # wait for either task to finish (which means a connection has been closed)
            done, pending = await asyncio.wait(
                [fwd_to_backend, fwd_to_client],
                return_when=asyncio.FIRST_COMPLETED,
            )

            # Cancel the other task to ensure it exits cleanly
            for task in pending:
                task.cancel()

    except websockets.exceptions.ConnectionClosedError:
        print(f"Connection closed to {target_ws_url}", flush=True)
    except Exception as e:
        print(f"WebSocket proxy error: {e}", flush=True)


async def forward_to_backend(client_ws: WebSocket, server_ws):
    """Listens for messages from the client and forwards them to the server."""
    try:
        while True:
            message = await client_ws.receive()
            if message["type"] == "websocket.disconnect":
                await server_ws.close()
                break
            data = message.get("text") or message.get("bytes")
            if data:
                await server_ws.send(data)
    except (websockets.exceptions.ConnectionClosed, asyncio.CancelledError):
        # The connection was closed or the task was cancelled.
        # Ensure the other connection is closed as well.
        if not server_ws.closed:
            await server_ws.close()


async def forward_to_client(server_ws, client_ws: WebSocket):
    """Listens for messages from the server and forwards them to the client."""
    try:
        # The async for loop elegantly handles the connection closing.
        async for message in server_ws:
            if isinstance(message, str):
                await client_ws.send_text(message)
            elif isinstance(message, bytes):
                await client_ws.send_bytes(message)
    except (websockets.exceptions.ConnectionClosed, asyncio.CancelledError):
        # The connection was closed or the task was cancelled.
        # Ensure the other connection is closed as well.
        if client_ws.client_state != "DISCONNECTED":
            await client_ws.close()


# --- Main Application Execution Block ---

if __name__ == "__main__":
    setup_embykeeper()

    gradio_port = get_free_port()
    ek_port = get_free_port()
    print(f"Internal ports - Gradio: {gradio_port}, EK: {ek_port}", flush=True)

    # Start Gradio in a separate, isolated process
    gradio_process = multiprocessing.Process(target=run_gradio, args=(gradio_port,))
    gradio_process.daemon = True
    gradio_process.start()

    # Start embykeeperweb in a background thread
    ek_thread = threading.Thread(
        target=lambda: subprocess.run(["embykeeperweb", "--port", str(ek_port), "--prefix", "/ek"])
    )
    ek_thread.daemon = True
    ek_thread.start()

    # Define the proxy application routes
    # The order is important: more specific routes should come first.
    routes = [
        WebSocketRoute("/queue/join", endpoint=ws_proxy),  # For Gradio
        WebSocketRoute("/socket.io/", endpoint=ws_proxy),  # For embykeeperweb (at root)
        WebSocketRoute("/ek/socket.io/", endpoint=ws_proxy),  # For embykeeperweb (with prefix, just in case)
        Route("/ek/{path:path}", endpoint=http_proxy, methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"]),
        Route("/{path:path}", endpoint=http_proxy, methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"]),
    ]
    app = Starlette(routes=routes)

    print(f"Starting modern proxy on http://0.0.0.0:7860", flush=True)
    uvicorn.run(app, host="0.0.0.0", port=7860, ws="websockets")
