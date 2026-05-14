APP_STYLESHEET = """
QMainWindow {
    background: #15171a;
}
QWidget {
    color: #e7e9ee;
    font-size: 10pt;
}
QGroupBox {
    border: 1px solid #303640;
    border-radius: 6px;
    margin-top: 12px;
    padding: 10px 8px 8px 8px;
    font-weight: 600;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
    color: #c7ccd5;
}
QPushButton {
    background: #252b33;
    border: 1px solid #3a424e;
    border-radius: 5px;
    padding: 7px 10px;
}
QPushButton:hover {
    background: #303845;
}
QPushButton:pressed {
    background: #1f252d;
}
QPushButton:disabled {
    color: #767d89;
    background: #20242a;
    border-color: #2b3038;
}
QPushButton#exportButton {
    background: #d9a441;
    border-color: #f0bf5b;
    color: #191a1c;
    font-weight: 700;
}
QPushButton#exportButton:hover {
    background: #e6b557;
}
QListWidget, QSpinBox, QDoubleSpinBox {
    background: #101216;
    border: 1px solid #303640;
    border-radius: 5px;
    padding: 4px;
    selection-background-color: #355c7d;
}
QLabel#pathLabel, QLabel#statusLabel {
    color: #aeb5c1;
}
QSplitter::handle {
    background: #222830;
}
"""

COLOR_DIALOG_STYLESHEET = """
QColorDialog {
    background: #1b1f24;
    color: #eef1f5;
}
QColorDialog QWidget {
    background: #1b1f24;
    color: #eef1f5;
}
QColorDialog QLabel {
    color: #eef1f5;
    background: transparent;
}
QColorDialog QLineEdit, QColorDialog QSpinBox {
    background: #0f1216;
    color: #ffffff;
    border: 1px solid #4c5665;
    border-radius: 4px;
    padding: 3px;
}
QColorDialog QPushButton {
    background: #2b333d;
    color: #f4f6f8;
    border: 1px solid #566171;
    border-radius: 5px;
    padding: 6px 10px;
}
QColorDialog QPushButton:hover {
    background: #364250;
}
"""
