import React, { useState, useRef, useCallback, useEffect } from 'react';
import { Button, message } from 'antd';
import { AudioOutlined, StopOutlined } from '@ant-design/icons';

interface AudioRecorderProps {
  onSTTResult: (text: string, isFinal: boolean, confidence: number) => void;
  onError: (error: string) => void;
  onStatusChange: (status: string) => void;
  websocketUrl: string;
  sessionId: string;
}

const AudioRecorder: React.FC<AudioRecorderProps> = ({
  onSTTResult,
  onError,
  onStatusChange,
  websocketUrl,
  sessionId
}) => {
  const [isRecording, setIsRecording] = useState(false);
  const [isConnected, setIsConnected] = useState(false);
  
  const websocketRef = useRef<WebSocket | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const processorRef = useRef<ScriptProcessorNode | null>(null);
  const sourceRef = useRef<MediaStreamAudioSourceNode | null>(null);
  const isRecordingRef = useRef<boolean>(false); // 用于音频处理回调中访问最新的录音状态

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
            console.log('🎯 准备调用onSTTResult回调函数');
            onSTTResult(text, is_final || false, confidence || 0.85);
            console.log('🎯 onSTTResult回调函数调用完成');
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
    };
  }, []); // 移除connectWebSocket依赖，避免重复连接

  return (
    <Button
      type={isRecording ? "primary" : "default"}
      icon={isRecording ? <StopOutlined /> : <AudioOutlined />}
      onClick={(e) => {
        console.log('🖱️ 录音按钮被点击', {
          isRecording,
          event: e,
          timestamp: new Date().toISOString()
        });
        if (isRecording) {
          stopRecording();
        } else {
          startRecording();
        }
      }}
      size="large"
      style={{
        borderRadius: '25px',
        background: isRecording ? '#ff4d4f' : 'rgba(255,255,255,0.2)',
        border: isRecording ? 'none' : '2px solid #e2e8f0',
        color: isRecording ? 'white' : '#666',
        fontWeight: '600',
        minWidth: '50px'
      }}
    />
  );
};

export default AudioRecorder;
