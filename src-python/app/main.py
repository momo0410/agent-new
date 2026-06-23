import asyncio
import json
from contextlib import asynccontextmanager
import asyncssh
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app.routers.api import router, init_state, get_ssh_manager
@asynccontextmanager
async def lifespan(app: FastAPI):
    init_state()
    print("SDIT Python 后端已启动")
    yield
    try:
        ssh_manager = get_ssh_manager()
        if ssh_manager and ssh_manager.is_connected():
            await ssh_manager.disconnect()
    except Exception:
        pass
    print("SDIT Python 后端已关闭")
app = FastAPI(
    title="SDIT API",
    description="SDIT - Linux 应急响应工具 Python 后端",
    version="0.55.0",
    lifespan=lifespan,
)
@app.exception_handler(ConnectionError)
async def handle_connection_error(_, exc: ConnectionError):
    detail = str(exc).strip() or "没有活动的 SSH 连接"
    return JSONResponse(status_code=400, content={"detail": detail})
@app.exception_handler(asyncssh.Error)
async def handle_asyncssh_error(_, exc: asyncssh.Error):
    detail = str(exc).strip() or "SSH 连接异常"
    return JSONResponse(status_code=400, content={"detail": detail})
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)
@app.websocket("/ws/terminal/{terminal_id}")
async def websocket_terminal(websocket: WebSocket, terminal_id: str):
    await websocket.accept()
    try:
        ssh_manager = get_ssh_manager()
    except Exception as e:
        await websocket.close(code=1011, reason=f"SSH管理器不可用: {e}")
        return

    print(f"WebSocket 终端连接: {terminal_id}, ssh_connected={ssh_manager and ssh_manager.is_connected()}")

    session_preexisting = ssh_manager.has_terminal_session(terminal_id) if ssh_manager else False

    # 只有在会话不存在且 SSH 未连接时才拒绝
    # 如果会话已存在（HTTP API 刚创建），即使 is_connected() 暂时返回 False 也允许重连
    if not session_preexisting:
        if not ssh_manager or not ssh_manager.is_connected():
            await websocket.close(code=1001, reason="没有活动的 SSH 连接")
            return

    try:
        if not session_preexisting:
            # 允许最多2次重试，处理SSH通道临时繁忙的情况
            max_retries = 2
            for attempt in range(1, max_retries + 1):
                try:
                    await ssh_manager.create_terminal_session(terminal_id, 80, 24)
                    break
                except (ConnectionError, RuntimeError) as e:
                    if attempt == max_retries:
                        raise
                    print(f"终端会话创建尝试 {attempt}/{max_retries} 失败，等待后重试: {e}")
                    await asyncio.sleep(0.3)
    except Exception as e:
        await websocket.close(code=1001, reason=str(e))
        return
    ws_alive = True
    consecutive_empty_errors = 0

    async def read_output():
        nonlocal ws_alive, consecutive_empty_errors
        try:
            while ws_alive:
                try:
                    data = await ssh_manager.read_terminal_output(terminal_id, timeout=0.02)
                except (ValueError, ConnectionError, OSError) as e:
                    print(f"WebSocket 终端 SSH通道错误: {terminal_id} - {e}")
                    ws_alive = False
                    try:
                        await websocket.close(code=1011, reason=f"SSH通道异常: {e}")
                    except Exception:
                        pass
                    return
                if data:
                    consecutive_empty_errors = 0
                    try:
                        await websocket.send_bytes(data)
                    except Exception as e:
                        print(f"WebSocket 终端发送失败: {terminal_id} - {e}")
                        ws_alive = False
                        return
                    continue
                consecutive_empty_errors += 1
                if consecutive_empty_errors > 500:
                    if not ssh_manager.has_terminal_session(terminal_id):
                        print(f"WebSocket 终端 SSH会话已丢失: {terminal_id}")
                        ws_alive = False
                        try:
                            await websocket.close(code=1011, reason="SSH会话已丢失")
                        except Exception:
                            pass
                        return
                    consecutive_empty_errors = 0
                await asyncio.sleep(0.002)
        except Exception as e:
            print(f"WebSocket 终端读输出异常: {terminal_id} - {e}")
            ws_alive = False

    async def send_server_pings():
        nonlocal ws_alive
        try:
            while ws_alive:
                await asyncio.sleep(15)
                if not ws_alive:
                    break
                try:
                    await websocket.send_json({"type": "ping"})
                except Exception:
                    ws_alive = False
                    return
        except Exception as e:
            print(f"WebSocket 终端 ping 异常: {terminal_id} - {e}")
            ws_alive = False

    output_task = asyncio.create_task(read_output())
    ping_task = asyncio.create_task(send_server_pings())
    try:
        while ws_alive:
            message = await websocket.receive()
            msg_type = message.get("type")
            if msg_type == "websocket.disconnect":
                print(
                    "WebSocket 终端断开: "
                    f"{terminal_id} code={message.get('code')} "
                    f"reason={message.get('reason') or 'n/a'}"
                )
                break
            if msg_type != "websocket.receive":
                continue
            data = message.get("bytes")
            if data is None:
                text = message.get("text")
                if text is None:
                    continue
                try:
                    json_msg = json.loads(text)
                    if isinstance(json_msg, dict) and json_msg.get("type") == "ping":
                        await websocket.send_json({"type": "pong"})
                        continue
                    if isinstance(json_msg, dict) and json_msg.get("type") == "pong":
                        continue
                except (json.JSONDecodeError, ValueError):
                    pass
                data = text.encode("utf-8")
            try:
                await ssh_manager.send_terminal_input(terminal_id, data)
            except (ValueError, ConnectionError, OSError) as e:
                print(f"WebSocket 终端写入SSH失败: {terminal_id} - {e}")
                ws_alive = False
                try:
                    await websocket.close(code=1011, reason=f"SSH写入失败: {e}")
                except Exception:
                    pass
                break
    except WebSocketDisconnect:
        print(f"WebSocket 终端断开: {terminal_id}")
    except Exception as e:
        print(f"WebSocket 终端错误: {e}")
    finally:
        ws_alive = False
        output_task.cancel()
        ping_task.cancel()
        if not session_preexisting:
            await ssh_manager.close_terminal_session(terminal_id)
@app.websocket("/ws/events")
async def websocket_events(websocket: WebSocket):
    await websocket.accept()
    print("WebSocket 事件通道连接")
    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data) if data else {}
            event_type = msg.get("type", "")
            if event_type == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        print("WebSocket 事件通道断开")
    except Exception as e:
        print(f"WebSocket 事件通道错误: {e}")
@app.get("/health")
async def health_check():
    ssh_connected = False
    try:
        ssh_manager = get_ssh_manager()
        ssh_connected = ssh_manager.is_connected() if ssh_manager else False
    except Exception:
        ssh_connected = False
    return {
        "status": "ok",
        "service": "SDIT Python Backend",
        "version": "0.55.0",
        "ssh_connected": ssh_connected,
    }
