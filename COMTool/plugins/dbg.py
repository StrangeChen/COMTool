try:
    import parameters,helpAbout,autoUpdate
    from Combobox import ComboBox
    import i18n
    from i18n import _
    import version
    import utils
except ImportError:
    from COMTool import parameters,helpAbout,autoUpdate, utils
    from COMTool.Combobox import ComboBox
    from COMTool import i18n
    from COMTool.i18n import _
    from COMTool import version

try:
    from base import Plugin_Base
except Exception:
    from .base import Plugin_Base

from PyQt5.QtCore import pyqtSignal,Qt, QRect, QMargins
from PyQt5.QtWidgets import (QApplication, QWidget,QPushButton,QMessageBox,QDesktopWidget,QMainWindow,
                             QVBoxLayout,QHBoxLayout,QGridLayout,QTextEdit,QLabel,QRadioButton,QCheckBox,
                             QLineEdit,QGroupBox,QSplitter,QFileDialog, QScrollArea)
from PyQt5.QtGui import QIcon,QFont,QTextCursor,QPixmap,QColor
import os, threading, time, re, binascii
from datetime import datetime

class Plugin(Plugin_Base):
    '''
        call sequence:
            set vars like hintSignal, hintSignal
            onInit
            onWidget
            onUiInitDone
                send
                onReceived
            getConfig
    '''
    # vars set by caller
    send = None              # send(data_bytes=None, file_path=None)
    hintSignal = None       # hintSignal.emit(title, msg)
    clearCountSignal = None  # clearCountSignal.emit()
    configGlobal = {}
    # other vars
    connParent = "main"
    connChilds = []
    id = "dbg"
    # 
    receiveUpdateSignal = pyqtSignal(str, list, str) # head, content, encoding
    sendFileOkSignal = pyqtSignal(bool, str)
    receiveProgressStop = False
    receivedData = []
    lock = threading.Lock()
    sendRecord = []
    lastColor = None
    lastBg = None
    defaultColor = None
    defaultBg = None

    def onInit(self, config):
        self.keyControlPressed = False
        self.isScheduledSending = False
        self.config = {
            "receiveAscii" : True,
            "receiveAutoLinefeed" : False,
            "receiveAutoLindefeedTime" : 200,
            "sendAscii" : True,
            "sendScheduled" : False,
            "sendScheduledTime" : 300,
            "useCRLF" : True,
            "showTimestamp" : False,
            "recordSend" : False,
            "saveLogPath" : "",
            "saveLog" : False,
            "color" : False,
            "sendEscape" : False,
            "customSendItems" : [],
            "sendHistoryList" : [],
        }
        self.config.update(config)

    def onWidgetMain(self):
        self.mainWidget = QSplitter(Qt.Vertical)
        # widgets receive and send area
        self.receiveArea = QTextEdit()
        font = QFont('Menlo,Consolas,Bitstream Vera Sans Mono,Courier New,monospace, Microsoft YaHei', 10)
        self.receiveArea.setFont(font)
        self.receiveArea.setLineWrapMode(QTextEdit.NoWrap)
        self.sendArea = QTextEdit()
        self.sendArea.setLineWrapMode(QTextEdit.NoWrap)
        self.sendArea.setAcceptRichText(False)
        self.clearReceiveButtion = QPushButton(_("ClearReceive"))
        self.sendButtion = QPushButton(_("Send"))
        self.sendHistory = ComboBox()
        sendWidget = QWidget()
        sendAreaWidgetsLayout = QHBoxLayout()
        sendAreaWidgetsLayout.setContentsMargins(0,4,0,0)
        sendWidget.setLayout(sendAreaWidgetsLayout)
        buttonLayout = QVBoxLayout()
        buttonLayout.addWidget(self.clearReceiveButtion)
        buttonLayout.addStretch(1)
        buttonLayout.addWidget(self.sendButtion)
        sendAreaWidgetsLayout.addWidget(self.sendArea)
        sendAreaWidgetsLayout.addLayout(buttonLayout)
        self.mainWidget.addWidget(self.receiveArea)
        self.mainWidget.addWidget(sendWidget)
        self.mainWidget.addWidget(self.sendHistory)
        self.mainWidget.setStretchFactor(0, 7)
        self.mainWidget.setStretchFactor(1, 2)
        self.mainWidget.setStretchFactor(2, 1)
        # event
        self.sendButtion.clicked.connect(self.onSendData)
        self.clearReceiveButtion.clicked.connect(self.clearReceiveBuffer)
        self.receiveUpdateSignal.connect(self.updateReceivedDataDisplay)

        return self.mainWidget

    def onWidgetSettings(self):
        # serial receive settings
        layout = QVBoxLayout()
        serialReceiveSettingsLayout = QGridLayout()
        serialReceiveSettingsGroupBox = QGroupBox(_("Receive Settings"))
        self.receiveSettingsAscii = QRadioButton(_("ASCII"))
        self.receiveSettingsAscii.setToolTip(_("Show recived data as visible format, select decode method at top right corner"))
        self.receiveSettingsHex = QRadioButton(_("HEX"))
        self.receiveSettingsHex.setToolTip(_("Show recived data as hex format"))
        self.receiveSettingsAscii.setChecked(True)
        self.receiveSettingsAutoLinefeed = QCheckBox(_("Auto\nLinefeed\nms"))
        self.receiveSettingsAutoLinefeed.setToolTip(_("Auto linefeed after interval, unit: ms"))
        self.receiveSettingsAutoLinefeedTime = QLineEdit("200")
        self.receiveSettingsAutoLinefeedTime.setProperty("class", "smallInput")
        self.receiveSettingsAutoLinefeedTime.setToolTip(_("Auto linefeed after interval, unit: ms"))
        self.receiveSettingsAutoLinefeed.setMaximumWidth(75)
        self.receiveSettingsAutoLinefeedTime.setMaximumWidth(75)
        self.receiveSettingsTimestamp = QCheckBox(_("Timestamp"))
        self.receiveSettingsTimestamp.setToolTip(_("Add timestamp before received data, will automatically enable auto line feed"))
        self.receiveSettingsColor = QCheckBox(_("Color"))
        self.receiveSettingsColor.setToolTip(_("Enable unix terminal color support, e.g. \\33[31;43mhello\\33[0m"))
        serialReceiveSettingsLayout.addWidget(self.receiveSettingsAscii,1,0,1,1)
        serialReceiveSettingsLayout.addWidget(self.receiveSettingsHex,1,1,1,1)
        serialReceiveSettingsLayout.addWidget(self.receiveSettingsAutoLinefeed, 2, 0, 1, 1)
        serialReceiveSettingsLayout.addWidget(self.receiveSettingsAutoLinefeedTime, 2, 1, 1, 1)
        serialReceiveSettingsLayout.addWidget(self.receiveSettingsTimestamp, 3, 0, 1, 1)
        serialReceiveSettingsLayout.addWidget(self.receiveSettingsColor, 3, 1, 1, 1)
        serialReceiveSettingsGroupBox.setLayout(serialReceiveSettingsLayout)
        serialReceiveSettingsGroupBox.setAlignment(Qt.AlignHCenter)
        layout.addWidget(serialReceiveSettingsGroupBox)

        # serial send settings
        serialSendSettingsLayout = QGridLayout()
        serialSendSettingsGroupBox = QGroupBox(_("Send Settings"))
        self.sendSettingsAscii = QRadioButton(_("ASCII"))
        self.sendSettingsHex = QRadioButton(_("HEX"))
        self.sendSettingsAscii.setToolTip(_("Get send data as visible format, select encoding method at top right corner"))
        self.sendSettingsHex.setToolTip(_("Get send data as hex format, e.g. hex '31 32 33' equal to ascii '123'"))
        self.sendSettingsAscii.setChecked(True)
        self.sendSettingsScheduledCheckBox = QCheckBox(_("Timed Send\nms"))
        self.sendSettingsScheduledCheckBox.setToolTip(_("Timed send, unit: ms"))
        self.sendSettingsScheduled = QLineEdit("300")
        self.sendSettingsScheduled.setProperty("class", "smallInput")
        self.sendSettingsScheduled.setToolTip(_("Timed send, unit: ms"))
        self.sendSettingsScheduledCheckBox.setMaximumWidth(75)
        self.sendSettingsScheduled.setMaximumWidth(75)
        self.sendSettingsCRLF = QCheckBox(_("<CRLF>"))
        self.sendSettingsCRLF.setToolTip(_("Select to send \\r\\n instead of \\n"))
        self.sendSettingsCRLF.setChecked(False)
        self.sendSettingsRecord = QCheckBox(_("Record"))
        self.sendSettingsRecord.setToolTip(_("Record send data"))
        self.sendSettingsEscape= QCheckBox(_("Escape"))
        self.sendSettingsEscape.setToolTip(_("Enable escape characters support like \\t \\r \\n \\x01 \\001"))
        serialSendSettingsLayout.addWidget(self.sendSettingsAscii,1,0,1,1)
        serialSendSettingsLayout.addWidget(self.sendSettingsHex,1,1,1,1)
        serialSendSettingsLayout.addWidget(self.sendSettingsScheduledCheckBox, 2, 0, 1, 1)
        serialSendSettingsLayout.addWidget(self.sendSettingsScheduled, 2, 1, 1, 1)
        serialSendSettingsLayout.addWidget(self.sendSettingsCRLF, 3, 0, 1, 1)
        serialSendSettingsLayout.addWidget(self.sendSettingsRecord, 3, 1, 1, 1)
        serialSendSettingsLayout.addWidget(self.sendSettingsEscape, 4, 0, 1, 2)
        serialSendSettingsGroupBox.setLayout(serialSendSettingsLayout)
        layout.addWidget(serialSendSettingsGroupBox)

        widget = QWidget()
        widget.setLayout(layout)
        layout.setContentsMargins(0,0,0,0)
        # event
        self.receiveSettingsTimestamp.clicked.connect(self.onTimeStampClicked)
        self.receiveSettingsAutoLinefeed.clicked.connect(self.onAutoLinefeedClicked)
        self.receiveSettingsAscii.clicked.connect(lambda : self.bindVar(self.receiveSettingsAscii, self.config, "receiveAscii"))
        self.receiveSettingsHex.clicked.connect(lambda : self.bindVar(self.receiveSettingsHex, self.config, "receiveAscii", invert = True))
        self.sendSettingsHex.clicked.connect(self.onSendSettingsHexClicked)
        self.sendSettingsAscii.clicked.connect(self.onSendSettingsAsciiClicked)
        self.sendSettingsRecord.clicked.connect(self.onRecordSendClicked)
        self.sendSettingsEscape.clicked.connect(lambda: self.bindVar(self.sendSettingsEscape, self.config, "sendEscape"))
        self.sendSettingsCRLF.clicked.connect(lambda: self.bindVar(self.sendSettingsCRLF, self.config, "useCRLF"))
        self.sendHistory.activated.connect(self.onSendHistoryIndexChanged)
        self.receiveSettingsColor.clicked.connect(self.onSetColorChanged)
        self.receiveSettingsAutoLinefeedTime.textChanged.connect(lambda: self.bindVar(self.receiveSettingsAutoLinefeedTime, self.config, "receiveAutoLindefeedTime", vtype=int, vErrorMsg=_("Auto line feed value error, must be integer")))
        self.sendSettingsScheduled.textChanged.connect(lambda: self.bindVar(self.sendSettingsScheduled, self.config, "sendScheduledTime", vtype=int, vErrorMsg=_("Timed send value error, must be integer")))
        self.sendSettingsScheduledCheckBox.clicked.connect(lambda: self.bindVar(self.sendSettingsScheduledCheckBox, self.config, "sendScheduled"))
        return widget


    def onWidgetFunctional(self):
        sendFunctionalLayout = QVBoxLayout()
        # right functional layout
        self.filePathWidget = QLineEdit()
        self.openFileButton = QPushButton(_("Open File"))
        self.sendFileButton = QPushButton(_("Send File"))
        self.clearHistoryButton = QPushButton(_("Clear History"))
        self.addButton = QPushButton(_("+"))
        self.fileSendGroupBox = QGroupBox(_("Sendding File"))
        fileSendGridLayout = QGridLayout()
        fileSendGridLayout.addWidget(self.filePathWidget, 0, 0, 1, 1)
        fileSendGridLayout.addWidget(self.openFileButton, 0, 1, 1, 1)
        fileSendGridLayout.addWidget(self.sendFileButton, 1, 0, 1, 2)
        self.fileSendGroupBox.setLayout(fileSendGridLayout)
        self.logFileGroupBox = QGroupBox(_("Save log"))
        # cumtom send zone
        #   groupbox
        customSendGroupBox = QGroupBox(_("Cutom send"))
        customSendItemsLayout0 = QVBoxLayout()
        customSendItemsLayout0.setContentsMargins(0,8,0,0)
        customSendGroupBox.setLayout(customSendItemsLayout0)
        #   scroll

        self.customSendScroll = QScrollArea()
        self.customSendScroll.setMinimumHeight(parameters.customSendItemHeight + 20)
        self.customSendScroll.setWidgetResizable(True)
        self.customSendScroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        #   add scroll to groupbox
        customSendItemsLayout0.addWidget(self.customSendScroll)
        #   wrapper widget
        cutomSendItemsWraper = QWidget()
        customSendItemsLayoutWrapper = QVBoxLayout()
        customSendItemsLayoutWrapper.setContentsMargins(0,0,0,0)
        cutomSendItemsWraper.setLayout(customSendItemsLayoutWrapper)
        #    custom items
        customItems = QWidget()
        self.customSendItemsLayout = QVBoxLayout()
        self.customSendItemsLayout.setContentsMargins(0,0,0,0)
        customItems.setLayout(self.customSendItemsLayout)
        customSendItemsLayoutWrapper.addWidget(customItems)
        customSendItemsLayoutWrapper.addWidget(self.addButton)
        #   set wrapper widget
        self.customSendScroll.setWidget(cutomSendItemsWraper)
        self.customSendScroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        # 
        logFileLayout = QHBoxLayout()
        self.saveLogCheckbox = QCheckBox()
        self.logFilePath = QLineEdit()
        self.logFileBtn = QPushButton(_("Log path"))
        logFileLayout.addWidget(self.saveLogCheckbox)
        logFileLayout.addWidget(self.logFilePath)
        logFileLayout.addWidget(self.logFileBtn)
        self.logFileGroupBox.setLayout(logFileLayout)
        sendFunctionalLayout.addWidget(self.logFileGroupBox)
        sendFunctionalLayout.addWidget(self.fileSendGroupBox)
        sendFunctionalLayout.addWidget(self.clearHistoryButton)
        sendFunctionalLayout.addWidget(customSendGroupBox)
        sendFunctionalLayout.addStretch(1)
        widget = QWidget()
        widget.setLayout(sendFunctionalLayout)
        # event
        self.sendFileButton.clicked.connect(self.sendFile)
        self.sendFileOkSignal.connect(self.onSentFile)
        self.saveLogCheckbox.clicked.connect(self.setSaveLog)
        self.logFileBtn.clicked.connect(self.selectLogFile)
        self.openFileButton.clicked.connect(self.selectFile)
        self.addButton.clicked.connect(self.customSendAdd)
        self.clearHistoryButton.clicked.connect(self.clearHistory)
        return widget

    def onUiInitDone(self):
        self.receiveProcess = threading.Thread(target=self.receiveDataProcess)
        self.receiveProcess.setDaemon(True)
        self.receiveProcess.start()

    def onSendSettingsHexClicked(self):
        self.config["sendAscii"] = False
        data = self.sendArea.toPlainText().replace("\n","\r\n")
        data = utils.bytes_to_hex_str(data.encode())
        self.sendArea.clear()
        self.sendArea.insertPlainText(data)

    def onSendSettingsAsciiClicked(self):
        self.config["sendAscii"] = True
        try:
            data = self.sendArea.toPlainText().replace("\n"," ").strip()
            self.sendArea.clear()
            if data != "":
                data = utils.hex_str_to_bytes(data).decode(self.config["encoding"],'ignore')
                self.sendArea.insertPlainText(data)
        except Exception as e:
            # QMessageBox.information(self,self.strings.strWriteFormatError,self.strings.strWriteFormatError)
            print("format error")

    def onAutoLinefeedClicked(self):
        if (self.config["showTimestamp"] or self.config["recordSend"]) and not self.receiveSettingsAutoLinefeed.isChecked():
            self.receiveSettingsAutoLinefeed.setChecked(True)
            self.hintSignal.emit(_("linefeed always on if timestamp or record send is on"))
        self.config["receiveAutoLinefeed"] = self.receiveSettingsAutoLinefeed.isChecked()

    def onTimeStampClicked(self):
        self.config["showTimestamp"] = self.receiveSettingsTimestamp.isChecked()
        if self.config["showTimestamp"]:
            self.config["receiveAutoLinefeed"] = True
            self.receiveSettingsAutoLinefeed.setChecked(True)

    def onRecordSendClicked(self):
        self.config["recordSend"] = self.sendSettingsRecord.isChecked()
        if self.config["recordSend"]:
            self.config["receiveAutoLinefeed"] = True
            self.receiveSettingsAutoLinefeed.setChecked(True)

    def onEscapeSendClicked(self):
        self.config["sendEscape"] = self.sendSettingsEscape.isChecked()

    def onSetColorChanged(self):
        self.config["color"] = self.receiveSettingsColor.isChecked()

    def onSendHistoryIndexChanged(self):
        self.sendArea.clear()
        self.sendArea.insertPlainText(self.sendHistory.currentText())

    def clearHistory(self):
        self.config["sendHistoryList"].clear()
        self.sendHistory.clear()
        self.hintSignal.emit(_("History cleared!"))


    def onSentFile(self, ok, path):
        print("file sent {}, path: {}".format('ok' if ok else 'fail', path))
        self.sendFileButton.setText(self.strings.strSendFile)
        self.sendFileButton.setDisabled(False)

    def setSaveLog(self):
        if self.saveLogCheckbox.isChecked():
            self.config["saveLog"] = True
        else:
            self.config["saveLog"] = False

    def selectFile(self):
        oldPath = self.filePathWidget.text()
        if oldPath=="":
            oldPath = os.getcwd()
        fileName_choose, filetype = QFileDialog.getOpenFileName(self.mainWidget,  
                                    _("Select file"),
                                    oldPath,
                                    _("All Files (*)"))

        if fileName_choose == "":
            return
        self.filePathWidget.setText(fileName_choose)
        self.filePathWidget.setToolTip(fileName_choose)

    def selectLogFile(self):
        oldPath = self.logFilePath.text()
        if oldPath=="":
            oldPath = os.getcwd()
        fileName_choose, filetype = QFileDialog.getSaveFileName(self.mainWidget,  
                                    _("Select file"),
                                    os.path.join(oldPath, "comtool.log"),
                                    _("Log file (*.log);;txt file (*.txt);;All Files (*)"))

        if fileName_choose == "":
            return
        self.logFilePath.setText(fileName_choose)
        self.logFilePath.setToolTip(fileName_choose)
        self.config["saveLogPath"] = fileName_choose

    def onLog(self, text):
        if self.config["saveLogPath"]:
            with open(self.config["saveLogPath"], "a+", encoding=self.configGlobal["encoding"], newline="\n") as f:
                f.write(text)

    def onKeyPressEvent(self, event):
        if event.key() == Qt.Key_Control:
            self.keyControlPressed = True
        elif event.key() == Qt.Key_Return or event.key()==Qt.Key_Enter:
            if self.keyControlPressed:
                self.onSendData()
        elif event.key() == Qt.Key_L:
            if self.keyControlPressed:
                self.sendArea.clear()
        elif event.key() == Qt.Key_K:
            if self.keyControlPressed:
                self.receiveArea.clear()

    def onKeyReleaseEvent(self, event):
        if event.key() == Qt.Key_Control:
            self.keyControlPressed = False

    def insertSendItem(self, text="", load = False):
        itemsNum = self.customSendItemsLayout.count() + 1
        height = parameters.customSendItemHeight * (itemsNum + 1) + 20
        topHeight = self.fileSendGroupBox.height() + self.logFileGroupBox.height() + 200
        if height + topHeight > self.height():
            height = self.height() - topHeight
        self.customSendScroll.setMinimumHeight(height)
        item = QWidget()
        layout = QHBoxLayout()
        layout.setContentsMargins(0,0,0,0)
        item.setLayout(layout)
        cmd = QLineEdit(text)
        send = QPushButton(_("Send"))
        cmd.setToolTip(text)
        send.setToolTip(text)
        cmd.textChanged.connect(lambda: self.onCustomItemChange(self.customSendItemsLayout.indexOf(item), cmd, send))
        send.setProperty("class", "smallBtn")
        send.clicked.connect(lambda: self.sendCustomItem(self.config["customSendItems"][self.customSendItemsLayout.indexOf(item)]))
        delete = QPushButton("x")
        delete.setProperty("class", "deleteBtn")
        layout.addWidget(cmd)
        layout.addWidget(send)
        layout.addWidget(delete)
        delete.clicked.connect(lambda: self.deleteSendItem(self.customSendItemsLayout.indexOf(item), item))
        self.customSendItemsLayout.addWidget(item)
        if not load:
            self.config["customSendItems"].append("")

    def deleteSendItem(self, idx, item):
        item.setParent(None)
        self.config["customSendItems"].pop(idx)
        itemsNum = self.customSendItemsLayout.count()
        height = parameters.customSendItemHeight * (itemsNum + 1) + 20
        topHeight = self.fileSendGroupBox.height() + self.logFileGroupBox.height() + 200
        if height + topHeight > self.height():
            height = self.height() - topHeight
        self.customSendScroll.setMinimumHeight(height)

    def onCustomItemChange(self, idx, edit, send):
        text = edit.text()
        edit.setToolTip(text)
        send.setToolTip(text)
        self.config["customSendItems"][idx] = text

    def sendCustomItem(self, text):
        self.onSendData(data = text)

    def customSendAdd(self):
        self.insertSendItem()

    def getSendData(self, data=None) -> bytes:
        if data is None:
            data = self.sendArea.toPlainText()
        if not data:
            return b''
        if self.config["useCRLF"]:
            data = data.replace("\n", "\r\n")
        if not self.config["sendAscii"]:
            if self.config["useCRLF"]:
                data = data.replace("\r\n", " ")
            else:
                data = data.replace("\n", " ")
            data = utils.hex_str_to_bytes(data)
            if data == -1:
                self.hintSignal.emit(_("Format error, should be like 00 01 02 03"))
                return b''
        else:
            encoding = self.configGlobal["encoding"]
            if not self.config["sendEscape"]:
                data = data.encode(encoding,"ignore")
            else: # '11234abcd\n123你好\r\n\thello\x00\x01\x02'
                final = b""
                p = 0
                escapes = {
                    "a": (b'\a', 2),
                    "b": (b'\b', 2),
                    "f": (b'\f', 2),
                    "n": (b'\n', 2),
                    "r": (b'\r', 2),
                    "t": (b'\t', 2),
                    "v": (b'\v', 2),
                    "\\": (b'\\', 2),
                    "\'": (b"'", 2),
                    '\"': (b'"', 2),
                }
                octstr = ["0", "1", "2", "3", "4", "5", "6", "7"]
                while 1:
                    idx = data[p:].find("\\")
                    if idx < 0:
                        final += data[p:].encode(encoding, "ignore")
                        break
                    final += data[p : p + idx].encode(encoding, "ignore")
                    p += idx
                    e = data[p+1]
                    if e in escapes:
                        r = escapes[e][0]
                        p += escapes[e][1]
                    elif e == "x": # \x01
                        try:
                            r = bytes([int(data[p+2 : p+4], base=16)])
                            p += 4
                        except Exception:
                            self.hintSignal.emit(_("Escape is on, but escape error:") + data[p : p+4])
                            return b''
                    elif e in octstr and len(data) > (p+2) and data[p+2] in octstr: # \dd or \ddd e.g. \001
                        try:
                            twoOct = False
                            if len(data) > (p+3) and data[p+3] in octstr: # \ddd
                                try:
                                    r = bytes([int(data[p+1 : p+4], base=8)])
                                    p += 4
                                except Exception:
                                    twoOct = True
                            else:
                                twoOct = True
                            if twoOct:
                                r = bytes([int(data[p+1 : p+3], base=8)])
                                p += 3
                        except Exception as e:
                            print(e)
                            self.hintSignal.emit(_("Escape is on, but escape error:") + data[p : p+4])
                            return b''
                    else:
                        r = data[p: p+2].encode(encoding, "ignore")
                        p += 2
                    final += r

                data = final
        return data

    def onSendData(self):
        pass

    def sendFile(self):
        filename = self.filePathWidget.text()
        if not os.path.exists(filename):
            self.hintSignal.emit(_("File path error\npath") + ":%s" %(filename))
            return
        if not self.com.is_open:
            self.hintSignal.emit(_("Connect first please"))
        else:
            self.sendFileButton.setDisabled(True)
            self.sendFileButton.setText(self.strings.strSendingFile)
            self.send(file_path=filename)


    def scheduledSend(self):
        self.isScheduledSending = True
        while self.config["sendScheduled"]:
            self.onSendData()
            try:
                time.sleep(self.config["sendScheduledTime"]/1000)
            except Exception:
                self.hintSignal.emit(self.strings.strTimeFormatError)
        self.isScheduledSending = False

    def onSendData(self, notClick=True, data=None):
        try:
            if self.com.is_open:
                data = self.getSendData(data)
                if not data:
                    return
                # record send data
                if self.config["recordSend"]:
                    head = '=> '
                    if self.config["showTimestamp"]:
                        head += '[{}] '.format(utils.datetime_format_ms(datetime.now()))
                    isHexStr, sendStr, sendStrsColored = self.bytes2String(data, not self.config["receiveAscii"], encoding=self.configGlobal["encoding"])
                    if isHexStr:
                        head += "[HEX] "
                        sendStr = sendStr.upper()
                        sendStrsColored= sendStr
                    if self.config["useCRLF"]:
                        head = "\r\n" + head
                    else:
                        head = "\n" + head
                    if head.strip() != '=>':
                        head = '{}: '.format(head.rstrip())
                    self.receiveUpdateSignal.emit(head, [sendStrsColored], self.config["encoding"])
                    self.sendRecord.insert(0, head + sendStr)
                self.sendData(data_bytes=data)
                data = self.sendArea.toPlainText()
                self.sendHistoryFindDelete(data)
                self.sendHistory.insertItem(0,data)
                self.sendHistory.setCurrentIndex(0)
                # scheduled send
                if self.config["sendScheduled"]:
                    if not self.isScheduledSending:
                        t = threading.Thread(target=self.scheduledSend)
                        t.setDaemon(True)
                        t.start()
        except Exception as e:
            print("[Error] onSendData", e)
            self.hintSignal.emit(self.strings.strWriteError)
            # print(e)

    def updateReceivedDataDisplay(self, head : str, datas : list, encoding):
        if datas:
            curScrollValue = self.receiveArea.verticalScrollBar().value()
            self.receiveArea.moveCursor(QTextCursor.End)
            endScrollValue = self.receiveArea.verticalScrollBar().value()
            cursor = self.receiveArea.textCursor()
            format = cursor.charFormat()
            font = QFont('Menlo,Consolas,Bitstream Vera Sans Mono,Courier New,monospace, Microsoft YaHei', 10)
            format.setFont(font)
            if not self.defaultColor:
                self.defaultColor = format.foreground()
            if not self.defaultBg:
                self.defaultBg = format.background()
            if head:
                format.setForeground(self.defaultColor)
                cursor.setCharFormat(format)
                format.setBackground(self.defaultBg)
                cursor.setCharFormat(format)
                cursor.insertText(head)
            for data in datas:
                if type(data) == str:
                    self.receiveArea.insertPlainText(data)
                elif type(data) == list:
                    for color, bg, text in data:
                        if color:
                            format.setForeground(QColor(color))
                            cursor.setCharFormat(format)
                        else:
                            format.setForeground(self.defaultColor)
                            cursor.setCharFormat(format)
                        if bg:
                            format.setBackground(QColor(bg))
                            cursor.setCharFormat(format)
                        else:
                            format.setBackground(self.defaultBg)
                            cursor.setCharFormat(format)
                        cursor.insertText(text)
                else: # bytes
                    self.receiveArea.insertPlainText(data.decode(encoding=encoding, errors="ignore"))
            if curScrollValue < endScrollValue:
                self.receiveArea.verticalScrollBar().setValue(curScrollValue)
            else:
                self.receiveArea.moveCursor(QTextCursor.End)

    def sendHistoryFindDelete(self,str):
        self.sendHistory.removeItem(self.sendHistory.findText(str))

    def _getColorByfmt(self, fmt:bytes):
        colors = {
            b"0": None,
            b"30": "#000000",
            b"31": "#ff0000",
            b"32": "#008000",
            b"33": "#f9a825",
            b"34": "#0000ff",
            b"35": "#9c27b0",
            b"36": "#1b5e20",
            b"37": "#000000",
        }
        bgs = {
            b"0": None,
            b"40": "#000000",
            b"41": "#ff0000",
            b"42": "#008000",
            b"43": "#f9a825",
            b"44": "#0000ff",
            b"45": "#9c27b0",
            b"46": "#1b5e20",
            b"47": "#000000",
        }
        fmt = fmt[2:-1].split(b";")
        color = colors[b'0']
        bg = bgs[b'0']
        for cmd in fmt:
            if cmd in colors:
                color = colors[cmd]
            if cmd in bgs:
                bg = bgs[cmd]
        return color, bg

    def _texSplitByColor(self, text:bytes):
        colorFmt = re.findall(rb'\x1b\[.*?m', text)
        plaintext = text
        for fmt in colorFmt:
            plaintext = plaintext.replace(fmt, b"")
        colorStrs = []
        if colorFmt:
            p = 0
            for fmt in colorFmt:
                idx = text[p:].index(fmt)
                if idx != 0:
                    colorStrs.append([self.lastColor, self.lastBg, text[p:p+idx]])
                    p += idx
                self.lastColor, self.lastBg = self._getColorByfmt(fmt)
                p += len(fmt)
            colorStrs.append([self.lastColor, self.lastBg, text[p:]])
        else:
            colorStrs = [[self.lastColor, self.lastBg, text]]
        return plaintext, colorStrs

    def getColoredText(self, data_bytes, decoding=None):
        plainText, coloredText = self._texSplitByColor(data_bytes)
        if decoding:
            plainText = plainText.decode(encoding=decoding, errors="ignore")
            decodedColoredText = []
            for color, bg, text in coloredText:
                decodedColoredText.append([color, bg, text.decode(encoding=decoding, errors="ignore")])
            coloredText = decodedColoredText
        return plainText, coloredText

    def bytes2String(self, data : bytes, showAsHex : bool, encoding="utf-8"):
        isHexString = False
        dataColored = None
        if showAsHex:
            return True, binascii.hexlify(data, ' ').decode(encoding=encoding), dataColored
        try:
            dataPlain, dataColored = self.getColoredText(data, self.config["encoding"])
        except Exception:
            dataPlain = binascii.hexlify(data, ' ').decode(encoding=encoding)
            isHexString = True
        return isHexString, dataPlain, dataColored

    def clearReceiveBuffer(self):
        self.receiveArea.clear()
        self.clearCountSignal.emit()

    def onReceived(self, data : bytes):
        self.receivedData.append(data)
        self.lock.release()

    def receiveDataProcess(self):
        self.receiveProgressStop = False
        timeLastReceive = 0
        new_line = True
        logData = None
        buffer = b''
        while(not self.receiveProgressStop):
            logData = None
            bytes = b''
            head = ""
            self.lock.acquire()
            buffer += b"".join(self.receivedData)
            self.receivedData = []
            # timeout, add new line
            if time.time() - timeLastReceive> self.config["receiveAutoLindefeedTime"]:
                if self.config["showTimestamp"] or self.config["receiveAutoLinefeed"]:
                    if self.config["useCRLF"]:
                        head += "\r\n"
                    else:
                        head += "\n"
                    new_line = True
            if bytes:
                timeLastReceive = time.time()
            data = ""
            # have data in buffer
            if len(buffer) > 0:
                # show as hex, just show
                if not self.config["receiveAscii"]:
                    data = utils.bytes_to_hex_str(buffer)
                    colorData = data
                    buffer = b''
                # show as string, and don't need to render color
                elif not self.config["color"]:
                    data = buffer.decode(encoding=self.configGlobal["encoding"], errors="ignore")
                    colorData = data
                    buffer = b''
                # show as string, and need to render color, wait for \n or until timeout to ensure color flag in buffer
                else:
                    if time.time() - timeLastReceive >  self.config["receiveAutoLindefeedTime"] or b'\n' in buffer:
                        data, colorData = self.getColoredText(buffer, self.configGlobal["encoding"])
                        buffer = b''
                # add time receive head
                # get data from buffer, now render
                if data:
                    # add time header
                    if new_line:
                        timeNow = '[{}] '.format(utils.datetime_format_ms(datetime.now()))
                        if self.config["recordSend"]:
                            head += "<= " 
                        if self.config["showTimestamp"]:
                            head += timeNow
                            head = '{}: '.format(head.rstrip())
                        new_line = False
                    self.receiveUpdateSignal.emit(head, [colorData], self.configGlobal["encoding"])
                    logData = head + data

            while len(self.sendRecord) > 0:
                self.onLog(self.sendRecord.pop())
            if logData:
                self.onLog(logData)

