import React, { useState, useRef, useCallback, useEffect } from 'react';
import { Button, message } from 'antd';
import { AudioOutlined, StopOutlined, SoundOutlined, BorderBottomOutlined, BorderHorizontalOutlined, ArrowUpOutlined, EditOutlined } from '@ant-design/icons';

interface AudioRecorderProps {
  onSTTResult: (text: string, isFinal: boolean, confidence: number) => void;
  onError: (error: string) => void;
  onStatusChange: (status: string) => void;
  websocketUrl: string;
  sessionId: string;
  onMobileDirectSend?: (text: string) => void; // 新增：移动端直接发送回调
  hasInputText?: boolean; // 新增：是否有输入文本
  onSendText?: () => void; // 新增：发送文本回调
  isInRecordMode?: boolean; // 新增：是否在录音模式
  onRecordModeChange?: (isInRecordMode: boolean) => void; // 新增：录音模式变化回调
}

const AudioRecorder: React.FC<AudioRecorderProps> = ({
  onSTTResult,
  onError,
  onStatusChange,
  websocketUrl,
  sessionId,
  onMobileDirectSend,
  hasInputText = false,
  onSendText,
  isInRecordMode = false,
  onRecordModeChange
}) => {
  const [isRecording, setIsRecording] = useState(false);
  const [isConnected, setIsConnected] = useState(false);
  const [isTextMode, setIsTextMode] = useState(false); // 新增：文本输入模式
  const [isLongPressing, setIsLongPressing] = useState(false); // 是否正在长按
  const [isCancelling, setIsCancelling] = useState(false); // 是否正在取消录音

  const websocketRef = useRef<WebSocket | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const processorRef = useRef<ScriptProcessorNode | null>(null);
  const sourceRef = useRef<MediaStreamAudioSourceNode | null>(null);
  const isRecordingRef = useRef<boolean>(false); // 用于音频处理回调中访问最新的录音状态
  const longPressTimerRef = useRef<NodeJS.Timeout | null>(null); // 长按定时器
  const isMobileRef = useRef<boolean>(false); // 是否为移动端
  const touchStartYRef = useRef<number>(0); // 触摸开始时的Y坐标
  const touchStartTimeRef = useRef<number>(0); // 触摸开始时间
  const sttResultsRef = useRef<string[]>([]); // 存储STT结果
  const globalMouseUpHandlerRef = useRef<((e: MouseEvent) => void) | null>(null); // 全局鼠标事件处理器

  // 连接WebSocket
  const connectWebSocket = useCallback(async () => {
    try {
      console.log('🔌 开始连接WebSocket:', websocketUrl);
      onStatusChange('正在连接WebSocket...');

      const ws = new WebSocket(websocketUrl);
      websocketRef.current = ws;

      ws.onopen = () => {
        console.log('✅ WebSocket连接成功');
        setIsConnected(true);
        onStatusChange('WebSocket连接成功');

        // 发送hello消息 - 前端录音协议
        const helloMessage = {
          type: 'hello',
          session_id: sessionId,
          capabilities: {
            audio: true,
            stt: true,
            pcm_format: true
          },
          audio_params: {
            format: 'pcm',
            sample_rate: 16000,
            channels: 1,
            bits_per_sample: 16
          }
        };
        console.log('📤 发送hello消息:', helloMessage);
        ws.send(JSON.stringify(helloMessage));
      };

      ws.onmessage = (event) => {
        console.log('📨 收到WebSocket消息:', event.data);
        try {
          const data = JSON.parse(event.data);
          console.log('📨 解析后的消息数据:', data);

          if (data.type === 'hello_ack') {
            console.log('✅ 收到hello确认消息');
            onStatusChange('音频服务就绪');
          } else if (data.type === 'recording_start_ack') {
            console.log('✅ 收到录音开始确认消息');
            onStatusChange('录音已开始');
          } else if (data.type === 'recording_end_ack') {
            console.log('✅ 收到录音结束确认消息');
            onStatusChange('录音已结束');
          } else if (data.type === 'stt_result') {
            console.log('🎯 收到STT结果:', data);
            console.log('🎯 STT结果数据结构:', JSON.stringify(data, null, 2));
            const { text, is_final, confidence } = data.data;
            console.log('🎯 提取的STT数据:', { text, is_final, confidence });

            // 更新STT结果存储
            if (text && text.trim()) {
              sttResultsRef.current.push(text);
              console.log('📝 更新STT结果存储:', sttResultsRef.current);
            }

                         // 移动端处理：如果是最终结果且是移动端，显示在输入框中
             if (is_final && isMobileRef.current && text.trim()) {
               console.log('📱 移动端收到最终STT结果，显示在输入框中:', text);
               console.log('📱 准备调用onSTTResult回调函数');
               onSTTResult(text, is_final || false, confidence || 0.85);
               console.log('📱 移动端STT结果已显示在输入框中');
             } else if (is_final && isMobileRef.current) {
               console.log('📱 移动端收到最终STT结果，但文本为空:', { text });
             } else {
               // 桌面端或非最终结果：正常回调
               console.log('🎯 准备调用onSTTResult回调函数');
               onSTTResult(text, is_final || false, confidence || 0.85);
               console.log('🎯 onSTTResult回调函数调用完成');
             }
          } else if (data.type === 'error') {
            console.error('❌ 收到错误消息:', data);
            onError(data.data?.message || data.message || '未知错误');
          } else {
            console.log('📨 收到未知类型消息:', data.type);
          }
        } catch (error) {
          console.error('❌ 解析WebSocket消息失败:', error);
          const errorMessage = error instanceof Error ? error.message : String(error);
          console.error('解析错误详情:', errorMessage);
        }
      };

      ws.onerror = (error) => {
        console.error('WebSocket错误:', error);
        onError('WebSocket连接错误');
        setIsConnected(false);
      };

      ws.onclose = () => {
        console.log('WebSocket连接关闭');
        setIsConnected(false);
        onStatusChange('WebSocket连接已断开');
      };

    } catch (error) {
      console.error('连接WebSocket失败:', error);
      const errorMessage = error instanceof Error ? error.message : String(error);
      onError('连接WebSocket失败: ' + errorMessage);
    }
  }, [websocketUrl, sessionId, onSTTResult, onError, onStatusChange]);

  // 初始化音频
  const initializeAudio = useCallback(async () => {
    try {
      console.log('🎵 开始初始化音频...');
      onStatusChange('正在初始化音频...');

      // 获取音频权限
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          sampleRate: 16000,
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true
        }
      });

      console.log('✅ 获取音频权限成功');
      mediaStreamRef.current = stream;

      // 创建音频上下文
      const audioContext = new AudioContext({
        sampleRate: 16000
      });
      audioContextRef.current = audioContext;
      console.log('✅ 创建音频上下文成功');

      // 创建音频源
      const source = audioContext.createMediaStreamSource(stream);
      sourceRef.current = source;
      console.log('✅ 创建音频源成功');

      // 创建音频处理器
      const processor = audioContext.createScriptProcessor(4096, 1, 1);
      processorRef.current = processor;
      console.log('✅ 创建音频处理器成功');

      // 音频处理回调 - 使用ref来访问最新的状态
      processor.onaudioprocess = (event) => {
        // 使用ref来获取最新的isRecording状态，避免闭包问题
        const currentIsRecording = isRecordingRef.current;
        const currentWebSocket = websocketRef.current;

        console.log('🎤 音频处理回调被触发', {
          isRecording: currentIsRecording,
          websocketReadyState: currentWebSocket?.readyState,
          inputBufferLength: event.inputBuffer.length
        });

        // 检查WebSocket连接状态和录音状态
        if (currentIsRecording && currentWebSocket?.readyState === WebSocket.OPEN) {
          const inputBuffer = event.inputBuffer;
          const pcmData = inputBuffer.getChannelData(0);

          // 转换为16位PCM
          const pcm16 = new Int16Array(pcmData.length);
          for (let i = 0; i < pcmData.length; i++) {
            pcm16[i] = Math.max(-32768, Math.min(32767, pcmData[i] * 32768));
          }

          // 发送音频数据 - 直接发送整个音频块
          try {
            currentWebSocket.send(pcm16.buffer);
            console.log('🎵 发送音频数据块，大小:', pcm16.buffer.byteLength, '字节');
          } catch (error) {
            console.error('❌ 发送音频数据失败:', error);
          }
        } else {
          console.log('🔇 跳过音频发送:', {
            isRecording: currentIsRecording,
            websocketReadyState: currentWebSocket?.readyState,
            websocketOpen: currentWebSocket?.readyState === WebSocket.OPEN
          });
        }
      };

      // 连接音频节点
      source.connect(processor);
      processor.connect(audioContext.destination);
      console.log('✅ 音频节点连接成功');

      onStatusChange('音频初始化完成');

    } catch (error) {
      console.error('❌ 初始化音频失败:', error);
      const errorMessage = error instanceof Error ? error.message : String(error);
      onError('初始化音频失败: ' + errorMessage);
    }
  }, [isRecording, onStatusChange, onError]);

  // 同步录音状态到ref
  useEffect(() => {
    isRecordingRef.current = isRecording;
  }, [isRecording]);

  // 开始录音
  const startRecording = useCallback(async () => {
    console.log('🎤 开始录音按钮被点击');
    console.log('当前状态:', {
      isConnected,
      websocketReadyState: websocketRef.current?.readyState,
      audioContextExists: !!audioContextRef.current,
      sessionId
    });

    try {
      // 如果WebSocket未连接，尝试重新连接
      if (!isConnected || websocketRef.current?.readyState !== WebSocket.OPEN) {
        console.log('🔌 WebSocket未连接，尝试重新连接...');
        await connectWebSocket();
      }

      // 发送录音开始消息
      if (websocketRef.current?.readyState === WebSocket.OPEN) {
        const startMessage = {
          type: 'recording_start',
          session_id: sessionId
        };
        console.log('📤 发送录音开始消息:', startMessage);
        websocketRef.current.send(JSON.stringify(startMessage));
      } else {
        console.error('❌ WebSocket未连接，无法发送录音开始消息');
        onError('WebSocket连接失败，无法开始录音');
        return;
      }

             // 初始化音频（如果还没有初始化）
       if (!audioContextRef.current) {
         console.log('🎵 音频上下文不存在，初始化音频...');
         await initializeAudio();
       }

       // 清空STT结果存储
       sttResultsRef.current = [];
       console.log('📝 清空STT结果存储');

      // 最后设置录音状态为true，这样音频处理器就会开始发送数据
      console.log('✅ 设置录音状态为true');
      setIsRecording(true);
      isRecordingRef.current = true; // 同时更新ref
      onStatusChange('正在录音...');

    } catch (error) {
      console.error('❌ 开始录音失败:', error);
      const errorMessage = error instanceof Error ? error.message : String(error);
      onError('开始录音失败: ' + errorMessage);
      // 如果出错，重置录音状态
      setIsRecording(false);
    }
  }, [isConnected, connectWebSocket, initializeAudio, sessionId, onStatusChange, onError]);

  // 停止录音
  const stopRecording = useCallback(async () => {
    console.log('⏹️ 停止录音按钮被点击');
    console.log('当前状态:', {
      isRecording,
      websocketReadyState: websocketRef.current?.readyState,
      sessionId
    });

    try {
      console.log('✅ 设置录音状态为false');
      setIsRecording(false);
      isRecordingRef.current = false; // 同时更新ref
      
             // 移动端录音完成后重置长按状态，并退出录音模式，回到输入框状态
       if (isMobileRef.current) {
         setIsLongPressing(false);
         // 退出录音模式，回到输入框状态
         if (onRecordModeChange) {
           onRecordModeChange(false);
         }
         console.log('📱 录音结束，退出录音模式，回到输入框状态');
       }
      
      onStatusChange('录音已停止');

      // 发送录音结束信号
      if (websocketRef.current?.readyState === WebSocket.OPEN) {
        const endMessage = {
          type: 'recording_end',
          session_id: sessionId
        };
        console.log('📤 发送录音结束消息:', endMessage);
        websocketRef.current.send(JSON.stringify(endMessage));
      } else {
        console.warn('⚠️ WebSocket未连接，无法发送录音结束消息');
      }

    } catch (error) {
      console.error('❌ 停止录音失败:', error);
      const errorMessage = error instanceof Error ? error.message : String(error);
      onError('停止录音失败: ' + errorMessage);
    }
  }, [sessionId, onStatusChange, onError, isRecording]);

  // 移动端长按开始录音
  const handleTouchStart = useCallback(async (e: React.TouchEvent) => {
    if (!isMobileRef.current || !isInRecordMode) return;

    e.preventDefault();
    console.log('📱 移动端触摸开始');

    // 记录触摸开始的位置和时间
    touchStartYRef.current = e.touches[0].clientY;
    touchStartTimeRef.current = Date.now();

    // 设置长按定时器
    longPressTimerRef.current = setTimeout(async () => {
      console.log('📱 长按触发，开始录音');
      setIsLongPressing(true);
      await startRecording();
    }, 500); // 500ms长按触发
  }, [isInRecordMode, startRecording]);

  // 鼠标事件处理 - 用于电脑模拟手机
  const handleMouseDown = useCallback(async (e: React.MouseEvent) => {
    console.log('🖱️ 鼠标按下事件被触发');
    e.preventDefault(); // 阻止默认行为
    e.stopPropagation(); // 阻止事件冒泡
    
    if (!isMobileRef.current || !isInRecordMode) {
      console.log('🖱️ 鼠标按下事件被忽略 - 不是移动端或不在录音模式');
      return;
    }

    console.log('🖱️ 模拟移动端触摸开始');
    // 记录触摸开始时间
    touchStartTimeRef.current = Date.now();

    // 设置长按定时器
    longPressTimerRef.current = setTimeout(async () => {
      console.log('🖱️ 模拟长按触发，开始录音');
      setIsLongPressing(true);
      await startRecording();
    }, 500); // 500ms长按触发
  }, [isInRecordMode, startRecording]);

  // 移动端触摸移动
  const handleTouchMove = useCallback((e: React.TouchEvent) => {
    if (!isMobileRef.current || !isInRecordMode || !isLongPressing) return;

    e.preventDefault();
    const currentY = e.touches[0].clientY;
    const startY = touchStartYRef.current;
    const moveDistance = startY - currentY; // 向上移动的距离

    // 如果向上移动超过50px，触发取消录音
    if (moveDistance > 50) {
      if (!isCancelling) {
        console.log('📱 检测到上移取消手势');
        setIsCancelling(true);
      }
    } else {
      if (isCancelling) {
        console.log('📱 取消手势已重置');
        setIsCancelling(false);
      }
    }
  }, [isInRecordMode, isLongPressing, isCancelling]);

  // 移动端触摸结束
  const handleTouchEnd = useCallback(async (e: React.TouchEvent) => {
    if (!isMobileRef.current || !isInRecordMode) return;

    e.preventDefault();
    console.log('📱 移动端触摸结束');

    // 清除长按定时器
    if (longPressTimerRef.current) {
      clearTimeout(longPressTimerRef.current);
      longPressTimerRef.current = null;
    }

    // 如果正在录音，停止录音
    if (isLongPressing) {
      if (isCancelling) {
        console.log('📱 取消录音');
        setIsCancelling(false);
        // 取消录音，不发送STT结果
        setIsLongPressing(false);
        setIsRecording(false);
        isRecordingRef.current = false;
        // 退出录音模式，回到输入框状态
        if (onRecordModeChange) {
          onRecordModeChange(false);
        }
        onStatusChange('录音已取消');
      } else {
        console.log('📱 停止录音');
        setIsLongPressing(false);
        await stopRecording();
      }
    }
  }, [isInRecordMode, isLongPressing, isCancelling, stopRecording, onStatusChange]);

  const handleMouseUp = useCallback(async (e: React.MouseEvent) => {
    console.log('🖱️ 鼠标松开事件被触发');
    e.preventDefault(); // 阻止默认行为
    e.stopPropagation(); // 阻止事件冒泡
    
    if (!isMobileRef.current || !isInRecordMode) {
      console.log('🖱️ 鼠标松开事件被忽略 - 不是移动端或不在录音模式');
      return;
    }

    console.log('🖱️ 模拟移动端触摸结束');

    // 清除长按定时器
    if (longPressTimerRef.current) {
      clearTimeout(longPressTimerRef.current);
      longPressTimerRef.current = null;
    }

    // 如果正在录音，停止录音
    if (isLongPressing) {
      if (isCancelling) {
        console.log('🖱️ 取消录音');
        setIsCancelling(false);
        // 取消录音，不发送STT结果
        setIsLongPressing(false);
        setIsRecording(false);
        isRecordingRef.current = false;
        // 退出录音模式，回到输入框状态
        if (onRecordModeChange) {
          onRecordModeChange(false);
        }
        onStatusChange('录音已取消');
      } else {
        console.log('🖱️ 停止录音');
        setIsLongPressing(false);
        await stopRecording();
      }
    }
  }, [isInRecordMode, isLongPressing, isCancelling, stopRecording, onStatusChange]);

  // 移动端触摸取消
  const handleTouchCancel = useCallback(async (e: React.TouchEvent) => {
    if (!isMobileRef.current || !isInRecordMode) return;

    e.preventDefault();
    console.log('📱 移动端触摸取消');

    // 清除长按定时器
    if (longPressTimerRef.current) {
      clearTimeout(longPressTimerRef.current);
      longPressTimerRef.current = null;
    }

    // 如果正在录音，停止录音
    if (isLongPressing) {
      setIsLongPressing(false);
      await stopRecording();
    }
  }, [isInRecordMode, isLongPressing, stopRecording]);

  // 桌面端点击处理
  const handleClick = useCallback(async (e: React.MouseEvent) => {
    if (isMobileRef.current) return; // 移动端不处理点击

    console.log('🖱️ 桌面端点击');
    if (isRecording) {
      await stopRecording();
    } else {
      await startRecording();
    }
  }, [isRecording, startRecording, stopRecording]);

     // 移动端点击处理
   const handleMobileClick = useCallback((e: React.MouseEvent) => {
     if (!isMobileRef.current) return;

     e.preventDefault();
     console.log('📱 移动端点击处理');
     
     // 如果已经在录音模式，退出录音模式
     if (isInRecordMode) {
       console.log('📱 退出录音模式');
       if (onRecordModeChange) {
         onRecordModeChange(false);
       }
       onStatusChange('文本输入模式');
     } else {
       // 进入录音模式
       console.log('📱 进入录音模式');
       if (onRecordModeChange) {
         onRecordModeChange(true);
       }
       onStatusChange('录音模式 - 按住说话');
     }
   }, [isInRecordMode, onStatusChange]);

  // 检测是否为移动端
  useEffect(() => {
    const isMobile = /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent);
    isMobileRef.current = isMobile;
    console.log('📱 设备检测结果:', { 
      userAgent: navigator.userAgent,
      isMobile,
      isSimulated: navigator.userAgent.includes('Chrome') && navigator.userAgent.includes('Mobile')
    });
  }, []);

  // 组件加载时自动连接WebSocket
  useEffect(() => {
    console.log('🚀 AudioRecorder组件初始化', {
      websocketUrl,
      sessionId,
      timestamp: new Date().toISOString()
    });

    // 自动连接WebSocket
    connectWebSocket();

    // 清理资源
    return () => {
      console.log('🧹 AudioRecorder组件清理资源');
      if (processorRef.current) {
        processorRef.current.disconnect();
      }
      if (sourceRef.current) {
        sourceRef.current.disconnect();
      }
      if (mediaStreamRef.current) {
        mediaStreamRef.current.getTracks().forEach(track => track.stop());
      }
      if (audioContextRef.current && audioContextRef.current.state !== 'closed') {
        audioContextRef.current.close();
      }
      if (websocketRef.current) {
        websocketRef.current.close();
      }
      // 清理长按定时器
      if (longPressTimerRef.current) {
        clearTimeout(longPressTimerRef.current);
      }
    };
  }, []); // 移除connectWebSocket依赖，避免重复连接

  // 全局鼠标事件监听 - 用于电脑模拟手机
  useEffect(() => {
    console.log('🌍 设置全局鼠标事件监听器');
    
    // 移除之前的监听器
    if (globalMouseUpHandlerRef.current) {
      document.removeEventListener('mouseup', globalMouseUpHandlerRef.current);
      console.log('🌍 移除之前的全局鼠标事件监听器');
    }
    
    const handleGlobalMouseUp = async (e: MouseEvent) => {
      console.log('🌍 全局鼠标松开事件被触发');
      console.log('🌍 当前状态检查:', {
        isMobile: isMobileRef.current,
        isInRecordMode,
        isLongPressing,
        isRecording,
        isCancelling
      });
      
      // 只在移动端且正在录音时处理
      if (isMobileRef.current && isInRecordMode && (isLongPressing || isRecording)) {
        console.log('🌍 全局鼠标松开事件被触发 - 条件满足');
        
        // 清除长按定时器
        if (longPressTimerRef.current) {
          clearTimeout(longPressTimerRef.current);
          longPressTimerRef.current = null;
          console.log('🌍 已清除长按定时器');
        }

        // 如果正在录音，停止录音
        if (isLongPressing || isRecording) {
          if (isCancelling) {
            console.log('🌍 取消录音');
            setIsCancelling(false);
            setIsLongPressing(false);
            setIsRecording(false);
            isRecordingRef.current = false;
            // 退出录音模式，回到输入框状态
            if (onRecordModeChange) {
              onRecordModeChange(false);
            }
            onStatusChange('录音已取消');
          } else {
            console.log('🌍 停止录音 - 准备调用stopRecording');
            setIsLongPressing(false);
            await stopRecording();
            console.log('🌍 stopRecording调用完成');
          }
        }
      } else {
        console.log('🌍 全局鼠标松开事件被忽略 - 条件不满足');
      }
    };
    
    // 保存处理器引用
    globalMouseUpHandlerRef.current = handleGlobalMouseUp;
    
    // 添加全局鼠标事件监听
    document.addEventListener('mouseup', handleGlobalMouseUp);
    console.log('🌍 全局鼠标事件监听器已添加');
    
    return () => {
      if (globalMouseUpHandlerRef.current) {
        document.removeEventListener('mouseup', globalMouseUpHandlerRef.current);
        console.log('🌍 全局鼠标事件监听器已移除');
      }
    };
  }, [isInRecordMode, isLongPressing, isRecording, isCancelling, stopRecording, onStatusChange]);

     // 根据状态确定按钮样式和内容
   const getButtonContent = () => {
     if (isMobileRef.current) {
       if (isInRecordMode) {
         if (isLongPressing || isRecording) {
           // 正在录音状态
           if (isCancelling) {
             // 取消录音状态
             return {
               text: '松开手指，取消发送',
               icon: null,
               background: '#ff4d4f',
               color: 'white',
               border: 'none'
             };
           } else {
             // 正常录音状态
             return {
               text: '松手发送，上移取消',
               icon: null,
               background: '#1890ff',
               color: 'white',
               border: 'none'
             };
           }
                   } else {
            // 录音模式，等待长按 - 显示按住说话文案
            return {
              text: '按住说话',
              icon: null,
              background: 'transparent',
              color: '#333333',
              border: 'none'
            };
          }
                } else {
           // 非录音模式
           if (hasInputText) {
             // 有输入文本时显示发送按钮
             return {
               text: '',
               icon: <ArrowUpOutlined />,
               background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
               color: 'white',
               border: 'none'
             };
           } else {
             // 初始状态 - 录音按钮
             return {
               text: '',
               icon: <SoundOutlined />,
               background: 'transparent',
               color: '#6b7280',
               border: 'none'
             };
           }
         }
     } else {
       // 桌面端
       if (isRecording) {
         return {
           text: '',
           icon: <StopOutlined />,
           background: '#ff4d4f',
           color: 'white',
           border: 'none'
         };
       } else {
         return {
           text: '',
           icon: <SoundOutlined />,
           background: 'rgba(255,255,255,0.8)',
           color: '#6b7280',
           border: '1px solid #d1d5db'
         };
       }
     }
   };

  const buttonContent = getButtonContent();
  
  // 调试信息
  console.log('🎯 AudioRecorder 状态:', {
    isMobile: isMobileRef.current,
    isInRecordMode,
    isLongPressing,
    isRecording,
    isCancelling,
    hasInputText
  });

  // 移动端文本输入模式切换处理
  const handleTextModeToggle = () => {
    if (isMobileRef.current) {
      // 切换到文本输入模式，通知父组件
      if (onMobileDirectSend) {
        onMobileDirectSend('TEXT_MODE'); // 发送特殊信号表示切换到文本模式
      }
      if (onRecordModeChange) {
        onRecordModeChange(false);
      }
      onStatusChange('文本输入模式');
    }
  };

  return (
    <div style={{
      display: 'flex',
      alignItems: 'center',
      gap: '8px',
      position: 'relative',
      width: isMobileRef.current && isInRecordMode ? '100%' : 'auto',
      height: isMobileRef.current && isInRecordMode ? '100%' : 'auto',
      padding: isMobileRef.current && isInRecordMode ? '0' : '0',
      minWidth: isMobileRef.current && isInRecordMode ? '100%' : 'auto',
      minHeight: isMobileRef.current && isInRecordMode ? '100%' : 'auto'
    }}>
      {/* 移动端录音模式 - 显示按住说话文案和返回文本按钮 */}
      {isMobileRef.current && isInRecordMode && !isLongPressing && !isRecording ? (
        <div style={{
          position: 'relative',
          width: '100%',
          height: '100%',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center'
        }}>
          {/* 返回文本输入按钮 - 右上角 */}
          <Button
            type="default"
            icon={<EditOutlined />}
            onClick={handleTextModeToggle}
            size="small"
            style={{
              position: 'absolute',
              top: '4px',
              right: '4px',
              zIndex: 10,
              borderRadius: '50%',
              width: '28px',
              height: '28px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              background: 'rgba(255, 255, 255, 0.9)',
              border: '1px solid #e2e8f0',
              color: '#6b7280',
              boxShadow: '0 2px 4px rgba(0, 0, 0, 0.1)',
              transition: 'all 0.2s ease'
            }}
          />
          
          {/* 按住说话按钮 */}
          <div
            onClick={handleMobileClick}
            onTouchStart={handleTouchStart}
            onTouchMove={handleTouchMove}
            onTouchEnd={handleTouchEnd}
            onTouchCancel={handleTouchCancel}
            onMouseDown={handleMouseDown}
            onMouseUp={handleMouseUp}
            style={{
              fontSize: '16px',
              color: '#333333',
              fontWeight: '500',
              cursor: 'pointer',
              userSelect: 'none',
              WebkitUserSelect: 'none',
              textAlign: 'center',
              position: 'absolute',
              left: '0',
              top: '0',
              right: '0',
              bottom: '0',
              zIndex: 5,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              backgroundColor: '#ffffff',
              borderRadius: '25px',
              border: '2px solid #e2e8f0',
              boxShadow: '0 1px 3px rgba(0, 0, 0, 0.1)'
            }}
          >
            按住说话
          </div>
        </div>
      ) : (
        /* 其他状态 - 保持原有样式 */
        <div style={{
          position: 'relative',
          width: isMobileRef.current && isInRecordMode ? '100%' : 'auto',
          height: isMobileRef.current && isInRecordMode ? '100%' : 'auto'
        }}>
          {/* 移动端录音模式下的返回文本按钮 - 仅在非录音状态显示 */}
          {isMobileRef.current && isInRecordMode && !isLongPressing && !isRecording && (
            <Button
              type="default"
              icon={<EditOutlined />}
              onClick={handleTextModeToggle}
              size="small"
              style={{
                position: 'absolute',
                top: '4px',
                right: '4px',
                zIndex: 10,
                borderRadius: '50%',
                width: '28px',
                height: '28px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                background: 'rgba(255, 255, 255, 0.9)',
                border: '1px solid #e2e8f0',
                color: '#6b7280',
                boxShadow: '0 2px 4px rgba(0, 0, 0, 0.1)',
                transition: 'all 0.2s ease'
              }}
            />
          )}
          
          <Button
            type={isRecording || isLongPressing ? "primary" : "default"}
            icon={buttonContent.icon}
            onClick={isMobileRef.current ? (hasInputText ? onSendText : handleMobileClick) : handleClick}
            onTouchStart={handleTouchStart}
            onTouchMove={handleTouchMove}
            onTouchEnd={handleTouchEnd}
            onTouchCancel={handleTouchCancel}
            onMouseDown={handleMouseDown}
            onMouseUp={handleMouseUp}
            size="middle"
            style={{
              borderRadius: isMobileRef.current && isInRecordMode ? '20px' : '50%',
              background: buttonContent.background,
              border: buttonContent.border,
              color: buttonContent.color,
              fontWeight: '600',
              width: isMobileRef.current && isInRecordMode ? (isLongPressing || isRecording ? '100%' : '32px') : '32px',
              height: isMobileRef.current && isInRecordMode ? '100%' : '32px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              boxShadow: isRecording || isLongPressing ? '0 2px 8px rgba(255, 77, 79, 0.3)' : '0 1px 3px rgba(0, 0, 0, 0.1)',
              transition: 'all 0.2s ease',
              fontSize: isMobileRef.current && isInRecordMode ? '14px' : '14px',
              whiteSpace: 'nowrap',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              position: 'relative'
            }}
          >
            {buttonContent.text}
          </Button>
        </div>
      )}
    </div>
  );
};

export default AudioRecorder;
