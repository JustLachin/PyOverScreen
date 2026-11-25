"""Window targeting for Qt's X11 platform, including XWayland clients."""

import os

from Xlib import X, Xatom, display, error


class X11Windows:
    def __init__(self):
        self.connection = display.Display()
        self.root = self.connection.screen().root
        self.atoms = {
            name: self.connection.intern_atom(name)
            for name in ("_NET_CLIENT_LIST", "_NET_CLIENT_LIST_STACKING",
                         "_NET_ACTIVE_WINDOW", "_NET_WM_NAME", "_NET_WM_PID",
                         "UTF8_STRING")
        }

    def _property(self, window, name, value_type):
        prop = window.get_full_property(self.atoms[name], value_type)
        return prop.value if prop is not None else ()

    def _window_info(self, xid):
        window = self.connection.create_resource_object("window", xid)
        try:
            raw_title = self._property(window, "_NET_WM_NAME", self.atoms["UTF8_STRING"])
            title = raw_title.decode("utf-8", errors="replace") if raw_title else window.get_wm_name()
            pid = next(iter(self._property(window, "_NET_WM_PID", Xatom.CARDINAL)), None)
            wm_class = window.get_wm_class()
            if (title and pid != os.getpid() and not title.startswith("PyOverScreen - ")
                    and window.get_attributes().map_state == X.IsViewable):
                return title, int(xid), int(pid) if pid else None, wm_class[-1] if wm_class else ""
        except error.BadWindow:
            # A client can close between reading the client list and its properties.
            pass
        return None

    def list_windows(self):
        windows = []
        for xid in self._property(self.root, "_NET_CLIENT_LIST", Xatom.WINDOW):
            info = self._window_info(xid)
            if info:
                windows.append(info)
        return windows

    def should_raise(self, overlay_id, target_id, identity):
        active = next(iter(self._property(self.root, "_NET_ACTIVE_WINDOW", Xatom.WINDOW)), None)
        if not active:
            return False
        if active != target_id:
            info = self._window_info(active)
            if not info or (info[0], info[3]) != tuple(identity):
                return False
        stacking = self._property(self.root, "_NET_CLIENT_LIST_STACKING", Xatom.WINDOW)
        # The order is bottom-to-top. Raise only when a target obscures the overlay.
        for xid in reversed(stacking):
            if xid == overlay_id:
                return False
            if xid == active:
                return True
        return False


def connect_x11():
    try:
        return X11Windows()
    except (error.DisplayError, OSError):
        return None
