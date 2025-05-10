# macro_input_listeners.py
from PyQt5.QtCore import QThread, pyqtSignal
# pynput 모듈은 생성자에서 주입받음

class MouseCoordListenerThread(QThread):
    coords_captured_signal = pyqtSignal(int, int)
    capture_failed_signal = pyqtSignal(str)
    def __init__(self, pynput_mouse_module, parent=None):
        super().__init__(parent)
        self.listener = None
        self.mouse_module = pynput_mouse_module
    def run(self):
        try:
            def on_click(x, y, button, pressed):
                if button == self.mouse_module.Button.left and pressed:
                    self.coords_captured_signal.emit(x, y)
                    return False 
            self.listener = self.mouse_module.Listener(on_click=on_click)
            self.listener.start()
            self.listener.join()
        except Exception as e:
            self.capture_failed_signal.emit(f"좌표 캡처 중 오류: {e}")
    def stop_listener(self):
        if self.listener and hasattr(self.listener, 'stop') and self.listener.is_alive():
            try: self.listener.stop()
            except Exception: pass

class KeyboardKeyListenerThread(QThread):
    key_captured_signal = pyqtSignal(str)
    capture_failed_signal = pyqtSignal(str)
    def __init__(self, pynput_keyboard_module, parent=None):
        super().__init__(parent)
        self.keyboard_module = pynput_keyboard_module
        self.listener = None
        self.pressed_modifiers = set()
        self._captured_key_combo_str = None
    def _key_to_display_name(self, key):
        if isinstance(key, self.keyboard_module.Key):
            name = key.name
            display_map = { "space": "Space", "enter": "Enter", "backspace": "Backspace", "tab": "Tab",
                            "escape": "Esc", "delete": "Del", "ctrl": "Ctrl", "ctrl_l": "Ctrl", 
                            "ctrl_r": "Ctrl", "shift": "Shift", "shift_l": "Shift", "shift_r": "Shift",
                            "alt": "Alt", "alt_l": "Alt", "alt_r": "Alt", "alt_gr": "Alt",
                            "cmd": "Cmd", "cmd_l": "Cmd", "cmd_r": "Cmd", "win_l": "Win", 
                            "win_r": "Win", "super": "Super", "up": "Up", "down": "Down", 
                            "left": "Left", "right": "Right", "home": "Home", "end": "End", 
                            "page_up": "PageUp", "page_down": "PageDown",}
            if name.startswith('f') and name[1:].isdigit() and 1 <= int(name[1:]) <= 24: return name.upper()
            return display_map.get(name, name.capitalize())
        elif isinstance(key, self.keyboard_module.KeyCode):
            return key.char if key.char else f"[vk={key.vk}]"
        return None
    def run(self):
        self.pressed_modifiers.clear(); self._captured_key_combo_str = None
        def on_press(key):
            nonlocal self; is_modifier_key = False; mod_name_for_set = None
            if key in [self.keyboard_module.Key.ctrl_l, self.keyboard_module.Key.ctrl_r]: is_modifier_key = True; mod_name_for_set = "Ctrl"
            elif key in [self.keyboard_module.Key.shift_l, self.keyboard_module.Key.shift_r]: is_modifier_key = True; mod_name_for_set = "Shift"
            elif key in [self.keyboard_module.Key.alt_l, self.keyboard_module.Key.alt_r, self.keyboard_module.Key.alt_gr]: is_modifier_key = True; mod_name_for_set = "Alt"
            elif key in [self.keyboard_module.Key.cmd_l, self.keyboard_module.Key.cmd_r] or \
                 (hasattr(self.keyboard_module.Key, 'win_l') and key in [self.keyboard_module.Key.win_l, self.keyboard_module.Key.win_r]) or \
                 (hasattr(self.keyboard_module.Key, 'super') and key == self.keyboard_module.Key.super): is_modifier_key = True; mod_name_for_set = "Meta"
            if is_modifier_key and mod_name_for_set: self.pressed_modifiers.add(mod_name_for_set); return True
            main_key_display_name = self._key_to_display_name(key)
            if not main_key_display_name: return True
            final_mods_display = []
            if "Ctrl" in self.pressed_modifiers: final_mods_display.append("Ctrl")
            if "Shift" in self.pressed_modifiers: final_mods_display.append("Shift")
            if "Alt" in self.pressed_modifiers: final_mods_display.append("Alt")
            if "Meta" in self.pressed_modifiers: final_mods_display.append("Meta")
            if final_mods_display: self._captured_key_combo_str = "+".join(final_mods_display + [main_key_display_name])
            else: self._captured_key_combo_str = main_key_display_name
            self.key_captured_signal.emit(self._captured_key_combo_str); return False
        def on_release(key):
            nonlocal self; mod_name_for_set = None
            if key in [self.keyboard_module.Key.ctrl_l, self.keyboard_module.Key.ctrl_r]: mod_name_for_set = "Ctrl"
            elif key in [self.keyboard_module.Key.shift_l, self.keyboard_module.Key.shift_r]: mod_name_for_set = "Shift"
            elif key in [self.keyboard_module.Key.alt_l, self.keyboard_module.Key.alt_r, self.keyboard_module.Key.alt_gr]: mod_name_for_set = "Alt"
            elif key in [self.keyboard_module.Key.cmd_l, self.keyboard_module.Key.cmd_r] or \
                 (hasattr(self.keyboard_module.Key, 'win_l') and key in [self.keyboard_module.Key.win_l, self.keyboard_module.Key.win_r]) or \
                 (hasattr(self.keyboard_module.Key, 'super') and key == self.keyboard_module.Key.super): mod_name_for_set = "Meta"
            if mod_name_for_set and mod_name_for_set in self.pressed_modifiers:
                try: self.pressed_modifiers.remove(mod_name_for_set)
                except KeyError: pass
            if self._captured_key_combo_str is not None: return False
            return True
        try:
            with self.keyboard_module.Listener(on_press=on_press, on_release=on_release, suppress=False) as l:
                self.listener = l; l.join()
        except Exception as e: self.capture_failed_signal.emit(f"키 캡처 리스너 오류: {e}")
    def stop_listener(self):
        if self.listener and hasattr(self.listener, 'stop') and self.listener.is_alive():
            try: self.listener.stop()
            except: pass