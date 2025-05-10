# macro_app_widget.py
import sys
import time
import json
import os
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QListWidget, 
                             QPushButton, QLabel, QLineEdit, QDialog, QKeySequenceEdit,
                             QAbstractItemView, QMessageBox, QGroupBox, QDateTimeEdit, QApplication, QCheckBox, QFormLayout) # QCheckBox 추가
from PyQt5.QtCore import Qt, QTimer, QDateTime
from PyQt5.QtGui import QKeySequence

from macro_action_dialog import ActionInputDialog 

try:
    from PIL import ImageGrab
except ImportError:
    ImageGrab = None

class MacroApp(QWidget):
    CONFIG_FILE = "macro_config.json"

    def __init__(self, pynput_mouse_module, pynput_keyboard_module):
        super().__init__()
        self.pynput_mouse = pynput_mouse_module
        self.pynput_keyboard = pynput_keyboard_module
        self.actions_list = []
        self.hotkey = None
        self.hotkey_listener_thread = None
        self.hotkey_id_str = None
        self.scheduled_datetime = None
        self.schedule_timer = QTimer(self)
        self.schedule_timer.timeout.connect(self.check_schedule_and_execute)
        self.is_schedule_active = False
        self.initUI()
        self.load_config()

    def initUI(self):
        self.setWindowTitle('나만의 자동 입력기 Ver 1.5 (기능 추가)')
        self.setGeometry(150, 150, 750, 750) # 높이 약간 더 증가

        main_layout = QVBoxLayout(self)

        # --- 액션 목록 및 관리 버튼 그룹 ---
        action_list_group_box = QGroupBox("액션 목록") # 그룹박스 추가
        action_list_group_layout = QVBoxLayout() # 그룹박스 내부 레이아웃

        action_list_and_buttons_layout = QHBoxLayout()
        self.action_list_widget = QListWidget()
        self.action_list_widget.setSelectionMode(QAbstractItemView.SingleSelection)
        self.action_list_widget.itemDoubleClicked.connect(self.edit_selected_action)
        action_list_and_buttons_layout.addWidget(self.action_list_widget, 3)

        action_buttons_layout = QVBoxLayout()
        self.add_action_button = QPushButton("➕ 액션 추가")
        self.edit_action_button = QPushButton("✏️ 액션 수정")
        self.delete_action_button = QPushButton("➖ 액션 삭제")
        self.delete_all_button = QPushButton("🗑️ 모두 삭제") # *** 모두 삭제 버튼 추가 ***
        self.move_up_button = QPushButton("▲ 위로 이동")
        self.move_down_button = QPushButton("▼ 아래로 이동")
        
        action_buttons_layout.addWidget(self.add_action_button)
        action_buttons_layout.addWidget(self.edit_action_button)
        action_buttons_layout.addWidget(self.delete_action_button)
        action_buttons_layout.addWidget(self.delete_all_button) # 버튼 추가
        action_buttons_layout.addSpacing(20)
        action_buttons_layout.addWidget(self.move_up_button)
        action_buttons_layout.addWidget(self.move_down_button)
        action_buttons_layout.addStretch()
        action_list_and_buttons_layout.addLayout(action_buttons_layout, 1)
        action_list_group_layout.addLayout(action_list_and_buttons_layout)
        
        # --- 일괄 딜레이 체크박스 추가 ---
        self.inter_delay_checkbox = QCheckBox("모든 액션 사이에 600ms 딜레이 자동 삽입/삭제")
        action_list_group_layout.addWidget(self.inter_delay_checkbox)
        # --- 일괄 딜레이 체크박스 끝 ---

        action_list_group_box.setLayout(action_list_group_layout)
        main_layout.addWidget(action_list_group_box)


        # --- 단축키 설정 그룹 (이전과 동일) ---
        hotkey_group_box = QGroupBox("실행 단축키 설정") # 이하 동일
        hotkey_form_layout = QFormLayout()
        self.hotkey_display = QLineEdit()
        self.hotkey_display.setReadOnly(True); self.hotkey_display.setPlaceholderText("설정되지 않음")
        hotkey_form_layout.addRow(QLabel("현재 단축키:"), self.hotkey_display)
        hotkey_buttons_layout = QHBoxLayout()
        self.set_hotkey_button = QPushButton("단축키 설정/변경"); self.clear_hotkey_button = QPushButton("단축키 해제")
        hotkey_buttons_layout.addWidget(self.set_hotkey_button); hotkey_buttons_layout.addWidget(self.clear_hotkey_button)
        hotkey_form_layout.addRow(hotkey_buttons_layout)
        hotkey_group_box.setLayout(hotkey_form_layout); main_layout.addWidget(hotkey_group_box)
        
        # --- 예약 실행 설정 그룹 (이전과 동일) ---
        schedule_group_box = QGroupBox("예약 실행 설정") # 이하 동일
        schedule_form_layout = QFormLayout()
        self.schedule_datetime_edit = QDateTimeEdit(self)
        self.schedule_datetime_edit.setDateTime(QDateTime.currentDateTime().addSecs(300))
        self.schedule_datetime_edit.setCalendarPopup(True); self.schedule_datetime_edit.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
        schedule_form_layout.addRow(QLabel("실행 시간:"), self.schedule_datetime_edit)
        self.schedule_status_label = QLabel("예약 없음")
        schedule_form_layout.addRow(QLabel("예약 상태:"), self.schedule_status_label)
        schedule_buttons_layout = QHBoxLayout()
        self.set_schedule_button = QPushButton("예약 설정"); self.cancel_schedule_button = QPushButton("예약 취소")
        self.cancel_schedule_button.setEnabled(False)
        schedule_buttons_layout.addWidget(self.set_schedule_button); schedule_buttons_layout.addWidget(self.cancel_schedule_button)
        schedule_form_layout.addRow(schedule_buttons_layout)
        schedule_group_box.setLayout(schedule_form_layout); main_layout.addWidget(schedule_group_box)

        self.status_label = QLabel("준비 완료.")
        self.status_label.setStyleSheet("padding: 5px; background-color: #e9e9e9; border: 1px solid #cccccc;")
        main_layout.addWidget(self.status_label)

        # 시그널 연결
        self.add_action_button.clicked.connect(self.add_new_action)
        self.edit_action_button.clicked.connect(self.edit_selected_action)
        self.delete_action_button.clicked.connect(self.delete_selected_action)
        self.delete_all_button.clicked.connect(self.delete_all_actions) # *** 모두 삭제 연결 ***
        self.set_hotkey_button.clicked.connect(self.set_hotkey_dialog)
        self.clear_hotkey_button.clicked.connect(self.clear_hotkey_user_action)
        self.move_up_button.clicked.connect(self.move_action_up)
        self.move_down_button.clicked.connect(self.move_action_down)
        self.set_schedule_button.clicked.connect(self.set_schedule)
        self.cancel_schedule_button.clicked.connect(self.cancel_schedule_user_action)
        self.inter_delay_checkbox.stateChanged.connect(self.toggle_inter_action_delay) # *** 딜레이 체크박스 연결 ***


    def update_status(self, message): # 이전과 동일
        current_time = time.strftime('%H:%M:%S'); log_message = f"[{current_time}] {message}"
        self.status_label.setText(log_message); print(log_message)

    def save_config(self): # user_given_name 저장 로직은 ActionInputDialog에서 처리, 여기선 actions_list 그대로 저장
        config_data = {'actions': self.actions_list, 'hotkey': self.hotkey.toString(QKeySequence.PortableText) if self.hotkey and not self.hotkey.isEmpty() else None}
        try:
            with open(self.CONFIG_FILE, 'w', encoding='utf-8') as f: json.dump(config_data, f, ensure_ascii=False, indent=4)
            self.update_status(f"설정이 '{self.CONFIG_FILE}'에 저장되었습니다.")
        except IOError as e: self.update_status(f"설정 저장 실패: {e}"); QMessageBox.warning(self, "저장 오류", f"파일 저장 중 오류:\n{e}")

    def load_config(self): # user_given_name 로드 로직은 ActionInputDialog에서 처리, 여기선 actions_list 그대로 로드
        if not os.path.exists(self.CONFIG_FILE): self.update_status(f"설정 파일 '{self.CONFIG_FILE}' 없음. 기본 설정 시작."); return
        try:
            with open(self.CONFIG_FILE, 'r', encoding='utf-8') as f: config_data = json.load(f)
            self.actions_list = config_data.get('actions', []); 
            
            # 로드 후 inter_delay_checkbox 상태 업데이트 (auto_inserted 플래그 기반)
            has_auto_inserted_delay = any(action.get('auto_inserted', False) for action in self.actions_list if action['type'] == '딜레이')
            self.inter_delay_checkbox.blockSignals(True) # 상태 변경 시그널 임시 비활성화
            self.inter_delay_checkbox.setChecked(has_auto_inserted_delay)
            self.inter_delay_checkbox.blockSignals(False)

            self.update_action_list_widget() # UI 업데이트 먼저

            hotkey_str = config_data.get('hotkey')
            if hotkey_str:
                self.hotkey = QKeySequence.fromString(hotkey_str, QKeySequence.PortableText)
                if self.hotkey and not self.hotkey.isEmpty():
                    self.hotkey_display.setText(self.hotkey.toString(QKeySequence.NativeText))
                    if self.setup_hotkey_listener(): self.update_status(f"저장된 단축키 '{self.hotkey_display.text()}' 로드 및 리스너 설정됨.")
                    else: self.update_status(f"저장된 단축키 '{self.hotkey_display.text()}' 리스너 설정 실패."); self.clear_hotkey_internal_logic()
                else: self.hotkey = None; self.hotkey_display.clear(); self.hotkey_display.setPlaceholderText("설정되지 않음"); self.update_status(f"저장된 단축키 문자열 '{hotkey_str}' 유효하지 않음.")
            else: self.hotkey = None; self.hotkey_display.clear(); self.hotkey_display.setPlaceholderText("설정되지 않음")
            self.update_status(f"설정이 '{self.CONFIG_FILE}'에서 로드되었습니다.")
        except json.JSONDecodeError as e:
            self.update_status(f"설정 파일 '{self.CONFIG_FILE}' 파싱 오류: {e}. 기본 설정 시작."); QMessageBox.warning(self, "로드 오류", f"설정 파일 JSON 분석 오류:\n{e}")
            self.actions_list = []; self.update_action_list_widget(); self.clear_hotkey_internal_logic()
        except Exception as e:
            self.update_status(f"설정 로드 중 오류: {e}. 기본 설정 시작."); QMessageBox.critical(self, "로드 오류", f"설정 로드 오류:\n{e}")
            self.actions_list = []; self.update_action_list_widget(); self.clear_hotkey_internal_logic()

    def add_new_action(self): # 이전과 동일
        dialog = ActionInputDialog(self.update_status, self.pynput_mouse, self.pynput_keyboard, self)
        if dialog.exec_() == QDialog.Accepted:
            action_data = dialog.action_data
            if action_data:
                # 일괄 딜레이 체크 상태에 따라 새 액션 뒤에 딜레이 추가 (선택적)
                # 현재는 toggle_inter_action_delay 에서 일괄 처리하므로 여기서는 추가 안 함.
                self.actions_list.append(action_data)
                self.update_action_list_widget()
                self.update_status(f"액션 추가됨: {action_data.get('user_given_name') or action_data['details']}")


    def edit_selected_action(self): # 이전과 동일
        current_row = self.action_list_widget.currentRow()
        if current_row < 0: QMessageBox.warning(self, "선택 오류", "수정할 액션을 선택하세요."); self.update_status("액션 수정 시도: 선택된 항목 없음."); return
        action_to_edit = self.actions_list[current_row]
        dialog = ActionInputDialog(self.update_status, self.pynput_mouse, self.pynput_keyboard, self, action_to_edit=action_to_edit)
        if dialog.exec_() == QDialog.Accepted:
            updated_action_data = dialog.action_data
            if updated_action_data:
                self.actions_list[current_row] = updated_action_data
                self.update_action_list_widget(); self.action_list_widget.setCurrentRow(current_row)
                self.update_status(f"액션 수정됨: {updated_action_data.get('user_given_name') or updated_action_data['details']}")

    def delete_selected_action(self): # 이전과 동일
        current_row = self.action_list_widget.currentRow()
        if current_row >= 0: 
            removed_action = self.actions_list.pop(current_row)
            self.update_action_list_widget()
            self.update_status(f"액션 삭제됨: {removed_action.get('user_given_name') or removed_action['details']}")
        else: QMessageBox.warning(self, "선택 오류", "삭제할 액션을 선택해주세요.")

    # *** 모두 삭제 기능 메서드 ***
    def delete_all_actions(self):
        if not self.actions_list:
            QMessageBox.information(self, "알림", "삭제할 액션이 목록에 없습니다.")
            return
        
        reply = QMessageBox.question(self, "모두 삭제 확인", 
                                     "정말로 모든 액션을 삭제하시겠습니까?\n이 작업은 되돌릴 수 없습니다.",
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.actions_list.clear()
            self.update_action_list_widget()
            self.update_status("모든 액션이 삭제되었습니다.")
            # 일괄 딜레이 체크박스도 초기화 (선택적)
            self.inter_delay_checkbox.blockSignals(True)
            self.inter_delay_checkbox.setChecked(False)
            self.inter_delay_checkbox.blockSignals(False)


    def move_action_up(self): # 이전과 동일
        current_row = self.action_list_widget.currentRow()
        if current_row > 0:
            action = self.actions_list.pop(current_row)
            self.actions_list.insert(current_row - 1, action)
            self.update_action_list_widget(); self.action_list_widget.setCurrentRow(current_row - 1)
            self.update_status(f"액션 '{action.get('user_given_name') or action['details']}' 위로 이동됨.")

    def move_action_down(self): # 이전과 동일
        current_row = self.action_list_widget.currentRow()
        if current_row >= 0 and current_row < len(self.actions_list) - 1:
            action = self.actions_list.pop(current_row)
            self.actions_list.insert(current_row + 1, action)
            self.update_action_list_widget(); self.action_list_widget.setCurrentRow(current_row + 1)
            self.update_status(f"액션 '{action.get('user_given_name') or action['details']}' 아래로 이동됨.")

    def update_action_list_widget(self): # 사용자 지정 이름 반영
        self.action_list_widget.clear()
        for i, action_data in enumerate(self.actions_list):
            display_name = action_data.get('user_given_name')
            details = action_data.get('details', '정의되지 않은 액션')
            if display_name: # 사용자 이름이 있으면
                # "이름 (자동 상세)" 또는 "이름"만 표시 등 선택 가능
                # 여기서는 자동 상세 설명을 괄호 안에 표시
                # details에서 사용자 이름 부분을 제외하고 표시하도록 수정 필요 (현재 details에 이미 이름이 포함될 수 있음)
                # get_action_data 에서 details 생성 시 user_given_name을 반영하므로, 여기서는 details만 써도 됨.
                # 단, get_action_data의 details 생성 방식을 일관되게 해야 함.
                # ActionInputDialog.get_action_data 수정: 'details'는 순수 자동 설명, 'display_text'를 새로 만들거나 여기서 조합
                list_item_text = f"{i+1}. {details}" # get_action_data에서 details에 이미 이름 반영
            else:
                list_item_text = f"{i+1}. {details}"
            self.action_list_widget.addItem(list_item_text)

    # --- 일괄 딜레이 삽입/삭제 메서드 ---
    def toggle_inter_action_delay(self, state):
        is_checked = (state == Qt.Checked)
        delay_action_template = {'type': '딜레이', 'duration_ms': 600, 
                                 'details': '자동 삽입된 600ms 대기', 
                                 'auto_inserted': True,
                                 'user_given_name': None} # 자동 삽입 딜레이에는 사용자 이름 없음

        if is_checked:
            self.update_status("액션 사이에 600ms 딜레이 삽입 중...")
            new_actions_list = []
            for i, action in enumerate(self.actions_list):
                new_actions_list.append(action)
                # 마지막 액션이 아니고, 현재 액션이나 다음 액션이 자동 삽입된 딜레이가 아닐 경우에만 추가
                if i < len(self.actions_list) - 1:
                    is_current_auto_delay = action.get('auto_inserted', False) and action['type'] == '딜레이'
                    # 다음 액션이 자동 삽입된 딜레이인지 미리 보기는 어려우므로,
                    # 일단 추가하고 나중에 중복 제거하는 방식 또는,
                    # 현재 액션 뒤에 무조건 추가 후, 다음 액션이 auto_inserted 딜레이면 그것을 건너뛰는 방식.
                    # 여기서는 더 간단하게, 현재 액션이 딜레이가 아니면 그 뒤에 추가.
                    if not (action['type'] == '딜레이' and action.get('auto_inserted', False)):
                         # 다음 액션이 이미 자동 딜레이인지 확인 (더 복잡한 로직 필요 시)
                         # 현재는 단순하게, 현재 액션과 다음 액션 사이에 딜레이가 필요한지 판단하여 삽입
                         # 이미 사용자 정의 딜레이가 있거나, 다음 액션이 자동딜레이인 경우 등 고려하면 복잡해짐
                         # 가장 단순하게: 액션 뒤에, 만약 그 액션이 auto_inserted 딜레이가 아니라면, 딜레이 추가
                        new_actions_list.append(delay_action_template.copy())
            
            # 위 로직은 너무 많은 딜레이를 만들 수 있음. 정확한 "사이" 로직으로 변경:
            if is_checked:
                new_actions_list_with_delays = []
                for i, current_action in enumerate(self.actions_list):
                    new_actions_list_with_delays.append(current_action)
                    # 마지막 액션이 아니고, 현재 액션이 자동 삽입된 딜레이가 아닐 경우에만 뒤에 딜레이 추가
                    if i < len(self.actions_list) - 1 and not (current_action.get('auto_inserted') and current_action['type'] == '딜레이'):
                        # 다음 액션이 자동 삽입된 딜레이가 아닌 경우에만 추가
                        # (하지만 다음 액션은 아직 new_actions_list_with_delays에 없음)
                        # -> 기존 리스트를 기준으로 판단해야 함.
                        # 기존 리스트에서 현재 액션과 다음 액션 사이에 자동딜레이가 없다면 추가.
                        # 이 방식은 복잡하므로, 일단 단순하게 "모든 non-auto-delay 액션 뒤에 추가 (마지막 제외)"
                        new_actions_list_with_delays.append(delay_action_template.copy())
                
                # 위 로직도 여전히 문제 소지가 있음.
                # 가장 확실한 방법:
                # 1. 먼저 모든 auto_inserted 딜레이를 제거한다.
                # 2. 그 후, 액션 사이에 auto_inserted 딜레이를 삽입한다.
                self.actions_list = [act for act in self.actions_list if not act.get('auto_inserted')]
                
                final_actions_list = []
                for i, action in enumerate(self.actions_list):
                    final_actions_list.append(action)
                    if i < len(self.actions_list) - 1: # 마지막 액션 뒤에는 추가 안 함
                        final_actions_list.append(delay_action_template.copy())
                self.actions_list = final_actions_list
                self.update_status("모든 액션 사이에 600ms 딜레이가 삽입되었습니다.")

        else: # 체크 해제 시
            self.update_status("자동 삽입된 딜레이 삭제 중...")
            self.actions_list = [action for action in self.actions_list if not action.get('auto_inserted')]
            self.update_status("자동 삽입된 모든 600ms 딜레이가 삭제되었습니다.")
        
        self.update_action_list_widget()


    # set_hotkey_dialog, get_pynput_hotkey_str, stop_existing_hotkey_listener, setup_hotkey_listener,
    # on_hotkey_activated, _clear_hotkey_state_variables_no_ui_change, clear_hotkey_internal_logic,
    # clear_hotkey_user_action: 이전과 동일 (개선된 버전 사용)
    # set_schedule, check_schedule_and_execute, cancel_schedule_internal, cancel_schedule_user_action: 이전과 동일
    # execute_actions: 이전과 동일 (키보드 조합키 처리는 여전히 TODO)
    # closeEvent: 이전과 동일

    # 복사/붙여넣기 할 이전 메서드들 (MacroApp의 set_hotkey_dialog 부터 closeEvent 까지)
    # ... (이전 답변의 MacroApp 코드에서 해당 부분 복사) ...
    def set_hotkey_dialog(self):
        dialog = QDialog(self); dialog.setWindowTitle("단축키 설정")
        layout = QVBoxLayout(dialog); label = QLabel("새로운 단축키를 누르세요 (예: Ctrl+Shift+F1):")
        key_sequence_edit = QKeySequenceEdit()
        if self.hotkey and not self.hotkey.isEmpty(): key_sequence_edit.setKeySequence(self.hotkey)
        layout.addWidget(label); layout.addWidget(key_sequence_edit)
        ok_button = QPushButton("설정")
        def on_ok():
            sequence = key_sequence_edit.keySequence()
            if not sequence.isEmpty() and sequence != self.hotkey : 
                self.update_status(f"사용자 선택 단축키: {sequence.toString(QKeySequence.NativeText)}")
                self.hotkey = sequence 
                self.hotkey_display.setText(self.hotkey.toString(QKeySequence.NativeText))
                if self.setup_hotkey_listener(): self.update_status(f"단축키 '{self.hotkey_display.text()}' 설정 및 리스너 시작됨.")
                else: self.update_status(f"단축키 '{self.hotkey_display.text()}' 리스너 설정 실패."); self.clear_hotkey_internal_logic()
                dialog.accept()
            elif sequence.isEmpty(): QMessageBox.warning(dialog, "오류", "단축키를 입력해주세요.")
            else: dialog.accept() 
        ok_button.clicked.connect(on_ok); layout.addWidget(ok_button)
        dialog.exec_()

    def get_pynput_hotkey_str(self):
        if not self.hotkey or self.hotkey.isEmpty(): return None
        portable_str = self.hotkey.toString(QKeySequence.PortableText); q_parts = portable_str.split('+'); pynput_parts = []
        for part_name in q_parts:
            part_lower = part_name.lower(); processed_part = None
            if part_lower == "ctrl": processed_part = "<control>"
            elif part_lower == "shift": processed_part = "<shift>"
            elif part_lower == "alt": processed_part = "<alt>"
            elif part_lower == "meta": processed_part = "<cmd>" if sys.platform == "darwin" else "<super>"
            elif len(part_name) == 1: processed_part = part_lower
            else: 
                key_map = { "esc": "escape", "return": "enter", "enter": "enter", "del": "delete", "pgup": "page_up", 
                            "pagedown": "page_down", "pgdn": "page_down", "backspace": "backspace", "tab": "tab", 
                            "space": "space", "home": "home", "end": "end", "left": "left", "up": "up", 
                            "right": "right", "down": "down",}
                effective_key_name = key_map.get(part_lower, part_lower)
                processed_part = f"<{effective_key_name}>"
            if processed_part: pynput_parts.append(processed_part)
        if not pynput_parts: return None
        MODIFIERS_PYNPUT = {"<control>", "<shift>", "<alt>", "<cmd>", "<super>"}
        final_modifiers = sorted([p for p in pynput_parts if p in MODIFIERS_PYNPUT])
        final_keys = sorted([p for p in pynput_parts if p not in MODIFIERS_PYNPUT])
        if not final_keys and final_modifiers : self.update_status(f"[경고] 단축키가 모디파이어로만 구성됨: {final_modifiers}.")
        final_pynput_parts_ordered = final_modifiers + final_keys
        return "+".join(final_pynput_parts_ordered)

    def stop_existing_hotkey_listener(self):
        if self.hotkey_listener_thread:
            try:
                if hasattr(self.hotkey_listener_thread, 'is_alive') and self.hotkey_listener_thread.is_alive():
                     self.hotkey_listener_thread.stop()
            except Exception as e: self.update_status(f"기존 단축키 리스너 중지 중 오류: {type(e).__name__}: {e}")
            finally: self.hotkey_listener_thread = None; self.hotkey_id_str = None

    def setup_hotkey_listener(self):
        self.stop_existing_hotkey_listener()
        if not self.hotkey or self.hotkey.isEmpty(): return False
        self.hotkey_id_str = self.get_pynput_hotkey_str()
        if not self.hotkey_id_str:
            self.update_status(f"단축키 문자열 변환 실패 ({self.hotkey.toString(QKeySequence.NativeText)}).")
            return False
        try:
            hotkey_map = {self.hotkey_id_str: self.on_hotkey_activated}
            self.hotkey_listener_thread = self.pynput_keyboard.GlobalHotKeys(hotkey_map)
            self.hotkey_listener_thread.start()
            return True
        except Exception as e:
            error_message = f"단축키 리스너 설정 중 오류 ('{self.hotkey_id_str}'):\n{type(e).__name__}: {e}"
            self.update_status(error_message); QMessageBox.critical(self, "핫키 설정 오류", error_message)
            return False

    def on_hotkey_activated(self):
        self.update_status(f"단축키 '{self.hotkey_display.text()}' 감지됨. 액션 실행...")
        self.execute_actions()

    def _clear_hotkey_state_variables_no_ui_change(self):
        self.hotkey = None; self.hotkey_id_str = None

    def clear_hotkey_internal_logic(self):
        self.stop_existing_hotkey_listener()
        self._clear_hotkey_state_variables_no_ui_change()
        self.hotkey_display.clear(); self.hotkey_display.setPlaceholderText("설정되지 않음")

    def clear_hotkey_user_action(self):
        self.clear_hotkey_internal_logic()
        self.update_status("사용자에 의해 단축키가 해제되었습니다.")

    def set_schedule(self):
        selected_dt = self.schedule_datetime_edit.dateTime(); current_dt = QDateTime.currentDateTime()
        if not self.actions_list: QMessageBox.warning(self, "예약 불가", "실행할 액션이 없습니다."); self.update_status("예약 시도 실패: 액션 목록 비어있음."); return
        if selected_dt <= current_dt: QMessageBox.warning(self, "시간 오류", "예약 시간은 현재 시간 이후여야 합니다."); self.update_status("예약 시간 설정 오류: 과거/현재 시간 선택."); return
        self.scheduled_datetime = selected_dt; self.is_schedule_active = True
        self.schedule_timer.start(1000)
        self.schedule_status_label.setText(f"예약됨: {self.scheduled_datetime.toString('yyyy-MM-dd HH:mm:ss')}")
        self.set_schedule_button.setEnabled(False); self.cancel_schedule_button.setEnabled(True); self.schedule_datetime_edit.setEnabled(False)
        self.update_status(f"매크로가 {self.scheduled_datetime.toString('yyyy-MM-dd HH:mm:ss')}에 실행되도록 예약되었습니다.")

    def check_schedule_and_execute(self):
        if not self.is_schedule_active or not self.scheduled_datetime: return
        current_dt = QDateTime.currentDateTime()
        if current_dt >= self.scheduled_datetime:
            self.update_status(f"예약된 시간({self.scheduled_datetime.toString('yyyy-MM-dd HH:mm:ss')}) 도달. 매크로 실행...")
            self.schedule_timer.stop(); scheduled_time_str_for_log = self.scheduled_datetime.toString('yyyy-MM-dd HH:mm:ss')
            self.is_schedule_active = False; self.scheduled_datetime = None
            self.schedule_status_label.setText("실행 완료 후 예약 해제됨")
            self.set_schedule_button.setEnabled(True); self.cancel_schedule_button.setEnabled(False); self.schedule_datetime_edit.setEnabled(True)
            self.schedule_datetime_edit.setDateTime(QDateTime.currentDateTime().addSecs(300))
            self.execute_actions()
            self.update_status(f"매크로가 예약된 시간({scheduled_time_str_for_log})에 실행 완료. 예약이 해제되었습니다.")

    def cancel_schedule_internal(self, reason_message="예약이 취소되었습니다."):
        if not self.is_schedule_active and not self.schedule_timer.isActive(): self.update_status("취소할 활성 예약이 없습니다."); return
        self.schedule_timer.stop(); self.is_schedule_active = False
        cancelled_time_str = self.scheduled_datetime.toString('yyyy-MM-dd HH:mm:ss') if self.scheduled_datetime else "알 수 없음"
        self.update_status(f"'{cancelled_time_str}'의 예약 취소: {reason_message}")
        self.scheduled_datetime = None; self.schedule_status_label.setText("예약 없음")
        self.set_schedule_button.setEnabled(True); self.cancel_schedule_button.setEnabled(False); self.schedule_datetime_edit.setEnabled(True)
        self.schedule_datetime_edit.setDateTime(QDateTime.currentDateTime().addSecs(300))

    def cancel_schedule_user_action(self):
        self.cancel_schedule_internal(reason_message="사용자에 의해 취소됨")

    def execute_actions(self):
        if not self.actions_list: self.update_status("실행할 액션이 없습니다."); QMessageBox.information(self, "알림", "실행할 액션 목록 없음."); return
        self.update_status(f"액션 실행 시작 (총 {len(self.actions_list)}개)..."); QApplication.processEvents()
        mouse_ctrl, keyboard_ctrl = None, None
        try:
            mouse_ctrl = self.pynput_mouse.Controller(); keyboard_ctrl = self.pynput_keyboard.Controller()
        except Exception as e: self.update_status(f"pynput 컨트롤러 생성 실패: {e}"); QMessageBox.critical(self, "실행 오류", f"제어기 생성 실패: {e}"); return
        
        for i, action in enumerate(self.actions_list):
            self.update_status(f"실행 ({i+1}/{len(self.actions_list)}): {action.get('user_given_name') or action['details']}") # 이름 표시
            QApplication.processEvents(); time.sleep(0.01)
            try:
                if action['type'] == '마우스 클릭':
                    mouse_ctrl.position = (action['x'], action['y']); time.sleep(0.03)
                    button_to_click = getattr(self.pynput_mouse.Button, action['button'])
                    mouse_ctrl.click(button_to_click, 1)
                elif action['type'] == '키보드 입력':
                    key_str_to_execute = action['key_str']
                    parts = key_str_to_execute.split('+'); modifiers_to_press_pynput_keys = []; main_key_action_parts = []
                    mod_display_to_pynput_key_map = {
                        "Ctrl": self.pynput_keyboard.Key.ctrl, "Shift": self.pynput_keyboard.Key.shift,
                        "Alt": self.pynput_keyboard.Key.alt, 
                        "Meta": self.pynput_keyboard.Key.cmd if sys.platform == "darwin" 
                                else getattr(self.pynput_keyboard.Key, 'super', getattr(self.pynput_keyboard.Key, 'win_l', self.pynput_keyboard.Key.cmd))}
                    for part in parts:
                        if part in mod_display_to_pynput_key_map: modifiers_to_press_pynput_keys.append(mod_display_to_pynput_key_map[part])
                        else: main_key_action_parts.append(part)
                    main_key_action_str = "".join(main_key_action_parts)
                    if not main_key_action_str and modifiers_to_press_pynput_keys:
                        for mod_key in modifiers_to_press_pynput_keys: keyboard_ctrl.press(mod_key); keyboard_ctrl.release(mod_key); time.sleep(0.01)
                        continue
                    pynput_special_key_obj = getattr(self.pynput_keyboard.Key, main_key_action_str.lower(), None)
                    with keyboard_ctrl.pressed(*modifiers_to_press_pynput_keys):
                        if pynput_special_key_obj and isinstance(pynput_special_key_obj, self.pynput_keyboard.Key):
                            keyboard_ctrl.press(pynput_special_key_obj); keyboard_ctrl.release(pynput_special_key_obj)
                        elif len(main_key_action_str) == 1: keyboard_ctrl.tap(main_key_action_str.lower())
                        else: 
                            if modifiers_to_press_pynput_keys: self.update_status(f"경고: 모디파이어와 문자열 '{main_key_action_str}' 동시 입력 미지원.")
                            keyboard_ctrl.type(main_key_action_str)
                elif action['type'] == '딜레이': time.sleep(action['duration_ms'] / 1000.0)
                elif action['type'] == '색 찾기 후 클릭':
                    if ImageGrab is None: self.update_status("오류: Pillow 라이브러리 없어 '색 찾기' 액션 실행 불가."); QMessageBox.warning(self, "실행 오류", "Pillow 라이브러리 필요."); continue
                    target_color = tuple(action['target_color']); search_area = tuple(action['search_area'])
                    if not (len(search_area) == 4 and search_area[0] < search_area[2] and search_area[1] < search_area[3]): self.update_status(f"오류: '색 찾기' 검색 범위 잘못됨 {search_area}."); continue
                    self.update_status(f"색상 RGB{target_color} 검색 중 (범위: {search_area})..."); QApplication.processEvents()
                    try:
                        img = ImageGrab.grab(bbox=search_area, all_screens=True); found_at = None
                        for x_offset in range(img.width):
                            for y_offset in range(img.height):
                                pixel_color = img.getpixel((x_offset, y_offset))
                                if pixel_color[:3] == target_color:
                                    abs_x = search_area[0] + x_offset; abs_y = search_area[1] + y_offset
                                    found_at = (abs_x, abs_y); break
                            if found_at: break
                        if found_at:
                            self.update_status(f"색상 {target_color} 발견 위치: {found_at}. 클릭합니다.")
                            mouse_ctrl.position = found_at; time.sleep(0.05)
                            mouse_ctrl.click(self.pynput_mouse.Button.left, 1)
                        else: self.update_status(f"색상 {target_color}을(를) 범위 {search_area} 내에서 찾지 못했습니다.")
                    except Exception as e_color_find: self.update_status(f"'색 찾기' 액션 중 오류: {e_color_find}")
                    try: ImageGrab.grab(all_screens=True).save("debug_color_find_error_fullscreen.png")
                    except: pass
                time.sleep(0.05) 
            except Exception as e_action:
                error_msg = f"액션 '{action.get('user_given_name') or action['details']}' 실행 중 오류: {type(e_action).__name__}: {e_action}"
                self.update_status(error_msg); QMessageBox.warning(self, "액션 실행 오류", error_msg); break 
        self.update_status("모든 액션 실행 완료."); QApplication.processEvents()

    def closeEvent(self, event):
        self.update_status("자동 입력기 종료 중... 설정 저장 및 리소스 정리.")
        self.save_config()
        self.stop_existing_hotkey_listener()
        if self.schedule_timer.isActive(): self.schedule_timer.stop(); self.update_status("활성 예약 타이머 중지됨.")
        super().closeEvent(event)