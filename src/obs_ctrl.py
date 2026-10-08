"""OBS WebSocket integration via obs-websocket-py (supports OBS WebSocket v5)."""
from __future__ import annotations

import logging
import socket
import time
from typing import Optional

try:
    import obsws_python as obs
    OBS_LIB_OK = True
    # The library logs a full traceback whenever OBS isn't running; we already report "not connected".
    logging.getLogger("obsws_python").setLevel(logging.CRITICAL)
except ImportError:
    OBS_LIB_OK = False

from src.config import OBS_HOST, OBS_PASSWORD, OBS_PORT

# When OBS isn't running, a websocket connect takes ~4s on Windows before failing, and the
# dashboard asks on every rerun. Probe the port quickly and remember a failure for a while.
_RETRY_AFTER = 15.0
_down_until = 0.0


def _reachable() -> bool:
    global _down_until
    if time.monotonic() < _down_until:
        return False
    try:
        with socket.create_connection((OBS_HOST, OBS_PORT), timeout=0.5):
            return True
    except OSError:
        _down_until = time.monotonic() + _RETRY_AFTER
        return False


def retry_now():
    """Forget a recent connection failure so the next call tries OBS straight away."""
    global _down_until
    _down_until = 0.0


def _client() -> Optional["obs.ReqClient"]:
    if not OBS_LIB_OK:
        return None
    if not OBS_PASSWORD:
        return None
    if not _reachable():
        return None
    try:
        return obs.ReqClient(host=OBS_HOST, port=OBS_PORT, password=OBS_PASSWORD, timeout=3)
    except Exception:
        return None


def get_status() -> dict:
    """Return stream/record status and current scene."""
    cl = _client()
    if not cl:
        return {"connected": False}
    try:
        stream = cl.get_stream_status()
        record = cl.get_record_status()
        scene = cl.get_current_program_scene()
        stats = cl.get_stats()
        return {
            "connected": True,
            "streaming": stream.output_active,
            "recording": record.output_active,
            "current_scene": scene.current_program_scene_name,
            "cpu_usage": round(stats.cpu_usage, 1),
            "memory_usage": round(stats.memory_usage, 1),
            "fps": round(stats.active_fps, 1),
            "render_skipped_frames": stats.render_skipped_frames,
            "output_skipped_frames": stats.output_skipped_frames,
        }
    except Exception as e:
        return {"connected": False, "error": str(e)}
    finally:
        try:
            cl.disconnect()
        except Exception:
            pass


def get_scenes() -> list[str]:
    cl = _client()
    if not cl:
        return []
    try:
        resp = cl.get_scene_list()
        scenes = [s["sceneName"] for s in resp.scenes]
        return scenes
    except Exception:
        return []
    finally:
        try:
            cl.disconnect()
        except Exception:
            pass


def switch_scene(scene_name: str) -> bool:
    cl = _client()
    if not cl:
        return False
    try:
        cl.set_current_program_scene(scene_name)
        return True
    except Exception:
        return False
    finally:
        try:
            cl.disconnect()
        except Exception:
            pass


def start_stream() -> bool:
    cl = _client()
    if not cl:
        return False
    try:
        cl.start_stream()
        return True
    except Exception:
        return False
    finally:
        try:
            cl.disconnect()
        except Exception:
            pass


def stop_stream() -> bool:
    cl = _client()
    if not cl:
        return False
    try:
        cl.stop_stream()
        return True
    except Exception:
        return False
    finally:
        try:
            cl.disconnect()
        except Exception:
            pass


def start_recording() -> bool:
    cl = _client()
    if not cl:
        return False
    try:
        cl.start_record()
        return True
    except Exception:
        return False
    finally:
        try:
            cl.disconnect()
        except Exception:
            pass


def stop_recording() -> bool:
    cl = _client()
    if not cl:
        return False
    try:
        cl.stop_record()
        return True
    except Exception:
        return False
    finally:
        try:
            cl.disconnect()
        except Exception:
            pass


def set_source_visibility(scene_name: str, source_name: str, visible: bool) -> bool:
    cl = _client()
    if not cl:
        return False
    try:
        items = cl.get_scene_item_list(scene_name).scene_items
        for item in items:
            if item["sourceName"] == source_name:
                cl.set_scene_item_enabled(scene_name, item["sceneItemId"], visible)
                return True
        return False
    except Exception:
        return False
    finally:
        try:
            cl.disconnect()
        except Exception:
            pass


def get_sources(scene_name: str) -> list[dict]:
    cl = _client()
    if not cl:
        return []
    try:
        items = cl.get_scene_item_list(scene_name).scene_items
        return [
            {
                "id": i["sceneItemId"],
                "name": i["sourceName"],
                "visible": i["sceneItemEnabled"],
            }
            for i in items
        ]
    except Exception:
        return []
    finally:
        try:
            cl.disconnect()
        except Exception:
            pass
