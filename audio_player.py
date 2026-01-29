"""
音频播放模块 - 支持关键词触发和定时播放音频，支持TTS文字转语音
"""
import os
import json
import threading
import time
from datetime import datetime
from typing import List, Dict, Optional
import re

try:
    from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
    from PyQt6.QtCore import QUrl, QObject, pyqtSignal, QTimer
    # PyQt6的QMediaPlayer使用PlaybackState枚举和playbackStateChanged信号
    try:
        from PyQt6.QtCore import QMediaPlayer as QMediaPlayerCore
        PlaybackState = QMediaPlayerCore.PlaybackState
        AUDIO_AVAILABLE = True
    except ImportError:
        # 如果无法导入PlaybackState，尝试直接使用QMediaPlayer
        PlaybackState = None
        AUDIO_AVAILABLE = True
except ImportError as e:
    AUDIO_AVAILABLE = False
    PlaybackState = None
    print(f"[音频播放] 警告：PyQt6.QtMultimedia 不可用，音频播放功能将受限: {e}")

# TTS文字转语音支持
try:
    # 优先尝试使用PyQt6的QTextToSpeech（如果可用）
    from PyQt6.QtTextToSpeech import QTextToSpeech
    TTS_AVAILABLE = True
    TTS_ENGINE = "Qt"
except ImportError:
    # 如果PyQt6的TTS不可用，尝试使用pyttsx3（离线TTS）
    try:
        import pyttsx3
        TTS_AVAILABLE = True
        TTS_ENGINE = "pyttsx3"
    except ImportError:
        TTS_AVAILABLE = False
        TTS_ENGINE = None
        print(f"[TTS] 警告：TTS功能不可用，需要安装pyttsx3: pip install pyttsx3")


class AudioPlayer(QObject if AUDIO_AVAILABLE else object):
    """音频播放器（必须在Qt主线程中创建和使用）"""
    
    finished = pyqtSignal() if AUDIO_AVAILABLE else None
    
    def __init__(self, audio_file: str, parent=None):
        """
        初始化音频播放器（必须在Qt主线程中调用）
        
        Args:
            audio_file: 音频文件路径
            parent: Qt父对象
        """
        if AUDIO_AVAILABLE:
            super().__init__(parent)
            self.audio_file = audio_file
            try:
                self.player = QMediaPlayer(parent)
                self.audio_output = QAudioOutput(parent)
                self.player.setAudioOutput(self.audio_output)
                # 设置源文件
                file_url = QUrl.fromLocalFile(audio_file)
                self.player.setSource(file_url)
                # PyQt6的QMediaPlayer使用playbackStateChanged信号，而不是finished信号
                # 注意：这里不连接信号，因为播放完成检测不是必需的
                # 如果需要播放完成通知，可以使用其他机制
            except Exception as e:
                print(f"[音频播放器] 初始化失败: {e}")
                import traceback
                traceback.print_exc()
                self.player = None
                self.audio_output = None
        else:
            self.audio_file = audio_file
            self.player = None
            self.audio_output = None
    
    def _on_playback_state_changed(self, state):
        """播放状态变化回调（PyQt6使用playbackStateChanged）"""
        # 注意：这个方法当前不使用，因为QMediaPlayer的playbackStateChanged可能会误触发
        # 如果需要播放完成通知，可以使用其他机制
        pass
    
    def play(self):
        """播放音频（必须在Qt主线程中调用）"""
        if not AUDIO_AVAILABLE:
            print(f"[音频播放] 警告：音频播放功能不可用")
            return
        
        if not self.player:
            print(f"[音频播放] 警告：播放器未初始化")
            return
        
        if not os.path.exists(self.audio_file):
            print(f"[音频播放] 警告：音频文件不存在: {self.audio_file}")
            return
        
        try:
            # 重新设置源文件（确保文件路径正确）
            file_url = QUrl.fromLocalFile(self.audio_file)
            self.player.setSource(file_url)
            # 播放
            self.player.play()
            print(f"[音频播放器] 开始播放: {os.path.basename(self.audio_file)}")
        except Exception as e:
            print(f"[音频播放器] 播放失败: {e}")
            import traceback
            traceback.print_exc()
    
    def stop(self):
        """停止播放"""
        if AUDIO_AVAILABLE and self.player:
            try:
                self.player.stop()
            except:
                pass
    
    def _on_finished(self):
        """播放完成回调（已弃用，使用_on_playback_state_changed代替）"""
        # 这个方法保留用于兼容，但不再使用
        pass


class TTSEngine:
    """TTS文字转语音引擎（支持队列播放）"""
    
    def __init__(self, parent=None):
        """初始化TTS引擎"""
        self.parent = parent
        self.engine = None
        self.lock = threading.Lock()
        self.queue_lock = threading.Lock()  # 队列锁
        self.play_queue = []  # 播报队列: [(text, add_time), ...]
        self.is_playing = False  # 是否正在播放
        self.queue_timeout = 10.0  # 队列超时时间（秒），超过此时间的待播报项目会被删除
        self._current_speaking_thread = None  # 当前播报线程（用于pyttsx3）
        self._init_engine()
        
        # 启动队列处理定时器（如果使用Qt引擎）
        if TTS_ENGINE == "Qt" and parent:
            from PyQt6.QtCore import QTimer
            self.queue_timer = QTimer(parent)
            self.queue_timer.timeout.connect(self._process_queue)
            self.queue_timer.start(100)  # 每100ms检查一次队列
        else:
            self.queue_timer = None
    
    def _init_engine(self):
        """初始化TTS引擎"""
        try:
            if TTS_ENGINE == "Qt":
                # 使用PyQt6的QTextToSpeech
                from PyQt6.QtTextToSpeech import QTextToSpeech
                from PyQt6.QtWidgets import QApplication
                app = QApplication.instance()
                if app:
                    self.engine = QTextToSpeech(parent=app)
                    # 获取可用的语音列表
                    voices = self.engine.availableVoices()
                    if voices:
                        self.engine.setVoice(voices[0])  # 使用第一个可用语音
                    print(f"[TTS引擎] Qt TTS引擎初始化成功")
                else:
                    print(f"[TTS引擎] QApplication实例不存在")
                    self.engine = None
            elif TTS_ENGINE == "pyttsx3":
                # 使用pyttsx3（离线TTS）
                # 注意：pyttsx3引擎不需要在初始化时创建，每次使用时创建新的引擎实例更稳定
                # 这里只保存配置信息
                try:
                    import pyttsx3
                    # 测试初始化以验证pyttsx3可用
                    test_engine = pyttsx3.init()
                    if test_engine:
                        # 保存默认配置
                        self.engine = test_engine  # 保存引擎实例用于获取配置
                        # 尝试设置中文语音（Windows系统）
                        try:
                            voices = self.engine.getProperty('voices')
                            self.chinese_voice_id = None
                            # 查找中文语音
                            for voice in voices:
                                voice_name = voice.name.lower() if hasattr(voice, 'name') else ''
                                voice_id = voice.id.lower() if hasattr(voice, 'id') else ''
                                if 'chinese' in voice_name or 'zh' in voice_id or '中文' in voice_name:
                                    self.chinese_voice_id = voice.id
                                    print(f"[TTS引擎] 找到中文语音: {voice.name}")
                                    break
                        except Exception as ve:
                            print(f"[TTS引擎] 设置中文语音失败: {ve}")
                            self.chinese_voice_id = None
                        print(f"[TTS引擎] pyttsx3引擎初始化成功")
                    else:
                        self.engine = None
                except Exception as e:
                    print(f"[TTS引擎] pyttsx3初始化失败: {e}")
                    import traceback
                    traceback.print_exc()
                    self.engine = None
                    self.chinese_voice_id = None
            else:
                self.engine = None
        except Exception as e:
            print(f"[TTS引擎] 初始化失败: {e}")
            import traceback
            traceback.print_exc()
            self.engine = None
    
    def set_queue_timeout(self, timeout: float):
        """设置队列超时时间（秒）"""
        with self.queue_lock:
            self.queue_timeout = timeout
    
    def speak(self, text: str):
        """
        添加文字到播报队列（不立即播放）
        
        Args:
            text: 要播放的文字
        """
        if not TTS_AVAILABLE or not self.engine or not text:
            return
        
        # 添加到队列
        with self.queue_lock:
            now = time.time()
            self.play_queue.append((text, now))
            # 清理过期的待播报项目（只保留最新的）
            if len(self.play_queue) > 1:
                # 找出所有超过超时时间的项目索引
                expired_indices = []
                for i, (_, add_time) in enumerate(self.play_queue[:-1]):  # 除了最后一个（最新的）
                    if now - add_time > self.queue_timeout:
                        expired_indices.append(i)
                
                # 从后往前删除，避免索引变化问题
                for i in reversed(expired_indices):
                    removed_text, _ = self.play_queue.pop(i)
                    print(f"[TTS] 队列超时，已删除待播报: {removed_text[:30]}...")
        
        # 如果当前没有在播放，启动队列处理
        if not self.is_playing:
            if TTS_ENGINE == "Qt" and self.parent:
                # Qt引擎使用定时器在主线程中处理
                from PyQt6.QtCore import QTimer
                QTimer.singleShot(0, self._process_queue)
            elif TTS_ENGINE == "pyttsx3":
                # pyttsx3使用后台线程处理
                self._process_queue_pyttsx3()
    
    def _process_queue(self):
        """处理队列（Qt引擎使用，在主线程中调用）"""
        if not TTS_AVAILABLE or not self.engine or self.is_playing:
            return
        
        with self.queue_lock:
            if not self.play_queue:
                return
            
            # 清理过期的待播报项目
            now = time.time()
            expired_indices = []
            for i, (_, add_time) in enumerate(self.play_queue[:-1]):  # 除了最后一个
                if now - add_time > self.queue_timeout:
                    expired_indices.append(i)
            
            # 从后往前删除
            for i in reversed(expired_indices):
                removed_text, _ = self.play_queue.pop(i)
                print(f"[TTS] 队列超时，已删除待播报: {removed_text[:30]}...")
            
            if not self.play_queue:
                return
            
            # 取出最新的待播报项目（如果队列中有多个，只保留最新的）
            if len(self.play_queue) > 1:
                # 只保留最新的，删除其他所有
                while len(self.play_queue) > 1:
                    removed_text, _ = self.play_queue.pop(0)
                    print(f"[TTS] 队列堆积，已跳过旧播报: {removed_text[:30]}...")
            
            text, _ = self.play_queue[0]
            self.is_playing = True
        
        # 在主线程中播放
        try:
            if self.engine and self.parent:
                # 检查Qt引擎状态
                if TTS_ENGINE == "Qt":
                    try:
                        # QTextToSpeech的stateChanged信号可以监听播放状态
                        if not hasattr(self, '_state_connected'):
                            # 连接状态变化信号（只连接一次）
                            from PyQt6.QtTextToSpeech import QTextToSpeech
                            if hasattr(self.engine, 'stateChanged'):
                                self.engine.stateChanged.connect(self._on_speech_state_changed)
                            self._state_connected = True
                        
                        self.engine.say(text)
                        print(f"[TTS] 开始播报: {text[:50]}...")
                        
                        # 对于Qt引擎，由于无法准确检测播放完成，使用估算时间
                        # 假设每个字符播报需要0.1秒，最少3秒，最多30秒
                        from PyQt6.QtCore import QTimer
                        estimated_time = min(30.0, max(3.0, len(text) * 0.1))
                        QTimer.singleShot(int(estimated_time * 1000), lambda: self._mark_qt_speech_done(text))
                    except Exception as e:
                        print(f"[TTS] 播放失败: {e}")
                        import traceback
                        traceback.print_exc()
                        with self.queue_lock:
                            if self.play_queue and self.play_queue[0][0] == text:
                                self.play_queue.pop(0)
                            self.is_playing = False
                        # 继续处理队列
                        if self.play_queue:
                            from PyQt6.QtCore import QTimer
                            QTimer.singleShot(100, self._process_queue)
        except Exception as e:
            print(f"[TTS] 处理队列失败: {e}")
            with self.queue_lock:
                self.is_playing = False
    
    def _on_speech_state_changed(self, state):
        """Qt引擎播放状态变化回调（可选，如果状态检测可用）"""
        # 这个回调可能不会被调用，因为我们使用估算时间
        pass
    
    def _mark_qt_speech_done(self, text):
        """标记Qt引擎播报完成（使用估算时间）"""
        from PyQt6.QtCore import QTimer
        with self.queue_lock:
            # 检查队列中的第一个项目是否是刚才播报的
            if self.play_queue and self.play_queue[0][0] == text:
                self.play_queue.pop(0)  # 移除已播放的项目
                print(f"[TTS] 播报完成: {text[:30]}...")
            self.is_playing = False
            
            # 继续处理队列
            if self.play_queue:
                QTimer.singleShot(100, self._process_queue)
    
    def _process_queue_pyttsx3(self):
        """处理队列（pyttsx3引擎使用，在后台线程中调用）"""
        if self.is_playing:
            return
        
        with self.queue_lock:
            if not self.play_queue:
                return
            
            # 清理过期的待播报项目
            now = time.time()
            expired_indices = []
            for i, (_, add_time) in enumerate(self.play_queue[:-1]):  # 除了最后一个
                if now - add_time > self.queue_timeout:
                    expired_indices.append(i)
            
            # 从后往前删除
            for i in reversed(expired_indices):
                removed_text, _ = self.play_queue.pop(i)
                print(f"[TTS] 队列超时，已删除待播报: {removed_text[:30]}...")
            
            if not self.play_queue:
                return
            
            # 如果队列中有多个，只保留最新的
            if len(self.play_queue) > 1:
                while len(self.play_queue) > 1:
                    removed_text, _ = self.play_queue.pop(0)
                    print(f"[TTS] 队列堆积，已跳过旧播报: {removed_text[:30]}...")
            
            text, _ = self.play_queue[0]
            self.is_playing = True
        
        # 在后台线程中播放
        def speak_in_thread():
            try:
                import pyttsx3
                temp_engine = pyttsx3.init()
                if temp_engine:
                    # 设置语音属性
                    temp_engine.setProperty('rate', 150)  # 语速
                    temp_engine.setProperty('volume', 0.8)  # 音量
                    # 如果有中文语音，使用中文语音
                    if hasattr(self, 'chinese_voice_id') and self.chinese_voice_id:
                        try:
                            temp_engine.setProperty('voice', self.chinese_voice_id)
                        except:
                            pass
                    # 播报文字
                    temp_engine.say(text)
                    temp_engine.runAndWait()  # 等待播放完成
                    print(f"[TTS] 播报完成: {text[:50]}...")
            except Exception as e:
                print(f"[TTS] 播放失败: {e}")
                import traceback
                traceback.print_exc()
            finally:
                # 播放完成，移除队列中的项目，继续处理下一项
                with self.queue_lock:
                    if self.play_queue and self.play_queue[0][0] == text:
                        self.play_queue.pop(0)
                    self.is_playing = False
                
                # 继续处理队列
                if self.play_queue:
                    self._process_queue_pyttsx3()
        
        # 启动播放线程
        self._current_speaking_thread = threading.Thread(target=speak_in_thread, daemon=True)
        self._current_speaking_thread.start()
    
    def stop(self):
        """停止播放并清空队列"""
        try:
            with self.queue_lock:
                if self.engine:
                    if TTS_ENGINE == "Qt":
                        if hasattr(self.engine, 'stop'):
                            self.engine.stop()
                    elif TTS_ENGINE == "pyttsx3":
                        # pyttsx3无法直接停止，只能清空队列
                        pass
                
                # 清空队列
                self.play_queue.clear()
                self.is_playing = False
                print(f"[TTS] 已停止播放并清空队列")
        except Exception as e:
            print(f"[TTS] 停止播放失败: {e}")


class TTSRule:
    """TTS文字转语音规则"""
    
    def __init__(self, keyword: str, match_mode: str = "contains", tts_text: str = ""):
        """
        初始化TTS规则
        
        Args:
            keyword: 触发关键词
            match_mode: 匹配模式（"contains" 包含 / "exact" 精确 / "regex" 正则）
            tts_text: TTS播报的文字（空字符串表示播报完整弹幕内容）
        """
        self.keyword = keyword
        self.match_mode = match_mode
        self.tts_text = tts_text  # 空字符串表示播报完整弹幕内容
        self.last_trigger_time = 0
        self.trigger_count = 0
    
    def match(self, content: str) -> bool:
        """
        检查内容是否匹配规则
        
        Args:
            content: 要检查的内容
            
        Returns:
            bool: 是否匹配
        """
        if not content:
            return False
        
        content = content.strip()
        
        if self.match_mode == "exact":
            return content == self.keyword
        elif self.match_mode == "contains":
            return self.keyword in content
        elif self.match_mode == "regex":
            try:
                return bool(re.search(self.keyword, content))
            except re.error:
                return False
        
        return False
    
    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            "keyword": self.keyword,
            "match_mode": self.match_mode,
            "tts_text": self.tts_text,
            "last_trigger_time": self.last_trigger_time,
            "trigger_count": self.trigger_count
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'TTSRule':
        """从字典创建"""
        rule = cls(
            keyword=data.get("keyword", ""),
            match_mode=data.get("match_mode", "contains"),
            tts_text=data.get("tts_text", "")
        )
        rule.last_trigger_time = data.get("last_trigger_time", 0)
        rule.trigger_count = data.get("trigger_count", 0)
        return rule


class AudioRule:
    """音频规则"""
    
    def __init__(self, keyword: str, audio_file: str, match_mode: str = "contains", 
                 play_mode: str = "随机挑一"):
        """
        初始化音频规则
        
        Args:
            keyword: 触发关键词
            audio_file: 音频文件路径（可以是单个文件路径，也可以是多个路径用|分隔）
            match_mode: 匹配模式（"contains" 包含 / "exact" 精确 / "regex" 正则）
            play_mode: 播放模式（"随机挑一" 随机选一个 / "顺序全发" 顺序播放所有）
        """
        self.keyword = keyword
        self.audio_file = audio_file  # 可以是单个文件或"file1|file2|file3"格式
        self.match_mode = match_mode
        self.play_mode = play_mode  # "随机挑一" 或 "顺序全发"
        self.last_trigger_time = 0
        self.trigger_count = 0
        self.next_index = 0  # 用于顺序全发模式，记录下一个要播放的索引
    
    def match(self, content: str) -> bool:
        """
        检查内容是否匹配规则
        
        Args:
            content: 要检查的内容
            
        Returns:
            bool: 是否匹配
        """
        if not content:
            return False
        
        content = content.strip()
        
        if self.match_mode == "exact":
            return content == self.keyword
        elif self.match_mode == "contains":
            return self.keyword in content
        elif self.match_mode == "regex":
            try:
                return bool(re.search(self.keyword, content))
            except re.error:
                return False
        
        return False
    
    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            "keyword": self.keyword,
            "audio_file": self.audio_file,
            "match_mode": self.match_mode,
            "play_mode": self.play_mode,
            "last_trigger_time": self.last_trigger_time,
            "trigger_count": self.trigger_count,
            "next_index": self.next_index  # 保存顺序播放的索引位置
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'AudioRule':
        """从字典创建"""
        rule = cls(
            keyword=data.get("keyword", ""),
            audio_file=data.get("audio_file", ""),
            match_mode=data.get("match_mode", "contains"),
            play_mode=data.get("play_mode", "随机挑一")
        )
        rule.last_trigger_time = data.get("last_trigger_time", 0)
        rule.trigger_count = data.get("trigger_count", 0)
        rule.next_index = data.get("next_index", 0)
        return rule
    
    def get_audio_files(self) -> List[str]:
        """获取音频文件列表（支持单个文件或多个文件用|分隔）"""
        if "|" in self.audio_file:
            # 多个文件用|分隔
            files = [f.strip() for f in self.audio_file.split("|") if f.strip()]
            return files
        else:
            # 单个文件
            return [self.audio_file] if self.audio_file else []


class TTSManager:
    """TTS文字转语音管理器（独立管理TTS规则）"""
    
    def __init__(self, cfg_ref: Dict, parent=None):
        """
        初始化TTS管理器
        
        Args:
            cfg_ref: 配置字典引用
            parent: Qt父对象（用于确保在主线程中）
        """
        self.cfg = cfg_ref
        self.parent = parent
        self.tts_rules: List[TTSRule] = []
        self.block_keywords: List[str] = []  # 屏蔽关键词列表
        self.enabled = False
        self.speak_all_danmu = False  # 是否播报所有弹幕（默认关闭）
        self.lock = threading.Lock()
        # 初始化TTS引擎
        self.tts_engine = TTSEngine(parent=parent) if TTS_AVAILABLE else None
        # 设置队列超时时间（从配置读取，默认10秒）
        if self.tts_engine:
            queue_timeout = cfg_ref.get('tts_queue_timeout', 10.0)
            self.tts_engine.set_queue_timeout(queue_timeout)
        # 加载播报所有弹幕选项（在_load_config之前，因为_load_config会加载规则）
        self.speak_all_danmu = cfg_ref.get('tts_speak_all_danmu', False)
        # 加载屏蔽关键词列表
        self.block_keywords = cfg_ref.get('tts_block_keywords', [])
        self._load_config()
    
    def _load_config(self):
        """从配置加载TTS规则和屏蔽关键词"""
        # 加载TTS规则
        tts_rules_data = self.cfg.get('tts_rules', [])
        self.tts_rules = []
        for rule_data in tts_rules_data:
            try:
                rule = TTSRule.from_dict(rule_data)
                self.tts_rules.append(rule)
            except Exception as e:
                print(f"[TTS管理器] 加载TTS规则失败: {e}")
                import traceback
                traceback.print_exc()
        
        # 加载屏蔽关键词（如果还没有从cfg_ref中加载）
        if not self.block_keywords:
            self.block_keywords = self.cfg.get('tts_block_keywords', [])
    
    def save_config(self):
        """保存配置到文件"""
        try:
            tts_rules_data = [rule.to_dict() for rule in self.tts_rules]
            self.cfg['tts_rules'] = tts_rules_data
            self.cfg['tts_enabled'] = self.enabled
            self.cfg['tts_speak_all_danmu'] = self.speak_all_danmu
            self.cfg['tts_block_keywords'] = self.block_keywords
            # 保存队列超时时间
            if self.tts_engine:
                self.cfg['tts_queue_timeout'] = self.tts_engine.queue_timeout
            
            from config_manager import save_cfg
            save_cfg(self.cfg)
            print(f"[TTS管理器] 配置已保存: TTS规则{len(tts_rules_data)}条, 屏蔽关键词{len(self.block_keywords)}个")
        except Exception as e:
            print(f"[TTS管理器] 保存配置失败: {e}")
            import traceback
            traceback.print_exc()
    
    def set_enabled(self, enabled: bool):
        """设置功能开关"""
        self.enabled = enabled
        if not enabled and self.tts_engine:
            # 禁用时停止所有播放并清空队列
            self.tts_engine.stop()
        self.save_config()
    
    def set_queue_timeout(self, timeout: float):
        """设置队列超时时间（秒）"""
        if self.tts_engine:
            self.tts_engine.set_queue_timeout(timeout)
            self.save_config()
    
    def set_speak_all_danmu(self, enabled: bool):
        """设置是否播报所有弹幕"""
        self.speak_all_danmu = enabled
        self.save_config()
    
    def add_block_keyword(self, keyword: str) -> bool:
        """
        添加屏蔽关键词
        
        Args:
            keyword: 屏蔽关键词
            
        Returns:
            bool: 是否成功
        """
        if not keyword:
            return False
        
        with self.lock:
            keyword = keyword.strip()
            if keyword and keyword not in self.block_keywords:
                self.block_keywords.append(keyword)
                self.save_config()
                return True
            return False
    
    def remove_block_keyword(self, index: int) -> bool:
        """
        删除屏蔽关键词
        
        Args:
            index: 关键词索引
            
        Returns:
            bool: 是否成功
        """
        with self.lock:
            if 0 <= index < len(self.block_keywords):
                self.block_keywords.pop(index)
                self.save_config()
                return True
            return False
    
    def _contains_block_keyword(self, text: str) -> bool:
        """
        检查文本是否包含屏蔽关键词（必须在锁内调用）
        
        Args:
            text: 要检查的文本（可以是"用户昵称 内容"的组合）
            
        Returns:
            bool: 如果包含屏蔽关键词返回True，否则返回False
        """
        if not text or not self.block_keywords:
            return False
        
        text_lower = text.lower()  # 转换为小写进行匹配（不区分大小写）
        for keyword in self.block_keywords:
            if keyword and keyword.strip():
                keyword_lower = keyword.strip().lower()
                # 使用包含匹配（检查用户昵称或内容中是否包含关键词）
                if keyword_lower in text_lower:
                    return True
        return False
    
    def add_tts_rule(self, keyword: str, match_mode: str = "contains", tts_text: str = "") -> bool:
        """
        添加TTS规则
        
        Args:
            keyword: 触发关键词
            match_mode: 匹配模式
            tts_text: TTS播报的文字（空字符串表示播报完整弹幕内容）
            
        Returns:
            bool: 是否成功
        """
        if not keyword:
            return False
        
        with self.lock:
            # 检查是否已存在相同规则
            for rule in self.tts_rules:
                if rule.keyword == keyword and rule.match_mode == match_mode:
                    return False
            
            rule = TTSRule(keyword, match_mode, tts_text)
            self.tts_rules.append(rule)
            self.save_config()
            return True
    
    def remove_tts_rule(self, index: int) -> bool:
        """
        删除TTS规则
        
        Args:
            index: 规则索引
            
        Returns:
            bool: 是否成功
        """
        with self.lock:
            if 0 <= index < len(self.tts_rules):
                self.tts_rules.pop(index)
                self.save_config()
                return True
            return False
    
    def process_danmu(self, content: str, user: str = ""):
        """
        处理弹幕，检查是否触发TTS规则
        
        Args:
            content: 弹幕内容
            user: 用户昵称（可选）
        """
        if not self.enabled or not content or not self.tts_engine:
            return
        
        # 过滤礼物消息（检查内容中是否包含礼物特征，防止礼物信息以弹幕形式出现）
        if self._is_gift_message(content):
            return  # 屏蔽礼物消息
        
        # 过滤只有标点符号的内容
        if self._is_only_punctuation(content):
            return  # 不播报只有标点符号的内容
        
        # 检查用户昵称或内容是否包含屏蔽关键词（在锁内检查）
        with self.lock:
            check_text = f"{user} {content}".strip() if user else content
            if self._contains_block_keyword(check_text):
                return  # 屏蔽包含关键词的弹幕
            
            matched_rules = []
            # 收集所有匹配的规则
            for rule in self.tts_rules:
                if rule.match(content):
                    matched_rules.append(rule)
            
            # 如果有匹配的规则，处理所有匹配的规则
            if matched_rules:
                for rule in matched_rules:
                    # 确定要播报的文字
                    if rule.tts_text:
                        # 使用自定义文字
                        tts_content = rule.tts_text
                    else:
                        # 使用完整弹幕内容，包含用户昵称
                        tts_content = self._format_tts_content(content, user)
                    
                    if tts_content:
                        self.tts_engine.speak(tts_content)
                        print(f"[TTS管理器] TTS播报（规则匹配）: {rule.keyword} -> {tts_content[:50]}...")
                    
                    rule.last_trigger_time = time.time()
                    rule.trigger_count += 1
                    
                    # 注意：如果多个规则匹配，会依次播报，但通常只播报一次即可
                    # 这里为了兼容性，每个匹配的规则都会播报
            elif self.speak_all_danmu:
                # 如果开启了"播报所有弹幕"选项，即使没有匹配规则，也播报弹幕
                tts_content = self._format_tts_content(content, user)
                if tts_content:
                    self.tts_engine.speak(tts_content)
                    print(f"[TTS管理器] TTS播报（所有弹幕模式）: {tts_content[:50]}...")
    
    def _is_gift_message(self, content: str) -> bool:
        """
        检查内容是否是礼物消息
        
        Args:
            content: 弹幕内容
            
        Returns:
            bool: 如果是礼物消息返回True，否则返回False
        """
        if not content:
            return False
        
        # 检查是否包含礼物特征
        # 礼物消息通常包含：×数字、x数字、送出了、礼物、🎁等
        gift_patterns = [
            r'[×x]\s*\d+',  # ×数字 或 x数字
            r'送出了',      # "送出了"字样
            r'礼物',        # "礼物"字样
        ]
        
        for pattern in gift_patterns:
            if re.search(pattern, content):
                return True
        
        return False
    
    def _is_only_punctuation(self, content: str) -> bool:
        """
        检查内容是否只包含标点符号和空白字符
        
        Args:
            content: 弹幕内容
            
        Returns:
            bool: 如果只包含标点符号返回True，否则返回False
        """
        if not content:
            return True
        
        # 移除空白字符
        content_no_whitespace = content.strip()
        if not content_no_whitespace:
            return True
        
        # 使用正则表达式匹配所有非标点、非空白字符
        # 如果有任何字母、数字或中文汉字，则不是只有标点符号
        # 匹配字母、数字、中文字符（包括中文汉字）
        has_meaningful_char = re.search(r'[a-zA-Z0-9\u4e00-\u9fff]', content_no_whitespace)
        
        # 如果没有字母、数字、中文汉字，说明只有标点符号和特殊符号
        return has_meaningful_char is None
    
    def _format_tts_content(self, content: str, user: str = "") -> str:
        """
        格式化TTS播报内容，包含用户昵称
        
        Args:
            content: 弹幕内容
            user: 用户昵称（可选）
            
        Returns:
            str: 格式化后的TTS内容
        """
        content_stripped = content.strip()
        if user and user.strip():
            user_stripped = user.strip()
            # 检查内容是否已经包含用户昵称（防止重复）
            has_user_prefix = (
                content_stripped.startswith(f"{user_stripped}:") or 
                content_stripped.startswith(f"{user_stripped}：") or
                content_stripped.startswith(f"{user_stripped}说:") or
                content_stripped.startswith(f"{user_stripped}说：")
            )
            
            if has_user_prefix:
                # 内容已包含用户信息，确保格式是"用户说: 内容"
                if content_stripped.startswith(f"{user_stripped}:"):
                    return f"{user_stripped}说: {content_stripped[len(user_stripped)+1:].strip()}"
                elif content_stripped.startswith(f"{user_stripped}："):
                    return f"{user_stripped}说: {content_stripped[len(user_stripped)+1:].strip()}"
                else:
                    # 已经有"说:"格式，直接使用
                    return content_stripped
            else:
                # 内容不包含用户信息，添加"用户说: 内容"
                return f"{user_stripped}说: {content_stripped}"
        else:
            # 没有用户信息，直接使用内容
            return content_stripped


class AudioManager:
    """音频管理器（仅管理音频播放，不包含TTS）"""
    
    def __init__(self, cfg_ref: Dict, parent=None):
        """
        初始化音频管理器
        
        Args:
            cfg_ref: 配置字典引用
            parent: Qt父对象（用于确保在主线程中）
        """
        self.cfg = cfg_ref
        self.parent = parent
        self.keyword_rules: List[AudioRule] = []
        self.timer_rules: List[Dict] = []  # 定时播放规则
        self.current_player: Optional[AudioPlayer] = None
        self.enabled = False
        self.lock = threading.Lock()
        self._load_config()
    
    def _load_config(self):
        """从配置加载规则"""
        # 加载关键词规则（即使文件不存在也加载，允许用户稍后修复路径）
        keyword_rules_data = self.cfg.get('audio_keyword_rules', [])
        self.keyword_rules = []
        for rule_data in keyword_rules_data:
            try:
                rule = AudioRule.from_dict(rule_data)
                # 即使文件不存在也加载规则（允许用户稍后修复路径或文件）
                # 只在播放时检查文件是否存在
                self.keyword_rules.append(rule)
                if not os.path.exists(rule.audio_file):
                    print(f"[音频管理器] 警告：关键词规则 '{rule.keyword}' 的音频文件不存在: {rule.audio_file}")
            except Exception as e:
                print(f"[音频管理器] 加载关键词规则失败: {e}")
                import traceback
                traceback.print_exc()
        
        # 加载定时规则（即使文件不存在也加载）
        timer_rules_data = self.cfg.get('audio_timer_rules', [])
        self.timer_rules = []
        if isinstance(timer_rules_data, list):
            for rule_data in timer_rules_data:
                try:
                    # 确保规则是字典格式
                    if isinstance(rule_data, dict):
                        audio_file = rule_data.get('audio_file', '')
                        # 即使文件不存在也加载规则（允许用户稍后修复路径）
                        if not os.path.exists(audio_file):
                            print(f"[音频管理器] 警告：定时规则的音频文件不存在: {audio_file}")
                        # 使用copy避免引用问题，并确保包含所有必要字段
                        rule_copy = {
                            "interval": rule_data.get("interval", 0),
                            "audio_file": rule_data.get("audio_file", ""),
                            "last_play_time": rule_data.get("last_play_time", 0),
                            "play_count": rule_data.get("play_count", 0)
                        }
                        self.timer_rules.append(rule_copy)
                except Exception as e:
                    print(f"[音频管理器] 加载定时规则失败: {e}")
                    import traceback
                    traceback.print_exc()
    
    def save_config(self):
        """保存配置到文件"""
        try:
            # 将规则列表转换为字典列表（确保可序列化）
            keyword_rules_data = [rule.to_dict() for rule in self.keyword_rules]
            # 定时规则已经是字典列表，直接复制
            timer_rules_data = [rule.copy() if isinstance(rule, dict) else rule for rule in self.timer_rules]
            
            # 保存到配置字典
            self.cfg['audio_keyword_rules'] = keyword_rules_data
            self.cfg['audio_timer_rules'] = timer_rules_data
            self.cfg['audio_enabled'] = self.enabled
            
            # 保存到文件
            from config_manager import save_cfg
            save_cfg(self.cfg)
            print(f"[音频管理器] 配置已保存: 关键词规则{len(keyword_rules_data)}条, 定时规则{len(timer_rules_data)}条")
        except Exception as e:
            print(f"[音频管理器] 保存配置失败: {e}")
            import traceback
            traceback.print_exc()
    
    def set_enabled(self, enabled: bool):
        """设置功能开关"""
        self.enabled = enabled
        self.save_config()
    
    def add_keyword_rule(self, keyword: str, audio_file: str, match_mode: str = "contains", 
                        play_mode: str = "随机挑一") -> bool:
        """
        添加关键词规则
        
        Args:
            keyword: 触发关键词
            audio_file: 音频文件路径（可以是单个文件或"file1|file2|file3"格式）
            match_mode: 匹配模式
            play_mode: 播放模式（"随机挑一" 或 "顺序全发"）
            
        Returns:
            bool: 是否成功
        """
        if not keyword or not audio_file:
            return False
        
        # 检查音频文件是否存在（支持多个文件）
        audio_files = [f.strip() for f in audio_file.split("|") if f.strip()]
        if not audio_files:
            return False
        
        # 检查所有文件是否存在
        for af in audio_files:
            if not os.path.exists(af):
                return False
        
        with self.lock:
            # 检查是否已存在相同规则
            for rule in self.keyword_rules:
                if rule.keyword == keyword and rule.audio_file == audio_file:
                    return False
            
            rule = AudioRule(keyword, audio_file, match_mode, play_mode)
            self.keyword_rules.append(rule)
            self.save_config()
            return True
    
    def remove_keyword_rule(self, index: int) -> bool:
        """
        删除关键词规则
        
        Args:
            index: 规则索引
            
        Returns:
            bool: 是否成功
        """
        with self.lock:
            if 0 <= index < len(self.keyword_rules):
                self.keyword_rules.pop(index)
                self.save_config()
                return True
            return False
    
    def add_timer_rule(self, interval_seconds: int, audio_file: str) -> bool:
        """
        添加定时播放规则
        
        Args:
            interval_seconds: 播放间隔（秒）
            audio_file: 音频文件路径
            
        Returns:
            bool: 是否成功
        """
        if interval_seconds <= 0 or not audio_file:
            return False
        
        if not os.path.exists(audio_file):
            return False
        
        with self.lock:
            rule = {
                "interval": interval_seconds,
                "audio_file": audio_file,
                "last_play_time": 0,
                "play_count": 0
            }
            self.timer_rules.append(rule)
            self.save_config()
            return True
    
    def remove_timer_rule(self, index: int) -> bool:
        """
        删除定时播放规则
        
        Args:
            index: 规则索引
            
        Returns:
            bool: 是否成功
        """
        with self.lock:
            if 0 <= index < len(self.timer_rules):
                self.timer_rules.pop(index)
                self.save_config()
                return True
            return False
    
    def process_danmu(self, content: str):
        """
        处理弹幕，检查是否触发关键词规则
        
        Args:
            content: 弹幕内容
        """
        if not self.enabled or not content:
            return
        
        import random
        
        with self.lock:
            matched_rules = []
            # 收集所有匹配的规则
            for rule in self.keyword_rules:
                if rule.match(content):
                    matched_rules.append(rule)
            
            # 根据规则决定播放方式
            for rule in matched_rules:
                # 处理音频文件播放
                audio_files = rule.get_audio_files()
                if audio_files:
                    if rule.play_mode == "随机挑一":
                        # 随机选一个文件播放
                        selected_file = random.choice(audio_files)
                        self._play_audio(selected_file)
                        print(f"[音频管理器] 关键词触发（随机）: {rule.keyword} -> {os.path.basename(selected_file)}")
                    elif rule.play_mode == "顺序全发":
                        # 顺序播放所有文件（每次触发播放一个，下次触发播放下一个）
                        # 获取当前要播放的文件索引
                        current_index = rule.next_index % len(audio_files)
                        current_file = audio_files[current_index]
                        self._play_audio(current_file)
                        # 更新索引，下次播放下一个
                        rule.next_index = (rule.next_index + 1) % len(audio_files)
                        print(f"[音频管理器] 关键词触发（顺序）: {rule.keyword} -> {os.path.basename(current_file)} ({current_index + 1}/{len(audio_files)})")
                
                rule.last_trigger_time = time.time()
                rule.trigger_count += 1
                
                # 注意：如果多个规则匹配，会依次播放，这可能需要根据需求调整
                # 如果需要只播放第一个匹配的规则，可以在这里添加break
    
    def check_timer_rules(self):
        """检查定时播放规则"""
        if not self.enabled:
            return
        
        now = time.time()
        
        with self.lock:
            for rule in self.timer_rules:
                last_play = rule.get('last_play_time', 0)
                interval = rule.get('interval', 0)
                
                if interval > 0 and (now - last_play) >= interval:
                    audio_file = rule.get('audio_file', '')
                    if audio_file and os.path.exists(audio_file):
                        self._play_audio(audio_file)
                        rule['last_play_time'] = now
                        rule['play_count'] = rule.get('play_count', 0) + 1
                        print(f"[音频管理器] 定时播放: {audio_file}")
    
    def _play_audio(self, audio_file: str):
        """
        播放音频文件（需要在Qt主线程中调用）
        
        Args:
            audio_file: 音频文件路径
        """
        try:
            if not AUDIO_AVAILABLE:
                print(f"[音频管理器] 音频功能不可用，无法播放: {audio_file}")
                return
            
            if not os.path.exists(audio_file):
                print(f"[音频管理器] 音频文件不存在: {audio_file}")
                return
            
            # 如果当前正在播放，先停止
            if self.current_player:
                try:
                    self.current_player.stop()
                except:
                    pass
            
            # 创建新的播放器并播放（必须在Qt主线程中）
            def play_in_main_thread():
                try:
                    # 获取parent对象（用于确保在正确的线程中）
                    parent_obj = self.parent if hasattr(self, 'parent') and self.parent else None
                    # 创建播放器（必须指定parent）
                    self.current_player = AudioPlayer(audio_file, parent=parent_obj)
                    self.current_player.play()
                    print(f"[音频管理器] 开始播放音频: {os.path.basename(audio_file)}")
                except Exception as e:
                    print(f"[音频管理器] 播放音频失败: {e}")
                    import traceback
                    traceback.print_exc()
                    self.current_player = None
            
            # 确保在主线程中执行（使用QTimer）
            try:
                from PyQt6.QtWidgets import QApplication
                app = QApplication.instance()
                if app:
                    # 使用QTimer确保在主线程中执行
                    QTimer.singleShot(0, play_in_main_thread)
                else:
                    print(f"[音频管理器] 警告：QApplication实例不存在，尝试直接播放")
                    # 如果没有应用实例，直接尝试播放（可能在初始化阶段）
                    play_in_main_thread()
            except Exception as e2:
                print(f"[音频管理器] 调度播放失败: {e2}")
                import traceback
                traceback.print_exc()
                # 如果QTimer失败，直接尝试播放
                try:
                    play_in_main_thread()
                except:
                    pass
            
        except Exception as e:
            print(f"[音频管理器] 播放音频失败: {e}")
            import traceback
            traceback.print_exc()
    
    def test_play_audio(self, audio_file: str) -> bool:
        """
        测试播放音频文件（用于UI测试，必须在Qt主线程中调用）
        
        Args:
            audio_file: 音频文件路径
            
        Returns:
            bool: 是否成功
        """
        try:
            if not AUDIO_AVAILABLE:
                print(f"[音频测试] 音频功能不可用")
                return False
            
            if not os.path.exists(audio_file):
                print(f"[音频测试] 音频文件不存在: {audio_file}")
                return False
            
            # 在主线程中播放（确保在正确的线程中）
            def play_in_main_thread():
                try:
                    # 停止当前播放
                    if self.current_player:
                        try:
                            self.current_player.stop()
                            self.current_player = None
                        except:
                            pass
                    
                    # 获取parent对象
                    parent_obj = self.parent if hasattr(self, 'parent') and self.parent else None
                    
                    # 创建新的播放器并播放
                    test_player = AudioPlayer(audio_file, parent=parent_obj)
                    test_player.play()
                    
                    # 保存到当前播放器（避免被垃圾回收）
                    self.current_player = test_player
                    
                    print(f"[音频测试] 开始播放: {os.path.basename(audio_file)}")
                except Exception as e:
                    print(f"[音频测试] 播放失败: {e}")
                    import traceback
                    traceback.print_exc()
                    self.current_player = None
            
            # 确保在主线程中执行
            try:
                from PyQt6.QtWidgets import QApplication
                app = QApplication.instance()
                if app:
                    # 使用QTimer确保在主线程中执行
                    QTimer.singleShot(0, play_in_main_thread)
                else:
                    print(f"[音频测试] 警告：QApplication实例不存在，尝试直接播放")
                    # 如果没有应用实例，直接尝试播放
                    play_in_main_thread()
            except Exception as e2:
                print(f"[音频测试] 调度播放失败: {e2}")
                # 如果QTimer失败，直接尝试播放
                try:
                    play_in_main_thread()
                except:
                    pass
            
            return True
            
        except Exception as e:
            print(f"[音频测试] 测试播放失败: {e}")
            import traceback
            traceback.print_exc()
            return False
