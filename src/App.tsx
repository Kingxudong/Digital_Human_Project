/**
 * Copyright 2024 Beijing Volcano Engine Technology Co., Ltd. All Rights Reserved.
 * SPDX-license-identifier: BSD-3-Clause
 */

import React, { useMemo, useState } from 'react';
import 'antd/dist/antd.min.css';
import styled from 'styled-components';
import VERTC from '@volcengine/rtc';

import JoinRoom from './pages/JoinRoom';
import Meeting from './pages/Meeting';
import { Context } from './context';
import config from './config';
import { getQueryString, checkLoginInfo } from './utils';
import ErrorBoundary from './components/ErrorBoundary';

const HeaderWrapper = styled.div`
  width: 100%;
  height: 80px;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  display: flex;
  justify-content: space-between;
  align-items: center;
  position: relative;
  overflow: hidden;
  padding: 0 20px;
  
  &::before {
    content: '';
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: url('data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><defs><pattern id="grain" width="100" height="100" patternUnits="userSpaceOnUse"><circle cx="20" cy="20" r="1" fill="%23ffffff" opacity="0.1"/><circle cx="80" cy="40" r="1" fill="%23ffffff" opacity="0.1"/><circle cx="40" cy="80" r="1" fill="%23ffffff" opacity="0.1"/></pattern></defs><rect width="100" height="100" fill="url(%23grain)"/></svg>') repeat;
    animation: float 20s ease-in-out infinite;
  }
  
  @keyframes float {
    0%, 100% { transform: translateY(0px); }
    50% { transform: translateY(-10px); }
  }
`;

const ContentWrapper = styled.div`
  height: calc(100vh - 80px);
  background: linear-gradient(to bottom, #f8fafc, #e2e8f0);
`;

const LeftTitle = styled.div`
  position: relative;
  z-index: 2;
  flex: 0 0 auto;
`;

const CenterTitle = styled.div`
  position: relative;
  z-index: 2;
  flex: 1;
  text-align: center;
`;

const MainTitle = styled.h1`
  font-size: 2.2rem;
  font-weight: 800;
  background: linear-gradient(45deg, #ffffff, #e2e8f0, #ffffff);
  background-size: 200% 200%;
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
  margin: 0;
  text-shadow: 0 4px 8px rgba(0,0,0,0.3);
  animation: shimmer 3s ease-in-out infinite;
  letter-spacing: 2px;
  
  @keyframes shimmer {
    0%, 100% { background-position: 0% 50%; }
    50% { background-position: 100% 50%; }
  }
  
  @media (max-width: 768px) {
    font-size: 1.8rem;
  }
`;

const SubTitle = styled.p`
  font-size: 1.1rem;
  background: linear-gradient(45deg, #ffffff, #f0f8ff, #e6f3ff, #ffffff);
  background-size: 300% 300%;
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
  margin: 0;
  font-weight: 500;
  letter-spacing: 1.5px;
  text-shadow: 0 2px 8px rgba(0,0,0,0.4);
  animation: subtitleGlow 4s ease-in-out infinite;
  font-family: 'SF Pro Display', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  
  @keyframes subtitleGlow {
    0%, 100% { 
      background-position: 0% 50%;
      filter: drop-shadow(0 0 8px rgba(255,255,255,0.3));
    }
    50% { 
      background-position: 100% 50%;
      filter: drop-shadow(0 0 12px rgba(255,255,255,0.5));
    }
  }
  
  @media (max-width: 768px) {
    font-size: 0.95rem;
    letter-spacing: 1px;
  }
`;

const RoomInfo = styled.div`
  position: absolute;
  top: 20px;
  right: 20px;
  background: rgba(255, 255, 255, 0.2);
  backdrop-filter: blur(10px);
  padding: 8px 16px;
  border-radius: 20px;
  color: white;
  font-size: 14px;
  font-weight: 500;
  border: 1px solid rgba(255, 255, 255, 0.3);
`;

/**
 * 模块描述
 * @module App index
 */
const App: React.FC<Record<string, unknown>> = () => {
  const hasLogin = useMemo(() => {
    return checkLoginInfo();
  }, []);

  const [hasJoin, setJoin] = useState(hasLogin);
  const [joinFailReason, setJoinFailReason] = useState<string>('');
  const [userId, setUserId] = useState<string>(getQueryString('userId') || '');
  const [roomId, setRoomId] = useState<string>(getQueryString('roomId') || config.roomId || '');

  return (
    <ErrorBoundary>
      <Context.Provider value={{ hasJoin, userId, roomId, joinFailReason, setUserId, setRoomId, setJoin, setJoinFailReason }}>
        <HeaderWrapper>
          <LeftTitle>
            <MainTitle>Hi Agent</MainTitle>
          </LeftTitle>
          <CenterTitle>
            <SubTitle>Digital Human Demo</SubTitle>
          </CenterTitle>
          {hasJoin && (
            <RoomInfo>Room: {roomId}</RoomInfo>
          )}
        </HeaderWrapper>
        <ContentWrapper>
          {hasJoin ? (
            <Meeting />
          ) : (
            <JoinRoom joinRoom={() => setJoin(true)} />
          )}
        </ContentWrapper>
      </Context.Provider>
    </ErrorBoundary>
  );
};

export default App;
