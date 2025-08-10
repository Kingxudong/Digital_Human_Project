/**
 * Copyright 2024 Beijing Volcano Engine Technology Co., Ltd. All Rights Reserved.
 * SPDX-license-identifier: BSD-3-Clause
 */

import React, { FC, useContext } from 'react';
import styled from 'styled-components';
import { StoreValue } from 'rc-field-form/lib/interface';

import { Input, Button, Form, Modal, message } from 'antd';
import { Context } from '../../context';
import { setSessionInfo } from '../../utils/index';

type IForm = { roomId: string; userId: string };

const ModalWrapper = styled(Modal)`
  .ant-modal-header {
    border-bottom: none;
    padding: 24px 32px 0px;
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    border-radius: 20px 20px 0 0;
  }
  .ant-modal-body {
    padding: 24px 32px 32px;
    background: rgba(255, 255, 255, 0.98);
    backdrop-filter: blur(20px);
  }
  .ant-modal-content {
    height: auto;
    min-height: 420px;
    border-radius: 20px;
    border: none;
    box-shadow: 0 25px 50px rgba(0,0,0,0.15);
    overflow: hidden;
  }
  .ant-modal-title {
    font-family: 'SF Pro Display', -apple-system, BlinkMacSystemFont, sans-serif;
    font-size: 28px;
    font-style: normal;
    font-weight: 700;
    line-height: 1.2;
    text-align: center;
    color: white;
    margin: 0;
    text-shadow: 0 2px 4px rgba(0,0,0,0.3);
    letter-spacing: 1px;
  }
  .ant-modal-header {
    border-radius: 20px 20px 0 0;
  }
  .ant-modal-mask {
    backdrop-filter: blur(8px);
    background: rgba(0,0,0,0.6);
  }
`;

const FormContainer = styled.div`
  padding: 20px 0;
`;

const StyledInput = styled(Input)`
  height: 50px;
  border-radius: 25px;
  border: 2px solid #e2e8f0;
  font-size: 16px;
  padding: 0 20px;
  transition: all 0.3s ease;
  
  &:focus {
    border-color: #667eea;
    box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
  }
  
  &:hover {
    border-color: #667eea;
  }
`;

const StyledButton = styled(Button)`
  height: 50px;
  border-radius: 25px;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  border: none;
  font-size: 16px;
  font-weight: 600;
  box-shadow: 0 4px 15px rgba(102, 126, 234, 0.4);
  transition: all 0.3s ease;
  
  &:hover {
    transform: translateY(-2px);
    box-shadow: 0 6px 20px rgba(102, 126, 234, 0.5);
  }
  
  &:active {
    transform: translateY(0);
  }
`;

const ErrorMessage = styled.div`
  color: #ef4444;
  font-size: 14px;
  margin-top: 8px;
  padding: 8px 12px;
  background: rgba(239, 68, 68, 0.1);
  border-radius: 8px;
  border-left: 3px solid #ef4444;
`;

enum ERROR_TYPES {
  VALID,
  EMPTY_STRING,
  INVALID_CHARACTERS,
}

const messages = {
  userIdErrType: {
    1: 'Please enter User ID',
    2: 'Invalid User ID format, please re-enter',
  },
  roomIdErrType: {
    1: 'Please enter Room ID',
    2: 'Invalid Room ID format, please re-enter',
  },
};

const getLoginFieldRules = (
  value: StoreValue,
  name: 'userId' | 'roomId',
  regRes: boolean
): Promise<void | any> | void => {
  const errorTypeKey = name === 'userId' ? 'userIdErrType' : 'roomIdErrType';

  let result: Promise<Error | void>;

  if (!value || regRes) {
    const _value = !value ? ERROR_TYPES.EMPTY_STRING : ERROR_TYPES.INVALID_CHARACTERS;
    result = Promise.reject(new Error(messages[errorTypeKey][_value]));
  } else {
    result = Promise.resolve();
  }

  return result;
};

const JoinRoom: FC<{ joinRoom: () => void }> = ({ joinRoom }) => {
  const [form] = Form.useForm<IForm>();


    const { setRoomId, setUserId, userId, roomId, joinFailReason} = useContext(Context);

  const onFinish = (value: IForm) => {
    const { roomId, userId } = value;
    setUserId(userId);
    setRoomId(roomId);
    // 将图片URL保存到sessionStorage中，供后续使用

    joinRoom();
    setSessionInfo({ roomId, uid: userId });
    window.history.replaceState('', '', `/?userId=${userId}&roomId=${roomId}`);
  };

  // 图片上传处理


  return (
    <>
      <ModalWrapper width={450} title="Welcome to Hi Agent" open={true} closable={false} footer={null} centered>
        <FormContainer>
          <Form form={form} onFinish={onFinish} initialValues={{ userId, roomId }}>
            <Form.Item
              name="roomId"
              rules={[
                {
                  required: true,
                  validator: (_, value) => {
                    const regRes = !/^[0-9a-zA-Z_\-@.]{1,128}$/.test(value);
                    return getLoginFieldRules(value, 'roomId', regRes);
                  },
                },
              ]}
              style={{ marginBottom: '20px' }}
            >
              <StyledInput placeholder="Enter Room ID" />
            </Form.Item>
            <Form.Item
              name="userId"
              rules={[
                {
                  required: true,
                  validator: (_, value) => {
                    const regRes = !/^[0-9a-zA-Z_\-@.]{1,128}$/.test(value);
                    return getLoginFieldRules(value, 'userId', regRes);
                  },
                },
              ]}
              style={{ marginBottom: '20px' }}
            >
              <StyledInput placeholder="Enter User ID" />
            </Form.Item>
            

            {joinFailReason && (
              <ErrorMessage>
                {joinFailReason}
              </ErrorMessage>
            )}
            <Form.Item style={{ marginTop: '30px', marginBottom: 0 }}>
              <StyledButton
                type="primary"
                htmlType="submit"
                block
              >
Start Digital Human Experience
              </StyledButton>
            </Form.Item>
          </Form>
        </FormContainer>
      </ModalWrapper>
    </>
  );
};

export default JoinRoom;
