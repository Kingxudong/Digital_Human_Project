/**
 * Copyright 2024 Beijing Volcano Engine Technology Co., Ltd. All Rights Reserved.
 * SPDX-license-identifier: BSD-3-Clause
 */

import React, { useState, useContext, useEffect, useCallback, useRef, useMemo } from 'react';
import { message, Input, Button, List, Typography } from 'antd';
import { AudioOutlined, StopOutlined, SettingOutlined } from '@ant-design/icons';
import styled from 'styled-components';
import {
  MediaType,
  onUserJoinedEvent,
  onUserLeaveEvent,
  PlayerEvent,
  AutoPlayFailedEvent,
} from '@volcengine/rtc';
import { ControlBar, AutoPlayModal } from '../../modules';
import { Context } from '../../context';
import AudioRecorder from '../../components/AudioRecorder';

import RTCComponent from '../../sdk/rtc-component';
import { RTCClient } from '../../app-interfaces';
import { streamOptions } from './constant';
import config from '../../config';
import MediaPlayer from '../../components/MediaPlayer';
import { removeLoginInfo } from '../../utils';
import ErrorBoundary from '../../components/ErrorBoundary';
import { globalErrorHandler, resetGlobalErrorCount } from '../../utils/errorHandler';

const Container = styled.div`
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  padding: 20px;
  gap: 20px;
  background: linear-gradient(to bottom, #f8fafc, #e2e8f0);
  animation: fadeIn 0.6s ease-out;
  
  @media (max-width: 768px) {
    padding: 12px;
    gap: 12px;
  }
`;

const VideoContainer = styled.div`
  flex: 1;
  width: 100%;
  height: 65%;
  display: flex;
  justify-content: center;
  align-items: center;
  background: linear-gradient(135deg, #1e293b, #334155);
  border-radius: 20px;
  position: relative;
  box-shadow: 0 20px 40px rgba(0,0,0,0.1);
  overflow: hidden;
  animation: fadeIn 0.8s ease-out;
  
  &::before {
    content: '';
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: radial-gradient(circle at 30% 30%, rgba(99, 102, 241, 0.1), transparent 50%);
    pointer-events: none;
    animation: float 6s ease-in-out infinite;
  }
  
  @keyframes float {
    0%, 100% { transform: translateY(0px) scale(1); }
    50% { transform: translateY(-5px) scale(1.02); }
  }
  
  /* 确保数字人视频为1:1长宽比 */
  & > div {
    aspect-ratio: 1 / 1;
    max-width: min(100%, 60vh);
    max-height: min(100%, 60vh);
    width: auto;
    height: auto;
    border-radius: 16px;
    overflow: hidden;
    box-shadow: 0 10px 30px rgba(0,0,0,0.3);
    transition: transform 0.3s ease;
    
    &:hover {
      transform: scale(1.02);
    }
  }
  
  @media (max-width: 768px) {
    height: 60%;
    
    & > div {
      max-width: min(100%, 50vh);
      max-height: min(100%, 50vh);
    }
  }
`;

const ChatContainer = styled.div`
  height: 35%;
  width: 100%;
  display: flex;
  flex-direction: column;
  background: rgba(255, 255, 255, 0.95);
  backdrop-filter: blur(20px);
  border-radius: 20px;
  padding: 24px;
  box-shadow: 0 20px 40px rgba(0,0,0,0.1);
  border: 1px solid rgba(255, 255, 255, 0.2);
  animation: slideIn 0.8s ease-out 0.2s both;
  
  @media (max-width: 768px) {
    padding: 16px;
    height: 40%;
  }
`;

const ChatHeader = styled.div`
  display: flex;
  align-items: center;
  margin-bottom: 16px;
  padding-bottom: 12px;
  border-bottom: 1px solid rgba(0,0,0,0.1);
  max-width: 300px;
`;

const ChatTitle = styled.h3`
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: #1e293b;
  display: flex;
  align-items: center;
  gap: 8px;
  
  &::before {
    content: '💬';
    font-size: 20px;
  }
`;

const ChatMessages = styled.div`
  flex: 1;
  overflow-y: auto;
  margin-bottom: 16px;
  padding-right: 8px;
  
  /* 自定义滚动条 */
  &::-webkit-scrollbar {
    width: 6px;
  }
  
  &::-webkit-scrollbar-track {
    background: rgba(0,0,0,0.05);
    border-radius: 3px;
  }
  
  &::-webkit-scrollbar-thumb {
    background: rgba(0,0,0,0.2);
    border-radius: 3px;
    
    &:hover {
      background: rgba(0,0,0,0.3);
    }
  }
`;

const ChatInput = styled.div`
  display: flex;
  gap: 12px;
  align-items: flex-end;
`;

const MessageBubble = styled.div<{ sender: 'user' | 'ai' }>`
  max-width: 75%;
  padding: 12px 16px;
  border-radius: 18px;
  margin: 8px 0;
  position: relative;
  word-wrap: break-word;
  animation: fadeIn 0.4s ease-out;
  transition: transform 0.2s ease, box-shadow 0.2s ease;
  
  &:hover {
    transform: translateY(-1px);
  }
  
  ${props => props.sender === 'user' ? `
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    color: white;
    margin-left: auto;
    border-bottom-right-radius: 6px;
    box-shadow: 0 4px 12px rgba(102, 126, 234, 0.3);
    
    &:hover {
      box-shadow: 0 6px 16px rgba(102, 126, 234, 0.4);
    }
  ` : `
    background: linear-gradient(135deg, #f8fafc 0%, #e2e8f0 100%);
    color: #1e293b;
    margin-right: auto;
    border-bottom-left-radius: 6px;
    box-shadow: 0 4px 12px rgba(0,0,0,0.1);
    border: 1px solid rgba(0,0,0,0.05);
    
    &:hover {
      box-shadow: 0 6px 16px rgba(0,0,0,0.15);
    }
  `}
  
  &::before {
    content: '';
    position: absolute;
    bottom: 0;
    width: 0;
    height: 0;
    border: 8px solid transparent;
    
    ${props => props.sender === 'user' ? `
      right: -8px;
      border-left-color: #764ba2;
      border-bottom: none;
    ` : `
      left: -8px;
      border-right-color: #e2e8f0;
      border-bottom: none;
    `}
  }
  
  @media (max-width: 768px) {
    max-width: 85%;
    padding: 10px 14px;
    font-size: 14px;
  }
`;

const WaitingIndicator = styled.div`
  display: flex;
  justify-content: center;
  align-items: center;
  color: rgba(255, 255, 255, 0.8);
  font-size: 18px;
  font-weight: 500;
  gap: 12px;
  flex-direction: column;
  
  &::after {
    content: '';
    width: 20px;
    height: 20px;
    border: 2px solid rgba(255, 255, 255, 0.3);
    border-top: 2px solid rgba(255, 255, 255, 0.8);
    border-radius: 50%;
    animation: spin 1s linear infinite;
  }
  
  /* 当有错误状态时不显示旋转动画 */
  &.error {
    &::after {
      display: none;
    }
  }
  
  @keyframes spin {
    0% { transform: rotate(0deg); }
    100% { transform: rotate(360deg); }
  }
`;

const Meeting: React.FC<Record<string, unknown>> = () => {
  const { roomId, userId, setJoin, setJoinFailReason } = useContext(Context);
  const [isMicOn, setMicOn] = useState<boolean>(false); // 默认关闭麦克风
  const [isVideoOn, setVideoOn] = useState<boolean>(false); // 默认关闭摄像头
  const rtc = useRef<RTCClient>();
  const [autoPlayFailUser, setAutoPlayFailUser] = useState<string[]>([]);
  const playStatus = useRef<{ [key: string]: { audio: boolean; video: boolean } }>({});
  const autoPlayFailUserdRef = useRef<string[]>([]);
  
  // 聊天相关状态
  const [chatMessages, setChatMessages] = useState<Array<{id: string, text: string, timestamp: Date, sender: 'user' | 'ai'}>>([]);
  const [inputMessage, setInputMessage] = useState<string>('');
  const [isLoading, setIsLoading] = useState<boolean>(false);
  
  // 语音录音相关状态
  const [isRecording, setIsRecording] = useState<boolean>(false);
  
  // 前端录音模式相关状态
  const [recordingStatus, setRecordingStatus] = useState<string>('未连接');
  const [sttResults, setSttResults] = useState<string[]>([]);
  
  // STT相关状态
  const [sttEnabled, setSttEnabled] = useState<boolean>(false);
  const [digitalHumanJoined, setDigitalHumanJoined] = useState<boolean>(false);
  const [digitalHumanJoining, setDigitalHumanJoining] = useState<boolean>(false);
  const [digitalHumanJoinError, setDigitalHumanJoinError] = useState<string>('');
  const [currentLiveId, setCurrentLiveId] = useState<string>('');

  // 使用useMemo确保前端录音的sessionId在组件生命周期内保持稳定
  const frontendSessionId = useMemo(() => 
    `session_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`, 
    []
  );

  const [remoteStreams, setRemoteStreams] = useState<{
    [key: string]: {
      playerComp: React.ReactNode;
    };
  }>({});

  const leaveRoom = useCallback(
    (refresh: boolean) => {
      if (!rtc.current) return;

      // 立即清空所有状态，避免状态残留
      setDigitalHumanJoined(false);
      setDigitalHumanJoining(false);
      setDigitalHumanJoinError('');
      setCurrentLiveId('');
      setChatMessages([]);
      setInputMessage('');
      setIsLoading(false);
      setAutoPlayFailUser([]);
      setJoinFailReason('');
      
      // 重置错误计数
      resetGlobalErrorCount();

      // off the event
      rtc.current.removeEventListener();

      rtc.current.leave();
      if (!refresh) {
        setJoin(false);
        removeLoginInfo();
      }
    },
    [rtc, setJoin]
  );

  /**
   * @brief call leaveRoom function when the browser window closes or refreshes
   */
  const leaveFunc = () => {
    leaveRoom(true);
    sessionStorage.setItem('store', JSON.stringify({ test: new Date().toString() }));
  };
  useEffect(() => {
    window.addEventListener('pagehide', leaveFunc);
    return () => {
      leaveRoom(true);
      window.removeEventListener('pagehide', leaveFunc);
    };
  }, [leaveRoom]);

  const handleUserPublishStream = useCallback(
    async (stream: { userId: string; mediaType: MediaType }) => {
      const userId = stream.userId;
      if (stream.mediaType & MediaType.VIDEO) {
        if (remoteStreams[userId]) {
          const result = await rtc.current?.setRemoteVideoPlayer(userId, `remoteStream_${userId}`) as { success: boolean; error?: string } | undefined;
          if (result && !result.success) {
            console.warn('数字人视频流设置失败:', result.error);
            setDigitalHumanJoinError('数字人加入失败，请重试');
            setDigitalHumanJoining(false);
          }
        }
      }
    },
    [remoteStreams]
  );

  /**
   * @brief remove stream & update remote streams list
   * @param {Event} event
   */
  const handleUserUnpublishStream = (event: { userId: string; mediaType: MediaType }) => {
    const { userId, mediaType } = event;

    if (mediaType & MediaType.VIDEO) {
      rtc.current?.setRemoteVideoPlayer(userId, undefined);
    }
  };

  const handleUserStartVideoCapture = async (event: { userId: string }) => {
    const { userId } = event;

    if (remoteStreams[userId]) {
      const result = await rtc.current?.setRemoteVideoPlayer(userId, `remoteStream_${userId}`) as { success: boolean; error?: string } | undefined;
      if (result && !result.success) {
        console.warn('数字人视频流设置失败:', result.error);
        setDigitalHumanJoinError('数字人加入失败，请重试');
        setDigitalHumanJoining(false);
      }
    }
  };

  /**
   * Remove the user specified from the room in the local and clear the unused dom
   * @param {*} event
   */
  const handleUserStopVideoCapture = (event: { userId: string }) => {
    const { userId } = event;

    rtc.current?.setRemoteVideoPlayer(userId, undefined);
  };

  const handleUserJoin = (e: onUserJoinedEvent) => {
    console.log('handleUserJoin', e);

    const { userInfo } = e;
    const remoteUserId = userInfo.userId;

    if (Object.keys(remoteStreams).length < 3) {
      if (remoteStreams[remoteUserId]) return;
      remoteStreams[remoteUserId] = {
        playerComp: <MediaPlayer userId={remoteUserId} />,
      };

      setRemoteStreams({
        ...remoteStreams,
      });
    }
  };

  useEffect(() => {
    const streams = Object.keys(remoteStreams);
    const _autoPlayFailUser = autoPlayFailUser.filter(
      (item) => streams.findIndex((stream) => stream === item) !== -1
    );
    setAutoPlayFailUser([..._autoPlayFailUser]);
  }, [remoteStreams]);

  const handleUserLeave = (e: onUserLeaveEvent) => {
    const { userInfo } = e;
    const remoteUserId = userInfo.userId;
    if (remoteStreams[remoteUserId]) {
      delete remoteStreams[remoteUserId];
    }
    setRemoteStreams({
      ...remoteStreams,
    });
  };

  useEffect(() => {
    (async () => {
      if (!roomId || !userId || !rtc.current) return;
      // rtc.current.bindEngineEvents();

      let token = null;
      config.tokens.forEach((item) => {
        if (item.userId === userId) {
          token = item.token;
        }
      });

      rtc.current
        .join((token as any) || null, roomId, userId)
        .then(() => {
          // 不创建本地视频和音频流，只接收远程流
          console.log('用户成功加入房间，等待数字人加入');
        })
        .catch((err: any) => {
          console.warn('加入房间失败:', err);
          resetGlobalErrorCount();
          // 静默处理错误，不显示给用户
          leaveRoom(false);
          setJoinFailReason('连接失败，请稍后重试');
        });
    })();
  }, [roomId, userId, rtc]);

  const changeMicState = useCallback((): void => {
    if (!rtc.current) return;
    rtc.current.changeAudioState(!isMicOn);
    setMicOn(!isMicOn);
  }, [isMicOn, rtc]);

  const changeVideoState = useCallback((): void => {
    if (!rtc.current) return;
    rtc.current.changeVideoState(!isVideoOn);
    setVideoOn(!isVideoOn);
  }, [isVideoOn, rtc]);

  const handleEventError = (e: any, VERTC: any) => {
    // 重置错误计数
    resetGlobalErrorCount();
    
    if (e.errorCode === VERTC.ErrorCode.DUPLICATE_LOGIN) {
      message.error('你的账号被其他人顶下线了');
      leaveRoom(false);
    } else {
      // 静默处理其他错误，不显示给用户
      console.warn('RTC连接错误:', e);
    }
  };

  const handleAutoPlayFail = (event: AutoPlayFailedEvent) => {
    console.log('handleAutoPlayFail', event.userId, event);
    const { userId, kind } = event;

    let playUser = playStatus.current?.[userId] || {};
    playUser = { ...playUser, [kind]: false };
    playStatus.current[userId] = playUser;

    addFailUser(userId);
  };

  const addFailUser = (userId: string) => {
    const index = autoPlayFailUser.findIndex((item) => item === userId);
    if (index === -1) {
      autoPlayFailUser.push(userId);
    }
    setAutoPlayFailUser([...autoPlayFailUser]);
  };

  const playerFail = (params: { type: 'audio' | 'video'; userId: string }) => {
    const { type, userId } = params;
    let playUser = playStatus.current?.[userId] || {};

    playUser = { ...playUser, [type]: false };

    const { audio, video } = playUser;

    if (audio === false || video === false) {
      addFailUser(userId);
    }
  };

  const handlePlayerEvent = (event: PlayerEvent) => {
    const { userId, rawEvent, type } = event;

    console.log('handlePlayerEvent', event, userId, type, rawEvent.type);

    let playUser = playStatus.current?.[userId] || {};

    if (!playStatus.current) return;

    if (rawEvent.type === 'playing') {
      playUser = { ...playUser, [type]: true };
      const { audio, video } = playUser;
      if (audio !== false && video !== false) {
        const _autoPlayFailUser = autoPlayFailUserdRef.current.filter((item) => item !== userId);
        setAutoPlayFailUser([..._autoPlayFailUser]);
      }
    } else if (rawEvent.type === 'pause') {
      playerFail({ userId, type });
    }

    playStatus.current[userId] = playUser;
    console.log('playStatusplayStatusplayStatus', playStatus);
  };

  const handleAutoPlay = () => {
    const users: string[] = autoPlayFailUser;
    console.log('handleAutoPlay autoPlayFailUser', autoPlayFailUser);
    if (users && users.length) {
      users.forEach((user) => {
        rtc.current?.engine.play(user);
      });
    }
    setAutoPlayFailUser([]);
  };

  useEffect(() => {
    autoPlayFailUserdRef.current = autoPlayFailUser;
  }, [autoPlayFailUser]);

    // 数字人加入房间
  const joinDigitalHuman = useCallback(async () => {
    if (digitalHumanJoining || digitalHumanJoined) return;

    // 开始前先清理状态，避免状态残留
    setDigitalHumanJoinError('');
    setDigitalHumanJoining(true);

    try {
      // 进入房间前主动清理后端状态
      const liveId = `live_${roomId}_${Date.now()}`;
      try {
        await fetch(`${config.apiBaseUrl}/api/digital_human_develop/leave_room/${liveId}`, { method: 'DELETE' });
      } catch (error) {
        // 静默处理清理错误
        console.warn('清理后端状态失败:', error);
      }

      const response = await fetch(`${config.apiBaseUrl}/api/digital_human_develop/join_room`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          live_id: liveId,
          avatar_type: '3min',
          role: '250623-zhibo-linyunzhi',
          rtc_room_id: roomId,
          rtc_uid: 'digital_human_develop'
        })
      });
      
      if (response.ok) {
        const result = await response.json();
        console.log('数字人加入房间API响应成功:', result);
        setDigitalHumanJoined(true);
        setDigitalHumanJoinError('');
        setCurrentLiveId(liveId);
        message.success('Digital Human joined successfully');
        console.log('数字人成功加入房间，状态已更新');
      } else {
        const errorData = await response.json().catch(() => ({ message: 'Unknown error' }));
        const errorMsg = errorData.message || `Request failed (${response.status})`;
        setDigitalHumanJoinError(errorMsg);
        // 移除错误提示，静默处理
        console.warn('数字人加入房间失败:', response.status, errorData);
      }
    } catch (error) {
      console.warn('数字人加入房间失败:', error);
      resetGlobalErrorCount();
      // 移除错误提示，静默处理
      const errorMsg = '数字人连接失败，请重试';
      setDigitalHumanJoinError(errorMsg);
    } finally {
      setDigitalHumanJoining(false);
    }
  }, [roomId, digitalHumanJoining, digitalHumanJoined, setDigitalHumanJoinError, setDigitalHumanJoining, setDigitalHumanJoined, setCurrentLiveId, resetGlobalErrorCount]);

  // 处理挂断逻辑
  const handleHangUp = async () => {
    try {
      // 立即清空所有前端状态，避免状态残留
      setDigitalHumanJoined(false);
      setDigitalHumanJoining(false);
      setDigitalHumanJoinError('');
      setCurrentLiveId('');
      setChatMessages([]);
      setInputMessage('');
      setIsLoading(false);
      
      // 重置错误计数
      resetGlobalErrorCount();
      
      // 如果数字人已加入，先让数字人离开房间
      if (currentLiveId) {
        console.log('正在让数字人离开房间:', currentLiveId);
        try {
          const response = await fetch(`${config.apiBaseUrl}/api/digital_human_develop/leave_room/${currentLiveId}`, {
            method: 'DELETE',
          });
          
          if (response.ok) {
            console.log('数字人成功离开房间');
          } else {
            console.warn('数字人离开房间失败:', response.status);
          }
        } catch (error) {
          console.warn('调用数字人离开房间API失败:', error);
          // 静默处理错误，不显示给用户
        }
      }
    } catch (error) {
      console.warn('挂断处理异常:', error);
      // 静默处理错误，不显示给用户
    } finally {
      // 无论数字人离开是否成功，都执行用户离开房间
      leaveRoom(false);
    }
  };

  // 处理STT识别结果
  const handleSTTResult = (text: string) => {
    if (text.trim()) {
      setInputMessage(text);
      // 自动发送识别到的文本
      sendMessageInternal(text);
    }
  };

  // 前端录音相关处理函数
  const handleFrontendSTTResult = (text: string, isFinal: boolean, confidence: number) => {
    console.log('🎯 父组件收到前端STT结果:', text, '最终结果:', isFinal, '置信度:', confidence);
    
    if (isFinal) {
      console.log('🎯 处理最终STT结果，设置输入消息:', text);
      setInputMessage(text);
      setSttResults(prev => [...prev, text]);
      // 自动发送识别到的文本
      if (text.trim()) {
        console.log('🎯 自动发送识别到的文本到数字人:', text);
        sendMessageInternal(text);
      } else {
        console.log('🎯 STT结果为空，跳过发送');
      }
    } else {
      // 中间结果，可以显示在界面上
      console.log('🎯 处理中间STT结果，更新输入消息:', text);
      setInputMessage(text);
    }
  };

  const handleRecordingError = (error: string) => {
    console.error('❌ 父组件收到录音错误:', error);
    message.error('录音错误: ' + error);
  };

  const handleRecordingStatusChange = (status: string) => {
    console.log('📊 父组件收到录音状态变化:', status);
    setRecordingStatus(status);
  };

  // 内部发送消息函数
  const sendMessageInternal = async (messageText?: string) => {
    const textToSend = messageText || inputMessage;
    if (!textToSend.trim() || isLoading) return;
    
    const userMessage = {
      id: Date.now().toString(),
      text: textToSend,
      timestamp: new Date(),
      sender: 'user' as const
    };
    
    setChatMessages(prev => {
      console.log('添加用户消息:', userMessage);
      const newMessages = [...prev, userMessage];
      console.log('当前聊天消息数量:', newMessages.length);
      return newMessages;
    });
    setInputMessage('');
    setIsLoading(true);
    
    try {
      console.log('发送消息:', textToSend, '用户ID:', userId, '房间ID:', roomId);
      const response = await fetch(`${config.apiBaseUrl}/api/query/stream`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          query: textToSend,
          user_id: userId,
          live_id: `live_${roomId}_${Date.now()}`
        })
      });
      console.log('响应状态:', response.status, response.ok);
      
      if (response.ok) {
        const reader = response.body?.getReader();
        let aiMessageId = (Date.now() + 1).toString();
        
        // 先创建一个空的AI消息
        const initialAiMessage = {
          id: aiMessageId,
          text: '',
          timestamp: new Date(),
          sender: 'ai' as const
        };
        console.log('创建初始AI消息:', initialAiMessage);
        setChatMessages(prev => {
          const newMessages = [...prev, initialAiMessage];
          console.log('添加AI消息后总数量:', newMessages.length);
          return newMessages;
        });
        
        if (reader) {
          while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            
            const chunk = new TextDecoder().decode(value);
            const lines = chunk.split('\n');
            
            for (const line of lines) {
              if (line.startsWith('data: ')) {
                try {
                  const data = JSON.parse(line.slice(6));
                  console.log('收到streaming数据:', data);
                  
                  // 处理不同类型的streaming数据
                  if (data.type === 'text_chunk' && data.accumulated_text) {
                    // 使用accumulated_text来显示完整的累积文本
                    const newText = data.accumulated_text;
                    setChatMessages(prev => 
                      prev.map(msg => 
                        msg.id === aiMessageId 
                          ? { ...msg, text: newText }
                          : msg
                      )
                    );
                  } else if (data.type === 'complete' && data.full_text) {
                    // 当收到完整响应时，确保显示完整文本
                    const newText = data.full_text;
                    setChatMessages(prev => 
                      prev.map(msg => 
                        msg.id === aiMessageId 
                          ? { ...msg, text: newText }
                          : msg
                      )
                    );
                  } else if (data.type === 'token' && data.token) {
                    // 兼容原有的token格式
                    setChatMessages(prev => {
                      const currentMsg = prev.find(msg => msg.id === aiMessageId);
                      const currentText = currentMsg ? currentMsg.text : '';
                      const newText = currentText + data.token;
                      return prev.map(msg => 
                        msg.id === aiMessageId 
                          ? { ...msg, text: newText }
                          : msg
                      );
                    });
                  }
                } catch (e) {
                  console.error('解析streaming数据失败:', e, '原始数据:', line);
                }
              }
            }
          }
        }
      }
    } catch (error) {
      console.error('发送消息失败:', error);
    } finally {
      setIsLoading(false);
    }
  };

  // 发送消息（事件处理器）
  const sendMessage = () => {
    sendMessageInternal();
  };

  // 开始录音
  const startRecording = async () => {
    try {
      // 使用单按钮控制API开始录音
      const sessionId = `session_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
      
      const response = await fetch(`${config.apiBaseUrl}/api/voice/single_button_control`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          session_id: sessionId,
          user_id: userId,
          action: 'toggle'
        })
      });

      const result = await response.json();
      
      if (result.success) {
        setIsRecording(true);
        // 存储sessionId用于停止录音
        sessionStorage.setItem('recordingSessionId', sessionId);
        message.success('开始录音');
      } else {
        message.error(result.message || '录音启动失败');
      }

    } catch (error) {
      console.error('录音失败:', error);
      message.error('录音启动失败');
    }
  };

  // 停止录音
  const stopRecording = async () => {
    try {
      const sessionId = sessionStorage.getItem('recordingSessionId');
      if (!sessionId) {
        message.error('未找到录音会话');
        setIsRecording(false);
        return;
      }

      // 使用录制完成处理API
      const response = await fetch(`${config.apiBaseUrl}/api/voice/record_and_process`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          session_id: sessionId,
          user_id: userId
        })
      });

      // 处理JSON响应
      const result = await response.json();
      if (result.success) {
        message.success('录音处理完成');
        // 录制完成后一次性显示识别结果
        if (result.recognized_text) {
          setInputMessage(result.recognized_text);
          // 自动发送识别到的文本
          sendMessageInternal(result.recognized_text);
        }
      } else {
        if (result.status === 'too_short') {
          message.warning('录音时间太短，请说话时间更长一些');
        } else {
          message.error(result.message || '录音处理失败');
        }
      }

      setIsRecording(false);
      sessionStorage.removeItem('recordingSessionId');

    } catch (error) {
      console.error('停止录音失败:', error);
      message.error('停止录音失败');
      setIsRecording(false);
    }
  };



  // 用户加入房间后自动让数字人加入
  useEffect(() => {
    console.log('检查数字人加入条件:', { roomId, userId, digitalHumanJoined });
    if (roomId && userId && !digitalHumanJoined) {
      console.log('开始自动加入数字人...');
      joinDigitalHuman();
    }
  }, [roomId, userId, digitalHumanJoined, joinDigitalHuman]);



  return (
    <>
      <RTCComponent
        onRef={(ref: any) => (rtc.current = ref)}
        config={{
          ...config,
          roomId,
          uid: '',
        }}
        streamOptions={streamOptions}
        handleUserPublishStream={handleUserPublishStream}
        handleUserUnpublishStream={handleUserUnpublishStream}
        handleUserStartVideoCapture={handleUserStartVideoCapture}
        handleUserStopVideoCapture={handleUserStopVideoCapture}
        handleUserJoin={handleUserJoin}
        handleUserLeave={handleUserLeave}
        handleEventError={handleEventError}
        handleAutoPlayFail={handleAutoPlayFail}
        handlePlayerEvent={handlePlayerEvent}
      />
      <Container>
        <VideoContainer>
          {/* 只显示数字人的视频流 */}
          {Object.keys(remoteStreams).length > 0 ? (
            Object.keys(remoteStreams).map((key) => {
              const Comp = remoteStreams[key].playerComp;
              return (
                <div key={key} style={{ width: '100%', height: '100%' }}>
                  {Comp}
                </div>
              );
            })
          ) : (
            <WaitingIndicator className={digitalHumanJoinError ? 'error' : ''}>
              {digitalHumanJoining ? (
                <>Digital Human is joining...</>
              ) : digitalHumanJoinError ? (
                <div style={{ textAlign: 'center' }}>
                  <div style={{ marginBottom: '12px', color: '#ef4444' }}>
                    Digital Human join failed: {digitalHumanJoinError}
                  </div>
                  <Button 
                    type="primary" 
                    onClick={joinDigitalHuman}
                    style={{ 
                      borderRadius: '8px',
                      background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
                      border: 'none'
                    }}
                  >
                    Retry
                  </Button>
                </div>
              ) : (
                <>Waiting for Digital Human to join...</>
              )}
            </WaitingIndicator>
          )}
        </VideoContainer>
        
        <ChatContainer>
          <ChatHeader>
            <ChatTitle>AI Conversation</ChatTitle>
          </ChatHeader>
          
          <ChatMessages>
            {chatMessages.length === 0 ? (
              <div style={{ textAlign: 'center', color: '#888', padding: '20px' }}>
                No messages yet. Start a conversation!
              </div>
            ) : (
              chatMessages.map((item) => (
                <div key={item.id} style={{
                  display: 'flex',
                  justifyContent: item.sender === 'user' ? 'flex-end' : 'flex-start',
                  marginBottom: '4px'
                }}>
                  <MessageBubble sender={item.sender}>
                    {item.text || 'Loading...'}
                  </MessageBubble>
                </div>
              ))
            )}
          </ChatMessages>
          
          <ChatInput>
            <Input
              value={inputMessage}
              onChange={(e) => setInputMessage(e.target.value)}
              onPressEnter={sendMessage}
              placeholder="Type your message..."
              disabled={isLoading}
              size="large"
              style={{
                borderRadius: '25px',
                border: '2px solid #e2e8f0',
                boxShadow: 'none',
                fontSize: '16px'
              }}
            />
            <Button 
              type="primary" 
              onClick={sendMessage}
              loading={isLoading}
              disabled={!inputMessage.trim()}
              size="large"
              style={{
                borderRadius: '25px',
                background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
                border: 'none',
                boxShadow: '0 4px 12px rgba(102, 126, 234, 0.3)',
                fontWeight: '600',
                minWidth: '80px'
              }}
            >
              Send
            </Button>
            
            {/* 录音控制区域 */}
            <div style={{ 
              display: 'flex', 
              alignItems: 'center', 
              gap: '12px',
              marginTop: '12px',
              padding: '12px',
              background: 'rgba(255,255,255,0.9)',
              borderRadius: '16px',
              border: '1px solid #e2e8f0',
              boxShadow: '0 2px 8px rgba(0,0,0,0.1)'
            }}>
                             <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '4px' }}>
                 {(() => {
                   console.log('🎨 渲染AudioRecorder组件', {
                     frontendSessionId,
                     recordingStatus,
                     timestamp: new Date().toISOString()
                   });
                   return (
                     <AudioRecorder
                       onSTTResult={handleFrontendSTTResult}
                       onError={handleRecordingError}
                       onStatusChange={handleRecordingStatusChange}
                       websocketUrl="ws://localhost:9002/audio"
                       sessionId={frontendSessionId}
                     />
                   );
                 })()}
               </div>
              
              {/* 后端录音按钮已隐藏 */}
              {/* 
              <div style={{ 
                width: '1px', 
                height: '40px', 
                background: '#e2e8f0',
                margin: '0 8px'
              }} />
              
              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '4px' }}>
                <span style={{ fontSize: '12px', color: '#666', fontWeight: '500' }}>后端录音</span>
                <Button 
                  type={isRecording ? "primary" : "default"}
                  icon={isRecording ? <StopOutlined /> : <AudioOutlined />}
                  onClick={isRecording ? stopRecording : startRecording}
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
                <span style={{ fontSize: '10px', color: '#999' }}>
                  {isRecording ? '录音中...' : '就绪'}
                </span>
              </div>
              
              <div style={{ 
                width: '1px', 
                height: '40px', 
                background: '#e2e8f0',
                margin: '0 8px'
              }} />
              */}
              
              <Button 
                type="default" 
                onClick={handleHangUp}
                size="large"
                style={{
                  borderRadius: '25px',
                  border: '2px solid #ef4444',
                  color: '#ef4444',
                  fontWeight: '600',
                  minWidth: '80px'
                }}
              >
                Hang Up
              </Button>
            </div>
          </ChatInput>
          
          {/* STT语音识别组件已移除 - 使用简化的语音输入 */}
        </ChatContainer>
      </Container>
      

      <AutoPlayModal handleAutoPlay={handleAutoPlay} autoPlayFailUser={autoPlayFailUser} />
    </>
  );
};

export default Meeting;
