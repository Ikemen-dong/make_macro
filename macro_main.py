# macro_main.py
import sys
from PyQt5.QtWidgets import QApplication, QMessageBox

# pynput 및 Pillow, mss 로드 시도
pynput_mouse_module_loaded = None
pynput_keyboard_module_loaded = None
pillow_loaded = False 
mss_loaded = False 

try:
    from pynput import mouse as pynput_mouse_mod
    from pynput import keyboard as pynput_keyboard_mod # keyboard import 추가
    pynput_mouse_module_loaded = pynput_mouse_mod
    pynput_keyboard_module_loaded = pynput_keyboard_mod
except ImportError:
    pass 

try:
    from PIL import ImageGrab 
    pillow_loaded = True
except ImportError:
    pass 

try:
    import mss 
    mss_loaded = True
except ImportError:
    pass 

# MacroApp은 모든 import 시도 후에 import
from macro_app_widget import MacroApp 

if __name__ == '__main__':
    app = QApplication(sys.argv)

    if not (pynput_mouse_module_loaded and pynput_keyboard_module_loaded):
        QMessageBox.critical(None, "필수 라이브러리 오류",
                             "pynput 라이브러리 초기화에 실패했습니다.\n"
                             "'pip install pynput'으로 설치 후 다시 실행해주세요.\n"
                             "프로그램을 종료합니다.")
        sys.exit(1)
    
    # Pillow / mss 상태에 따른 알림 (선택적)
    # if not pillow_loaded and not mss_loaded: 
    #     QMessageBox.warning(None, "라이브러리 누락 경고", ...)
    # elif not mss_loaded and pillow_loaded:
    #      QMessageBox.information(None, "성능 알림", ...)
    # elif mss_loaded:
    #     print("mss 라이브러리가 로드되어 색상 미리보기에 사용됩니다.") # 상태바에서 확인 가능


    main_window = MacroApp(pynput_mouse_module_loaded, pynput_keyboard_module_loaded)
    main_window.show()
    sys.exit(app.exec_())