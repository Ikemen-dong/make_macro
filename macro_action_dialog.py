# macro_action_dialog.py
import sys
import platform 
import ctypes
from PyQt5.QtWidgets import (QApplication, QComboBox, QDialog, QFormLayout, QHBoxLayout, QLabel,
                             QLineEdit, QMessageBox, QPushButton, QSpinBox, QVBoxLayout, QWidget)
from PyQt5.QtCore import pyqtSignal, Qt, QPoint, QRect, QTimer
from PyQt5.QtGui import (QGuiApplication, QCursor, QColor, QPixmap, QImage, QPainter, QMouseEvent, QKeyEvent)

# Listener 스레드들을 import
from macro_input_listeners import MouseCoordListenerThread, KeyboardKeyListenerThread
# eyedropper.py 에서 Magnifier 등을 가져오도록 수정
from eyedropper import _SystemCursor, Magnifier, Overlay


class ActionInputDialog(QDialog):
    def __init__(self, main_app_status_update_func, pynput_mouse_module, pynput_keyboard_module, parent=None, action_to_edit=None):
        super().__init__(parent)
        self.pynput_mouse_module = pynput_mouse_module
        self.pynput_keyboard_module = pynput_keyboard_module
        self.main_app_status_update_func = main_app_status_update_func
        self.action_data = None
        self.coord_capture_listener_thread = None # 일반 좌표 및 검색 범위용
        self.key_listener_thread = None
        self.magnifier_widget: Magnifier | None = None
        self.magnifier_update_timer: QTimer | None = None
        self.overlay_widget_magnifier: Overlay | None = None
        self.is_magnifier_capture_active = False
        self._search_area_capture_stage = 0
        self._search_area_p1: QPoint | None = None

        self.setWindowTitle("액션 편집" if action_to_edit else "새 액션 추가")
        self.setMinimumWidth(450)
        
        self.layout = QVBoxLayout(self)

        # *** 사용자 지정 액션 이름 필드 추가 ***
        self.action_name_input = QLineEdit()
        self.action_name_input.setPlaceholderText("액션 이름 (선택 사항, 예: 로그인 버튼 클릭)")
        
        form_title_layout = QFormLayout()
        form_title_layout.addRow("액션 이름:", self.action_name_input)
        self.layout.addLayout(form_title_layout)
        # *** 사용자 지정 액션 이름 필드 끝 ***

        self.action_type_combo = QComboBox()
        self.action_type_combo.addItems(["마우스 클릭", "키보드 입력", "딜레이", "색 찾기 후 클릭"])
        self.layout.addWidget(QLabel("액션 유형:"))
        self.layout.addWidget(self.action_type_combo)
        
        self.form_layout = QFormLayout()
        self.layout.addLayout(self.form_layout)

        self.mouse_x_input = QSpinBox(); self.mouse_x_input.setRange(-99999, 99999)
        self.mouse_y_input = QSpinBox(); self.mouse_y_input.setRange(-99999, 99999)
        self.mouse_button_combo = QComboBox(); self.mouse_button_combo.addItems(["왼쪽 버튼", "오른쪽 버튼", "가운데 버튼"])
        self.capture_coords_button = QPushButton("마우스 좌표 캡처")
        
        self.captured_key_display = QLineEdit(); self.captured_key_display.setReadOnly(True); self.captured_key_display.setPlaceholderText("아래 버튼을 눌러 키를 캡처하세요.")
        self.capture_key_button = QPushButton("키보드 입력 캡처")
        
        self.delay_input_ms = QSpinBox(); self.delay_input_ms.setRange(1, 600000); self.delay_input_ms.setSuffix(" ms")
        self.delay_input_ms.setValue(100)
        self.delay_input_ms.setSingleStep(50) 
        
        self.color_capture_button = QPushButton("돋보기/색상 캡처 시작")
        self.captured_color_display = QLabel("캡처된 색상: 없음 (RGB)")
        self.captured_pos_display = QLabel("초기 위치: 없음 (X,Y)")
        self.search_x1_input = QSpinBox(); self.search_x1_input.setRange(-99999, 99999); self.search_x1_input.setToolTip("검색 시작 X")
        self.search_y1_input = QSpinBox(); self.search_y1_input.setRange(-99999, 99999); self.search_y1_input.setToolTip("검색 시작 Y")
        self.search_x2_input = QSpinBox(); self.search_x2_input.setRange(-99999, 99999); self.search_x2_input.setToolTip("검색 끝 X (X1과 다를 수 있음)")
        self.search_y2_input = QSpinBox(); self.search_y2_input.setRange(-99999, 99999); self.search_y2_input.setToolTip("검색 끝 Y (Y1과 다를 수 있음)")
        self.define_search_area_button = QPushButton("검색 범위 마우스 지정")
        self._temp_captured_color_rgb = None
        self._temp_captured_initial_xy = None

        self.action_type_combo.currentIndexChanged.connect(self.update_ui_for_action_type)
        self.capture_coords_button.clicked.connect(self.start_generic_coords_capture)
        self.capture_key_button.clicked.connect(self.start_key_capture_mode)
        self.color_capture_button.clicked.connect(self.start_color_capture_with_magnifier)
        self.define_search_area_button.clicked.connect(self.start_define_search_area_mode)

        self.ok_button = QPushButton("확인"); self.cancel_button = QPushButton("취소")
        self.ok_button.clicked.connect(self.accept_action)
        self.cancel_button.clicked.connect(self.reject)
        button_layout = QHBoxLayout(); button_layout.addStretch(); button_layout.addWidget(self.ok_button); button_layout.addWidget(self.cancel_button)
        self.layout.addLayout(button_layout)

        if action_to_edit: self._populate_widgets_for_editing(action_to_edit)
        self.update_ui_for_action_type() 
        if not action_to_edit: self.action_type_combo.setCurrentIndex(0)


    def _populate_widgets_for_editing(self, action_data):
        self.action_name_input.setText(action_data.get('user_given_name', '')) # 사용자 이름 로드
        action_type = action_data.get('type')
        self.action_type_combo.blockSignals(True)
        if action_type == "마우스 클릭":
            self.action_type_combo.setCurrentText("마우스 클릭"); self.mouse_x_input.setValue(action_data.get('x', 0)); self.mouse_y_input.setValue(action_data.get('y', 0))
            button_map_rev = {"left": "왼쪽 버튼", "right": "오른쪽 버튼", "middle": "가운데 버튼"}; self.mouse_button_combo.setCurrentText(button_map_rev.get(action_data.get('button'), "왼쪽 버튼"))
        elif action_type == "키보드 입력":
            self.action_type_combo.setCurrentText("키보드 입력"); self.captured_key_display.setText(action_data.get('key_str', ''))
        elif action_type == "딜레이":
            self.action_type_combo.setCurrentText("딜레이"); self.delay_input_ms.setValue(action_data.get('duration_ms', 100))
        elif action_type == "색 찾기 후 클릭":
            self.action_type_combo.setCurrentText("색 찾기 후 클릭")
            self._temp_captured_color_rgb = tuple(action_data.get('target_color', [0,0,0]))
            self._temp_captured_initial_xy = tuple(action_data.get('initial_xy', [0,0]))
            self.captured_color_display.setText(f"캡처된 색상: RGB{self._temp_captured_color_rgb}")
            self.captured_pos_display.setText(f"초기 위치: XY{self._temp_captured_initial_xy}")
            search_area = action_data.get('search_area', [0,0,100,100])
            self.search_x1_input.setValue(search_area[0]); self.search_y1_input.setValue(search_area[1])
            self.search_x2_input.setValue(search_area[2]); self.search_y2_input.setValue(search_area[3])
        self.action_type_combo.blockSignals(False)

    def update_ui_for_action_type(self):
        while self.form_layout.rowCount() > 0: self.form_layout.removeRow(0)
        current_action_type = self.action_type_combo.currentText()
        # 모든 타입별 위젯을 일단 숨김 (레이아웃에서 제거된 상태이므로 addRow 시 다시 나타남)
        # 또는 각 위젯의 setVisible(False)를 먼저 호출할 수도 있음
        if current_action_type == "마우스 클릭":
            self.form_layout.addRow("X 좌표:", self.mouse_x_input); self.form_layout.addRow("Y 좌표:", self.mouse_y_input)
            self.form_layout.addRow("버튼:", self.mouse_button_combo); self.form_layout.addRow(self.capture_coords_button)
        elif current_action_type == "키보드 입력":
            self.form_layout.addRow("캡처된 키:", self.captured_key_display); self.form_layout.addRow(self.capture_key_button)
        elif current_action_type == "딜레이":
            self.form_layout.addRow("대기 시간 (ms):", self.delay_input_ms)
        elif current_action_type == "색 찾기 후 클릭":
            self.form_layout.addRow(self.color_capture_button); self.form_layout.addRow(self.captured_color_display)
            self.form_layout.addRow(self.captured_pos_display); self.form_layout.addRow(QLabel("--- 검색 범위 (좌상단 XY, 우하단 XY) ---"))
            self.form_layout.addRow("X1:", self.search_x1_input); self.form_layout.addRow("Y1:", self.search_y1_input)
            self.form_layout.addRow("X2:", self.search_x2_input); self.form_layout.addRow("Y2:", self.search_y2_input)
            self.form_layout.addRow(self.define_search_area_button)

    def _is_any_capture_active(self): # 이전과 동일
        return self.is_magnifier_capture_active or \
               self._search_area_capture_stage > 0 or \
               (self.coord_capture_listener_thread and self.coord_capture_listener_thread.isRunning()) or \
               (self.key_listener_thread and self.key_listener_thread.isRunning())
    
    def start_generic_coords_capture(self): # 이전과 동일
        if self._is_any_capture_active(): QMessageBox.warning(self, "캡처 중복", "다른 캡처 기능이 활성화되어 있습니다."); return
        self.capture_coords_button.setEnabled(False); self.main_app_status_update_func("일반 좌표 캡처: 원하는 위치를 좌클릭하세요...")
        QMessageBox.information(self, "좌표 캡처", "원하는 위치를 마우스 왼쪽 버튼으로 클릭하세요.")
        self.coord_capture_listener_thread = MouseCoordListenerThread(self.pynput_mouse_module, self)
        self.coord_capture_listener_thread.coords_captured_signal.connect(self.on_generic_coords_captured)
        self.coord_capture_listener_thread.capture_failed_signal.connect(self.on_capture_failed_generic) 
        self.coord_capture_listener_thread.finished.connect(self.on_generic_coord_listener_finished)
        self.coord_capture_listener_thread.start()

    def on_generic_coords_captured(self, x, y): # 이전과 동일
        self.mouse_x_input.setValue(x); self.mouse_y_input.setValue(y)
        self.main_app_status_update_func(f"일반 좌표 캡처 완료: ({x}, {y})")
        QMessageBox.information(self, "캡처 완료", f"좌표 ({x}, {y})가 '마우스 클릭' 액션의 X,Y에 입력되었습니다.")

    def on_generic_coord_listener_finished(self): # 이전과 동일
        self.capture_coords_button.setEnabled(True)
        if self.coord_capture_listener_thread: self.main_app_status_update_func("일반 좌표 캡처 모드 종료.")
        self.coord_capture_listener_thread = None

    def start_key_capture_mode(self): # 이전과 동일
        if self._is_any_capture_active(): QMessageBox.warning(self, "캡처 중복", "다른 캡처 기능이 활성화되어 있습니다."); return
        self.capture_key_button.setEnabled(False); self.main_app_status_update_func("키 캡처 모드...")
        QMessageBox.information(self, "키 캡처 시작", "원하는 키(조합)를 누르세요.")
        self.key_listener_thread = KeyboardKeyListenerThread(self.pynput_keyboard_module, self)
        self.key_listener_thread.key_captured_signal.connect(self.on_key_captured)
        self.key_listener_thread.capture_failed_signal.connect(self.on_capture_failed_generic)
        self.key_listener_thread.finished.connect(self.on_key_listener_finished)
        self.key_listener_thread.start()

    def on_key_captured(self, key_str): # 이전과 동일
        self.captured_key_display.setText(key_str)
        self.main_app_status_update_func(f"키 캡처: '{key_str}'"); QMessageBox.information(self, "캡처 완료", f"키 '{key_str}' 입력됨.")

    def on_key_listener_finished(self): # 이전과 동일
        self.capture_key_button.setEnabled(True)
        if self.key_listener_thread: self.main_app_status_update_func("키보드 입력 캡처 모드 종료.")
        self.key_listener_thread = None

    def on_capture_failed_generic(self, error_message): # 이전과 동일
        self.main_app_status_update_func(f"캡처 실패: {error_message}"); QMessageBox.warning(self, "캡처 실패", error_message)
        if self.is_magnifier_capture_active: self._finish_magnifier_color_capture(False)
        if self._search_area_capture_stage > 0: self._finish_define_search_area_pynput(False)
        if self.coord_capture_listener_thread: self.on_generic_coord_listener_finished()
        if self.key_listener_thread: self.on_key_listener_finished()

    def start_color_capture_with_magnifier(self): # 이전과 동일 (Qt 이벤트 + Magnifier 위젯 사용)
        if self._is_any_capture_active(): QMessageBox.warning(self, "캡처 중복", "다른 캡처 기능이 이미 활성화되어 있습니다."); return
        self.is_magnifier_capture_active = True; self._search_area_capture_stage = 0
        self.main_app_status_update_func("돋보기/색상 캡처: 화면 클릭(선택) 또는 ESC(취소).")
        self.color_capture_button.setText("캡처 중... (ESC로 취소)"); self.color_capture_button.setEnabled(False)
        if not self.magnifier_widget: self.magnifier_widget = Magnifier()
        if not self.overlay_widget_magnifier: self.overlay_widget_magnifier = Overlay()
        QApplication.setOverrideCursor(Qt.BlankCursor); _SystemCursor.hide()
        self.overlay_widget_magnifier.show(); self.grabMouse(); self.grabKeyboard() 
        self.magnifier_widget.update_preview(QCursor.pos()); self.magnifier_widget.show()
        if not self.magnifier_update_timer:
            self.magnifier_update_timer = QTimer(self); self.magnifier_update_timer.setInterval(25)
            self.magnifier_update_timer.timeout.connect(self._update_magnifier_tick)
        self.magnifier_update_timer.start()

    def _update_magnifier_tick(self): # 이전과 동일
        if self.is_magnifier_capture_active and self.magnifier_widget: self.magnifier_widget.update_preview(QCursor.pos())

    def _finish_magnifier_color_capture(self, commit_data: bool): # 이전과 동일
        if not self.is_magnifier_capture_active : return
        if self.magnifier_update_timer: self.magnifier_update_timer.stop()
        self.releaseMouse(); self.releaseKeyboard()
        if self.overlay_widget_magnifier: self.overlay_widget_magnifier.hide()
        QApplication.restoreOverrideCursor(); _SystemCursor.show()
        if self.magnifier_widget:
            if commit_data:
                final_pos, q_color = self.magnifier_widget.get_current_color_info()
                if q_color.isValid():
                    self._temp_captured_initial_xy = (final_pos.x(), final_pos.y())
                    self._temp_captured_color_rgb = (q_color.red(), q_color.green(), q_color.blue())
                    self.captured_pos_display.setText(f"초기 위치: XY{self._temp_captured_initial_xy}")
                    self.captured_color_display.setText(f"캡처된 색상: RGB{self._temp_captured_color_rgb}")
                    self.main_app_status_update_func(f"색상/위치 캡처 성공: XY{self._temp_captured_initial_xy}, RGB{self._temp_captured_color_rgb}")
                else: self.main_app_status_update_func(f"색상 캡처 실패: 유효하지 않은 색상값({q_color.name()}).")
            self.magnifier_widget.hide()
        self.is_magnifier_capture_active = False
        self.color_capture_button.setText("돋보기/색상 캡처 시작"); self.color_capture_button.setEnabled(True)
        self.main_app_status_update_func("돋보기/색상 캡처 모드 종료됨."); self.activateWindow()
    
    def start_define_search_area_mode(self): # pynput 스레드 사용으로 변경
        if self._is_any_capture_active(): QMessageBox.warning(self, "캡처 중복", "다른 캡처 기능이 이미 활성화되어 있습니다."); return
        self._search_area_capture_stage = 1; self.is_magnifier_capture_active = False; self._search_area_p1 = None
        self.main_app_status_update_func("검색 범위 지정 (1/2): 첫 번째 모서리를 클릭하세요.")
        QMessageBox.information(self, "검색 범위 지정 (1/2)", "검색 범위의 첫 번째 모서리(예: 좌상단)를 클릭하세요.\n(ESC로 취소하려면 이 대화 상자를 닫아야 할 수 있습니다.)")
        self.define_search_area_button.setText("지정 중...(P1 대기)"); self.define_search_area_button.setEnabled(False)
        QApplication.setOverrideCursor(Qt.CrossCursor) # 전체 앱 커서 변경
        # _SystemCursor.hide() # 선택적: 검색 범위 지정 시에는 시스템 커서 유지도 괜찮음

        # MouseCoordListenerThread는 단일 클릭 후 종료되므로, 각 단계마다 새로 생성
        self.coord_capture_listener_thread = MouseCoordListenerThread(self.pynput_mouse_module, self)
        self.coord_capture_listener_thread.coords_captured_signal.connect(self._on_search_area_point_captured)
        self.coord_capture_listener_thread.capture_failed_signal.connect(self.on_capture_failed_generic)
        self.coord_capture_listener_thread.finished.connect(self._on_search_area_listener_stage_finished)
        self.coord_capture_listener_thread.start()

    def _on_search_area_point_captured(self, x, y):
        if not self._search_area_capture_stage: return # 이미 종료/취소된 경우

        if self._search_area_capture_stage == 1:
            self._search_area_p1 = QPoint(x, y)
            self.search_x1_input.setValue(x) # 임시로 첫 번째 클릭을 X1, Y1에 설정
            self.search_y1_input.setValue(y)
            self.main_app_status_update_func(f"첫 점 ({x},{y}) 선택. 검색 범위 지정 (2/2): 두 번째 모서리를 클릭하세요.")
            QMessageBox.information(self, "검색 범위 지정 (2/2)", f"첫 번째 점 ({x},{y})이 선택되었습니다.\n이제 두 번째 모서리(예: 우하단)를 클릭하세요.")
            self._search_area_capture_stage = 2
            self.define_search_area_button.setText("지정 중...(P2 대기)")
            
            # 다음 클릭을 위해 새 리스너 시작 (이전 리스너는 finished 후 정리됨)
            self.coord_capture_listener_thread = MouseCoordListenerThread(self.pynput_mouse_module, self)
            self.coord_capture_listener_thread.coords_captured_signal.connect(self._on_search_area_point_captured)
            self.coord_capture_listener_thread.capture_failed_signal.connect(self.on_capture_failed_generic)
            self.coord_capture_listener_thread.finished.connect(self._on_search_area_listener_stage_finished)
            self.coord_capture_listener_thread.start()

        elif self._search_area_capture_stage == 2:
            p2 = QPoint(x, y)
            if self._search_area_p1 is None: # 거의 발생하지 않아야 함
                self._finish_define_search_area_pynput(success=False, message="오류: 첫 번째 점 정보가 없습니다.")
                return

            x1_val = min(self._search_area_p1.x(), p2.x())
            y1_val = min(self._search_area_p1.y(), p2.y())
            x2_val = max(self._search_area_p1.x(), p2.x())
            y2_val = max(self._search_area_p1.y(), p2.y())

            if x1_val >= x2_val or y1_val >= y2_val: # 너비나 높이가 0이거나 음수면 안됨
                QMessageBox.warning(self, "영역 오류", "선택된 두 점으로 유효한 사각형 영역(너비/높이 > 0)을 만들 수 없습니다.\n첫 번째 점부터 다시 시도하세요.")
                self._search_area_p1 = None
                self._search_area_capture_stage = 1 
                self.main_app_status_update_func("검색 영역 지정 오류. 첫 번째 모서리를 다시 클릭하세요.")
                self.define_search_area_button.setText("지정 중...(P1 대기)")
                # 첫 번째 클릭을 위해 리스너 다시 시작
                self.coord_capture_listener_thread = MouseCoordListenerThread(self.pynput_mouse_module, self)
                self.coord_capture_listener_thread.coords_captured_signal.connect(self._on_search_area_point_captured)
                self.coord_capture_listener_thread.capture_failed_signal.connect(self.on_capture_failed_generic)
                self.coord_capture_listener_thread.finished.connect(self._on_search_area_listener_stage_finished)
                self.coord_capture_listener_thread.start()
                return

            self.search_x1_input.setValue(x1_val)
            self.search_y1_input.setValue(y1_val)
            self.search_x2_input.setValue(x2_val)
            self.search_y2_input.setValue(y2_val)
            self._finish_define_search_area_pynput(success=True)
        # MouseCoordListenerThread는 한 번의 클릭 후 자동으로 중지됨.

    def _on_search_area_listener_stage_finished(self):
        # 이 슬롯은 각 MouseCoordListenerThread가 끝날 때 호출됨.
        # self.coord_capture_listener_thread = None # 여기서 None으로 하면 다음 스레드 시작 불가
        # _finish_define_search_area_pynput 에서 최종 정리 및 버튼 상태 관리
        if not self._search_area_capture_stage: # 이미 종료된 경우
             self.define_search_area_button.setEnabled(True)
             self.define_search_area_button.setText("검색 범위 마우스 지정")

    def _finish_define_search_area_pynput(self, success: bool, message: str = None):
        if self.coord_capture_listener_thread and self.coord_capture_listener_thread.isRunning():
            self.coord_capture_listener_thread.coords_captured_signal.disconnect(self._on_search_area_point_captured)
            self.coord_capture_listener_thread.capture_failed_signal.disconnect(self.on_capture_failed_generic)
            self.coord_capture_listener_thread.finished.disconnect(self._on_search_area_listener_stage_finished)
            self.coord_capture_listener_thread.stop_listener()
        self.coord_capture_listener_thread = None # 참조 제거
        
        QApplication.restoreOverrideCursor() # 커서 원복
        # _SystemCursor.show() # 필요시

        self._search_area_capture_stage = 0 # 상태 초기화
        self.define_search_area_button.setText("검색 범위 마우스 지정")
        self.define_search_area_button.setEnabled(True)
        
        if success:
            self.main_app_status_update_func(f"검색 범위 지정 완료: ({self.search_x1_input.value()},{self.search_y1_input.value()})-({self.search_x2_input.value()},{self.search_y2_input.value()})")
        else:
            final_message = message if message else "검색 범위 지정이 취소되었거나 실패했습니다."
            self.main_app_status_update_func(final_message)
        self.activateWindow() # 다이얼로그 다시 활성화

    def mousePressEvent(self, event: QMouseEvent): # 돋보기 모드용 (검색 범위 지정은 pynput 사용)
        if self.is_magnifier_capture_active and not self._search_area_capture_stage:
            if event.button() == Qt.RightButton: self._finish_magnifier_color_capture(commit_data=False); event.accept(); return
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent): # 돋보기 모드용
        if self.is_magnifier_capture_active and not self._search_area_capture_stage: 
            if event.button() == Qt.LeftButton: self._finish_magnifier_color_capture(commit_data=True)
            event.accept(); return
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event: QKeyEvent): # 돋보기 모드 ESC 취소
        if event.key() == Qt.Key_Escape:
            if self.is_magnifier_capture_active:
                self.main_app_status_update_func("돋보기/색상 캡처가 ESC로 취소되었습니다.")
                self._finish_magnifier_color_capture(commit_data=False); event.accept(); return
            # 검색 범위 지정 모드에서 ESC는 현재 pynput 리스너가 가로채므로,
            # 이 이벤트 핸들러로 잘 안 올 수 있음. 사용자가 다이얼로그를 닫는 것으로 취소.
            # 또는, _finish_define_search_area_pynput(False)를 호출할 수 있는 다른 수단 필요.
        super().keyPressEvent(event)
        
    def get_action_data(self): # 사용자 지정 이름 추가
        action_type = self.action_type_combo.currentText()
        user_name = self.action_name_input.text().strip()
        data = {'type': action_type, 'user_given_name': user_name if user_name else None }
        details_list = []
        if action_type == "마우스 클릭": 
            x, y = self.mouse_x_input.value(), self.mouse_y_input.value()
            button_map = {"왼쪽 버튼": "left", "오른쪽 버튼": "right", "가운데 버튼": "middle"}
            button = button_map.get(self.mouse_button_combo.currentText(), "left")
            data.update({'x': x, 'y': y, 'button': button}); details_list.append(f"{self.mouse_button_combo.currentText()} 클릭 ({x},{y})")
        elif action_type == "키보드 입력": 
            key_str = self.captured_key_display.text().strip()
            if not key_str: QMessageBox.warning(self, "입력 오류", "캡처된 키가 없습니다."); return None
            data.update({'key_str': key_str}); details_list.append(f"키 입력: '{key_str}'")
        elif action_type == "딜레이": 
            duration = self.delay_input_ms.value(); data.update({'duration_ms': duration}); details_list.append(f"{duration}ms 대기")
        elif action_type == "색 찾기 후 클릭":
            if not self._temp_captured_color_rgb or not self._temp_captured_initial_xy: QMessageBox.warning(self, "입력 오류", "'색상 및 위치 캡처'를 먼저 실행해주세요."); return None
            x1, y1, x2, y2 = self.search_x1_input.value(), self.search_y1_input.value(), self.search_x2_input.value(), self.search_y2_input.value()
            if not (x1 < x2 and y1 < y2) : QMessageBox.warning(self, "범위 오류", "검색 범위의 끝 X,Y는 시작 X,Y보다 커야 합니다."); return None
            data.update({'target_color': list(self._temp_captured_color_rgb), 'initial_xy': list(self._temp_captured_initial_xy), 'search_area': [x1, y1, x2, y2]})
            details_list.append(f"색상 RGB{self._temp_captured_color_rgb} 찾아서 클릭 (범위: {x1},{y1}-{x2},{y2})")
        
        auto_details = " ".join(details_list) if details_list else "알 수 없는 액션"
        data['details'] = f"{user_name} ({auto_details})" if user_name and auto_details else (user_name if user_name else auto_details)
        return data

    def accept_action(self):
        self.action_data = self.get_action_data();
        if self.action_data:
            if self.action_data['type'] == "색 찾기 후 클릭":
                 self._temp_captured_color_rgb = None; self._temp_captured_initial_xy = None
            self.accept()

    def closeEvent(self, event):
        if self.is_magnifier_capture_active: self._finish_magnifier_color_capture(commit_data=False)
        if self._search_area_capture_stage > 0: self._finish_define_search_area_pynput(success=False)
        # pynput 리스너 스레드 정리
        if self.coord_capture_listener_thread and self.coord_capture_listener_thread.isRunning(): 
            self.coord_capture_listener_thread.stop_listener(); self.coord_capture_listener_thread.wait(500)
        if self.key_listener_thread and self.key_listener_thread.isRunning(): 
            self.key_listener_thread.stop_listener(); self.key_listener_thread.wait(500)
        # Magnifier, Overlay 위젯 정리
        if self.magnifier_widget: self.magnifier_widget.close() 
        if self.overlay_widget_magnifier: self.overlay_widget_magnifier.close()
        super().closeEvent(event)