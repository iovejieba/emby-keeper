import eventlet

eventlet.monkey_patch()

import os
import sys
import tempfile
import subprocess
import shutil
from pathlib import Path
import threading
import multiprocessing
from appdirs import user_data_dir
import socketio
import eventlet
import requests

EK_VERSION = "7.4.4"
APP_DATA_DIR = Path(user_data_dir("embykeeper"))
VERSION_CACHE_DIR = APP_DATA_DIR / "hf" / "version"


def setup_embykeeper():
    try:
        # Ensure cache directory exists
        VERSION_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cached_version = VERSION_CACHE_DIR / f"emby-keeper-{EK_VERSION}"
        cached_tarball = VERSION_CACHE_DIR / f"emby-keeper-{EK_VERSION}.tar.gz"

        if cached_version.exists():
            print(f"Using cached version from {cached_version}", flush=True)
            return True

        # Create temporary directory
        temp_dir = tempfile.mkdtemp()

        # Download and extract (using system proxy)
        print("Downloading EK...", flush=True)
        tarball_path = os.path.join(temp_dir, "embykeeper.tar.gz")

        if cached_tarball.exists():
            print(f"Using cached tarball from {cached_tarball}", flush=True)
            shutil.copy2(cached_tarball, tarball_path)
        else:
            # Use fixed GitHub release download URL
            release_url = f"https://github.com/emby-keeper/emby-keeper/archive/refs/tags/v{EK_VERSION}.tar.gz"
            subprocess.run(["wget", "-q", release_url, "-O", tarball_path], check=True)
            # Cache the downloaded file
            shutil.copy2(tarball_path, cached_tarball)

        subprocess.run(["tar", "xf", tarball_path, "-C", temp_dir], check=True)
        os.remove(tarball_path)  # Remove temporary tar.gz file

        # Get the extracted directory name
        extracted_dir = os.path.join(temp_dir, f"emby-keeper-{EK_VERSION}")

        # Obfuscate code
        print("Obfuscating code...", flush=True)
        if not obfuscate_with_pyarmor(extracted_dir):
            raise Exception("Obfuscation failed")

        # Install dependencies
        print("Installing dependencies...", flush=True)
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "-r", os.path.join(extracted_dir, "requirements.txt")],
            check=True,
        )
        subprocess.run([sys.executable, "-m", "pip", "install", extracted_dir], check=True)

        # Copy processed files to cache directory
        shutil.copytree(extracted_dir, cached_version, dirs_exist_ok=True)

        # Clean up temporary directory
        shutil.rmtree(temp_dir)

        return True
    except Exception as e:
        print(f"Error setting up EK: {e}", flush=True)
        return False


def obfuscate_with_pyarmor(package_path):
    try:
        # Install pyarmor if not already installed
        subprocess.run([sys.executable, "-m", "pip", "install", "pyarmor"], check=True)

        # Obfuscate packages
        for pkg in ["embykeeper", "embykeeperweb"]:
            pkg_dir = os.path.join(package_path, pkg)
            if not os.path.exists(pkg_dir):
                print(f"Package directory not found: {pkg_dir}", flush=True)
                continue

            print(f"Obfuscating {pkg}...", flush=True)

            # Run pyarmor with modified parameters
            subprocess.run(
                [
                    "pyarmor",
                    "gen",
                    "--recursive",
                    "--output",
                    os.path.join(package_path, "dist"),  # Specify output directory explicitly
                    pkg_dir,
                ],
                check=True,
            )

            # Handle obfuscated files
            dist_dir = os.path.join(package_path, "dist")
            if os.path.exists(dist_dir):
                # Copy all contents from dist directory back to package directory
                for item in os.listdir(dist_dir):
                    src = os.path.join(dist_dir, item)
                    dst = os.path.join(pkg_dir, item)
                    if os.path.isdir(src):
                        shutil.copytree(src, dst, dirs_exist_ok=True)
                    else:
                        shutil.copy2(src, dst)
                # Clean up dist directory
                shutil.rmtree(dist_dir)
            else:
                print(f"Dist directory not found after obfuscation for {pkg}", flush=True)
                return False

        return True
    except Exception as e:
        print(f"Error during obfuscation: {e}", flush=True)
        return False


def get_free_port():
    with eventlet.listen(("", 0)) as sock:
        return sock.getsockname()[1]


def run_gradio():
    import gradio as gr
    import random
    from time import time, ctime

    def promptgen(choice, num, artist):
        t = time()
        print(ctime(t))

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
        print(", ".join(set(generated)) + "\n\n")
        return ", ".join(set(generated))

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
                    Simple prompt generation script for Midjourney. EmbyKeeper is in <a href="#" onclick="const url = window.location.href; const isHfSpaces = url.includes('spaces/'); const newUrl = isHfSpaces ? url.replace('huggingface.co/spaces/', '').replace('prompt-generator', 'prompt-generator.hf.space/ek') : '/ek'; window.open(newUrl, '_blank'); return false;">/ek</a> path. <br> <p>More examples in <a class='link-info' href="https://github.com/emby-keeper/emby-keeper" target="_blank">Github</a> and <a class='link-info' href="https://emby-keeper.github.io/" target="_blank">Project site</a></p>
                  </p>
                  <center>
                    <img style="display: inline-block, margin-right: 1%;" src='https://visitor-badge.laobi.icu/badge?page_id=WiNE-iNEFF.Simple_Prompt_Generator&left_color=red&right_color=green&left_text=Visitors' alt='visitor badge'>
                  </center>
                </div>
            """
        )
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
    print(f"Starting Gradio on port {gradio_port}", flush=True)
    demo.launch(
        server_name="0.0.0.0",
        server_port=gradio_port,
        share=False,
        debug=True,
        show_error=True,
        prevent_thread_lock=True,
    )


def create_proxy_app():
    sio_server = socketio.Server(async_mode="eventlet", logger=False, engineio_logger=False)
    sio_client = socketio.Client(logger=False, engineio_logger=False)

    # Store sid mapping relationships
    client_sessions = {}

    @sio_server.on("connect", namespace="/pty")
    def connect(sid, environ):
        print(f"Client connected: {sid}", flush=True)
        if not sio_client.connected:
            try:
                sio_client.connect(f"http://127.0.0.1:{ek_port}", namespaces=["/pty"])
                client_sessions[sid] = True
            except Exception as e:
                print(f"Failed to connect to ek backend: {e}", flush=True)

    @sio_server.on("disconnect", namespace="/pty")
    def disconnect(sid):
        print(f"Client disconnected: {sid}", flush=True)
        client_sessions.pop(sid, None)
        if not client_sessions and sio_client.connected:
            sio_client.disconnect()

    @sio_server.on("*", namespace="/pty")
    def catch_all(event, sid, *args):
        if event not in ["connect", "disconnect"]:
            # print(f"Forward to ek: {event}")
            if sio_client.connected:
                sio_client.emit(event, *args, namespace="/pty")

    @sio_client.on("*", namespace="/pty")
    def forward_from_ek(event, *args):
        if event not in ["connect", "disconnect"]:
            # print(f"Forward from ek: {event}")
            sio_server.emit(event, *args, namespace="/pty")

    def proxy_handler(environ, start_response):
        path = environ.get("PATH_INFO", "")
        
        if path.startswith("/ek/socket.io"):
            # This path is handled by sio_server, so we let the wrapper handle it.
            # Returning a 404 or another response here would prevent socket.io from working.
            # The Socket.IO server will handle this request.
            # We pass it to the default handler of the WSGIApp.
            return sio_app.default_service(environ, start_response)

        target_port = ek_port if path.startswith("/ek") else gradio_port

        # Handle CORS preflight requests for Gradio, which is on a different effective origin
        if environ.get("REQUEST_METHOD") == "OPTIONS" and target_port == gradio_port:
            origin = environ.get("HTTP_ORIGIN")
            if origin:
                response_headers = [
                    ('Access-Control-Allow-Origin', origin),
                    ('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS'),
                    ('Access-Control-Allow-Headers', 'Content-Type, Authorization, X-Requested-With'),
                    ('Access-Control-Allow-Credentials', 'true'),
                    ('Access-Control-Max-Age', '86400') # Cache preflight for 1 day
                ]
                start_response("204 No Content", response_headers)
                return []
        
        target_url = f"http://127.0.0.1:{target_port}{path}"
        
        if environ.get("QUERY_STRING"):
            target_url += f"?{environ['QUERY_STRING']}"

        headers = {key: value for key, value in environ.items() if key.startswith("HTTP_")}
        headers = {key[5:].replace("_", "-").lower(): value for key, value in headers.items()}
        
        # Ensure correct Host and forwarding headers are passed to the backend.
        # This is crucial for the backend to generate correct redirect URLs.
        if "host" in headers:
            headers["x-forwarded-host"] = headers["host"]

        # Add client IP for backend processing
        if "HTTP_X_FORWARDED_FOR" in environ:
            headers["x-forwarded-for"] = environ["HTTP_X_FORWARDED_FOR"] + ", " + environ.get("REMOTE_ADDR", "")
        else:
            headers["x-forwarded-for"] = environ.get("REMOTE_ADDR", "")
        
        # Add protocol info
        if "HTTP_X_FORWARDED_PROTO" in environ:
            headers["x-forwarded-proto"] = environ["HTTP_X_FORWARDED_PROTO"]
        else:
            headers["x-forwarded-proto"] = environ.get("wsgi.url_scheme", "http")

        # Clean up hop-by-hop headers that shouldn't be forwarded
        headers.pop("connection", None)
        headers.pop("proxy-connection", None)
        headers.pop('keep-alive', None)
        headers.pop('proxy-authenticate', None)
        headers.pop('proxy-authorization', None)
        headers.pop('te', None)
        headers.pop('trailers', None)
        headers.pop('transfer-encoding', None)
        headers.pop('upgrade', None)
        
        content_length = environ.get("CONTENT_LENGTH")
        body = None
        if content_length:
            try:
                content_length = int(content_length)
                if content_length > 0:
                    body = environ["wsgi.input"].read(content_length)
            except (ValueError, IOError):
                 content_length = 0

        if "CONTENT_TYPE" in environ:
             headers["content-type"] = environ["CONTENT_TYPE"]

        try:
            resp = requests.request(
                method=environ["REQUEST_METHOD"],
                url=target_url,
                headers=headers,
                data=body,
                stream=True,
                allow_redirects=False,
                timeout=30
            )

            response_headers = []
            # Hop-by-hop headers. These are removed when sent to the backend.
            # http://www.w3.org/Protocols/rfc2616/rfc2616-sec13.html
            hop_by_hop_headers = {
                'connection', 'keep-alive', 'proxy-authenticate', 'proxy-authorization', 
                'te', 'trailers', 'transfer-encoding', 'upgrade'
            }
            for key, value in resp.raw.headers.items():
                if key.lower() not in hop_by_hop_headers:
                    response_headers.append((key, value))

            # If the backend sent a redirect to its internal address, rewrite it to the public address.
            # This is a robust way to handle backends that are not proxy-aware.
            is_redirect = resp.status_code in (301, 302, 307, 308)
            if is_redirect and target_port == ek_port:
                location_index = -1
                for i, (key, value) in enumerate(response_headers):
                    if key.lower() == 'location':
                        location_index = i
                        break
                
                if location_index != -1:
                    location = response_headers[location_index][1]
                    internal_host_base = f"http://127.0.0.1:{ek_port}"
                    if location.startswith(internal_host_base):
                        public_host = environ.get('HTTP_HOST')
                        public_scheme = environ.get('wsgi.url_scheme', 'http')
                        if public_host:
                            # Reconstruct the URL with the public host and scheme
                            path_and_query = location[len(internal_host_base):]
                            new_location = f"{public_scheme}://{public_host}{path_and_query}"
                            # Replace the old Location header with the rewritten one
                            response_headers[location_index] = ('Location', new_location)

            # Add CORS headers for Gradio responses to allow the frontend to access it
            if target_port == gradio_port:
                origin = environ.get("HTTP_ORIGIN")
                if origin:
                    # Remove existing CORS headers if they exist, to avoid duplicates
                    response_headers = [h for h in response_headers if h[0].lower() != 'access-control-allow-origin']
                    response_headers.append(('Access-Control-Allow-Origin', origin))
                    response_headers.append(('Access-Control-Allow-Credentials', 'true'))

            start_response(f"{resp.status_code} {resp.reason}", response_headers)
            
            # Stream the raw response back to the client. This is more robust as it 
            # avoids issues with requests' automatic decompression conflicting with 
            # the headers being sent, which can cause truncated files.
            return iter(lambda: resp.raw.read(8192), b'')

        except requests.exceptions.RequestException as e:
            print(f"Error forwarding request: {e}", flush=True)
            start_response("502 Bad Gateway", [("Content-Type", "text/plain")])
            return [b"Proxy error: Could not connect to the upstream server."]
        except Exception as e:
            print(f"Unhandled proxy error: {e}", flush=True)
            start_response("500 Internal Server Error", [("Content-Type", "text/plain")])
            return [b"An internal error occurred in the proxy."]

    # Wrap the proxy_handler with the socketio middleware
    sio_app = socketio.WSGIApp(sio_server, proxy_handler)
    return sio_app


if __name__ == "__main__":
    print("Setting up EK...", flush=True)
    if not setup_embykeeper():
        print("Failed to setup EK!", flush=True)
        sys.exit(1)

    # Get random ports for internal services
    gradio_port = get_free_port()
    ek_port = get_free_port()

    print(f"Using ports - Gradio: {gradio_port}, EK: {ek_port}", flush=True)

    gradio_process = multiprocessing.Process(target=run_gradio)
    gradio_process.daemon = True
    gradio_process.start()

    ek_thread = threading.Thread(
        target=lambda: subprocess.run(
            ["embykeeperweb", "--port", str(ek_port), "--prefix", "/ek", "--public"]
        )
    )
    ek_thread.daemon = True
    ek_thread.start()

    # Start proxy server on fixed port 7860
    print("Starting proxy server on port 7860...", flush=True)
    
    # Create the combined WSGI app
    app = create_proxy_app()
    
    # Run the server
    eventlet.wsgi.server(eventlet.listen(("", 7860)), app, log=None)
